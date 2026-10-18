// Shell tests driven by an in-memory fake, so they never spawn Python.
//
// The real backend path is covered by `backend_client_test.dart`; these tests are
// about layout, i18n, filtering and theme — they must stay fast and offline.

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:resource_hub/data/backend_models.dart';
import 'package:resource_hub/data/resource_api.dart';
import 'package:resource_hub/design/app_theme.dart';
import 'package:resource_hub/features/home/app_top_bar.dart';
import 'package:resource_hub/features/home/home_page.dart';
import 'package:resource_hub/features/home/resource_form.dart';
import 'package:resource_hub/l10n/strings_scope.dart';
import 'package:resource_hub/models/resource_item.dart';
import 'package:resource_hub/platform/backend_client.dart';
import 'package:resource_hub/widgets/app_card.dart';
import 'package:resource_hub/widgets/app_fields.dart';
import 'package:resource_hub/widgets/resource_grid.dart';
import 'package:resource_hub/widgets/resource_table.dart';

class FakeApi implements ResourceApi {
  FakeApi({List<ResourceItem>? folders, List<ResourceItem>? links})
      : _folders = folders ?? _seedFolders(),
        _links = links ?? _seedLinks();

  final List<ResourceItem> _folders;
  final List<ResourceItem> _links;

  /// How often the shell fell back to the backend for open/reveal.
  int openCalls = 0;
  int revealCalls = 0;

  List<ResourceItem> _bucket(ViewMode mode) => mode.isLinks ? _links : _folders;

  static List<ResourceItem> _seedLinks() => <ResourceItem>[
        ResourceItem(
          id: 'l1',
          name: 'GitHub',
          path: 'https://github.com',
          kind: ResourceKind.link,
          category: '开发',
          createdAt: DateTime(2026, 4, 20, 10, 30),
        ),
      ];

  static List<ResourceItem> _seedFolders() => <ResourceItem>[
        ResourceItem(
          id: 'f1',
          name: '项目主目录',
          path: r'D:\Workspace\resource-hub',
          kind: ResourceKind.folder,
          category: '开发',
          favorite: true,
          createdAt: DateTime(2026, 4, 21, 9, 0),
        ),
        ResourceItem(
          id: 'f2',
          name: '预算表 2026',
          path: r'D:\Finance\budget.xlsx',
          kind: ResourceKind.file,
          category: '财务',
          createdAt: DateTime(2026, 4, 19, 14, 5),
        ),
        ResourceItem(
          id: 'f3',
          name: '字体资源包',
          path: r'D:\Design\fonts',
          kind: ResourceKind.folder,
          createdAt: DateTime(2026, 4, 18, 8, 45),
        ),
      ];

  List<ResourceItem> get folders => List<ResourceItem>.unmodifiable(_folders);
  List<ResourceItem> get links => List<ResourceItem>.unmodifiable(_links);

  @override
  Stream<BackendEvent> get events => const Stream<BackendEvent>.empty();

  @override
  Future<ResourceListPage> list(
    ViewMode mode, {
    String? query,
    String? category,
    bool? favoritesOnly,
    String? uncategorizedLabel,
    String? favoriteMark,
  }) async {
    final List<ResourceItem> items = List<ResourceItem>.of(_bucket(mode));
    return ResourceListPage(
      items: items,
      total: items.length,
      visible: items.length,
      categories: <String>['开发', '财务'],
    );
  }

  @override
  Future<ResourceItem> add(
    ViewMode mode, {
    required String name,
    required String target,
    String? category,
    String? note,
  }) async {
    final ResourceItem item = ResourceItem(
      id: 'new-${_bucket(mode).length}',
      name: name,
      path: target,
      kind: mode.isLinks ? ResourceKind.link : ResourceKind.folder,
      category: category ?? kUncategorized,
      note: note ?? '',
      createdAt: DateTime(2026, 4, 22, 12, 0),
    );
    _bucket(mode).insert(0, item);
    return item;
  }

  @override
  Future<ResourceItem> update(
    ViewMode mode, {
    required String id,
    required String name,
    required String target,
    String? category,
    String? note,
  }) async {
    final List<ResourceItem> bucket = _bucket(mode);
    final int index = bucket.indexWhere((ResourceItem e) => e.id == id);
    final ResourceItem updated = bucket[index].copyWith(
      name: name,
      path: target,
      category: category ?? kUncategorized,
      note: note ?? '',
    );
    bucket[index] = updated;
    return updated;
  }

