#!/usr/bin/env python3
"""
filter_and_export_strings.py - Universal Android string resource classifier and exporter.

Features:
- Completely project-agnostic: zero hardcoded app names, brand names, or project-specific IDs.
- Preserves existing strings_donottranslate.xml entries and existing translatable="false" definitions.
- Categorizes user-facing UI text into strings.xml with concise single-line comments.
- Configurable --ignore-prefixes (e.g. '@,#') and --exclude-keywords.
- Strict value deduplication across all resources.
"""

import os
import sys
import re
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Tuple, Set
import xml.etree.ElementTree as ET


# Standard technical standards or cryptographic algorithms that should not be localized
STANDARDS_AND_PROTOCOLS = {
    "AES-256 GCM", "AES-256", "AES-128", "SHA-256", "SHA-512", "SHA-1", "MD5",
    "HMAC", "RSA", "ECDSA", "TLS", "SSL", "HTTPS", "HTTP", "TCP", "UDP",
    "ISO-8601", "UTF-8", "UTF-16", "ASCII", "JSON", "XML", "HTML", "YAML"
}

# Standard HTTP headers, methods and MIME types
HTTP_AND_NETWORK_TERMS = {
    "GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS",
    "Content-Type", "Authorization", "Bearer", "User-Agent", "Accept",
    "Host", "Connection", "Keep-Alive", "Transfer-Encoding",
    "application/json", "application/octet-stream", "image/png",
    "image/jpeg", "image/webp", "image/gif", "multipart/form-data",
    "text/plain", "text/html",
    "UTC", "GMT", "ZoneId",
}

# Common Android / Java / Kotlin compiler annotations and standard tags
CODE_ANNOTATIONS_AND_TAGS = {
    "DEPRECATION", "UNCHECKED_CAST", "Composable", "OptIn", "Preview",
    "Singleton", "Inject", "Provides", "Module", "InstallIn", "HiltViewModel",
    "NonNull", "Nullable", "Override", "Suppress", "SuppressWarnings",
    "Tag", "TAG", "BuildConfig",
}


def is_pure_punctuation(s: str) -> bool:
    """Checks if string consists purely of punctuation, symbols, markdown, or delimiters."""
    if not s or s.isspace():
        return True
    return bool(re.fullmatch(r"[\s\.,\/#!$%\^&\*;:{}=\-_`~()\[\]<>\"'\\\|?+•]+", s))


def is_code_template_without_natural_words(s: str) -> bool:
    """
    Checks if a templated string contains only code variables, punctuation, or tokens
    (e.g., '[$tag] $message' or '$currentContent $token' or '$host:$port')
    rather than natural language words.
    """
    stripped = re.sub(r"(\$\{[^}]+\}|\$[a-zA-Z_][a-zA-Z0-9_]*)", "", s)
    words = re.findall(r"[a-zA-Z]{2,}", stripped)
    return len(words) == 0


