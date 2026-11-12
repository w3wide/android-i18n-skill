#!/usr/bin/env python3
"""
replace_strings.py - Universal Android source & layout string replacer.

Replaces hardcoded strings across:
1. Jetpack Compose (Kotlin): stringResource(R.string.<key>) and context.getString(R.string.<key>).
2. Traditional Views (Kotlin & Java): setText(R.string.<key>) or getString(R.string.<key>).
3. Android XML Layouts & Menus: android:text="@string/<key>", android:hint="@string/<key>".

Features:
- Completely project-agnostic.
- Automatically discovers project R namespace from build.gradle(.kts) or AndroidManifest.xml.
- Prevents invalid composable invocations in non-composable scopes.
"""

import os
import sys
import re
import json
import argparse
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional


def detect_app_namespace(root_dir: Path) -> str:
    """Detects the Android application package namespace dynamically."""
    # 1. Try build.gradle / build.gradle.kts
    gradle_files = list(root_dir.rglob("build.gradle.kts")) + list(root_dir.rglob("build.gradle"))
    for gf in gradle_files:
        try:
            content = gf.read_text(encoding="utf-8")
            m = re.search(r'namespace\s*=?\s*["\']([^"\']+)["\']', content)
            if m:
                return m.group(1).strip()
        except Exception:
            pass

    # 2. Try AndroidManifest.xml
    manifest_files = list(root_dir.rglob("AndroidManifest.xml"))
    for mf in manifest_files:
        try:
            content = mf.read_text(encoding="utf-8")
            m = re.search(r'package\s*=\s*["\']([^"\']+)["\']', content)
            if m:
                return m.group(1).strip()
        except Exception:
            pass

    return "com.example.app"


def extract_template_args(raw_text: str) -> List[str]:
    """Extracts Kotlin template expressions in order from a templated string."""
    pattern = r"(\$\{[^}]+\}|\$[a-zA-Z_][a-zA-Z0-9_]*)"
    matches = re.findall(pattern, raw_text)
    args = []
    for m in matches:
        if m.startswith("${") and m.endswith("}"):
            expr = m[2:-1].strip()
        elif m.startswith("$"):
            expr = m[1:].strip()
        else:
            expr = m
        args.append(expr)
    return args


def load_translatable_map(report_path: Path) -> Dict[str, Dict[str, Any]]:
    """Loads map of original text -> item details from string_classification_report.json."""
    if not report_path.exists():
        raise FileNotFoundError(f"Report file not found: {report_path}")

    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    translatable_map: Dict[str, Dict[str, Any]] = {}
    for item in data.get("translatable", []):
        orig = item.get("original", "")
        if orig:
            translatable_map[orig] = item
    return translatable_map


def is_safe_composable_callsite(line: str) -> bool:
    """Checks if line contains a standard Compose UI call site where stringResource is valid."""
    stripped = line.strip()

    if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
        return False
    if stripped.startswith("import ") or stripped.startswith("package ") or stripped.startswith("@"):
        return False
    if "const val " in stripped:
        return False

    if "LaunchedEffect" in line or "remember(" in line or "remember {" in line:
        return False
    if "showSnackbar" in line or "SimpleDateFormat" in line:
        return False
    if "Log." in line or "Crashlytics" in line or "testTag" in line or "contentType" in line or "Route(" in line:
        return False
    if "LocalClipboardManager" in line or "clipboard." in line:
        return False

    valid_patterns = [
        r"Text\s*\(",
        r"contentDescription\s*=",
        r"text\s*=",
        r"label\s*=\s*\{",
        r"placeholder\s*=\s*\{",
        r"title\s*=\s*\{",
        r"title\s*=",
        r"subtitle\s*=",
        r"message\s*=",
        r"label\s*=",
        r"placeholder\s*=",
        r"Toast\.makeText\s*\(",
    ]

    return any(re.search(pat, line) for pat in valid_patterns)