  @override
  Future<bool> delete(ViewMode mode, String id) async {
    final List<ResourceItem> bucket = _bucket(mode);
    final int before = bucket.length;
    bucket.removeWhere((ResourceItem e) => e.id == id);
    return bucket.length != before;
  }

  @override
  Future<ResourceItem> setFavorite(
    ViewMode mode,
    String id, {
    bool? value,
  }) async {
    final List<ResourceItem> bucket = _bucket(mode);
    final int index = bucket.indexWhere((ResourceItem e) => e.id == id);
    final ResourceItem updated =
        bucket[index].copyWith(favorite: value ?? !bucket[index].favorite);
    bucket[index] = updated;
    return updated;
  }

  @override
  Future<void> open(ViewMode mode, String id) async {
    openCalls += 1;
  }

  @override
  Future<void> reveal(ViewMode mode, String id) async {
    revealCalls += 1;
  }

  @override
  Future<PathCheckOutcome> checkPaths(ViewMode mode) async => PathCheckOutcome(
        supported: !mode.isLinks,
        total: 0,
        missingIds: const <String>[],
      );

  @override
  Future<DropOutcome> drop(List<String> paths) async {
    final int before = _folders.length;
    for (final String path in paths) {
      _folders.insert(
        0,
        ResourceItem(
          id: 'dropped-${_folders.length}',
          name: path,
          path: path,
          kind: ResourceKind.folder,
        ),
      );
    }
    return DropOutcome(
      added: _folders.length - before,
      skipped: 0,
      invalid: 0,
    );
  }

  @override
  Future<List<Map<String, dynamic>>> export(ViewMode mode) async =>
      _bucket(mode).map((ResourceItem item) => item.toJson()).toList();

  @override
  Future<ImportOutcome> import(
    ViewMode mode,
    List<Map<String, dynamic>> items,
  ) async {
    final List<ResourceItem> imported = items
        .map(
          (Map<String, dynamic> item) =>
              ResourceItem.tryFromJson(item, mode: mode),
        )
        .whereType<ResourceItem>()
        .toList();
    final List<ResourceItem> bucket = _bucket(mode)
      ..clear()
      ..addAll(imported);
    return ImportOutcome(imported: bucket.length, skipped: 0);
  }

  @override
  Future<bool> probeHotkey(String hotkeyId) async => true;

  @override
  Future<HotkeyStatus> startHotkey() async =>
      const HotkeyStatus(registered: true, label: 'Ctrl + Alt + Space');

  @override
  Future<void> stopHotkey() async {}
}

/// Fake that always refuses a save with a duplicate error, so the status-bar
/// error path can be exercised without a backend.
class _RejectingApi extends FakeApi {
  @override
  Future<ResourceItem> add(
    ViewMode mode, {
    required String name,
    required String target,
    String? category,
    String? note,
  }) async {
    throw const BackendException(
      'duplicate',
      'duplicate path',
      key: 'duplicate_folder_path',
    );
  }
}

/// Minimal app shell around [HomePage] so tests control language and theme.
class Harness extends StatefulWidget {
  const Harness({super.key, required this.api, this.onSettingsChanged});

  final ResourceApi api;
  final Future<void> Function(AppSettings settings)? onSettingsChanged;

  @override
  State<Harness> createState() => _HarnessState();
}

class _HarnessState extends State<Harness> {
  AppLanguage _language = AppLanguage.zh;
  ThemeMode _themeMode = ThemeMode.light;

  @override
  Widget build(BuildContext context) {
    final AppStrings strings = AppStrings(_language);
    return AppStringsScope(
      strings: strings,
      onLanguageChanged: (AppLanguage value) =>
          setState(() => _language = value),
      child: MaterialApp(
        debugShowCheckedModeBanner: false,
        theme: AppTheme.light,
        darkTheme: AppTheme.dark,
        themeMode: _themeMode,
        home: HomePage(
          api: widget.api,
          dataCorrupt: false,
          settings: const AppSettings(),
          hotkey: null,
          themeMode: _themeMode,
          onThemeModeChanged: (ThemeMode value) =>
              setState(() => _themeMode = value),
          onSettingsChanged: widget.onSettingsChanged ??
              (AppSettings _) async {},
        ),
      ),
    );
  }
}

