/// Button layer.
///
/// Replaces the legacy `RoundedButton` (a `tk.Canvas` subclass that rendered
/// per-state rounded bitmaps via Pillow, `resource_hub.pyw:711`). Material 3
/// supplies the state layers; these wrappers only fix the desktop sizing and the
/// semantic variants the app actually uses.
library;

import 'package:flutter/material.dart';

import '../design/app_theme.dart';
import '../design/app_tokens.dart';

/// Visual weight of an [AppButton].
enum AppButtonVariant {
  /// Single primary action on a surface (e.g. "保存").
  primary,

  /// Secondary action (e.g. "设置", "清空表单").
  secondary,

  /// Low-emphasis inline action (e.g. "浏览").
  ghost,

  /// Destructive action (e.g. "删除").
  danger,
}

class AppButton extends StatelessWidget {
  const AppButton({
    super.key,
    required this.label,
    this.onPressed,
    this.icon,
    this.variant = AppButtonVariant.primary,
    this.compact = false,
    this.expand = false,
    this.tooltip,
  });

  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;
  final AppButtonVariant variant;

  /// 32px tall instead of 40px — for toolbars and dense forms.
  final bool compact;

  /// Stretch to the parent's width (used by the form's save button).
  final bool expand;

  final String? tooltip;

  @override
  Widget build(BuildContext context) {
    final AppSemanticColors semantic = context.semantic;
    final Size minSize = Size(
      0,
      compact ? AppSizes.controlHeightCompact : AppSizes.controlHeight,
    );
    final double iconSize = compact ? AppSizes.iconSm : 18;

    ButtonStyle base = ButtonStyle(
      minimumSize: WidgetStatePropertyAll<Size>(minSize),
    );

    Widget child;
    switch (variant) {
      case AppButtonVariant.primary:
        child = icon == null
            ? FilledButton(
                onPressed: onPressed,
                style: base,
                child: Text(label),
              )
            : FilledButton.icon(
                onPressed: onPressed,
                style: base,
                icon: Icon(icon, size: iconSize),
                label: Text(label),
              );
      case AppButtonVariant.secondary:
        child = icon == null
            ? OutlinedButton(
                onPressed: onPressed,
                style: base,
                child: Text(label),
              )
            : OutlinedButton.icon(
                onPressed: onPressed,
                style: base,
                icon: Icon(icon, size: iconSize),
                label: Text(label),
              );
      case AppButtonVariant.ghost:
        child = icon == null
            ? TextButton(onPressed: onPressed, style: base, child: Text(label))
            : TextButton.icon(
                onPressed: onPressed,
                style: base,
                icon: Icon(icon, size: iconSize),
                label: Text(label),
              );
      case AppButtonVariant.danger:
        child = FilledButton.icon(
          onPressed: onPressed,
          style: base.merge(
            ButtonStyle(
              backgroundColor: WidgetStateProperty.resolveWith<Color?>(
                (Set<WidgetState> states) => states.contains(WidgetState.disabled)
                    ? semantic.danger.withValues(alpha: 0.4)
                    : semantic.danger,
              ),
              foregroundColor: const WidgetStatePropertyAll<Color>(
                Color(0xFFFFFFFF),
              ),
            ),
          ),
          icon: Icon(icon ?? Icons.delete_outline, size: iconSize),
          label: Text(label),
        );
    }

    if (expand) {
      child = SizedBox(width: double.infinity, child: child);
    }
    if (tooltip != null) {
      child = Tooltip(message: tooltip!, child: child);
    }
    return child;
  }
}

/// Square icon button used in list toolbars.
///
/// [selected] renders the tonal "active" state — this is how "只看收藏" shows
/// whether the filter is on.
class ToolbarButton extends StatelessWidget {
  const ToolbarButton({
    super.key,
    required this.icon,
    required this.tooltip,
    this.onPressed,
    this.selected = false,
    this.tone,
  });

  final IconData icon;
  final String tooltip;
  final VoidCallback? onPressed;
  final bool selected;

  /// Overrides the icon colour (e.g. favourite star, danger delete).
  final Color? tone;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final bool enabled = onPressed != null;
    final Color foreground = !enabled
        ? scheme.onSurface.withValues(alpha: 0.3)
        : selected
            ? scheme.onPrimaryContainer
            : (tone ?? scheme.onSurfaceVariant);

    return Tooltip(
      message: tooltip,
      child: Material(
        color: selected ? scheme.primaryContainer : Colors.transparent,
        borderRadius: AppRadius.smAll,
        child: InkWell(
          onTap: onPressed,
          borderRadius: AppRadius.smAll,
          hoverColor: scheme.primary.withValues(alpha: 0.08),
          child: SizedBox(
            width: 34,
            height: 34,
            child: Icon(icon, size: AppSizes.iconMd, color: foreground),
          ),
        ),
      ),
    );
  }
}
