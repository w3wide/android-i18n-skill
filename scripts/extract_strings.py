#!/usr/bin/env python3
"""
extract_strings.py - Universal Android string literal extractor.

Scans:
- Kotlin source files (*.kt)
- Java source files (*.java)
- Android XML layout and menu files (*.xml)

Features:
- Completely project-agnostic.
- Strips code comments (//, /* ... */) and XML comments (<!-- ... -->).
- Excludes logger invocations (Log.*, Timber.*, println, print).
- Handles Kotlin multiline raw strings (\"\"\"...\"\"\") and recursive ${...} template nesting.
- Extracts hardcoded layout attributes (android:text, android:hint, android:title, android:contentDescription) that do not use @string/.
- Outputs index JSON file with file paths, line numbers, and occurrences.
"""

import os
import sys
import json
import re
import argparse
from pathlib import Path
from typing import List, Dict, Any
import xml.etree.ElementTree as ET


LOG_CALL_PATTERNS = [
    r"Log\.[deiwv]|Log\.wtf",
    r"Timber\.[deiwv]",
    r"println\s*\(",
    r"print\s*\(",
]


def is_logger_call(line_text: str) -> bool:
    """Checks if line contains a standard Android/Kotlin/Java logger invocation."""
    return any(re.search(pat, line_text) for pat in LOG_CALL_PATTERNS)


def extract_strings_from_code(file_path: Path, relative_to: Path) -> List[Dict[str, Any]]:
    """Lexically extracts string literals from Kotlin or Java files."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        print(f"[WARN] Failed to read {file_path}: {e}", file=sys.stderr)
        return []

    rel_path_str = str(file_path.relative_to(relative_to))
    length = len(content)
    i = 0
    line = 1
    extracted: List[Dict[str, Any]] = []

    lines = content.split("\n")

    while i < length:
        ch = content[i]

        if ch == "\n":
            line += 1
            i += 1
            continue

        # Single-line comment: //
        if ch == "/" and i + 1 < length and content[i + 1] == "/":
            i += 2
            while i < length and content[i] != "\n":
                i += 1
            continue

        # Multi-line comment: /* ... */
        if ch == "/" and i + 1 < length and content[i + 1] == "*":
            i += 2
            while i + 1 < length and not (content[i] == "*" and content[i + 1] == "/"):
                if content[i] == "\n":
                    line += 1
                i += 1
            i += 2
            continue

        # Character literal: 'c' or '\n'
        if ch == "'":
            i += 1
            while i < length and content[i] != "\n":
                if content[i] == "\\":
                    i += 2
                elif content[i] == "'":
                    i += 1
                    break
                else:
                    i += 1
            continue

        # Triple-quoted string literal: """...""" (Kotlin raw string)
        if content.startswith('"""', i):
            start_line = line
            i += 3
            buf: List[str] = []
            while i < length and not content.startswith('"""', i):
                c = content[i]
                if c == "\n":
                    line += 1
                buf.append(c)
                i += 1
            if content.startswith('"""', i):
                i += 3
            raw_text = "".join(buf)

            current_line_text = lines[start_line - 1] if start_line - 1 < len(lines) else ""
            if not is_logger_call(current_line_text):
                extracted.append({
                    "text": raw_text,
                    "file": rel_path_str,
                    "line": start_line,
                    "source_type": "code",
                    "raw": True,
                    "has_template": "$" in raw_text
                })
            continue

        # Regular double-quoted string literal: "..."
        if ch == '"':
            start_line = line
            i += 1
            buf: List[str] = []
            has_template = False

            while i < length:
                c = content[i]
                if c == "\n":
                    line += 1
                    break
                if c == "\\":
                    if i + 1 < length:
                        next_c = content[i + 1]
                        if next_c == "n":
                            buf.append("\n")
                        elif next_c == "t":
                            buf.append("\t")
                        elif next_c == "r":
                            buf.append("\r")
                        elif next_c == '"':
                            buf.append('"')
                        elif next_c == "\\":
                            buf.append("\\")
                        elif next_c == "$":
                            buf.append("$")
                        else:
                            buf.append("\\" + next_c)
                        i += 2
                        continue
                    else:
                        i += 1
                        break
                elif c == "$" and i + 1 < length and content[i + 1] == "{":
                    # Kotlin template expression ${...}
                    has_template = True
                    buf.append("${")
                    i += 2
                    brace_depth = 1
                    while i < length and brace_depth > 0:
                        ch_in = content[i]
                        if ch_in == "\n":
                            line += 1
                        if ch_in == "\\":
                            buf.append(content[i:i+2])
                            i += 2
                        elif ch_in == "{":
                            brace_depth += 1
                            buf.append(ch_in)
                            i += 1
                        elif ch_in == "}":
                            brace_depth -= 1
                            buf.append(ch_in)
                            i += 1
                        elif ch_in == '"':
                            # Inner string literal inside ${...}
                            inner_start_line = line
                            inner_buf: List[str] = []
                            buf.append('"')
                            i += 1
                            while i < length and content[i] != '"':
                                if content[i] == "\n":
                                    line += 1
                                if content[i] == "\\":
                                    inner_buf.append(content[i:i+2])
                                    buf.append(content[i:i+2])
                                    i += 2
                                else:
                                    inner_buf.append(content[i])
                                    buf.append(content[i])
                                    i += 1
                            if i < length and content[i] == '"':
                                buf.append('"')
                                i += 1
                            inner_text = "".join(inner_buf)
                            curr_line_text = lines[inner_start_line - 1] if inner_start_line - 1 < len(lines) else ""
                            if inner_text and not is_logger_call(curr_line_text):
                                extracted.append({
                                    "text": inner_text,
                                    "file": rel_path_str,
                                    "line": inner_start_line,
                                    "source_type": "code",
                                    "raw": False,
                                    "has_template": "$" in inner_text
                                })
                        else:
                            buf.append(ch_in)
                            i += 1
                    continue
                elif c == '"':
                    i += 1
                    break
                else:
                    if c == "$":
                        has_template = True
                    buf.append(c)
                    i += 1

            extracted_text = "".join(buf)
            current_line_text = lines[start_line - 1] if start_line - 1 < len(lines) else ""
            if not is_logger_call(current_line_text):
                extracted.append({
                    "text": extracted_text,
                    "file": rel_path_str,
                    "line": start_line,
                    "source_type": "code",
                    "raw": False,
                    "has_template": has_template
                })
            continue

        i += 1

    return extracted