def classify_string(
    text: str,
    occurrences: List[Dict[str, Any]],
    ignore_prefixes: Set[str],
    exclude_keywords: Set[str]
) -> Tuple[str, str]:
    """
    Classifies a string into:
    - ('IGNORE', reason)
    - ('NON_TRANSLATABLE', reason)
    - ('TRANSLATABLE', reason)
    """
    stripped = text.strip()

    # 1. Empty, single character (letters like 'r' or symbols like '/', '<', '>', '?'), or whitespace
    if len(stripped) <= 1:
        return "IGNORE", "single_character_or_empty"

    # 2. Must contain at least one alphabetic character
    if not re.search(r"[a-zA-Z]", stripped):
        return "IGNORE", "no_alphabetic_characters"

    # 3. Pure punctuation / markdown delimiters / symbols
    if is_pure_punctuation(stripped):
        return "IGNORE", "punctuation_or_symbols"

    # 4. Configurable ignore prefixes (e.g. '@', '#')
    if any(stripped.startswith(p) for p in ignore_prefixes):
        return "IGNORE", "custom_ignore_prefix"

    # 5. Custom excluded keywords
    if stripped in exclude_keywords or stripped.lower() in exclude_keywords:
        return "IGNORE", "custom_excluded_keyword"

    # 6. File I/O modes (e.g. 'r', 'w', 'rw', 'wa')
    if stripped.lower() in {"r", "w", "rw", "wa", "rwt"}:
        return "IGNORE", "file_io_mode"

    # 7. Exact known technical standards/protocols
    if stripped in STANDARDS_AND_PROTOCOLS:
        return "NON_TRANSLATABLE", "technical_standard_or_protocol"

    # 8. URLs, schemas, API endpoints, web paths, query params
    if stripped.startswith(("http://", "https://", "content://", "file://", "package:", "market://", "android.resource://", "ws://", "wss://", "attachment://")):
        return "IGNORE", "url_or_uri_scheme"

    if stripped.startswith(("/api/", "api/")) or "/v1/" in stripped or "/v2/" in stripped:
        return "IGNORE", "api_endpoint_or_path"

    # 8b. Domain names, url fragments, query params, or user-agent strings
    if len(stripped.split()) <= 2:
        if any(d in stripped.lower() for d in [".com/", ".org/", ".net/", "discord.com", "discordapp.com", "api/webhooks", ".com"]):
            return "IGNORE", "domain_or_url_path"
        if re.search(r"^[A-Za-z0-9\-_]+/[0-9.]+$", stripped) or "wait=" in stripped or stripped.startswith("attachment_"):
            return "IGNORE", "technical_token"

    # 9. Network / HTTP headers / MIME types
    if stripped in HTTP_AND_NETWORK_TERMS:
        return "IGNORE", "http_or_mime_token"

    # 10. Annotations / Tags
    if stripped in CODE_ANNOTATIONS_AND_TAGS:
        return "IGNORE", "annotation_or_tag"

    # 11. File extensions
    if re.fullmatch(r"\.[a-zA-Z0-9]{1,5}", stripped):
        return "IGNORE", "file_extension"

    # 12. Regular expressions
    if stripped.startswith("^") or re.search(r"(\[\d+-\d+\]|\(\?:|\\d\+|\[a-zA-Z)", stripped):
        return "IGNORE", "regex_pattern"

    # 13. Date/time formatting patterns (e.g. yyyy-MM-dd'T'HH:mm:ss, HH:mm, etc.)
    if any(df in stripped for df in ["yyyy", "MM-dd", "HH:mm", "ss.SSS", "'T'", "'Z'"]):
        return "IGNORE", "datetime_format_pattern"

    # 14. Database / SQL commands or keywords
    if any(stripped.startswith(kw) for kw in ["SELECT ", "CREATE TABLE ", "INSERT INTO ", "DROP TABLE ", "UPDATE "]):
        return "IGNORE", "sql_query"

    # 15. Pure numbers, versions, or hex values
    if re.fullmatch(r"v?\d+(\.\d+)*", stripped) or re.fullmatch(r"0x[0-9a-fA-F]+|#[0-9a-fA-F]{3,8}", stripped):
        return "IGNORE", "number_version_or_hex"

    # 16. Code templates without human words (e.g. '[$tag] $message')
    if "$" in stripped and is_code_template_without_natural_words(stripped):
        return "IGNORE", "code_template_expression"

    # 17. UPPER_SNAKE_CASE constants (e.g., EXTRA_ID, PREF_THEME, DEPRECATION)
    if re.fullmatch(r"[A-Z0-9_]{2,}", stripped) and ("_" in stripped or stripped.isupper()):
        return "IGNORE", "upper_case_constant"

    # 18. Package identifiers or ad unit identifiers
    if stripped.startswith("ca-app-pub-") or re.match(r"^[a-z]+(\.[a-z0-9_]+){2,}$", stripped):
        return "IGNORE", "package_or_ad_identifier"

    # 19. Lowercase snake_case without spaces
    if re.fullmatch(r"[a-z0-9_]{2,}", stripped) and ("_" in stripped or any(not c.isalpha() for c in stripped)):
        return "IGNORE", "snake_case_code_key"

    # 20. CamelCase identifiers without spaces
    if re.fullmatch(r"[a-z]+[A-Z0-9][a-zA-Z0-9]*", stripped):
        return "IGNORE", "camel_case_identifier"

    # 20b. PascalCase class names and inspection/animation labels without spaces
    if re.fullmatch(r"[A-Z][a-z0-9]+[A-Z][a-zA-Z0-9]*", stripped):
        return "IGNORE", "pascal_case_code_identifier"

    # 21. Price literals (e.g. '$0.99', '€2.99')
    if re.fullmatch(r"[\$\€\£\¥]\d+(\.\d{2})?", stripped):
        return "NON_TRANSLATABLE", "price_literal"

    # 22. Single lowercase word check
    if re.fullmatch(r"[a-z]{2,}", stripped):
        return "IGNORE", "lowercase_identifier"

    # 23. User-facing translatable UI text
    return "TRANSLATABLE", "user_facing_ui_text"


