/// Persistent bottom bar and empty-state placeholder.
library;

import 'package:flutter/material.dart';

import '../design/app_theme.dart';
import '../design/app_tokens.dart';

/// Tone of a status message. Mirrors the legacy `set_status(..., error=True)`
/// split between neutral and error output.
enum StatusTone { info, success, warning, error }

/// Bottom status strip, mirroring the legacy `status_label` (`resource_hub.pyw:2334`).
class AppStatusBar extends StatelessWidget {
  const AppStatusBar({
    super.key,
    required this.message,
    this.tone = StatusTone.info,
    this.trailing,
  });

  final String message;
  final StatusTone tone;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final AppSemanticColors semantic = context.semantic;

    final (IconData icon, Color color) = switch (tone) {
      StatusTone.info => (Icons.info_outline, scheme.onSurfaceVariant),
      StatusTone.success => (Icons.check_circle_outline, semantic.success),
      StatusTone.warning => (Icons.warning_amber_outlined, semantic.warning),
      StatusTone.error => (Icons.error_outline, semantic.danger),
    };

    return Container(
      height: AppSizes.statusBarHeight,
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl),
      decoration: BoxDecoration(
        // Same neutral surface as the body; the hairline divider marks the edge.
        color: scheme.surface,
        border: Border(top: BorderSide(color: scheme.outlineVariant)),
      ),
      child: Row(
        children: <Widget>[
          Icon(icon, size: 14, color: color),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              message,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: tone == StatusTone.error
                        ? semantic.danger
                        : scheme.onSurfaceVariant,
                  ),
            ),
          ),
          ?trailing,
        ],
      ),
    );
  }
}

/// Centred placeholder for an empty list.
///
/// Legacy rendered a bare `empty_label` over the Treeview; this adds the icon and
/// a secondary hint so the state is not mistaken for a loading state.
class AppEmptyState extends StatelessWidget {
  const AppEmptyState({
    super.key,
    required this.title,
    this.hint,
    this.icon = Icons.inbox_outlined,
    this.action,
  });

  final String title;
  final String? hint;
  final IconData icon;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final TextTheme text = Theme.of(context).textTheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Container(
              width: 52,
              height: 52,
              decoration: BoxDecoration(
                color: scheme.surfaceContainerHigh,
                borderRadius: AppRadius.lgAll,
              ),
              child: Icon(icon, size: 24, color: scheme.onSurfaceVariant),
            ),
            const SizedBox(height: AppSpacing.md),
            Text(
              title,
              textAlign: TextAlign.center,
              style: text.bodyMedium?.copyWith(
                color: scheme.onSurfaceVariant,
                fontWeight: FontWeight.w500,
              ),
            ),
            if (hint != null) ...<Widget>[
              const SizedBox(height: AppSpacing.xs),
              Text(
                hint!,
                textAlign: TextAlign.center,
                style: text.bodySmall?.copyWith(
                  color: scheme.onSurfaceVariant.withValues(alpha: 0.75),
                ),
              ),
            ],
            if (action != null) ...<Widget>[
              const SizedBox(height: AppSpacing.lg),
              action!,
            ],
          ],
        ),
      ),
    );
  }
}
