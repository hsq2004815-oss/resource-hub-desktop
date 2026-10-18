/// Form controls.
///
/// The legacy form had five inputs (`name_entry`, `path_entry` + browse buttons,
/// `category_entry`, `notes_text`, read-only `added_value`). Each maps to one
/// widget here so Phase 5 can swap the Tk variables for controllers without
/// redesigning the layout.
library;

import 'package:flutter/material.dart';

import '../design/app_theme.dart';
import '../design/app_tokens.dart';

/// Labelled single-line field with an optional leading icon and trailing slot.
class AppTextField extends StatelessWidget {
  const AppTextField({
    super.key,
    required this.controller,
    required this.label,
    this.hint,
    this.prefixIcon,
    this.trailing,
    this.onChanged,
    this.onSubmitted,
    this.enabled = true,
    this.errorText,
    this.autofocus = false,
    this.maxLines = 1,
    this.keyboardType,
  });

  final TextEditingController controller;
  final String label;
  final String? hint;
  final IconData? prefixIcon;

  /// Usually a [ToolbarButton] pair ("选文件夹" / "选文件").
  final Widget? trailing;

  final ValueChanged<String>? onChanged;
  final ValueChanged<String>? onSubmitted;
  final bool enabled;
  final String? errorText;
  final bool autofocus;
  final int maxLines;
  final TextInputType? keyboardType;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(
          label,
          style: Theme.of(context).textTheme.labelMedium?.copyWith(
                color: scheme.onSurfaceVariant,
              ),
        ),
        const SizedBox(height: AppSpacing.xs),
        TextField(
          controller: controller,
          enabled: enabled,
          autofocus: autofocus,
          maxLines: maxLines,
          keyboardType: keyboardType,
          onChanged: onChanged,
          onSubmitted: onSubmitted,
          style: TextStyle(
            fontFamily: AppTypography.fontFamily,
            fontFamilyFallback: AppTypography.fontFamilyFallback,
            fontSize: 13,
            color: scheme.onSurface,
          ),
          decoration: InputDecoration(
            hintText: hint,
            errorText: errorText,
            prefixIcon: prefixIcon == null
                ? null
                : Icon(prefixIcon, size: AppSizes.iconSm),
            prefixIconConstraints: const BoxConstraints(
              minWidth: 34,
              minHeight: 34,
            ),
            suffixIcon: trailing,
            suffixIconConstraints: const BoxConstraints(
              minWidth: 34,
              minHeight: 34,
            ),
          ),
        ),
      ],
    );
  }
}

/// Pill-shaped search field with an inline result count on the right.
class AppSearchField extends StatelessWidget {
  const AppSearchField({
    super.key,
    required this.controller,
    required this.hint,
    this.onChanged,
    this.onClear,
    this.focusNode,
  });

  final TextEditingController controller;
  final String hint;
  final ValueChanged<String>? onChanged;
  final VoidCallback? onClear;

  /// Owned by the shell so a global-hotkey show can focus the search box, the
  /// way the legacy app did (``resource_hub.pyw:1470``).
  final FocusNode? focusNode;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    return ValueListenableBuilder<TextEditingValue>(
      valueListenable: controller,
      builder: (BuildContext context, TextEditingValue value, Widget? _) {
        return TextField(
          controller: controller,
          focusNode: focusNode,
          onChanged: onChanged,
          style: TextStyle(
            fontFamily: AppTypography.fontFamily,
            fontFamilyFallback: AppTypography.fontFamilyFallback,
            fontSize: 13,
            color: scheme.onSurface,
          ),
          decoration: InputDecoration(
            hintText: hint,
            isDense: true,
            contentPadding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.md,
              vertical: AppSpacing.sm + 2,
            ),
            prefixIcon: Icon(
              Icons.search,
              size: 18,
              color: scheme.onSurfaceVariant,
            ),
            prefixIconConstraints: const BoxConstraints(
              minWidth: 38,
              minHeight: 34,
            ),
            suffixIcon: value.text.isEmpty
                ? null
                : IconButton(
                    icon: const Icon(Icons.close, size: 16),
                    splashRadius: 16,
                    tooltip: '',
                    onPressed: () {
                      controller.clear();
                      onChanged?.call('');
                      onClear?.call();
                    },
                  ),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(AppRadius.pill),
              borderSide: BorderSide(color: scheme.outlineVariant),
            ),
            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(AppRadius.pill),
              borderSide: BorderSide(color: scheme.outlineVariant),
            ),
            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(AppRadius.pill),
              borderSide: BorderSide(color: scheme.primary, width: 1.6),
            ),
          ),
        );
      },
    );
  }
}

/// Category picker.
///
/// Legacy used a `ttk.Combobox` seeded from the data; [categories] should be the
/// distinct values currently in the dataset plus [kUncategorized].
class AppCategoryDropdown extends StatelessWidget {
  const AppCategoryDropdown({
    super.key,
    required this.value,
    required this.items,
    required this.onChanged,
    this.label,
    this.leadingIcon = Icons.sell_outlined,
    this.width,
    this.labelBuilder,
  });

