/// Shared drag handle for the resource table and grid.
///
/// The grip is visual chrome only: each view starts the actual drag
/// (`ReorderableDragStartListener` in the table, a `Draggable` in the grid), so
/// the two views can share the same hover/disabled behaviour and tooltip.
///
/// The handle is hover-only so the collection keeps reading as plain rows/cards,
/// and it stays visible-but-dimmed while reordering is unavailable (for example
/// while a search is active) so the reason is discoverable.
library;

import 'package:flutter/material.dart';

import '../design/app_tokens.dart';
import '../l10n/app_strings_ext.dart';
import '../l10n/strings_scope.dart';

class ReorderGrip extends StatelessWidget {
  const ReorderGrip({
    super.key,
    required this.visible,
    required this.enabled,
    this.disabledHintKey = 'reorder_disabled_search',
    this.compact = false,
  });

  /// Whether the row/card is hovered (or being dragged).
  final bool visible;

  /// Whether reordering is currently allowed at all.
  final bool enabled;

  /// Tooltip key shown while [enabled] is false; the reason differs per view
  /// (an active search here, the grouped quick panel there).
  final String disabledHintKey;

  /// Smaller hit box for a dense list (the quick panel HUD).
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final AppStrings t = context.l10n;
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final Color color = scheme.onSurfaceVariant.withValues(
      alpha: enabled ? 0.7 : 0.28,
    );
    return Tooltip(
      message: enabled ? t.tx('drag_to_reorder') : t.tx(disabledHintKey),
      waitDuration: const Duration(milliseconds: 500),
      child: MouseRegion(
        cursor: enabled ? SystemMouseCursors.grab : SystemMouseCursors.basic,
        child: SizedBox(
          width: compact ? 18 : AppSpacing.xxl,
          height: compact ? 22 : AppSpacing.xxxl,
          child: Center(
            child: AnimatedOpacity(
              opacity: visible || !enabled ? 1 : 0,
              duration: AppDurations.fast,
              child: Icon(
                Icons.drag_indicator,
                size: compact ? 14 : 16,
                color: color,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
