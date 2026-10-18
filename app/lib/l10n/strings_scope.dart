/// Ambient access to the active language and translation table.
library;

import 'package:flutter/widgets.dart';

import 'strings.g.dart';

export 'strings.g.dart';

/// Exposes [AppStrings] and a setter so any widget can switch language without
/// plumbing callbacks through the tree.
class AppStringsScope extends InheritedWidget {
  const AppStringsScope({
    super.key,
    required this.strings,
    required this.onLanguageChanged,
    required super.child,
  });

  final AppStrings strings;
  final ValueChanged<AppLanguage> onLanguageChanged;

  static AppStrings of(BuildContext context) {
    final AppStringsScope? scope =
        context.dependOnInheritedWidgetOfExactType<AppStringsScope>();
    assert(scope != null, 'AppStringsScope missing above this widget');
    return scope!.strings;
  }

  static ValueChanged<AppLanguage> languageSetterOf(BuildContext context) {
    final AppStringsScope? scope =
        context.dependOnInheritedWidgetOfExactType<AppStringsScope>();
    assert(scope != null, 'AppStringsScope missing above this widget');
    return scope!.onLanguageChanged;
  }

  @override
  bool updateShouldNotify(AppStringsScope oldWidget) =>
      oldWidget.strings.language != strings.language;
}

/// Shorthand: `context.l10n.t('save_link')`.
extension AppStringsContext on BuildContext {
  AppStrings get l10n => AppStringsScope.of(this);
}
