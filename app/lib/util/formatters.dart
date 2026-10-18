/// Small formatting helpers shared by the table and the status bar.
library;

/// Formats `createdAt` the way the legacy `format_added` did
/// (`resource_hub.pyw:1925` stores local ISO8601; the table shows date + time).
///
/// Returns an empty string for null so callers can fall back to a placeholder.
String formatAddedAt(DateTime? value) {
  if (value == null) {
    return '';
  }
  final DateTime local = value.toLocal();
  final String date = '${local.year.toString().padLeft(4, '0')}-'
      '${local.month.toString().padLeft(2, '0')}-'
      '${local.day.toString().padLeft(2, '0')}';
  final String time = '${local.hour.toString().padLeft(2, '0')}:'
      '${local.minute.toString().padLeft(2, '0')}';
  return '$date $time';
}

/// Shortens a long path for display: keeps the drive/root and the tail, and
/// elides the middle. The full value stays available via tooltip.
String shortenPath(String path, {int maxChars = 64}) {
  if (path.length <= maxChars) {
    return path;
  }
  final int head = (maxChars * 0.45).round();
  final int tail = maxChars - head - 1;
  return '${path.substring(0, head)}…${path.substring(path.length - tail)}';
}

/// Human-readable byte size. Used by the folder/file kind column later.
String formatBytes(int bytes) {
  const List<String> units = <String>['B', 'KB', 'MB', 'GB', 'TB'];
  double value = bytes.toDouble();
  int unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit++;
  }
  final String digits = unit == 0 ? value.toStringAsFixed(0) : value.toStringAsFixed(1);
  return '$digits ${units[unit]}';
}
