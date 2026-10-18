/// Reading and writing the JSON backup files used by export/import.
///
/// The legacy app wrote `json.dumps(..., ensure_ascii=False, indent=2)` with an
/// explicit UTF-8 encoding; this mirrors that byte-for-byte so a backup file
/// produced by either app can be read by the other. Keeping the file I/O here
/// (rather than inside the shell widget) also makes it unit-testable without a
/// widget binding, which has no real event loop for `dart:io`.
library;

import 'dart:convert';
import 'dart:io';

abstract final class JsonBackup {
  /// Writes [items] as a pretty-printed UTF-8 JSON array.
  static Future<void> write(
    String path,
    List<Map<String, dynamic>> items,
  ) async {
    final String json = const JsonEncoder.withIndent('  ').convert(items);
    await File(path).writeAsString(json, encoding: utf8, flush: true);
  }

  /// Reads a JSON array of objects from [path].
  ///
  /// Throws [FormatException] when the file is not valid JSON or is not an array
  /// of objects; the caller maps that to `import_failed` instead of a stack
  /// trace in the status bar.
  static Future<List<Map<String, dynamic>>> read(String path) async {
    final String raw = await File(path).readAsString(encoding: utf8);
    final Object? decoded = jsonDecode(raw);
    if (decoded is! List) {
      throw const FormatException('expected a JSON array');
    }
    return decoded.map((dynamic entry) {
      if (entry is! Map) {
        throw const FormatException('expected JSON objects');
      }
      return entry.map(
        (dynamic key, dynamic value) =>
            MapEntry<String, dynamic>('$key', value),
      );
    }).toList();
  }
}
