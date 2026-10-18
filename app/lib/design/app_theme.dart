/// Material 3 theme assembly for Resource Hub.
///
/// One entry point — [AppTheme.light] / [AppTheme.dark] — so every surface in the
/// app derives from the same [ColorScheme] and [AppSemanticColors].
library;

import 'package:flutter/material.dart';

import 'app_tokens.dart';

/// Colours that Material's [ColorScheme] does not model but this app needs:
/// path health, favourite markers, and the destructive action tone.
@immutable
class AppSemanticColors extends ThemeExtension<AppSemanticColors> {
  const AppSemanticColors({
    required this.success,
    required this.successContainer,
    required this.warning,
    required this.warningContainer,
    required this.danger,
    required this.dangerContainer,
    required this.favorite,
    required this.missingRowTint,
  });

  /// Healthy path / successful operation.
  final Color success;
  final Color successContainer;

  /// Degraded state, e.g. a category that no longer matches anything.
  final Color warning;
  final Color warningContainer;

  /// Destructive action and invalid input.
  final Color danger;
  final Color dangerContainer;

  /// Favourite star.
  final Color favorite;

  /// Row background for entries whose path no longer exists (legacy `missing` tag).
  final Color missingRowTint;

  static const AppSemanticColors light = AppSemanticColors(
    success: AppColors.successLight,
    successContainer: AppColors.successContainerLight,
    warning: AppColors.warningLight,
    warningContainer: AppColors.warningContainerLight,
    danger: AppColors.dangerLight,
    dangerContainer: AppColors.dangerContainerLight,
    favorite: AppColors.favoriteLight,
    missingRowTint: Color(0x14C14943),
  );

  static const AppSemanticColors dark = AppSemanticColors(
    success: AppColors.successDark,
    successContainer: AppColors.successContainerDark,
    warning: AppColors.warningDark,
    warningContainer: AppColors.warningContainerDark,
    danger: AppColors.dangerDark,
    dangerContainer: AppColors.dangerContainerDark,
    favorite: AppColors.favoriteDark,
    missingRowTint: Color(0x24F08D88),
  );

  @override
  AppSemanticColors copyWith({
    Color? success,
    Color? successContainer,
    Color? warning,
    Color? warningContainer,
    Color? danger,
    Color? dangerContainer,
    Color? favorite,
    Color? missingRowTint,
  }) {
    return AppSemanticColors(
      success: success ?? this.success,
      successContainer: successContainer ?? this.successContainer,
      warning: warning ?? this.warning,
      warningContainer: warningContainer ?? this.warningContainer,
      danger: danger ?? this.danger,
      dangerContainer: dangerContainer ?? this.dangerContainer,
      favorite: favorite ?? this.favorite,
      missingRowTint: missingRowTint ?? this.missingRowTint,
    );
  }

  @override
  AppSemanticColors lerp(ThemeExtension<AppSemanticColors>? other, double t) {
    if (other is! AppSemanticColors) {
      return this;
    }
    return AppSemanticColors(
      success: Color.lerp(success, other.success, t)!,
      successContainer:
          Color.lerp(successContainer, other.successContainer, t)!,
      warning: Color.lerp(warning, other.warning, t)!,
      warningContainer:
          Color.lerp(warningContainer, other.warningContainer, t)!,
      danger: Color.lerp(danger, other.danger, t)!,
      dangerContainer: Color.lerp(dangerContainer, other.dangerContainer, t)!,
      favorite: Color.lerp(favorite, other.favorite, t)!,
      missingRowTint: Color.lerp(missingRowTint, other.missingRowTint, t)!,
    );
  }
}

/// Convenience accessor so widgets can write `context.semantic.success`.
extension AppThemeContext on BuildContext {
  AppSemanticColors get semantic =>
      Theme.of(this).extension<AppSemanticColors>() ?? AppSemanticColors.light;
}

