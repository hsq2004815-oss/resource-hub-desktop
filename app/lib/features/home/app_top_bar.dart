/// Compact application bar (Material 3 top app bar) shown below the native
/// Windows title bar.
///
/// Deliberately minimal: app icon, short title, settings. Counts, mode switch,
/// search and view controls live in the workspace header so the app bar never
/// eats vertical space from the resource list.
library;

import 'package:flutter/material.dart';

import '../../design/app_tokens.dart';
import '../../l10n/strings_scope.dart';

class AppTopBar extends StatelessWidget {
  const AppTopBar({super.key, required this.onOpenSettings});

  final VoidCallback onOpenSettings;

  /// Kept in one place so tests and screenshots can assert the compact height.
  static const double height = 56;

  @override
  Widget build(BuildContext context) {
    final AppStrings t = context.l10n;
    final ColorScheme scheme = Theme.of(context).colorScheme;
    final TextTheme text = Theme.of(context).textTheme;

    return Container(
      height: height,
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xl),
      decoration: BoxDecoration(
        // Same neutral surface as the body: hierarchy comes from the hairline
        // divider, not from a tinted band.
        color: scheme.surface,
        border: Border(bottom: BorderSide(color: scheme.outlineVariant)),
      ),
      child: Row(
        children: <Widget>[
          Container(
            width: 28,
            height: 28,
            decoration: BoxDecoration(
              color: scheme.primary,
              borderRadius: BorderRadius.circular(AppRadius.sm),
            ),
            child: const Icon(
              Icons.dashboard_customize_outlined,
              color: Colors.white,
              size: 16,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          Text(
            t.t('window_title'),
            style: text.titleSmall?.copyWith(
              fontWeight: FontWeight.w600,
              color: scheme.onSurface,
            ),
          ),
          const Spacer(),
          IconButton(
            tooltip: t.t('settings_button'),
            visualDensity: VisualDensity.compact,
            icon: const Icon(Icons.settings_outlined, size: AppSizes.iconMd),
            color: scheme.onSurfaceVariant,
            onPressed: onOpenSettings,
          ),
        ],
      ),
    );
  }
}
