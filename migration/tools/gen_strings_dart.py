"""Generate app/lib/l10n/strings.g.dart from the STRINGS dict in resource_hub.pyw.

Single source of truth is the Python app: this keeps key parity and wording
identical between the legacy Tkinter UI and the Flutter UI, so Phase 5 can
compare screens side by side without hunting for typos.

    D:\\miniconda3\\python.exe migration/tools/gen_strings_dart.py
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "resource_hub.pyw"
TARGET = REPO_ROOT / "app" / "lib" / "l10n" / "strings.g.dart"

HEADER = """// GENERATED FILE — DO NOT EDIT BY HAND.
// Source: resource_hub.pyw  STRINGS dict
// Regenerate: D:\\miniconda3\\python.exe migration/tools/gen_strings_dart.py
//
// Key parity with the legacy Tkinter app is intentional: Phase 5 can diff the
// two UIs label by label. Placeholders use Python's `{0}` / `{1}` syntax and are
// substituted by [AppStrings.t].

/// Language codes supported by the app. Mirrors `settings.json` -> `language`.
enum AppLanguage {
  zh('zh'),
  en('en');

  const AppLanguage(this.code);

  final String code;

  static AppLanguage fromCode(String? code) {
    for (final AppLanguage value in AppLanguage.values) {
      if (value.code == code) {
        return value;
      }
    }
    return AppLanguage.zh;
  }
}

/// Flat translation table: `language code -> key -> text`.
const Map<String, Map<String, String>> kTranslations = <String, Map<String, String>>{
"""

FOOTER = """};

/// Looks up translations for the active language.
///
/// Missing keys fall back to the Chinese text, then to the key itself — the same
/// behaviour as `ResourceHubApp.t()` in `resource_hub.pyw:974`.
class AppStrings {
  const AppStrings(this.language);

  final AppLanguage language;

  String t(String key, [List<Object?> args = const <Object?>[]]) {
    final String? raw =
        kTranslations[language.code]?[key] ?? kTranslations['zh']?[key];
    final String text = raw ?? key;
    if (args.isEmpty) {
      return text;
    }
    String out = text;
    for (int i = 0; i < args.length; i++) {
      out = out.replaceAll('{$i}', '${args[i] ?? ''}');
    }
    return out;
  }
}
"""


def extract_strings() -> dict[str, dict[str, str]]:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"), filename=str(SOURCE))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "STRINGS"
        ):
            return ast.literal_eval(node.value)
    raise SystemExit("STRINGS assignment not found in resource_hub.pyw")


def dart_string(value: str) -> str:
    """Emit a Dart single-quoted literal; $ must be escaped, ' too."""
    escaped = value.replace("\\", "\\\\").replace("'", "\\'").replace("$", "\\$")
    escaped = escaped.replace("\n", "\\n").replace("\r", "")
    return f"'{escaped}'"


def main() -> int:
    strings = extract_strings()
    languages = list(strings.keys())
    zh_keys = set(strings.get("zh", {}))
    en_keys = set(strings.get("en", {}))
    only_zh = sorted(zh_keys - en_keys)
    only_en = sorted(en_keys - zh_keys)

    lines: list[str] = [HEADER.rstrip("\n")]
    for language in languages:
        lines.append(f"  '{language}': <String, String>{{")
        for key, value in strings[language].items():
            lines.append(f"    {dart_string(key)}: {dart_string(value)},")
        lines.append("  },")
    lines.append(FOOTER)

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text("\n".join(lines), encoding="utf-8")

    print(
        json.dumps(
            {
                "target": str(TARGET),
                "languages": languages,
                "keys": {lang: len(strings[lang]) for lang in languages},
                "keys_only_in_zh": only_zh,
                "keys_only_in_en": only_en,
                "bytes": TARGET.stat().st_size,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