abstract final class AppTheme {
  static ThemeData get light => _build(Brightness.light);
  static ThemeData get dark => _build(Brightness.dark);

  static ThemeData _build(Brightness brightness) {
    final bool isLight = brightness == Brightness.light;
    final ColorScheme scheme = _scheme(brightness);
    final AppSemanticColors semantic =
        isLight ? AppSemanticColors.light : AppSemanticColors.dark;

    final TextTheme textTheme = _textTheme(scheme);

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      textTheme: textTheme,
      fontFamily: AppTypography.fontFamily,
      fontFamilyFallback: AppTypography.fontFamilyFallback,
      scaffoldBackgroundColor: scheme.surface,
      // Desktop density: the legacy Tk UI was tight, not touch-sized.
      visualDensity: VisualDensity.compact,
      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
      splashFactory: InkSparkle.splashFactory,
      extensions: <ThemeExtension<dynamic>>[semantic],
      dividerTheme: DividerThemeData(
        color: scheme.outlineVariant,
        thickness: 1,
        space: 1,
      ),
      scrollbarTheme: ScrollbarThemeData(
        thumbVisibility: const WidgetStatePropertyAll<bool>(true),
        thickness: const WidgetStatePropertyAll<double>(8),
        radius: const Radius.circular(AppRadius.pill),
        thumbColor: WidgetStateProperty.resolveWith<Color?>(
          (Set<WidgetState> states) => states.contains(WidgetState.hovered)
              ? scheme.onSurfaceVariant.withValues(alpha: 0.55)
              : scheme.onSurfaceVariant.withValues(alpha: 0.32),
        ),
      ),
      tooltipTheme: TooltipThemeData(
        waitDuration: const Duration(milliseconds: 500),
        textStyle: TextStyle(
          fontSize: 12,
          color: scheme.onInverseSurface,
          fontFamily: AppTypography.fontFamily,
        ),
        decoration: BoxDecoration(
          color: scheme.inverseSurface,
          borderRadius: AppRadius.smAll,
        ),
      ),
      inputDecorationTheme: _inputTheme(scheme),
      filledButtonTheme: FilledButtonThemeData(style: _filledStyle(scheme)),
      outlinedButtonTheme: OutlinedButtonThemeData(style: _outlinedStyle(scheme)),
      textButtonTheme: TextButtonThemeData(style: _textStyle(scheme)),
      chipTheme: ChipThemeData(
        labelStyle: textTheme.labelMedium,
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.sm,
          vertical: AppSpacing.xxs,
        ),
        side: BorderSide(color: scheme.outlineVariant),
        shape: const RoundedRectangleBorder(borderRadius: AppRadius.smAll),
        backgroundColor: scheme.surfaceContainerLowest,
      ),
      segmentedButtonTheme: SegmentedButtonThemeData(
        style: ButtonStyle(
          visualDensity: VisualDensity.compact,
          textStyle: WidgetStatePropertyAll<TextStyle?>(textTheme.labelLarge),
          shape: const WidgetStatePropertyAll<OutlinedBorder>(
            RoundedRectangleBorder(borderRadius: AppRadius.smAll),
          ),
        ),
      ),
      popupMenuTheme: PopupMenuThemeData(
        color: scheme.surfaceContainerLowest,
        shape: const RoundedRectangleBorder(borderRadius: AppRadius.mdAll),
        textStyle: textTheme.bodyMedium,
        elevation: 3,
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        backgroundColor: scheme.inverseSurface,
        contentTextStyle: textTheme.bodyMedium?.copyWith(
          color: scheme.onInverseSurface,
        ),
        shape: const RoundedRectangleBorder(borderRadius: AppRadius.smAll),
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: scheme.surfaceContainerLowest,
        shape: const RoundedRectangleBorder(borderRadius: AppRadius.xlAll),
        titleTextStyle: textTheme.titleLarge,
        contentTextStyle: textTheme.bodyMedium,
      ),
    );
  }

  /// Light mode pins the legacy palette for visual continuity; dark mode is
  /// derived from the seed so it stays perceptually balanced.
  static ColorScheme _scheme(Brightness brightness) {
    final ColorScheme base = ColorScheme.fromSeed(
      seedColor: AppColors.seed,
      brightness: brightness,
    );
    if (brightness == Brightness.dark) {
      return base.copyWith(
        primary: const Color(0xFF9FBBFF),
        onPrimary: const Color(0xFF002A6B),
        primaryContainer: const Color(0xFF1B3E7D),
        onPrimaryContainer: const Color(0xFFD8E3FF),
        surface: const Color(0xFF12161D),
        surfaceContainerLowest: const Color(0xFF0D1016),
        surfaceContainerLow: const Color(0xFF171C24),
        surfaceContainer: const Color(0xFF1C222B),
        surfaceContainerHigh: const Color(0xFF232A35),
        surfaceContainerHighest: const Color(0xFF2A323E),
        onSurface: const Color(0xFFE4E8F0),
        onSurfaceVariant: const Color(0xFFA6AFBE),
        outlineVariant: const Color(0xFF333C49),
      );
    }
    return base.copyWith(
      primary: AppColors.legacyAccent,
      onPrimary: const Color(0xFFFFFFFF),
      primaryContainer: AppColors.legacyAccentSoft,
      onPrimaryContainer: const Color(0xFF12336E),
      surface: AppColors.legacyBg,
      surfaceContainerLowest: AppColors.legacyPanelStrong,
      surfaceContainerLow: AppColors.legacyPanel,
      surfaceContainer: AppColors.legacyPanelAlt,
      surfaceContainerHigh: AppColors.legacyHero,
      surfaceContainerHighest: const Color(0xFFE3EBF7),
      onSurface: AppColors.legacyInk,
      onSurfaceVariant: AppColors.legacyMuted,
      outline: const Color(0xFF9AA7BA),
      outlineVariant: AppColors.legacyBorder,
      error: AppColors.legacyDanger,
    );
  }

  static TextTheme _textTheme(ColorScheme scheme) {
    // `.black` is the light-theme text theme: its default colours are near-black,
    // which makes headings invisible on a dark surface. Force both colour roles to
    // onSurface so a single source works for both brightnesses.
    final TextTheme base = Typography.material2021(
      platform: TargetPlatform.windows,
      colorScheme: scheme,
    ).black.apply(
      bodyColor: scheme.onSurface,
      displayColor: scheme.onSurface,
    );
    return base.copyWith(
      displaySmall: base.displaySmall?.copyWith(
        fontSize: 26,
        fontWeight: FontWeight.w700,
        letterSpacing: -0.4,
        height: 1.25,
      ),
      headlineSmall: base.headlineSmall?.copyWith(
        fontSize: 20,
        fontWeight: FontWeight.w700,
        height: 1.3,
      ),
      titleLarge: base.titleLarge?.copyWith(
        fontSize: 18,
        fontWeight: FontWeight.w600,
        height: 1.3,
      ),
      titleMedium: base.titleMedium?.copyWith(
        fontSize: 15,
        fontWeight: FontWeight.w600,
        height: 1.35,
      ),
      titleSmall: base.titleSmall?.copyWith(
        fontSize: 13,
        fontWeight: FontWeight.w600,
      ),
      bodyLarge: base.bodyLarge?.copyWith(fontSize: 14, height: 1.45),
      bodyMedium: base.bodyMedium?.copyWith(fontSize: 13, height: 1.45),
      bodySmall: base.bodySmall?.copyWith(fontSize: 12, height: 1.4),
      labelLarge: base.labelLarge?.copyWith(
        fontSize: 13,
        fontWeight: FontWeight.w500,
      ),
      labelMedium: base.labelMedium?.copyWith(
        fontSize: 12,
        fontWeight: FontWeight.w500,
      ),
      labelSmall: base.labelSmall?.copyWith(
        fontSize: 11,
        fontWeight: FontWeight.w500,
        letterSpacing: 0.2,
      ),
    );
  }

  static InputDecorationTheme _inputTheme(ColorScheme scheme) {
    OutlineInputBorder border(Color color) => OutlineInputBorder(
          borderRadius: AppRadius.smAll,
          borderSide: BorderSide(color: color),
        );
    return InputDecorationTheme(
      isDense: true,
      filled: true,
      fillColor: scheme.surfaceContainerLowest,
      contentPadding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.md,
      ),
      border: border(scheme.outlineVariant),
      enabledBorder: border(scheme.outlineVariant),
      focusedBorder: border(scheme.primary).copyWith(
        borderSide: BorderSide(color: scheme.primary, width: 1.6),
      ),
      errorBorder: border(scheme.error),
      focusedErrorBorder: border(scheme.error).copyWith(
        borderSide: BorderSide(color: scheme.error, width: 1.6),
      ),
      hintStyle: TextStyle(
        fontSize: 13,
        color: scheme.onSurfaceVariant.withValues(alpha: 0.7),
      ),
      labelStyle: TextStyle(fontSize: 13, color: scheme.onSurfaceVariant),
      floatingLabelStyle: TextStyle(fontSize: 12.5, color: scheme.primary),
    );
  }

  static ButtonStyle _filledStyle(ColorScheme scheme) {
    // Material 3 filled button: 40px tall, fully rounded (stadium), 20px side
    // padding, 18px icon, 14px medium label. The previous 13px + 8px radius +
    // compact density made the Chinese label look cramped and slightly blurry
    // white-on-blue, especially at 125% Windows scaling.
    return ButtonStyle(
      minimumSize: const WidgetStatePropertyAll<Size>(
        Size(64, AppSizes.controlHeight),
      ),
      padding: const WidgetStatePropertyAll<EdgeInsetsGeometry>(
        EdgeInsets.symmetric(horizontal: AppSpacing.xl),
      ),
      iconSize: const WidgetStatePropertyAll<double>(18),
      visualDensity: VisualDensity.standard,
      shape: const WidgetStatePropertyAll<OutlinedBorder>(StadiumBorder()),
      textStyle: WidgetStatePropertyAll<TextStyle?>(
        const TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w600,
          height: 1.2,
          letterSpacing: 0.1,
        ),
      ),
    );
  }

  static ButtonStyle _outlinedStyle(ColorScheme scheme) {
    return ButtonStyle(
      minimumSize: const WidgetStatePropertyAll<Size>(
        Size(0, AppSizes.controlHeightCompact),
      ),
      padding: const WidgetStatePropertyAll<EdgeInsetsGeometry>(
        EdgeInsets.symmetric(horizontal: AppSpacing.md),
      ),
      side: WidgetStatePropertyAll<BorderSide>(
        BorderSide(color: scheme.outlineVariant),
      ),
      shape: const WidgetStatePropertyAll<OutlinedBorder>(
        RoundedRectangleBorder(borderRadius: AppRadius.smAll),
      ),
      textStyle: WidgetStatePropertyAll<TextStyle?>(
        TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
      ),
    );
  }

  static ButtonStyle _textStyle(ColorScheme scheme) {
    return ButtonStyle(
      minimumSize: const WidgetStatePropertyAll<Size>(
        Size(0, AppSizes.controlHeightCompact),
      ),
      padding: const WidgetStatePropertyAll<EdgeInsetsGeometry>(
        EdgeInsets.symmetric(horizontal: AppSpacing.sm),
      ),
      shape: const WidgetStatePropertyAll<OutlinedBorder>(
        RoundedRectangleBorder(borderRadius: AppRadius.smAll),
      ),
      textStyle: WidgetStatePropertyAll<TextStyle?>(
        TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
      ),
    );
  }
}
