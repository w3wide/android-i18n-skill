#!/usr/bin/env python3
"""
verify_accuracy.py - Deterministic accuracy verification for Android string resources.

Verifies:
1. Resource Existence: Every R.string.<key> in Kotlin/Java and @string/<key> in XML layouts exists in strings.xml or strings_donottranslate.xml.
2. Argument Count Matching: Positional format specifiers (%1$s, %2$d, %s) in XML match arguments passed in code.
3. Leftover Hardcoded Strings: Flags remaining hardcoded UI texts in Text("...") or android:text="...".
"""

import os
import sys
import re
import json
import argparse
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any
import xml.etree.ElementTree as ET


def find_android_project_paths(cwd: Path) -> Tuple[Path, Path]:
    """Dynamically finds the Android main source and res directory."""
    candidates = [
        cwd / "app/src/main",
        cwd / "src/main",
        cwd / "androidApp/src/main",
    ]
    for c in candidates:
        if (c / "res").exists():
            return c, c / "res"

    for mf in cwd.rglob("AndroidManifest.xml"):
        if any(part in {"build", ".gradle", ".idea"} for part in mf.parts):
            continue
        main_dir = mf.parent
        if (main_dir / "res").exists():
            return main_dir, main_dir / "res"

    return cwd / "app/src/main", cwd / "app/src/main/res"


def count_format_specifiers(xml_text: str) -> int:
    """Counts printf-style format specifiers (%s, %1$s, %d, etc.) in XML string."""
    pattern = r"%(?:(\d+)\$)?[-#+ 0,(]*\d*(?:\.\d+)?[a-zA-Z]"
    matches = re.findall(pattern, xml_text)
    if not matches:
        return 0
    indices = [int(m) for m in matches if m]
    if indices:
        return max(indices)
    return len(matches)


