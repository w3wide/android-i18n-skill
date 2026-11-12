# Android i18n & String Resource Localization Skill

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Android-green.svg)](https://developer.android.com)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://www.python.org/)

A portable, production-grade AI Agent Skill and CLI automation toolkit to extract hardcoded strings from any Android codebase, filter out technical artifacts, separate non-translatable identifiers into `strings_donottranslate.xml`, generate clean `strings.xml` resources, safely replace call sites across Jetpack Compose and Traditional Views, and deterministically verify resource integrity.

---

## 🌟 Features

- **Multi-Framework Coverage**:
  - **Jetpack Compose (Kotlin)**: Replaces strings with `stringResource(R.string.<key>, ...)` in `@Composable` scopes and `context.getString(...)` in non-composable callbacks (e.g. `Toast.makeText`, `remember`, coroutines) to prevent compilation errors.
  - **Traditional Android Views (Java & Kotlin)**: Replaces `setText("...")` with `setText(R.string.<key>)` and Activity/Fragment `getString(R.string.<key>)`.
  - **Android Layout & Menu XML**: Replaces `android:text="..."`, `android:hint="..."`, `android:title="..."` with `@string/<key>`.
- **Dynamic Package & R Resolution**: Discovers application package namespace dynamically from `build.gradle(.kts)` or `AndroidManifest.xml` and injects proper `import <namespace>.R` statements without inline fully-qualified class names.
- **Strict Heuristic Classification**:
  - Automatically skips all logging invocations (`Log.*`, `Timber.*`, `println`).
  - Filters out technical delimiters (`/`, `,`, `<`, `>`, `?`, `:`, `;`, `|`, `*`), URLs, regex, file extensions, MIME types, SQL, date formats, and PascalCase class names.
  - Preserves syntax tokens and mention tags via configurable `--ignore-prefixes` (e.g. `@`, `#`).
- **Clean Separation of Concerns**:
  - Translatable UI text is exported into `res/values/strings.xml` organized by logical sections.
  - Technical constants (SKU IDs, AdMob app IDs, internal schemes) are routed to `res/values/strings_donottranslate.xml`.
- **Zero Duplication Guarantee**: Normalizes XML values before indexing to prevent duplicated resource keys.
- **Deterministic Verification Engine**: Verifies that 100% of referenced keys exist and format argument signatures (`%1$s`, `%2$d`) match call sites.
- **Interactive Step 1 Interview**: Prompts the user before execution to configure ignore rules, keywords, and target file names, or supports auto-bypass.

---

## 📁 Repository Structure

```text
android-i18n-skill/
├── SKILL.md                               # Agent instruction runbook & interview protocol
├── README.md                              # Documentation and usage guide
├── LICENSE                                # Apache-2.0 License
├── references/
│   └── android_resource_rules.md          # AAPT2 escaping, format specifiers, plurals, BCP-47 cheatsheet
└── scripts/
    ├── runner.py                          # Unified pipeline orchestrator (CLI & interactive)
    ├── extract_strings.py                 # Lexical string scanner (code & XML)
    ├── filter_and_export_strings.py       # Heuristic classifier & XML generator
    ├── replace_strings.py                 # Safe Composable & View replacer
    └── verify_accuracy.py                 # Deterministic accuracy & format arg auditor
```

---

## 🚀 Installation & Setup

### Option 1: Install as Antigravity / Agent Skill
Clone directly into your global agent skills directory or project `.agents/skills`:

```bash
# Global Antigravity install
git clone https://github.com/w3wide/android-i18n-skill.git ~/.gemini/skills/android-i18n

# Or project-level install
git clone https://github.com/w3wide/android-i18n-skill.git .agents/skills/android-i18n
```

### Option 2: Standalone CLI
No external Python dependencies required (standard library only).

```bash
git clone https://github.com/w3wide/android-i18n-skill.git
cd android-i18n-skill
```

---

## 🛠️ Usage

### 1. One-Command Full Pipeline (Auto Mode)
Run the entire extraction, classification, replacement, and verification pipeline from your Android project root:

```bash
python3 /path/to/android-i18n-skill/scripts/runner.py --all
```

*Add `--dry-run` to preview all replacements without modifying any files:*
```bash
python3 /path/to/android-i18n-skill/scripts/runner.py --all --dry-run
```

### 2. Interactive Interview Mode
Prompts for user interview choices directly in the terminal before running:

```bash
python3 /path/to/android-i18n-skill/scripts/runner.py --interactive
```

### 3. Step-by-Step Execution

#### Step 1: Extract Strings
Scans source code and layout files into an intermediate index:
```bash
python3 scripts/extract_strings.py \
  --src app/src/main \
  --output .i18n_cache/extracted_strings_index.json
```

#### Step 2: Filter and Export XML Resources
Classifies strings, enforces deduplication, and generates XML files:
```bash
python3 scripts/filter_and_export_strings.py \
  --index .i18n_cache/extracted_strings_index.json \
  --translatable-xml app/src/main/res/values/strings.xml \
  --donottranslate-xml app/src/main/res/values/strings_donottranslate.xml \
  --report .i18n_cache/string_classification_report.json \
  --ignore-prefixes "@,#"
```

#### Step 3: Replace in Sources and Layouts
Replaces hardcoded strings with resource calls and injects necessary imports:
```bash
python3 scripts/replace_strings.py \
  --report .i18n_cache/string_classification_report.json \
  --target-dir app/src/main
```

#### Step 4: Verify Resource Accuracy & Build
Audits resource existence, format specifier signatures, and checks compilation:
```bash
python3 scripts/verify_accuracy.py
./gradlew compileDebugKotlin
```

---

## 🔒 Cache & Git Policy

All intermediate index and classification files are written to `.i18n_cache/`. Upon initialization, the scripts automatically create `.i18n_cache/.gitignore` containing `*` so intermediate artifacts are never staged to Git.

---

## 📄 License

Licensed under the [Apache License, Version 2.0](LICENSE).
Copyright 2026 [w3wide](https://github.com/w3wide).