def replace_in_xml_layout(
    file_path: Path,
    translatable_map: Dict[str, Dict[str, Any]],
    dry_run: bool = False
) -> int:
    """Replaces hardcoded string attributes in Android XML layout files with @string/key."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return 0

    replaced_count = 0
    lines = content.split("\n")
    new_lines = []

    sorted_items = sorted(
        translatable_map.items(),
        key=lambda kv: len(kv[0]),
        reverse=True
    )

    target_attrs = ["android:text", "android:hint", "android:title", "android:contentDescription", "app:title", "app:subtitle"]

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("<!--"):
            new_lines.append(line)
            continue

        modified_line = line
        for attr in target_attrs:
            for orig_text, meta in sorted_items:
                search_pat = f'{attr}="{orig_text}"'
                if search_pat in modified_line:
                    key = meta["key"]
                    replacement = f'{attr}="@string/{key}"'
                    modified_line = modified_line.replace(search_pat, replacement)
                    replaced_count += 1

        new_lines.append(modified_line)

    if replaced_count > 0 and not dry_run:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(new_lines))

    return replaced_count


def replace_in_code_file(
    file_path: Path,
    translatable_map: Dict[str, Dict[str, Any]],
    app_namespace: str,
    dry_run: bool = False
) -> int:
    """Replaces translatable string literals in Kotlin or Java files."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return 0

    lines = content.split("\n")
    replaced_count = 0
    new_lines = []
    is_java = file_path.suffix.lower() == ".java"

    sorted_items = sorted(
        translatable_map.items(),
        key=lambda kv: len(kv[0]),
        reverse=True
    )

    in_non_composable_func = False
    brace_depth = 0

    for line_idx, line in enumerate(lines, 1):
        stripped = line.strip()

        is_func_or_class = bool(re.search(r'\b(?:(?:public|private|protected|internal|override|suspend|final|open|inline)\s+)*fun\b', stripped)) or "enum class " in stripped
        if is_func_or_class:
            prev_line = lines[line_idx - 2].strip() if line_idx > 1 else ""
            if not stripped.startswith("@Composable") and not prev_line.startswith("@Composable") and "@Composable" not in stripped:
                in_non_composable_func = True
                brace_depth = 0

        if in_non_composable_func:
            brace_depth += line.count("{") - line.count("}")
            if brace_depth <= 0:
                in_non_composable_func = False
            new_lines.append(line)
            continue

        if line and not line[0].isspace() and not stripped.startswith("@Composable") and not stripped.startswith("fun ") and not is_java:
            new_lines.append(line)
            continue

        if not is_java and "ui" not in file_path.parts and not ("setText(" in line or "getString(" in line or "Toast.makeText(" in line):
            new_lines.append(line)
            continue

        is_view_call = any(k in line for k in ["setText(", "setHint(", "setTitle(", "setContentDescription("])
        is_safe_compose = is_safe_composable_callsite(line)

        if not is_safe_compose and not is_view_call:
            new_lines.append(line)
            continue

        modified_line = line
        is_toast = "Toast.makeText(" in line and "context" in line

        for orig_text, meta in sorted_items:
            key = meta["key"]
            args = extract_template_args(orig_text)

            search_str = f'"{orig_text}"'
            if search_str not in modified_line:
                continue

            if is_view_call and not args:
                # Traditional View setText("...") -> setText(R.string.<key>)
                for method in ["setText", "setHint", "setTitle", "setContentDescription"]:
                    pattern = f'{method}("{orig_text}")'
                    if pattern in modified_line:
                        modified_line = modified_line.replace(pattern, f'{method}(R.string.{key})')
                        replaced_count += 1
                        break
                continue

            if is_toast:
                if args:
                    args_str = ", ".join(args)
                    replacement = f"context.getString(R.string.{key}, {args_str})"
                else:
                    replacement = f"context.getString(R.string.{key})"
            else:
                if is_java:
                    replacement = f"getString(R.string.{key})"
                else:
                    if args:
                        args_str = ", ".join(args)
                        replacement = f"stringResource(R.string.{key}, {args_str})"
                    else:
                        replacement = f"stringResource(R.string.{key})"

            modified_line = modified_line.replace(search_str, replacement)
            replaced_count += 1

        new_lines.append(modified_line)

    if replaced_count > 0:
        new_content = "\n".join(new_lines)
        imports_to_add = []

        # Dynamic R import
        r_import = f"import {app_namespace}.R" + (";" if is_java else "")
        if f"import {app_namespace}.R" not in new_content and "R.string." in new_content:
            imports_to_add.append(r_import)

        if not is_java and "stringResource(R.string." in new_content:
            compose_import = "import androidx.compose.ui.res.stringResource"
            if compose_import not in new_content:
                imports_to_add.append(compose_import)

        if imports_to_add:
            split_res = new_content.split("\n")
            package_idx = -1
            for i, l in enumerate(split_res):
                if l.startswith("package "):
                    package_idx = i
                    break
            if package_idx != -1:
                insert_lines = [""] + imports_to_add
                split_res = split_res[:package_idx + 1] + insert_lines + split_res[package_idx + 1:]
                new_content = "\n".join(split_res)

        if not dry_run:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

    return replaced_count


def main():
    parser = argparse.ArgumentParser(
        description="Universal Android source & layout string replacer."
    )
    parser.add_argument(
        "--report",
        "-r",
        default="string_classification_report.json",
        help="Path to classification report (default: string_classification_report.json)"
    )
    parser.add_argument(
        "--target-dir",
        "-d",
        default="app/src/main",
        help="Target source directory (default: app/src/main)"
    )
    parser.add_argument(
        "--namespace",
        "-n",
        help="App package namespace for R imports (auto-detected if omitted)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform dry run without modifying files"
    )

    args = parser.parse_args()

    root_dir = Path.cwd()
    report_path = Path(args.report).resolve()
    translatable_map = load_translatable_map(report_path)

    app_namespace = args.namespace or detect_app_namespace(root_dir)
    print(f"[*] App namespace: {app_namespace}")
    print(f"[*] Loaded {len(translatable_map)} translatable strings.")

    target_dir = Path(args.target_dir).resolve()
    total_replacements = 0
    modified_files = 0

    for file_path in target_dir.rglob("*"):
        if not file_path.is_file():
            continue
        ext = file_path.suffix.lower()

        if ext == ".xml":
            parent = file_path.parent.name
            if parent.startswith(("layout", "menu")):
                count = replace_in_xml_layout(file_path, translatable_map, dry_run=args.dry_run)
                if count > 0:
                    modified_files += 1
                    total_replacements += count
                    rel_p = file_path.relative_to(root_dir) if file_path.is_relative_to(root_dir) else file_path
                    print(f"  [✓] {rel_p}: {count} layout replacements")
        elif ext in {".kt", ".java"}:
            if file_path.name.endswith(("ViewModel.kt", "Repository.kt", "Theme.kt", "Color.kt", "Type.kt")):
                continue
            count = replace_in_code_file(file_path, translatable_map, app_namespace, dry_run=args.dry_run)
            if count > 0:
                modified_files += 1
                total_replacements += count
                rel_p = file_path.relative_to(root_dir) if file_path.is_relative_to(root_dir) else file_path
                print(f"  [✓] {rel_p}: {count} code replacements")

    mode_str = "(Dry Run)" if args.dry_run else "(Applied)"
    print(f"\n[✓] Done {mode_str}: Replaced {total_replacements} strings across {modified_files} files.")


if __name__ == "__main__":
    main()