  final String value;
  final List<String> items;
  final ValueChanged<String> onChanged;
  final String? label;
  final IconData? leadingIcon;
  final double? width;

  /// Maps a stored value to its display text. Required because the data layer
  /// stores sentinels (`__uncategorized__`, `__all__`) that must never be shown.
  final String Function(String value)? labelBuilder;

  String _label(String value) => labelBuilder?.call(value) ?? value;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final List<String> entries =
        items.contains(value) ? items : <String>[value, ...items];
    return LayoutBuilder(
      builder: (BuildContext context, BoxConstraints constraints) {
        // Fill the available width when no explicit width is given, so the field
        // lines up with the text fields above it in the form.
        final double? effectiveWidth = width ??
            (constraints.hasBoundedWidth ? constraints.maxWidth : null);
        return SizedBox(
          width: effectiveWidth,
          child: DropdownMenu<String>(
            // `width` must be set explicitly: DropdownMenu otherwise shrinks to the
            // intrinsic width of its widest entry, ignoring the tight constraint
            // from the enclosing SizedBox.
            width: effectiveWidth,
        // Re-created when the value changes externally (mode switch, clear form);
        // `initialSelection` alone would not follow the parent.
        key: ValueKey<String>('category-$value'),
        initialSelection: value,
        requestFocusOnTap: false,
        label: label == null ? null : Text(label!),
        leadingIcon: leadingIcon == null
            ? null
            : Icon(leadingIcon, size: AppSizes.iconSm),
        textStyle: TextStyle(
          fontFamily: AppTypography.fontFamily,
          fontFamilyFallback: AppTypography.fontFamilyFallback,
          fontSize: 13,
          color: scheme.onSurface,
        ),
        inputDecorationTheme: InputDecorationTheme(
          isDense: true,
          filled: true,
          fillColor: scheme.surfaceContainerLowest,
          contentPadding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: AppSpacing.sm + 2,
          ),
          border: OutlineInputBorder(
            borderRadius: AppRadius.smAll,
            borderSide: BorderSide(color: scheme.outlineVariant),
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: AppRadius.smAll,
            borderSide: BorderSide(color: scheme.outlineVariant),
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: AppRadius.smAll,
            borderSide: BorderSide(color: scheme.primary, width: 1.6),
          ),
        ),
        menuStyle: MenuStyle(
          backgroundColor: WidgetStatePropertyAll<Color>(
            scheme.surfaceContainerLowest,
          ),
          shape: const WidgetStatePropertyAll<OutlinedBorder>(
            RoundedRectangleBorder(borderRadius: AppRadius.smAll),
          ),
        ),
        onSelected: (String? selected) {
          if (selected != null) {
            onChanged(selected);
          }
        },
        dropdownMenuEntries: entries
            .map(
              (String entry) => DropdownMenuEntry<String>(
                value: entry,
                label: _label(entry),
              ),
            )
            .toList(),
          ),
        );
      },
    );
  }
}

/// Read-only "added at" display, mirroring the legacy `added_value` label.
class AppReadonlyValue extends StatelessWidget {
  const AppReadonlyValue({
    super.key,
    required this.label,
    required this.value,
    this.icon = Icons.schedule,
  });

  final String label;
  final String value;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final TextTheme text = Theme.of(context).textTheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(
          label,
          style: text.labelMedium?.copyWith(color: scheme.onSurfaceVariant),
        ),
        const SizedBox(height: AppSpacing.xs),
        Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: AppSpacing.sm + 2,
          ),
          decoration: BoxDecoration(
            color: scheme.surfaceContainer,
            borderRadius: AppRadius.smAll,
            border: Border.all(color: scheme.outlineVariant),
          ),
          child: Row(
            children: <Widget>[
              Icon(icon, size: 14, color: scheme.onSurfaceVariant),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Text(
                  value,
                  style: text.bodySmall?.copyWith(
                    color: scheme.onSurfaceVariant,
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// Hint block shown under the form (legacy `data_note` label).
class AppNoteBanner extends StatelessWidget {
  const AppNoteBanner({super.key, required this.text, this.tone});

  final String text;
  final Color? tone;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final AppSemanticColors semantic = context.semantic;
    final Color color = tone ?? scheme.primary;
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: tone == null
            ? scheme.surfaceContainer
            : color.withValues(alpha: 0.08),
        borderRadius: AppRadius.smAll,
        border: Border.all(
          color: tone == null
              ? scheme.outlineVariant
              : color.withValues(alpha: 0.35),
        ),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Icon(
            tone == semantic.danger
                ? Icons.error_outline
                : Icons.info_outline,
            size: 15,
            color: color,
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              text,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: scheme.onSurfaceVariant,
                    height: 1.5,
                  ),
            ),
          ),
        ],
      ),
    );
  }
}