/// Desktop-sized surface: the shell is designed for 1280x820 and hard-codes a
/// 340px sidebar, so the 800x600 test default would be misleading.
Future<void> pumpApp(
  WidgetTester tester, {
  Size size = const Size(1600, 1100),
  FakeApi? api,
  Future<void> Function(AppSettings settings)? onSettingsChanged,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1.0;
  tester.platformDispatcher.platformBrightnessTestValue = Brightness.light;
  addTearDown(tester.view.reset);
  addTearDown(tester.platformDispatcher.clearPlatformBrightnessTestValue);

  // The runner (C++) provides `resource_hub/window`; widget tests have no
  // engine, so answer every outgoing call with "not implemented" instead of
  // leaving the future pending. Callers then take their fallback path.
  const MethodChannel shellChannel = MethodChannel('resource_hub/window');
  final TestDefaultBinaryMessenger messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(shellChannel, (MethodCall call) async {
    throw MissingPluginException('${call.method} is not available in tests');
  });
  addTearDown(() => messenger.setMockMethodCallHandler(shellChannel, null));

  await tester.pumpWidget(Harness(
    api: api ?? FakeApi(),
    onSettingsChanged: onSettingsChanged,
  ));
  await tester.pumpAndSettle();
}

/// Opens the settings dialog from the compact top bar.
Future<void> openSettings(WidgetTester tester) async {
  await tester.tap(find.byTooltip('设置'));
  await tester.pumpAndSettle();
}

/// Closes the top-most dialog (settings or editor) via its close icon.
Future<void> closeDialog(WidgetTester tester) async {
  await tester.tap(find.byIcon(Icons.close).last);
  await tester.pumpAndSettle();
}

/// Switches language through the settings dialog (the header toggle is gone).
Future<void> switchLanguage(WidgetTester tester, String label) async {
  await openSettings(tester);
  await tester.tap(find.text(label));
  await tester.pumpAndSettle();
  await closeDialog(tester);
}

void main() {
  testWidgets('boots with the Chinese shell', (WidgetTester tester) async {
    await pumpApp(tester);

    expect(find.byType(HomePage), findsOneWidget);
    expect(find.text('常用资源工具'), findsOneWidget);
    expect(find.text('已保存资源'), findsOneWidget);
    expect(find.text('项目主目录'), findsOneWidget);
  });

  testWidgets('compact top bar replaces the old hero header',
      (WidgetTester tester) async {
    await pumpApp(tester);

    expect(find.byType(AppTopBar), findsOneWidget);
    expect(tester.getSize(find.byType(AppTopBar)).height, AppTopBar.height);
    // Hero block, feature chips and metric cards must be gone.
    expect(find.byType(StatCard), findsNothing);
    expect(find.text('轻量桌面资源中枢'), findsNothing);
    expect(find.text('快速启动'), findsNothing);
    expect(find.text('资源总数'), findsNothing);
  });

  testWidgets('switching language re-renders every label',
      (WidgetTester tester) async {
    await pumpApp(tester);
    await switchLanguage(tester, 'English');

    expect(find.text('Resource Hub Desktop'), findsOneWidget);
    expect(find.text('Saved Resources'), findsOneWidget);
    expect(find.text('常用资源工具'), findsNothing);
  });

  testWidgets('search narrows the table', (WidgetTester tester) async {
    await pumpApp(tester);

    expect(find.text('字体资源包'), findsOneWidget);
    expect(find.text('预算表 2026'), findsOneWidget);

    await tester.enterText(
      find.descendant(
        of: find.byType(AppSearchField),
        matching: find.byType(TextField),
      ),
      '字体',
    );
    await tester.pumpAndSettle();

    expect(find.text('字体资源包'), findsOneWidget);
    expect(find.text('预算表 2026'), findsNothing);
  });

  testWidgets('theme mode switch reaches Theme.of(context)',
      (WidgetTester tester) async {
    await pumpApp(tester);

    final BuildContext context = tester.element(find.byType(HomePage));
    // The harness starts in light mode; the settings dialog owns the switch.
    expect(Theme.of(context).brightness, Brightness.light);

    await openSettings(tester);
    await tester.tap(find.text('深色'));
    await tester.pumpAndSettle();
    await closeDialog(tester);
    expect(Theme.of(context).brightness, Brightness.dark);

    await openSettings(tester);
    await tester.tap(find.text('浅色'));
    await tester.pumpAndSettle();
    await closeDialog(tester);
    expect(Theme.of(context).brightness, Brightness.light);
  });

  testWidgets('data sentinels never leak into the UI',
      (WidgetTester tester) async {
    await pumpApp(tester);
    expect(find.textContaining('__uncategorized__'), findsNothing);
    expect(find.textContaining('__all__'), findsNothing);
    expect(find.text('未分类'), findsWidgets);
    expect(find.text('全部分类'), findsWidgets);
  });

  testWidgets('dark theme keeps section headings readable',
      (WidgetTester tester) async {
    await pumpApp(tester);
    await openSettings(tester);
    await tester.tap(find.text('深色'));
    await tester.pumpAndSettle();
    await closeDialog(tester);

    final BuildContext context = tester.element(find.byType(HomePage));
    expect(Theme.of(context).brightness, Brightness.dark);

    final Color background = Theme.of(context).scaffoldBackgroundColor;
    for (final String heading in <String>['已保存资源', '常用资源工具']) {
      final RenderParagraph paragraph =
          tester.renderObject<RenderParagraph>(find.text(heading).first);
      final Color? foreground = paragraph.text.style?.color;
      expect(foreground, isNotNull, reason: '$heading has no explicit colour');
      expect(
        (foreground!.computeLuminance() - background.computeLuminance()).abs(),
        greaterThan(0.25),
        reason: '$heading is too close to the background in dark mode',
      );
    }
  });

  testWidgets('lays out at the minimum supported window size',
      (WidgetTester tester) async {
    await pumpApp(tester, size: const Size(1180, 760));
    expect(tester.takeException(), isNull);
    expect(find.text('已保存资源'), findsOneWidget);
  });

  testWidgets('English headers render without layout exceptions',
      (WidgetTester tester) async {
    await pumpApp(tester, size: const Size(1180, 760));
    await switchLanguage(tester, 'English');

    expect(tester.takeException(), isNull);
    for (final String header in <String>[
      'Favorite',
      'Name',
      'Type',
      'Status',
      'Category',
      'Added At',
      'Local Path',
      'Notes',
    ]) {
      expect(find.text(header), findsWidgets, reason: '"$header" missing');
    }
  });

  testWidgets('add button opens the editor dialog',
      (WidgetTester tester) async {
    await pumpApp(tester);

    expect(find.byType(ResourceForm), findsNothing);
    await tester.tap(find.text('新增资源'));
    await tester.pumpAndSettle();
    expect(find.byType(ResourceForm), findsOneWidget);

    await closeDialog(tester);
    expect(find.byType(ResourceForm), findsNothing);
  });

  testWidgets('view toggle switches between table and grid',
      (WidgetTester tester) async {
    await pumpApp(tester);

    expect(find.byType(ResourceTable), findsOneWidget);
    expect(find.byType(ResourceGrid), findsNothing);

    await tester.tap(find.byIcon(Icons.grid_view_outlined));
    await tester.pumpAndSettle();
    expect(find.byType(ResourceGrid), findsOneWidget);
    expect(find.byType(ResourceTable), findsNothing);

    await tester.tap(find.byIcon(Icons.view_list_outlined));
    await tester.pumpAndSettle();
    expect(find.byType(ResourceTable), findsOneWidget);
  });

  testWidgets('submitting the form adds a row through the api',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);

    await tester.tap(find.text('新增资源'));
    await tester.pumpAndSettle();

    final Finder formFields = find.descendant(
      of: find.byType(ResourceForm),
      matching: find.byType(TextField),
    );
    await tester.enterText(formFields.at(0), '新资源');
    await tester.enterText(formFields.at(1), r'D:\Workspace\new');
    await tester.tap(find.text('保存资源'));
    await tester.pumpAndSettle();

    expect(api.folders.first.name, '新资源');
    expect(find.text('新资源'), findsWidgets);
  });

  testWidgets('validation errors from the api surface in the status bar',
      (WidgetTester tester) async {
    // Empty name is rejected client-side by the form, so this asserts the path
    // where the backend is the one refusing (duplicate).
    final FakeApi api = _RejectingApi();
    await pumpApp(tester, api: api);

    await tester.tap(find.text('新增资源'));
    await tester.pumpAndSettle();

    final Finder formFields = find.descendant(
      of: find.byType(ResourceForm),
      matching: find.byType(TextField),
    );
    await tester.enterText(formFields.at(0), '重复项');
    await tester.enterText(formFields.at(1), r'D:\Workspace\dup');
    await tester.tap(find.text('保存资源'));
    await tester.pumpAndSettle();

    expect(find.text('这个文件或文件夹路径已经保存过了。'), findsOneWidget);
  });

  testWidgets('deleting asks for confirmation and removes the row',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);

    await tester.tap(find.text('预算表 2026'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('删除'));
    await tester.pumpAndSettle();

    expect(find.text('删除确认'), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, '删除'));
    await tester.pumpAndSettle();

    expect(find.text('预算表 2026'), findsNothing);
    expect(api.folders.map((ResourceItem e) => e.name), isNot(contains('预算表 2026')));
  });

  test('light and dark schemes expose the semantic extension', () {
    expect(AppTheme.light.extension<AppSemanticColors>()?.success, isNotNull);
    expect(AppTheme.dark.extension<AppSemanticColors>()?.danger, isNotNull);
    expect(AppTheme.light.colorScheme.primary, const Color(0xFF2F6FED));
  });

  testWidgets('list toolbar exposes import and export entries',
      (WidgetTester tester) async {
    await pumpApp(tester);

    expect(find.byTooltip('导出'), findsOneWidget);
    expect(find.byTooltip('导入'), findsOneWidget);
  });

  testWidgets('dropped paths are added through the api',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);

    await _emitDrop(<String>[r'C:\Dropped\资源']);
    await tester.pumpAndSettle();

    expect(api.folders.first.path, r'C:\Dropped\资源');
    expect(find.text('已添加 1 个资源。'), findsOneWidget);
  });

  testWidgets('open falls back to the backend when the native shell is absent',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);

    await tester.tap(find.text('项目主目录'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('打开'));
    await tester.pumpAndSettle();

    // Widget tests have no platform channel, so the runner path is unavailable
    // and the shell must call `resources.open` instead.
    expect(api.openCalls, 1);
  });

  testWidgets('hotkey recorder probes and saves a new combination',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    final List<AppSettings> saved = <AppSettings>[];
    await pumpApp(
      tester,
      api: api,
      onSettingsChanged: (AppSettings settings) async => saved.add(settings),
    );

    await openSettings(tester);
    expect(find.text('录制快捷键'), findsOneWidget);

    await tester.tap(find.text('录制快捷键'));
    await tester.pumpAndSettle();

    // A modifier-only press must not be taken as the combination; the real key
    // then arrives while Ctrl is held down.
    await tester.sendKeyDownEvent(LogicalKeyboardKey.controlLeft);
    await tester.pump();
    await tester.sendKeyEvent(LogicalKeyboardKey.f11);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.controlLeft);
    await tester.pumpAndSettle();

    expect(saved, isNotEmpty);
    expect(saved.last.globalHotkeyId, 'Ctrl + F11');
    expect(find.text('录制快捷键'), findsOneWidget);
  });

  testWidgets('settings language can be switched back and forth',
      (WidgetTester tester) async {
    await pumpApp(tester);

    await openSettings(tester);

    await tester.tap(find.text('English'));
    await tester.pumpAndSettle();
    expect(find.text('Settings'), findsWidgets);
    expect(find.text('简体中文'), findsOneWidget);

    // Regression: the dialog kept the language captured when it was opened, so
    // the visible "selected" segment stayed 简体中文 and tapping it was ignored
    // (SegmentedButton ignores taps on the already-selected segment).
    await tester.tap(find.text('简体中文'));
    await tester.pumpAndSettle();
    expect(find.text('设置'), findsWidgets);
    expect(find.text('Settings'), findsNothing);
  });

  testWidgets('settings theme mode can be switched back and forth',
      (WidgetTester tester) async {
    await pumpApp(tester);

    await openSettings(tester);

    SegmentedButton<ThemeMode> themeSelector() =>
        tester.widget<SegmentedButton<ThemeMode>>(
          find.byType(SegmentedButton<ThemeMode>),
        );

    await tester.tap(find.text('深色'));
    await tester.pumpAndSettle();
    expect(themeSelector().selected, <ThemeMode>{ThemeMode.dark});

    await tester.tap(find.text('浅色'));
    await tester.pumpAndSettle();
    expect(themeSelector().selected, <ThemeMode>{ThemeMode.light});
  });

  test('translation table keeps zh/en key parity', () {
    final Set<String> zh = kTranslations['zh']!.keys.toSet();
    final Set<String> en = kTranslations['en']!.keys.toSet();
    expect(zh.difference(en), isEmpty);
    expect(en.difference(zh), isEmpty);
    expect(zh.length, greaterThan(100));
  });
}

/// Delivers a native `dropPaths` call, as the Windows runner would.
Future<void> _emitDrop(List<String> paths) {
  return TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .handlePlatformMessage(
    'resource_hub/window',
    const StandardMethodCodec().encodeMethodCall(
      MethodCall('dropPaths', paths),
    ),
    (ByteData? _) {},
  );
}
