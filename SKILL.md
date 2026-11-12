---
name: android-i18n
description: >-
  Use when extracting hardcoded strings from any Android project, migrating UI text
  to strings.xml resources, externalizing non-translatable app IDs, or localizing
  Jetpack Compose, Android Views, Kotlin, Java, and XML layouts.
---

# Android i18n & String Resource Localization

Universal runbook and toolset to extract hardcoded strings from any Android codebase, filter out technical artifacts, separate non-translatable identifiers into `strings_donottranslate.xml`, generate clean `strings.xml` resources, safely replace call sites across Compose and Views, and deterministically verify resource integrity.

---

## When to Use This Skill

Activate this skill when:
- Localizing an existing Android application (Compose, Views, Java, Kotlin, XML layouts).
- Extracting hardcoded user-facing strings into `res/values/strings.xml`.
- Isolating non-translatable app IDs, AdMob units, and technical keys into `strings_donottranslate.xml`.
- Auditing codebase accuracy to ensure 100% of referenced `R.string.*` keys exist and printf format arguments (`%1$s`) match.

---

## Step 1: User Alignment & Interactive Interview Protocol

Before executing file modifications, the agent must check whether the user requested auto-execution or requires an alignment interview:

### 1. Auto-Execution Bypass
Skip the interview and proceed directly with recommended defaults if:
- The user prompt contains keywords: `auto`, `auto proceed`, `default`, `do it`, `proceed`, or
- The user explicitly supplied specific flags/exclusions in their prompt (e.g. `--ignore-prefixes`, `--all`).

### 2. Interactive Interview (Default when unprompted)
If no auto instruction is present, interview the user using the `ask_question` tool with helpful suggestions:

#### Q1: Execution Mode
- **Option 1**: `(Recommended) Auto-proceed with smart defaults (Universal filtering + strings_donottranslate.xml + full safe replacement)`
- **Option 2**: `Custom configuration (I want to specify what to ignore and customize file names)`

#### Q2: Custom Exclusions & Hardcoded Tokens (if custom chosen)
- **Agent Suggestion**: Filter out technical syntax (`/`, `,`, `<`, `>`, `?`), logs (`Log.*`, `Timber.*`), format specifiers, and syntax prefixes like `@` (mentions) or `#` (channels/tags).
- **Option 1**: `(Recommended) Universal technical filters + '@' (mentions) & '#' (channels/tags)`
- **Option 2**: `Universal technical filters only (do not ignore '@' or '#')`
- **Option 3**: `Specify custom prefixes or domain keywords`

#### Q3: Non-Translatable Resource Destination
- **Agent Suggestion**: Use a separate `strings_donottranslate.xml` file so external translation services/tools never accidentally translate internal constants or app IDs.
- **Option 1**: `(Recommended) strings_donottranslate.xml (Dedicated file for app IDs & constants)`
- **Option 2**: `strings.xml (Single file with translatable="false" attribute)`
- **Option 3**: `Custom XML file name (e.g. strings_constants.xml)`

---

## Architecture & Principles

1. **Zero Project-Specific Coupling**:
   - Discovers application package namespace dynamically from `build.gradle(.kts)` or `AndroidManifest.xml` for R imports (`import <namespace>.R`).
   - Does not assume specific app names or third-party brand names.
2. **Multi-Framework Coverage**:
   - **Jetpack Compose (Kotlin)**: Replaces with `stringResource(R.string.<key>, ...)` in `@Composable` contexts and `context.getString(R.string.<key>, ...)` in Toast / callbacks. Prevents invalid composable invocations in non-composable scopes.
   - **Traditional Android Views (Java & Kotlin)**: Replaces `setText("...")` with `setText(R.string.<key>)` and Activity/Fragment `getString(R.string.<key>)`.
   - **Android Layout & Menu XML**: Replaces `android:text="..."`, `android:hint="..."`, `android:title="..."` with `@string/<key>`.
3. **Smart Heuristic Filtration**:
   - Excludes punctuation/delimiters (`/`, `,`, `<`, `>`, `?`, `:`, `;`, `|`, `*`, `~~`), URLs, regex, file extensions, MIME types, SQL, date formats, and PascalCase class names.
   - Automatically skips logging statements (`Log.*`, `Timber.*`, `println`).
   - Configurable ignore prefixes (e.g. `--ignore-prefixes "@,#"`) to keep mentions or tags hardcoded in code.
   - Strict value deduplication across all resources.
4. **Cache & Git-Ignore Isolation**:
   - Intermediate index and classification reports are stored in `.i18n_cache/`.
   - `.i18n_cache/.gitignore` containing `*` is automatically created on initialization to recursively ignore all intermediate artifacts from Git, unless the user explicitly requests them to be tracked.

---

## Directory Structure

```text
.agents/skills/android-i18n/
├── SKILL.md                               # This guide & interview protocol
├── references/
│   └── android_resource_rules.md          # AAPT2 escaping, format specifiers, plurals, BCP-47 cheatsheet
└── scripts/
    ├── runner.py                          # Unified pipeline orchestrator (CLI & interactive)
    ├── extract_strings.py                 # Lexical string scanner (code & XML)
    ├── filter_and_export_strings.py       # Heuristic classifier & XML generator
    ├── replace_strings.py                 # Safe Composable & View replacer
    └── verify_accuracy.py                 # Deterministic accuracy & arg auditor
```

---

## Execution Procedures

### Option A: One-Command Full Pipeline (Auto Mode)
Run the entire pipeline from project root:
```bash
python3 .agents/skills/android-i18n/scripts/runner.py --all
```
*(Add `--dry-run` to preview changes without modifying files)*

### Option B: Interactive Terminal Mode
Prompts for user interview choices directly in the CLI:
```bash
python3 .agents/skills/android-i18n/scripts/runner.py --interactive
```

### Option C: Step-by-Step Execution

#### Step 2: Extract Strings
Scans Kotlin, Java, and XML layout files, recording strings into an index:
```bash
python3 .agents/skills/android-i18n/scripts/extract_strings.py \
  --src app/src/main \
  --output .i18n_cache/extracted_strings_index.json
```

#### Step 3: Filter and Export XML Resources
Classifies strings, enforces deduplication, and generates XML files:
```bash
python3 .agents/skills/android-i18n/scripts/filter_and_export_strings.py \
  --index .i18n_cache/extracted_strings_index.json \
  --translatable-xml app/src/main/res/values/strings.xml \
  --donottranslate-xml app/src/main/res/values/strings_donottranslate.xml \
  --report .i18n_cache/string_classification_report.json \
  --ignore-prefixes "@,#"
```

#### Step 4: Replace in Sources and Layouts
Replaces hardcoded strings with resource calls and injects necessary imports:
```bash
python3 .agents/skills/android-i18n/scripts/replace_strings.py \
  --report .i18n_cache/string_classification_report.json \
  --target-dir app/src/main
```

#### Step 5: Verify Resource Accuracy & Build
Audits resource existence, format specifier signatures, and verifies compilation:
```bash
python3 .agents/skills/android-i18n/scripts/verify_accuracy.py
./gradlew compileDebugKotlin
```

---

## Verification & Quality Gates

Before declaring localization complete, ensure:
1. `verify_accuracy.py` reports:
   - Missing resource keys: **0**
   - Format argument mismatches: **0**
2. `./gradlew compileDebugKotlin` passes with **0 errors**.
3. `./gradlew processDebugResources` passes with **0 errors**.