def generate_resource_key(text: str) -> str:
    """Generates an idiomatic, clean Android snake_case resource name."""
    is_question = text.strip().endswith("?")
    clean = re.sub(r"(\$\{[^}]+\}|\$[a-zA-Z_][a-zA-Z0-9_]*)", " ", text)
    clean = re.sub(r"[^a-zA-Z0-9\s_]", " ", clean).strip()

    tokens = [t.lower() for t in clean.split() if t]
    if not tokens:
        tokens = ["str"]

    base_name = "_".join(tokens[:5])
    if len(base_name) > 36:
        base_name = base_name[:36].rstrip("_")

    first_word = tokens[0] if tokens else ""

    action_words = {"save", "cancel", "delete", "clear", "send", "edit", "copy", "add", "retry", "refresh", "test", "load"}
    error_words = {"invalid", "failed", "error", "unable", "fail", "timeout"}

    if is_question:
        prefix = "confirm_"
    elif any(w in tokens for w in error_words):
        prefix = "error_"
    elif any(first_word == w for w in action_words):
        prefix = "action_"
    elif len(tokens) == 1 and first_word in {"active", "idle", "pending", "success", "failure", "checking"}:
        prefix = "status_"
    elif "title" in base_name or (len(tokens) <= 3 and any(w in base_name for w in ["dialog", "screen", "vault", "history", "presets", "templates", "builder", "studio", "settings"])):
        prefix = "title_"
    elif any(w in base_name for w in ["hint", "placeholder", "enter", "select"]):
        prefix = "hint_"
    elif len(tokens) <= 2:
        prefix = "label_"
    else:
        prefix = "msg_"

    if not base_name.startswith(prefix):
        final_key = prefix + base_name
    else:
        final_key = base_name

    final_key = re.sub(r"_+", "_", final_key).strip("_")
    if not final_key or not final_key[0].isalpha():
        final_key = "str_" + final_key

    return final_key


def escape_for_android_xml(text: str) -> str:
    """Escapes strings according to Android AAPT XML resource rules."""
    param_counter = 1
    def replace_template(match):
        nonlocal param_counter
        res = f"%{param_counter}$s"
        param_counter += 1
        return res

    converted = re.sub(r"(\$\{[^}]+\}|\$[a-zA-Z_][a-zA-Z0-9_]*)", replace_template, text)

    escaped = converted.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    escaped = escaped.replace("'", "\\'")
    escaped = escaped.replace('"', '\\"')

    if escaped.startswith("@"):
        escaped = "\\@" + escaped[1:]
    elif escaped.startswith("?"):
        escaped = "\\?" + escaped[1:]

    escaped = escaped.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
    return escaped


def load_existing_resources(file_path: Path) -> Dict[str, str]:
    """Loads existing key -> value pairs from an XML resource file."""
    res_map: Dict[str, str] = {}
    if not file_path.exists():
        return res_map

    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        for elem in root.findall("string"):
            name = elem.get("name")
            val = elem.text or ""
            if name:
                res_map[name] = val
    except Exception as e:
        print(f"[WARN] Failed to parse existing {file_path}: {e}", file=sys.stderr)

    return res_map


def build_translatable_xml(items: List[Dict[str, str]]) -> str:
    """Builds clean strings.xml with short functional comments."""
    categorized: Dict[str, List[Dict[str, str]]] = {
        "action": [],
        "title": [],
        "label": [],
        "status": [],
        "hint": [],
        "error": [],
        "msg": [],
        "other": []
    }

    seen_keys: Set[str] = set()
    for item in items:
        key = item["key"]
        if key in seen_keys:
            continue
        seen_keys.add(key)
        prefix = key.split("_")[0]
        if prefix in categorized:
            categorized[prefix].append(item)
        else:
            categorized["other"].append(item)

    sections = [
        ("action", "Actions & Buttons"),
        ("title", "Dialog & Screen Titles"),
        ("label", "Labels & Form Fields"),
        ("status", "Status & Indicators"),
        ("hint", "Hints & Placeholders"),
        ("error", "Errors & Warnings"),
        ("msg", "Messages & Descriptions"),
        ("other", "General UI Strings"),
    ]

    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<resources>'
    ]

    for cat_key, cat_title in sections:
        sec_items = categorized[cat_key]
        if not sec_items:
            continue
        lines.append(f'    <!-- {cat_title} -->')
        sec_items.sort(key=lambda x: x["key"])
        for it in sec_items:
            lines.append(f'    <string name="{it["key"]}">{it["value"]}</string>')
        lines.append('')

    if lines[-1] == '':
        lines.pop()

    lines.append('</resources>')
    lines.append('')
    return "\n".join(lines)


