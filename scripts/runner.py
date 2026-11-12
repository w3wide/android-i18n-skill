#!/usr/bin/env python3
"""
runner.py - Unified orchestrator for the android-i18n skill.

Coordinates the 4-step Android string localization pipeline:
1. extract: Scans Kotlin, Java, and Layout XML files for string literals (excluding logs).
2. filter: Classifies strings into translatable and non-translatable, enforcing zero duplicates.
3. replace: Safely replaces strings with stringResource() or getString() in Compose, Views, and XML.
4. verify: Deterministically validates that 100% of referenced resources and format args match.

Supports:
- Auto Mode: Executes immediately with recommended defaults.
- Interactive Mode (--interactive): Prompts the user for exclusion preferences and file names.
"""

import sys
import subprocess
import argparse
from pathlib import Path
from typing import Tuple


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


def run_command(cmd: list, desc: str) -> bool:
    print(f"\n▶ [{desc}] Running: {' '.join(str(c) for c in cmd)}")
    res = subprocess.run(cmd)
    if res.returncode != 0:
        print(f"❌ [{desc}] Failed with exit code {res.returncode}", file=sys.stderr)
        return False
    return True


def prompt_user_interview(default_ignore_prefixes: str, default_nt_file: str) -> Tuple[str, str, str]:
    """Conducts an interactive CLI interview for customized pipeline execution."""
    print("\n" + "=" * 65)
    print("🛠️  android-i18n: Interactive Setup Interview")
    print("=" * 65)

    # Question 1: Auto proceed or customize
    print("\n[1/3] How would you like to proceed?")
    print("  1. (Recommended) Auto-proceed with smart defaults")
    print("  2. Customize exclusion rules and file names")
    choice = input("Select [1/2] (default: 1): ").strip()

    if choice != "2":
        print("✓ Using recommended defaults.")
        return default_ignore_prefixes, "", default_nt_file

    # Question 2: Ignore prefixes & keywords
    print("\n[2/3] What prefixes or tokens should remain hardcoded in code?")
    print(f"  Default prefixes: '{default_ignore_prefixes}' (e.g. mentions, tags)")
    custom_prefixes = input(f"Enter prefixes to ignore [comma-separated, Enter for '{default_ignore_prefixes}']: ").strip()
    if not custom_prefixes:
        custom_prefixes = default_ignore_prefixes

    custom_keywords = input("Enter any specific keywords/tokens to ignore [comma-separated, or Enter to skip]: ").strip()

    # Question 3: Non-translatable XML file name
    print("\n[3/3] Where should non-translatable strings (app ID, ad IDs) be stored?")
    print(f"  1. (Recommended) {default_nt_file} (Separate dedicated file)")
    print("  2. strings.xml (Single file with translatable=\"false\" attribute)")
    print("  3. Custom file name")
    nt_choice = input("Select [1/2/3] (default: 1): ").strip()

    if nt_choice == "2":
        nt_file = "strings.xml"
    elif nt_choice == "3":
        custom_name = input("Enter custom XML file name (e.g. strings_constants.xml): ").strip()
        nt_file = custom_name if custom_name else default_nt_file
    else:
        nt_file = default_nt_file

    print("\n✓ Configuration confirmed:")
    print(f"  - Ignore Prefixes: {custom_prefixes}")
    print(f"  - Exclude Keywords: {custom_keywords or 'None'}")
    print(f"  - Non-translatable File: {nt_file}")
    return custom_prefixes, custom_keywords, nt_file


def main():
    parser = argparse.ArgumentParser(
        description="Unified runner for the android-i18n extraction & localization pipeline."
    )
    parser.add_argument("--all", action="store_true", help="Execute all 4 steps sequentially")
    parser.add_argument("--interactive", action="store_true", help="Prompt user with an interactive interview")
    parser.add_argument("--extract", action="store_true", help="Run Step 1: Extract strings to index JSON")
    parser.add_argument("--filter", action="store_true", help="Run Step 2: Filter and export XML resources")
    parser.add_argument("--replace", action="store_true", help="Run Step 3: Replace strings in source & layout files")
    parser.add_argument("--verify", action="store_true", help="Run Step 4: Verify resource integrity & signatures")
    parser.add_argument("--dry-run", action="store_true", help="Run in preview mode without modifying files")
    parser.add_argument("--src", help="Source directory (auto-detected if omitted)")
    parser.add_argument("--cache-dir", default=".i18n_cache", help="Directory for intermediate index & report files")
    parser.add_argument("--ignore-prefixes", default="@,#", help="Comma-separated prefixes to ignore (default: '@,#')")
    parser.add_argument("--exclude-keywords", default="", help="Comma-separated custom keywords to ignore")
    parser.add_argument("--non-translatable-file", default="strings_donottranslate.xml", help="Target non-translatable XML file name")

    args = parser.parse_args()

    ignore_prefixes = args.ignore_prefixes
    exclude_keywords = args.exclude_keywords
    nt_file_name = args.non_translatable_file

    if args.interactive:
        ignore_prefixes, exclude_keywords, nt_file_name = prompt_user_interview(ignore_prefixes, nt_file_name)

    cwd = Path.cwd()
    auto_src, auto_res = find_android_project_paths(cwd)
    src_dir = Path(args.src).resolve() if args.src else auto_src

    cache_dir = cwd / args.cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_gitignore = cache_dir / ".gitignore"
    if not cache_gitignore.exists():
        cache_gitignore.write_text("*\n", encoding="utf-8")
    index_file = cache_dir / "extracted_strings_index.json"
    report_file = cache_dir / "string_classification_report.json"

    run_all = args.all or not (args.extract or args.filter or args.replace or args.verify)

    scripts_dir = Path(__file__).parent.resolve()
    py = sys.executable

    # Step 1: Extract
    if run_all or args.extract:
        cmd = [
            py, str(scripts_dir / "extract_strings.py"),
            "--src", str(src_dir),
            "--output", str(index_file)
        ]
        if not run_command(cmd, "Step 1: Extract Strings"):
            sys.exit(1)

    # Step 2: Filter & Export
    if run_all or args.filter:
        cmd = [
            py, str(scripts_dir / "filter_and_export_strings.py"),
            "--index", str(index_file),
            "--translatable-xml", str(auto_res / "values/strings.xml"),
            "--donottranslate-xml", str(auto_res / f"values/{nt_file_name}"),
            "--report", str(report_file),
            "--ignore-prefixes", ignore_prefixes,
            "--exclude-keywords", exclude_keywords
        ]
        if args.dry_run:
            cmd.append("--dry-run")
        if not run_command(cmd, "Step 2: Filter & Export Resources"):
            sys.exit(1)

    # Step 3: Replace
    if run_all or args.replace:
        cmd = [
            py, str(scripts_dir / "replace_strings.py"),
            "--report", str(report_file),
            "--target-dir", str(src_dir)
        ]
        if args.dry_run:
            cmd.append("--dry-run")
        if not run_command(cmd, "Step 3: Replace in Sources & Layouts"):
            sys.exit(1)

    # Step 4: Verify
    if run_all or args.verify:
        cmd = [
            py, str(scripts_dir / "verify_accuracy.py"),
            "--src", str(src_dir),
            "--res", str(auto_res)
        ]
        if not run_command(cmd, "Step 4: Verify Resource Accuracy"):
            sys.exit(1)

    print("\n✅ [android-i18n] Pipeline completed successfully!")


if __name__ == "__main__":
    main()