def load_all_string_resources(res_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Loads all string resources defined across values*/strings*.xml."""
    resource_map: Dict[str, Dict[str, Any]] = {}

    for xml_file in res_dir.glob("values*/strings*.xml"):
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            for elem in root.findall("string"):
                name = elem.get("name")
                val = elem.text or ""
                translatable = elem.get("translatable", "true").lower() != "false"
                if name:
                    resource_map[name] = {
                        "value": val,
                        "file": str(xml_file.name),
                        "translatable": translatable,
                        "expected_args": count_format_specifiers(val)
                    }
        except Exception as e:
            print(f"[ERROR] Failed parsing {xml_file}: {e}", file=sys.stderr)

    return resource_map


def split_args(args_str: str) -> List[str]:
    """Splits argument list taking into account nested commas inside parentheses/brackets."""
    args = []
    current = []
    depth = 0
    for c in args_str:
        if c in "({[<":
            depth += 1
            current.append(c)
        elif c in ")}]>":
            depth -= 1
            current.append(c)
        elif c == "," and depth == 0:
            token = "".join(current).strip()
            if token:
                args.append(token)
            current = []
        else:
            current.append(c)
    if current:
        token = "".join(current).strip()
        if token:
            args.append(token)
    return args


def verify_sources(src_root: Path, resource_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Scans Kotlin, Java, and XML layout files and verifies resource references."""
    results = {
        "valid_references": 0,
        "missing_keys": [],
        "argument_mismatches": [],
        "leftover_hardcoded_texts": [],
        "files_checked": 0,
    }

    res_call_pattern = re.compile(
        r"(?:stringResource|getString)\s*\(\s*R\.string\.([a-zA-Z0-9_]+)(?:\s*,\s*([^)]+))?\s*\)"
    )
    xml_res_pattern = re.compile(r'@string/([a-zA-Z0-9_]+)')
    hardcoded_text_pattern = re.compile(r'Text\s*\(\s*"([^"]{2,})"')
    hardcoded_xml_pattern = re.compile(r'(?:android:text|android:hint)\s*=\s*"([^@?][^"]+)"')

    for file_path in src_root.rglob("*"):
        if not file_path.is_file():
            continue
        ext = file_path.suffix.lower()
        if ext not in {".kt", ".java", ".xml"}:
            continue

        results["files_checked"] += 1
        rel_path = str(file_path.relative_to(src_root))

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            continue

        for line_no, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("<!--"):
                continue

            # Code resource calls
            if ext in {".kt", ".java"}:
                for match in res_call_pattern.finditer(line):
                    key_name = match.group(1)
                    args_str = match.group(2)
                    arg_count = len(split_args(args_str)) if args_str else 0

                    if key_name not in resource_map:
                        results["missing_keys"].append({
                            "key": key_name,
                            "file": rel_path,
                            "line": line_no
                        })
                    else:
                        results["valid_references"] += 1
                        expected_args = resource_map[key_name]["expected_args"]
                        if arg_count != expected_args:
                            results["argument_mismatches"].append({
                                "key": key_name,
                                "file": rel_path,
                                "line": line_no,
                                "expected_args": expected_args,
                                "actual_args": arg_count,
                                "xml_value": resource_map[key_name]["value"]
                            })

                for match in hardcoded_text_pattern.finditer(line):
                    val = match.group(1).strip()
                    if len(val) > 1 and re.search(r"[a-zA-Z]{2,}", val):
                        if "testTag" not in line and "Preview" not in line and not val.startswith("http"):
                            results["leftover_hardcoded_texts"].append({
                                "text": val,
                                "file": rel_path,
                                "line": line_no
                            })

            # XML layout resource references
            elif ext == ".xml":
                parent = file_path.parent.name
                if parent.startswith(("layout", "menu")):
                    for match in xml_res_pattern.finditer(line):
                        key_name = match.group(1)
                        if key_name not in resource_map:
                            results["missing_keys"].append({
                                "key": key_name,
                                "file": rel_path,
                                "line": line_no
                            })
                        else:
                            results["valid_references"] += 1

                    for match in hardcoded_xml_pattern.finditer(line):
                        val = match.group(1).strip()
                        if len(val) > 1 and re.search(r"[a-zA-Z]{2,}", val):
                            results["leftover_hardcoded_texts"].append({
                                "text": val,
                                "file": rel_path,
                                "line": line_no
                            })

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Verify Android string resource accuracy & parameter signatures."
    )
    parser.add_argument("--src", help="Path to main source directory (auto-detected if omitted)")
    parser.add_argument("--res", help="Path to res directory (auto-detected if omitted)")
    args = parser.parse_args()

    cwd = Path.cwd()
    auto_src, auto_res = find_android_project_paths(cwd)

    src_dir = Path(args.src).resolve() if args.src else auto_src
    res_dir = Path(args.res).resolve() if args.res else auto_res

    print("=================================================================")
    print("🔍 Android String Resource Accuracy & Integrity Audit")
    print("=================================================================")
    print(f"[*] Project root: {cwd}")
    print(f"[*] Source dir:   {src_dir}")
    print(f"[*] Resource dir: {res_dir}")

    if not res_dir.exists():
        print(f"[ERROR] Resource directory not found at: {res_dir}", file=sys.stderr)
        sys.exit(1)

    resource_map = load_all_string_resources(res_dir)
    translatable_count = sum(1 for r in resource_map.values() if r["translatable"])
    non_translatable_count = len(resource_map) - translatable_count

    print(f"[*] Loaded {len(resource_map)} defined string resources:")
    print(f"    - Translatable (strings.xml): {translatable_count}")
    print(f"    - Non-translatable (strings_donottranslate.xml): {non_translatable_count}")

    audit = verify_sources(src_dir, resource_map)

    print(f"\n[*] Source Code Verification ({audit['files_checked']} files scanned):")
    print(f"    - Valid stringResource/getString/@string references: {audit['valid_references']}")
    print(f"    - Missing resource keys: {len(audit['missing_keys'])}")
    print(f"    - Format argument mismatches: {len(audit['argument_mismatches'])}")
    print(f"    - Leftover hardcoded UI text: {len(audit['leftover_hardcoded_texts'])}")

    has_error = False

    if audit["missing_keys"]:
        has_error = True
        print("\n❌ MISSING RESOURCE KEYS FOUND:")
        for item in audit["missing_keys"][:10]:
            print(f"    - {item['key']} at {item['file']}:{item['line']}")

    if audit["argument_mismatches"]:
        has_error = True
        print("\n❌ FORMAT ARGUMENT MISMATCHES:")
        for item in audit["argument_mismatches"][:10]:
            print(f"    - R.string.{item['key']} at {item['file']}:{item['line']} (expected {item['expected_args']}, got {item['actual_args']})")
            print(f"      XML: {item['xml_value']}")

    if audit["leftover_hardcoded_texts"]:
        print(f"\nℹ️  Leftover hardcoded text in UI ({len(audit['leftover_hardcoded_texts'])} found):")
        for item in audit["leftover_hardcoded_texts"][:10]:
            print(f"    - \"{item['text']}\" at {item['file']}:{item['line']}")

    if not has_error:
        print("\n✅ ACCURACY VERIFICATION PASSED: 100% of referenced string resources exist and match their signatures.")
        sys.exit(0)
    else:
        print("\n❌ ACCURACY VERIFICATION FAILED: Issues found above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
