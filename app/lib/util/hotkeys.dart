/// Maps Flutter key events to the legacy hotkey notation.
///
/// The backend (`parse_hotkey_id`, ported from `resource_hub.pyw:224`) accepts
/// `"Ctrl + Alt + Space"`-style labels with a fixed key-name vocabulary, so the
/// recorder in the settings dialog must produce exactly those names. Keeping the
/// mapping here (instead of in the dialog) keeps it unit-testable.
library;

import 'package:flutter/services.dart';

/// Modifier labels in the same order the backend formats them.
List<String> hotkeyModifiers() {
  final HardwareKeyboard keyboard = HardwareKeyboard.instance;
  return <String>[
    if (keyboard.isControlPressed) 'Ctrl',
    if (keyboard.isAltPressed) 'Alt',
    if (keyboard.isShiftPressed) 'Shift',
    if (keyboard.isMetaPressed) 'Win',
  ];
}

/// The legacy key name for [key], or null when the key cannot be part of a
/// hotkey (a bare modifier, an IME key, a media key, …).
String? hotkeyKeyName(LogicalKeyboardKey key) {
  // Not const: LogicalKeyboardKey overrides `==`/`hashCode`, which const maps
  // reject.
  final Map<LogicalKeyboardKey, String> special = <LogicalKeyboardKey, String>{
    LogicalKeyboardKey.space: 'Space',
    LogicalKeyboardKey.tab: 'Tab',
    LogicalKeyboardKey.enter: 'Enter',
    LogicalKeyboardKey.numpadEnter: 'Enter',
    LogicalKeyboardKey.escape: 'Esc',
    LogicalKeyboardKey.backspace: 'Backspace',
    LogicalKeyboardKey.delete: 'Delete',
    LogicalKeyboardKey.insert: 'Insert',
    LogicalKeyboardKey.home: 'Home',
    LogicalKeyboardKey.end: 'End',
    LogicalKeyboardKey.pageUp: 'PageUp',
    LogicalKeyboardKey.pageDown: 'PageDown',
    LogicalKeyboardKey.arrowLeft: 'Left',
    LogicalKeyboardKey.arrowUp: 'Up',
    LogicalKeyboardKey.arrowRight: 'Right',
    LogicalKeyboardKey.arrowDown: 'Down',
    LogicalKeyboardKey.minus: 'Minus',
    LogicalKeyboardKey.equal: 'Equals',
    LogicalKeyboardKey.comma: 'Comma',
    LogicalKeyboardKey.period: 'Period',
    LogicalKeyboardKey.slash: 'Slash',
    LogicalKeyboardKey.semicolon: 'Semicolon',
    LogicalKeyboardKey.quote: 'Apostrophe',
    LogicalKeyboardKey.bracketLeft: 'LeftBracket',
    LogicalKeyboardKey.bracketRight: 'RightBracket',
    LogicalKeyboardKey.backslash: 'Backslash',
    LogicalKeyboardKey.backquote: 'Backtick',
  };
  final String? name = special[key];
  if (name != null) {
    return name;
  }

  final String label = key.keyLabel;
  if (RegExp(r'^F([1-9]|1[0-9]|2[0-4])$').hasMatch(label)) {
    return label;
  }
  final String upper = label.toUpperCase();
  if (RegExp(r'^[A-Z0-9]$').hasMatch(upper)) {
    return upper;
  }
  return null;
}

/// Formats a combination the way the backend stores it.
String formatHotkey(List<String> modifiers, String keyName) =>
    <String>[...modifiers, keyName].join(' + ');