def extract_strings_from_xml(file_path: Path, relative_to: Path) -> List[Dict[str, Any]]:
    """Extracts hardcoded text attributes from Android layout and menu XML files."""
    rel_path_str = str(file_path.relative_to(relative_to))
    extracted: List[Dict[str, Any]] = []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return []

    target_attrs = {
        "android:text", "android:hint", "android:title",
        "android:contentDescription", "app:title", "app:subtitle"
    }

    attr_regex = re.compile(r'([a-zA-Z0-9_:]+)\s*=\s*"([^"]+)"')

    for line_no, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("<!--"):
            continue

        for match in attr_regex.finditer(line):
            attr_name = match.group(1)
            val = match.group(2)

            if attr_name in target_attrs:
                # If already using a resource reference (@string/, @android:string/), skip it
                if not val.startswith("@") and not val.startswith("?"):
                    extracted.append({
                        "text": val,
                        "file": rel_path_str,
                        "line": line_no,
                        "source_type": "xml_layout",
                        "raw": False,
                        "has_template": False
                    })

    return extracted


def build_string_index(source_paths: List[Path], root_dir: Path) -> Dict[str, Any]:
    """Scans all specified directories and files for extractable strings."""
    files_scanned = 0
    string_map: Dict[str, Dict[str, Any]] = {}

    for spath in source_paths:
        if not spath.exists():
            continue
        if spath.is_file():
            scan_files = [spath]
        else:
            scan_files = [p for p in spath.rglob("*") if p.is_file()]

        for file_path in scan_files:
            ext = file_path.suffix.lower()
            entries: List[Dict[str, Any]] = []

            if ext in {".kt", ".java"}:
                files_scanned += 1
                entries = extract_strings_from_code(file_path, root_dir)
            elif ext == ".xml":
                # Only inspect layout, menu, or navigation xml files (not values/strings.xml)
                parent_dir = file_path.parent.name
                if parent_dir.startswith(("layout", "menu", "navigation")):
                    files_scanned += 1
                    entries = extract_strings_from_xml(file_path, root_dir)

            for entry in entries:
                txt = entry["text"]
                if txt not in string_map:
                    string_map[txt] = {
                        "text": txt,
                        "source_type": entry["source_type"],
                        "raw": entry.get("raw", False),
                        "has_template": entry.get("has_template", False),
                        "count": 0,
                        "occurrences": []
                    }
                string_map[txt]["count"] += 1
                string_map[txt]["occurrences"].append({
                    "file": entry["file"],
                    "line": entry["line"]
                })

    items = list(string_map.values())
    items.sort(key=lambda x: (-x["count"], x["text"]))

    return {
        "metadata": {
            "files_scanned": files_scanned,
            "unique_strings": len(items),
            "total_occurrences": sum(item["count"] for item in items),
        },
        "strings": items
    }


def main():
    parser = argparse.ArgumentParser(
        description="Universal Android string literal extractor (Kotlin, Java, XML Layouts)."
    )
    parser.add_argument(
        "--src",
        nargs="+",
        default=["app/src/main"],
        help="Source directories or files to scan (default: app/src/main)"
    )
    parser.add_argument(
        "--output",
        "-o",
        default="extracted_strings_index.json",
        help="Output index JSON file (default: extracted_strings_index.json)"
    )
    args = parser.parse_args()

    root_dir = Path.cwd()
    source_paths = [Path(d).resolve() for d in args.src]
    output_path = Path(args.output).resolve()

    print(f"[*] Scanning source paths: {', '.join(args.src)}")
    index_data = build_string_index(source_paths, root_dir)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    for p in [output_path.parent] + list(output_path.parent.parents):
        if p.name == ".i18n_cache":
            gi = p / ".gitignore"
            if not gi.exists():
                gi.write_text("*\n", encoding="utf-8")
            break
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(index_data, f, indent=2, ensure_ascii=False)

    meta = index_data["metadata"]
    print(f"[✓] Extracted {meta['unique_strings']} unique strings ({meta['total_occurrences']} occurrences) from {meta['files_scanned']} files.")
    print(f"[✓] Index saved to: {output_path}")


if __name__ == "__main__":
    main()
