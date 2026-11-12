# Android String Resource Rules & Localization Reference

Comprehensive technical reference for Android resource escaping, positional format specifiers, plurals, HTML styling, and BCP-47 locale naming conventions.

---

## 1. Character Escaping & XML Syntax Rules

Android XML string parsers (`AAPT2`) enforce strict character escaping rules inside `<string>` elements.

| Character           | Escaped Form        | Reason / AAPT2 Rule                                                                               |
|:--------------------|:--------------------|:--------------------------------------------------------------------------------------------------|
| Single quote (`'`)  | `\'` or wrap in `"` | Unescaped single quotes throw compilation errors (e.g., `Can\'t` or `"Can't"`).                   |
| Double quote (`"`)  | `\"`                | Unescaped double quotes terminate string attribute parsing.                                       |
| Ampersand (`&`)     | `&amp;`             | Reserved XML character; bare `&` fails XML validation.                                            |
| Less-than (`<`)     | `&lt;`              | Reserved XML character; indicates tag start.                                                      |
| Greater-than (`>`)  | `&gt;`              | Reserved XML character; indicates tag end.                                                        |
| At symbol (`@`)     | `\@` (at start)     | Leading `@` is parsed as a resource reference (e.g. `@string/foo`). Use `\@` to treat as literal. |
| Question mark (`?`) | `\?` (at start)     | Leading `?` is parsed as a theme attribute (e.g. `?attr/color`). Use `\?` to treat as literal.    |
| Percent (`%`)       | `%%`                | In strings with format specifiers, literal percent signs must be doubled (`%%`).                  |
| Newline / Tab       | `\n` / `\t`         | Raw line breaks in XML are normalized to single spaces unless written as `\n`.                    |

### Leading & Trailing Whitespace
AAPT2 strips leading and trailing whitespace from string resources by default. To preserve spaces, wrap the value in double quotes:
```xml
<!-- Preserves space before 'credits' -->
<string name="credits_label">" 25 credits"</string>
```

---

## 2. Formatting & Positional Arguments

When substituting dynamic values at runtime (`stringResource(R.string.key, arg)` or `getString(R.string.key, arg)`):

### Rule 1: Always Use Positional Indexing for Multiple Arguments
Different languages structure sentences with different word orders. Never use un-indexed `%s` or `%d` more than once:
```xml
<!-- ❌ BAD: Word order cannot be rearranged by translators -->
<string name="file_summary">%s files scanned in %d ms</string>

<!-- ✅ GOOD: Positional specifiers allow translators to flip word order -->
<string name="file_summary">%1$s files scanned in %2$d ms</string>
```

### Rule 2: Non-Formatted Strings with Percent Signs
If a string contains a `%` character but is NOT meant to be used with `String.format()`, add `formatted="false"`:
```xml
<!-- Disables AAPT2 format validation -->
<string name="discount_badge" formatted="false">Save 50% Today!</string>
```

---

## 3. Plurals (`<plurals>`) Syntax

Use `<plurals>` instead of manual `if (count == 1)` branches. Different languages have distinct grammatical plural rules (e.g., Russian has 3 plural forms, Arabic has 6, English has 2).

```xml
<plurals name="credits_count">
    <item quantity="one">%1$d credit</item>
    <item quantity="other">%1$d credits</item>
</plurals>
```

### Runtime Usage:
- **Views**: `resources.getQuantityString(R.plurals.credits_count, count, count)`
- **Jetpack Compose**: `pluralStringResource(R.plurals.credits_count, count, count)`

---

## 4. XLIFF Protected Elements

Use XLIFF (`urn:oasis:names:tc:xliff:document:1.2`) tags inside string resources to prevent automated translation tools and translators from corrupting brand names, technical identifiers, or URLs:

```xml
<resources xmlns:xliff="urn:oasis:names:tc:xliff:document:1.2">
    <string name="send_to_channel">
        Send dispatch to <xliff:g id="channel_name" example="#general">%1$s</xliff:g>
    </string>
</resources>
```

---

## 5. Non-Translatable Resources

To prevent specific strings from ever being translated by Google Play App Translation Services, Crowdin, or automated scripts:

### Method A: Dedicated File (Recommended)
Store constants in `res/values/strings_donottranslate.xml`.
```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <!-- Technical IDs, AdMob IDs, SKU keys -->
    <string name="admob_app_id" translatable="false">ca-app-pub-3940256099942544~3347511713</string>
    <string name="sku_premium_upgrade" translatable="false">premium_upgrade_lifetime</string>
</resources>
```

### Method B: Inline Attribute
Add `translatable="false"` to individual strings in `res/values/strings.xml`:
```xml
<string name="deep_link_scheme" translatable="false">myapp</string>
```

---

## 6. BCP-47 Locale Directory Qualifiers

Resource directories in `res/` use BCP-47 language and region sub-tags:

| Directory               | Language / Region     | Note                                                        |
|:------------------------|:----------------------|:------------------------------------------------------------|
| `res/values/`           | Default / Fallback    | English (base strings)                                      |
| `res/values-pt/`        | Portuguese (Generic)  | Covers all Portuguese dialects                              |
| `res/values-b+pt+BR/`   | Portuguese (Brazil)   | Modern BCP-47 format (equivalent to legacy `values-pt-rBR`) |
| `res/values-hi/`        | Hindi                 |                                                             |
| `res/values-de/`        | German                |                                                             |
| `res/values-ru/`        | Russian               |                                                             |
| `res/values-fr/`        | French                |                                                             |
| `res/values-fil/`       | Filipino / Tagalog    | Android standard uses `fil` rather than `tl`                |
| `res/values-id/`        | Indonesian            |                                                             |
| `res/values-es/`        | Spanish               |                                                             |
| `res/values-ja/`        | Japanese              |                                                             |
| `res/values-b+zh+Hans/` | Chinese (Simplified)  | Simplified Chinese script                                   |
| `res/values-b+zh+Hant/` | Chinese (Traditional) | Traditional Chinese script                                  |

### Gradle Packaging Optimization
To prevent unwanted library locales from bloating APK size, configure locale filters in `app/build.gradle.kts`:
```kotlin
android {
    defaultConfig {
        androidResources {
            localeFilters += listOf("en", "pt", "hi", "de", "ru", "fr", "fil", "id")
        }
    }
}
```