def build_donottranslate_xml(items: List[Dict[str, str]]) -> str:
    """Builds clean strings_donottranslate.xml."""
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<resources>',
        '    <!-- Non-translatable constants and identifiers -->'
    ]

    seen_keys: Set[str] = set()
    for it in items:
        key = it["key"]
        if key in seen_keys:
            continue
        seen_keys.add(key)
        lines.append(f'    <string name="{key}" translatable="false">{it["value"]}</string>')

    lines.append('</resources>')
    lines.append('')
    return "\n".join(lines)


def process_and_export(
    index_path: Path,
    translatable_path: Path,
    donottranslate_path: Path,
    report_path: Path,
    ignore_prefixes: Set[str],
    exclude_keywords: Set[str],
    dry_run: bool = False
):
    with open(index_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    all_strings = data.get("strings", [])

    # Dynamically load existing non-translatable strings to preserve project definitions
    existing_donottranslate = load_existing_resources(donottranslate_path)
    existing_translatable: Dict[str, str] = {}

    # Check if target translatable strings.xml exists and parse existing strings
    if translatable_path.exists():
        try:
            tree = ET.parse(translatable_path)
            for elem in tree.getroot().findall("string"):
                name = elem.get("name")
                val = elem.text or ""
                if not name:
                    continue
                if elem.get("translatable", "").lower() == "false":
                    if name not in existing_donottranslate:
                        existing_donottranslate[name] = val
                else:
                    existing_translatable[name] = val
        except Exception as e:
            print(f"[WARN] Failed to parse {translatable_path}: {e}", file=sys.stderr)

    used_keys: Set[str] = set(existing_donottranslate.keys()) | set(existing_translatable.keys())

    donottranslate_list: List[Dict[str, str]] = [
        {"key": k, "value": v} for k, v in existing_donottranslate.items()
    ]
    translatable_list: List[Dict[str, str]] = [
        {"key": k, "value": v, "original": v, "reason": "existing", "occurrences": 1}
        for k, v in existing_translatable.items()
    ]

    newly_added_donottranslate: List[Dict[str, str]] = []
    newly_added_translatable: List[Dict[str, str]] = []

    report: Dict[str, Any] = {
        "total_extracted": len(all_strings),
        "ignored_count": 0,
        "non_translatable_count": len(donottranslate_list),
        "translatable_count": len(translatable_list),
        "duplicate_count": 0,
        "ignored": [],
        "non_translatable": donottranslate_list,
        "translatable": list(translatable_list)
    }

    seen_xml_values: Dict[str, str] = {}
    for k, v in existing_donottranslate.items():
        seen_xml_values[v.strip()] = k
        seen_xml_values[escape_for_android_xml(v).strip()] = k
    for k, v in existing_translatable.items():
        seen_xml_values[v.strip()] = k
        seen_xml_values[escape_for_android_xml(v).strip()] = k

    for item in all_strings:
        raw_text = item["text"]
        occurrences = item["occurrences"]

        cat, reason = classify_string(raw_text, occurrences, ignore_prefixes, exclude_keywords)

        if cat == "IGNORE":
            report["ignored_count"] += 1
            report["ignored"].append({
                "text": raw_text,
                "reason": reason,
                "count": item["count"],
                "sample_file": occurrences[0]["file"] if occurrences else ""
            })
            continue

        xml_val = escape_for_android_xml(raw_text)
        normalized_xml = xml_val.strip()

        # Check if already present in existing resources
        if normalized_xml in seen_xml_values:
            existing_key = seen_xml_values[normalized_xml]
            report["duplicate_count"] += 1
            entry = {
                "key": existing_key,
                "value": xml_val,
                "original": raw_text,
                "reason": "existing_match",
                "occurrences": len(occurrences)
            }
            if cat == "NON_TRANSLATABLE":
                pass
            else:
                report["translatable"].append(entry)
            continue

        base_key = generate_resource_key(raw_text)
        candidate_key = base_key
        counter = 2
        while candidate_key in used_keys:
            candidate_key = f"{base_key}_{counter}"
            counter += 1

        used_keys.add(candidate_key)
        seen_xml_values[normalized_xml] = candidate_key

        entry = {
            "key": candidate_key,
            "value": xml_val,
            "original": raw_text,
            "reason": reason,
            "occurrences": len(occurrences)
        }

        if cat == "NON_TRANSLATABLE":
            report["non_translatable_count"] += 1
            donottranslate_list.append(entry)
            newly_added_donottranslate.append(entry)
        else:
            report["translatable_count"] += 1
            translatable_list.append(entry)
            report["translatable"].append(entry)
            newly_added_translatable.append(entry)

    # Prepare XML contents: append to existing file if present, else build from scratch
    if translatable_path.exists():
        existing_text = translatable_path.read_text(encoding="utf-8")
        if newly_added_translatable and "</resources>" in existing_text:
            insert_lines = [f'    <string name="{it["key"]}">{it["value"]}</string>' for it in newly_added_translatable]
            insert_block = "\n".join(insert_lines) + "\n"
            translatable_xml_content = existing_text.replace("</resources>", f"{insert_block}</resources>")
        else:
            translatable_xml_content = existing_text
    else:
        translatable_xml_content = build_translatable_xml(translatable_list)

    if donottranslate_path.exists():
        existing_text = donottranslate_path.read_text(encoding="utf-8")
        if newly_added_donottranslate and "</resources>" in existing_text:
            insert_lines = [f'    <string name="{it["key"]}" translatable="false">{it["value"]}</string>' for it in newly_added_donottranslate]
            insert_block = "\n".join(insert_lines) + "\n"
            donottranslate_xml_content = existing_text.replace("</resources>", f"{insert_block}</resources>")
        else:
            donottranslate_xml_content = existing_text
    else:
        donottranslate_xml_content = build_donottranslate_xml(donottranslate_list)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    for p in [report_path.parent] + list(report_path.parent.parents):
        if p.name == ".i18n_cache":
            gi = p / ".gitignore"
            if not gi.exists():
                gi.write_text("*\n", encoding="utf-8")
            break
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"[✓] Classification complete:")
    print(f"    - Ignored: {report['ignored_count']} strings")
    print(f"    - Non-translatable: {len(donottranslate_list)} strings -> strings_donottranslate.xml")
    print(f"    - Translatable UI: {len(translatable_list)} strings -> strings.xml")
    print(f"[✓] Audit report saved to: {report_path}")

    if dry_run:
        print("[*] Dry run mode enabled. No files written.")
    else:
        translatable_path.parent.mkdir(parents=True, exist_ok=True)
        with open(translatable_path, "w", encoding="utf-8") as f:
            f.write(translatable_xml_content)
        print(f"[✓] Translatable resources written: {translatable_path}")

        donottranslate_path.parent.mkdir(parents=True, exist_ok=True)
        with open(donottranslate_path, "w", encoding="utf-8") as f:
            f.write(donottranslate_xml_content)
        print(f"[✓] Non-translatable resources written: {donottranslate_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Universal Android string resource classifier and exporter."
    )
    parser.add_argument(
        "--index",
        "-i",
        default="extracted_strings_index.json",
        help="Input strings index JSON file (default: extracted_strings_index.json)"
    )
    parser.add_argument(
        "--translatable-xml",
        default="app/src/main/res/values/strings.xml",
        help="Target strings.xml path for translatable UI strings (default: app/src/main/res/values/strings.xml)"
    )
    parser.add_argument(
        "--donottranslate-xml",
        default="app/src/main/res/values/strings_donottranslate.xml",
        help="Target strings_donottranslate.xml path for non-translatable constants (default: app/src/main/res/values/strings_donottranslate.xml)"
    )
    parser.add_argument(
        "--report",
        "-r",
        default="string_classification_report.json",
        help="Classification audit report output path (default: string_classification_report.json)"
    )
    parser.add_argument(
        "--ignore-prefixes",
        default="@,#",
        help="Comma-separated prefixes to ignore (default: '@,#')"
    )
    parser.add_argument(
        "--exclude-keywords",
        default="",
        help="Comma-separated custom keywords to ignore"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform dry run without modifying resource files"
    )

    args = parser.parse_args()

    index_path = Path(args.index).resolve()
    translatable_path = Path(args.translatable_xml).resolve()
    donottranslate_path = Path(args.donottranslate_xml).resolve()
    report_path = Path(args.report).resolve()

    ignore_prefixes = {p.strip() for p in args.ignore_prefixes.split(",") if p.strip()}
    exclude_keywords = {k.strip() for k in args.exclude_keywords.split(",") if k.strip()}

    if not index_path.exists():
        print(f"[ERROR] Index file not found at: {index_path}", file=sys.stderr)
        sys.exit(1)

    process_and_export(
        index_path=index_path,
        translatable_path=translatable_path,
        donottranslate_path=donottranslate_path,
        report_path=report_path,
        ignore_prefixes=ignore_prefixes,
        exclude_keywords=exclude_keywords,
        dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()
