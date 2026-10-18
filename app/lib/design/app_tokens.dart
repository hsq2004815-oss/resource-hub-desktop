/// Design tokens for Resource Hub.
///
/// Every visual constant the UI is allowed to use lives here. Nothing in
/// `widgets/` or `features/` should hard-code a colour, radius or gap — that is
/// what keeps the light/dark themes and future density changes honest.
///
/// Colour values are derived from the legacy Tkinter `THEME` dict
/// (`resource_hub.pyw:298`) so the migrated UI stays visually continuous with the
/// app users already know.
library;

import 'package:flutter/widgets.dart';

/// Brand + semantic palette, seeded from the legacy `accent` colour.
abstract final class AppColors {
  /// Legacy `THEME["accent"]` — the blue the whole app is built around.
  static const Color seed = Color(0xFF2F6FED);

  // ---- Legacy light palette (resource_hub.pyw:298-312) --------------------
  static const Color legacyBg = Color(0xFFEEF2F7);
  static const Color legacyPanel = Color(0xFFF8FBFF);
  static const Color legacyPanelStrong = Color(0xFFFFFFFF);
  static const Color legacyPanelAlt = Color(0xFFF2F6FC);
  static const Color legacyHero = Color(0xFFE9F1FF);
  static const Color legacyBorder = Color(0xFFD9E2EF);
  static const Color legacyAccent = Color(0xFF2F6FED);
  static const Color legacyAccentSoft = Color(0xFFE5EFFF);
  static const Color legacyAccentMuted = Color(0xFFF0F5FF);
  static const Color legacyInk = Color(0xFF162033);
  static const Color legacyMuted = Color(0xFF5F6B7D);
  static const Color legacySuccess = Color(0xFF23724F);
  static const Color legacyDanger = Color(0xFFC14943);

  // ---- Semantic extras not covered by Material's ColorScheme --------------
  static const Color successLight = Color(0xFF23724F);
  static const Color successContainerLight = Color(0xFFE4F3EB);
  static const Color warningLight = Color(0xFF9A6400);
  static const Color warningContainerLight = Color(0xFFFFF2D6);
  static const Color dangerLight = Color(0xFFC14943);
  static const Color dangerContainerLight = Color(0xFFFBE7E6);
  static const Color favoriteLight = Color(0xFFE0A008);

  static const Color successDark = Color(0xFF6FD3A3);
  static const Color successContainerDark = Color(0xFF17382A);
  static const Color warningDark = Color(0xFFF0C368);
  static const Color warningContainerDark = Color(0xFF3B2D0B);
  static const Color dangerDark = Color(0xFFF08D88);
  static const Color dangerContainerDark = Color(0xFF42201F);
  static const Color favoriteDark = Color(0xFFF3C44B);
}

/// Spacing scale. 4-based, matching the legacy layout's dominant rhythm.
abstract final class AppSpacing {
  static const double xxs = 2;
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 20;
  static const double xxl = 24;
  static const double xxxl = 32;
}

/// Corner radii.
abstract final class AppRadius {
  static const double xs = 6;
  static const double sm = 8;
  static const double md = 10;
  static const double lg = 12;
  static const double xl = 16;
  static const double pill = 999;

  static const BorderRadius smAll = BorderRadius.all(Radius.circular(sm));
  static const BorderRadius mdAll = BorderRadius.all(Radius.circular(md));
  static const BorderRadius lgAll = BorderRadius.all(Radius.circular(lg));
  static const BorderRadius xlAll = BorderRadius.all(Radius.circular(xl));
}

/// Control and layout metrics.
abstract final class AppSizes {
  /// Legacy `left_panel` fixed width (`resource_hub.pyw:2029`).
  static const double sidebarWidth = 340;

  /// Legacy `geometry("1280x820")` / `minsize(1180, 760)`.
  static const Size windowSize = Size(1280, 820);
  static const Size minWindowSize = Size(1180, 760);

  static const double controlHeight = 40;
  static const double controlHeightCompact = 32;
  static const double headerPaddingH = AppSpacing.xl;
  static const double headerPaddingV = AppSpacing.md;
  static const double statusBarHeight = 34;
  static const double tableHeaderHeight = 38;
  static const double tableRowHeight = 44;

  /// Leading grip column of the table (the row's drag handle lives here).
  static const double tableGripWidth = 28;
  static const double iconSm = 16;
  static const double iconMd = 20;
  static const double iconLg = 24;
}

/// Motion tokens. Kept short: this is a desktop utility, not a marketing page.
abstract final class AppDurations {
  static const Duration fast = Duration(milliseconds: 120);
  static const Duration normal = Duration(milliseconds: 180);
  static const Duration slow = Duration(milliseconds: 240);
}

/// Typography.
abstract final class AppTypography {
  /// Primary family. Falls back through the usual Windows CJK stack so mixed
  /// Chinese/Latin strings render consistently (validated in Phase 1 §8.2).
  static const String fontFamily = 'Microsoft YaHei UI';

  static const List<String> fontFamilyFallback = <String>[
    'Microsoft YaHei',
    'Segoe UI',
    'PingFang SC',
    'Noto Sans CJK SC',
    'sans-serif',
  ];
}
