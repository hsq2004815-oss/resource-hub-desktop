// Shell tests driven by an in-memory fake, so they never spawn Python.
//
// The real backend path is covered by `backend_client_test.dart`; these tests are
// about layout, i18n, filtering and theme — they must stay fast and offline.

import 'dart:async';

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:resource_hub/data/backend_models.dart';
import 'package:resource_hub/data/resource_api.dart';
import 'package:resource_hub/design/app_theme.dart';
import 'package:resource_hub/features/home/home_page.dart';
import 'package:resource_hub/features/home/resource_detail_panel.dart';
import 'package:resource_hub/features/home/resource_form.dart';
import 'package:resource_hub/l10n/strings_scope.dart';
import 'package:resource_hub/models/resource_item.dart';
import 'package:resource_hub/platform/backend_client.dart';
import 'package:resource_hub/widgets/app_card.dart';
import 'package:resource_hub/widgets/app_fields.dart';
import 'package:resource_hub/widgets/mind_map.dart';
import 'package:resource_hub/widgets/resource_grid.dart';
import 'package:resource_hub/widgets/resource_table.dart';

class FakeApi implements ResourceApi {
  FakeApi({
    List<ResourceItem>? folders,
    List<ResourceItem>? links,
    Map<String, List<FsEntry>>? children,
  })  : _folders = folders ?? _seedFolders(),
        _links = links ?? _seedLinks(),
        _children = children ?? _seedChildren();

  final List<ResourceItem> _folders;
  final List<ResourceItem> _links;
  final Map<String, List<FsEntry>> _children;

  /// How often the shell fell back to the backend for open/reveal.
  int openCalls = 0;
  int revealCalls = 0;

  /// Filesystem browsing (details panel).
  int listChildrenCalls = 0;
  int openPathCalls = 0;
  int revealPathCalls = 0;
  String? lastOpenedPath;
  String? lastRevealedPath;

  List<ResourceItem> _bucket(ViewMode mode) => mode.isLinks ? _links : _folders;

  static Map<String, List<FsEntry>> _seedChildren() => <String, List<FsEntry>>{
        r'D:\Workspace\resource-hub': <FsEntry>[
          FsEntry(
            name: 'src',
            path: r'D:\Workspace\resource-hub\src',
            kind: FsEntryKind.folder,
          ),
          FsEntry(
            name: 'docs',
            path: r'D:\Workspace\resource-hub\docs',
            kind: FsEntryKind.folder,
          ),
          FsEntry(
            name: 'README.md',
            path: r'D:\Workspace\resource-hub\README.md',
            kind: FsEntryKind.file,
          ),
        ],
        r'D:\Workspace\resource-hub\src': <FsEntry>[
          FsEntry(
            name: 'main.dart',
            path: r'D:\Workspace\resource-hub\src\main.dart',
            kind: FsEntryKind.file,
          ),
          FsEntry(
            name: 'widgets',
            path: r'D:\Workspace\resource-hub\src\widgets',
            kind: FsEntryKind.folder,
          ),
        ],
        r'D:\Workspace\resource-hub\src\widgets': <FsEntry>[],
      };

  @override
  Future<FsListing> listChildren(String path) async {
    listChildrenCalls += 1;
    final List<FsEntry>? entries = _children[path];
    if (entries == null) {
      throw const BackendException(
        'operation_failed',
        'path does not exist',
        key: 'fs_not_found',
      );
    }
    final List<FsEntry> sorted = List<FsEntry>.of(entries)
      ..sort((FsEntry a, FsEntry b) {
        final int byKind =
            (a.isFolder ? 0 : 1).compareTo(b.isFolder ? 0 : 1);
        return byKind != 0
            ? byKind
            : a.name.toLowerCase().compareTo(b.name.toLowerCase());
      });
    return FsListing(
      path: path,
      entries: sorted,
      total: sorted.length,
      truncated: false,
    );
  }

  @override
  Future<void> openPath(String path) async {
    openPathCalls += 1;
    lastOpenedPath = path;
  }

  @override
  Future<void> revealPath(String path) async {
    revealPathCalls += 1;
    lastRevealedPath = path;
  }

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
  Stream<BackendEvent> get events => _events.stream;
  final StreamController<BackendEvent> _events =
      StreamController<BackendEvent>.broadcast();

  /// Simulates a backend-pushed global hotkey press (Phase 16).
  void emitHotkey(String action) {
    _events.add(BackendEvent('hotkey', <String, dynamic>{'action': action}));
  }

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
  Future<DeleteOutcome> delete(
    ViewMode mode,
    String id, {
    bool removeFromBrowser = false,
  }) async {
    final List<ResourceItem> bucket = _bucket(mode);
    final int before = bucket.length;
    bucket.removeWhere((ResourceItem e) => e.id == id);
    lastDeleteRemovedFromBrowser = removeFromBrowser;
    return DeleteOutcome(
      deleted: bucket.length != before,
      browserQueued: removeFromBrowser,
      extensionConnected: removeFromBrowser && extensionConnected,
    );
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

  /// How often the shell persisted a manual order.
  int reorderCalls = 0;

  @override
  Future<List<ResourceItem>> reorder(ViewMode mode, List<String> ids) async {
    reorderCalls += 1;
    final List<ResourceItem> bucket = _bucket(mode);
    final Map<String, ResourceItem> byId = <String, ResourceItem>{
      for (final ResourceItem item in bucket) item.id: item,
    };
    final List<ResourceItem> next = <ResourceItem>[
      for (final String id in ids)
        if (byId[id] != null) byId[id]!,
    ];
    if (next.length != bucket.length) {
      throw const BackendException(
        'operation_failed',
        'ids do not match the collection',
        key: 'reorder_failed',
      );
    }
    bucket
      ..clear()
      ..addAll(next);
    return List<ResourceItem>.of(next);
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

  // -- Phase 17: browser bookmark sync -----------------------------------
  BookmarkStatus bookmarkStatus = const BookmarkStatus(
    profiles: <BookmarkProfile>[
      BookmarkProfile(
        label: 'Chrome · Default',
        path: r'C:\Chrome\User Data\Default',
        bookmarks: 3,
      ),
    ],
    lastSyncAt: '2026-10-18T07:00:00+08:00',
    syncedUrls: 3,
  );
  int syncBookmarkCalls = 0;
  int bookmarkAddedOnSync = 1;

  @override
  Future<BookmarkSyncResult> syncBookmarks() async {
    syncBookmarkCalls += 1;
    if (bookmarkAddedOnSync > 0) {
      _links.add(
        ResourceItem(
          id: 'synced-$syncBookmarkCalls',
          name: 'Synced Site $syncBookmarkCalls',
          path: 'https://synced$syncBookmarkCalls.example',
          kind: ResourceKind.link,
          category: '书签栏',
        ),
      );
    }
    return BookmarkSyncResult(
      added: bookmarkAddedOnSync,
      skipped: 0,
      total: bookmarkAddedOnSync,
      profiles: bookmarkStatus.profiles,
      lastSyncAt: bookmarkStatus.lastSyncAt,
    );
  }

  @override
  Future<BookmarkStatus> loadBookmarkStatus() async => bookmarkStatus;

  // -- Phase 18: extension + browser matches ------------------------------
  bool extensionConnected = false;
  List<BookmarkMatch> bookmarkMatchesResult = const <BookmarkMatch>[];
  bool? lastDeleteRemovedFromBrowser;

  @override
  Future<List<BookmarkMatch>> bookmarkMatches(List<String> urls) async =>
      bookmarkMatchesResult;

  @override
  Future<BookmarkExtensionStatus> loadBookmarkExtensionStatus() async =>
      BookmarkExtensionStatus(
        connected: extensionConnected,
        port: extensionConnected ? 47821 : null,
        extensionPath: extensionConnected ? r'C:\App\bookmark-extension' : '',
      );

  /// Adds a link as if a bookmark had been imported, for event tests.
  void addBookmarkLink(ResourceItem item) => _links.add(item);

  /// Simulates the backend's background "bookmarks" event.
  void emitBookmarkEvent(int added) {
    _events.add(
      BackendEvent('bookmarks', <String, dynamic>{
        'added': added,
        'lastSyncAt': '2026-10-18T07:10:00+08:00',
        'profiles': <dynamic>[],
      }),
    );
  }

  /// Simulates a reverse-sync event from the browser extension.
  void emitBookmarkRemoved(int deleted, {int renamed = 0}) {
    _events.add(
      BackendEvent('bookmarks', <String, dynamic>{
        'added': 0,
        'deleted': deleted,
        'renamed': renamed,
        'lastSyncAt': '2026-10-18T07:20:00+08:00',
      }),
    );
  }
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

/// Fake that accepts a reorder gesture but refuses to persist it.
class _RejectingReorderApi extends FakeApi {
  @override
  Future<List<ResourceItem>> reorder(ViewMode mode, List<String> ids) async {
    throw const BackendException(
      'operation_failed',
      'reorder rejected by the fake',
      key: 'reorder_failed',
    );
  }
}

/// Drags a reorder grip by [delta] with intermediate moves so the reorderable
/// list and the custom grid have time to update their insertion target.
Future<void> dragReorderGrip(
  WidgetTester tester,
  Finder grip,
  Offset delta,
) async {
  final TestGesture gesture = await tester.startGesture(tester.getCenter(grip));
  await tester.pump(const Duration(milliseconds: 40));
  const int steps = 5;
  for (int i = 0; i < steps; i++) {
    await gesture.moveBy(delta / steps.toDouble());
    await tester.pump(const Duration(milliseconds: 32));
  }
  await gesture.up();
  await tester.pumpAndSettle();
}

List<String> folderIds(FakeApi api) =>
    api.folders.map((ResourceItem item) => item.id).toList();

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
  Future<Object?> Function(MethodCall call)? shellHandler,
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
    if (shellHandler != null) {
      return shellHandler(call);
    }
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
    expect(find.text('常用资源工具'), findsNothing);
    expect(find.text('已保存资源'), findsOneWidget);
    expect(find.text('项目主目录'), findsOneWidget);
  });

  testWidgets('in-content top bar is gone and settings live in the toolbar',
      (WidgetTester tester) async {
    await pumpApp(tester);

    // The window title is the native Windows title bar; content starts directly
    // with the workspace header, and settings moved into the toolbar.
    expect(find.text('常用资源工具'), findsNothing);
    expect(find.byTooltip('设置'), findsOneWidget);
    expect(tester.getTopLeft(find.text('已保存资源')).dy, lessThan(120));
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
    for (final String heading in <String>['已保存资源']) {
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
    await tester.tap(find.byTooltip('新增资源'));
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

    await tester.tap(find.byTooltip('新增资源'));
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

    await tester.tap(find.byTooltip('新增资源'));
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

  testWidgets('backup export/import live in the overflow menu',
      (WidgetTester tester) async {
    await pumpApp(tester);

    // The two standalone toolbar buttons were removed as visual clutter.
    expect(find.byTooltip('导出'), findsNothing);
    expect(find.byTooltip('导入'), findsNothing);

    await tester.tap(find.byTooltip('更多操作'));
    await tester.pumpAndSettle();
    expect(find.text('导出'), findsOneWidget);
    expect(find.text('导入'), findsOneWidget);
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
    // The row click also opens the details panel, which has its own 打开 button;
    // the toolbar one comes first in the tree.
    await tester.tap(find.byTooltip('打开').first);
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
    expect(find.text('录制快捷键'), findsNWidgets(3));

    // The full-window recorder is the first row; the other two belong to the
    // quick-panel trees.
    await tester.tap(find.text('录制快捷键').first);
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
    expect(find.text('录制快捷键'), findsNWidgets(3));
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

  testWidgets('favourites are no longer pinned above the manual order',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi(
      folders: <ResourceItem>[
        ResourceItem(
          id: 'f2',
          name: '预算表 2026',
          path: r'D:\Finance\budget.xlsx',
          kind: ResourceKind.file,
          createdAt: DateTime(2026, 4, 19, 14, 5),
        ),
        ResourceItem(
          id: 'f1',
          name: '项目主目录',
          path: r'D:\Workspace\resource-hub',
          kind: ResourceKind.folder,
          favorite: true,
          createdAt: DateTime(2026, 4, 21, 9, 0),
        ),
        ResourceItem(
          id: 'f3',
          name: '字体资源包',
          path: r'D:\Design\fonts',
          kind: ResourceKind.folder,
          createdAt: DateTime(2026, 4, 18, 8, 45),
        ),
      ],
    );
    await pumpApp(tester, api: api);

    final double plainRow = tester.getTopLeft(find.text('预算表 2026')).dy;
    final double favouriteRow = tester.getTopLeft(find.text('项目主目录')).dy;
    expect(
      favouriteRow,
      greaterThan(plainRow),
      reason: 'the stored order must win over the favourite flag',
    );
  });

  testWidgets('dragging a list row saves the order and can be undone',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);
    expect(folderIds(api), <String>['f1', 'f2', 'f3']);

    await dragReorderGrip(
      tester,
      find.byIcon(Icons.drag_indicator).first,
      const Offset(0, 66),
    );

    expect(api.reorderCalls, 1);
    expect(folderIds(api), <String>['f2', 'f1', 'f3']);
    expect(find.text('顺序已更新'), findsOneWidget);
    expect(find.text('撤销'), findsOneWidget);

    await tester.tap(find.text('撤销'));
    await tester.pumpAndSettle();

    expect(api.reorderCalls, 2);
    expect(folderIds(api), <String>['f1', 'f2', 'f3']);
    expect(find.text('已撤销排序'), findsOneWidget);
  });

  testWidgets('searching disables reordering', (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);

    await tester.enterText(
      find.descendant(
        of: find.byType(AppSearchField),
        matching: find.byType(TextField),
      ),
      '项目',
    );
    await tester.pumpAndSettle();

    expect(find.byTooltip('清空搜索后可拖动排序'), findsWidgets);
    await dragReorderGrip(
      tester,
      find.byIcon(Icons.drag_indicator).first,
      const Offset(0, 66),
    );

    expect(api.reorderCalls, 0);
    expect(folderIds(api), <String>['f1', 'f2', 'f3']);
    expect(find.text('撤销'), findsNothing);
  });

  testWidgets('dragging a grid card saves the order',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);
    await tester.tap(find.byIcon(Icons.grid_view_outlined));
    await tester.pumpAndSettle();
    expect(find.byType(ResourceGrid), findsOneWidget);

    await dragReorderGrip(
      tester,
      find.byIcon(Icons.drag_indicator).first,
      const Offset(480, 0),
    );

    expect(api.reorderCalls, 1);
    expect(folderIds(api), <String>['f2', 'f1', 'f3']);
    await tester.pump(const Duration(seconds: 6));
  });

  testWidgets('sort by date added reorders the collection',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi(
      folders: <ResourceItem>[
        ResourceItem(
          id: 'f3',
          name: '字体资源包',
          path: r'D:\Design\fonts',
          kind: ResourceKind.folder,
          createdAt: DateTime(2026, 4, 18, 8, 45),
        ),
        ResourceItem(
          id: 'f2',
          name: '预算表 2026',
          path: r'D:\Finance\budget.xlsx',
          kind: ResourceKind.file,
          createdAt: DateTime(2026, 4, 19, 14, 5),
        ),
        ResourceItem(
          id: 'f1',
          name: '项目主目录',
          path: r'D:\Workspace\resource-hub',
          kind: ResourceKind.folder,
          favorite: true,
          createdAt: DateTime(2026, 4, 21, 9, 0),
        ),
      ],
    );
    await pumpApp(tester, api: api);
    expect(folderIds(api), <String>['f3', 'f2', 'f1']);

    await tester.tap(find.byIcon(Icons.more_vert));
    await tester.pumpAndSettle();
    await tester.tap(find.text('按添加时间排序'));
    await tester.pumpAndSettle();

    expect(folderIds(api), <String>['f1', 'f2', 'f3']);
    expect(find.text('已按添加时间排序'), findsOneWidget);
    await tester.pump(const Duration(seconds: 6));
  });

  testWidgets('Alt+Down moves the selected row down one position',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);

    await tester.tap(find.text('项目主目录'));
    await tester.pumpAndSettle();

    await tester.sendKeyDownEvent(LogicalKeyboardKey.altLeft);
    await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
    await tester.sendKeyUpEvent(LogicalKeyboardKey.altLeft);
    await tester.pumpAndSettle();

    expect(api.reorderCalls, 1);
    expect(folderIds(api), <String>['f2', 'f1', 'f3']);
    await tester.pump(const Duration(seconds: 6));
  });

  testWidgets('a rejected reorder restores the previous order',
      (WidgetTester tester) async {
    final FakeApi api = _RejectingReorderApi();
    await pumpApp(tester, api: api);

    await dragReorderGrip(
      tester,
      find.byIcon(Icons.drag_indicator).first,
      const Offset(0, 66),
    );

    expect(find.text('排序保存失败，已恢复原顺序'), findsOneWidget);
    expect(find.text('撤销'), findsNothing);
    expect(folderIds(api), <String>['f1', 'f2', 'f3']);
  });

  testWidgets('clicking a folder row opens the details mind map',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);

    await tester.tap(find.text('项目主目录'));
    await tester.pumpAndSettle();

    expect(find.byType(ResourceDetailPanel), findsOneWidget);
    expect(find.byType(MindMap), findsOneWidget);
    expect(api.listChildrenCalls, 1);
    expect(find.text('src'), findsOneWidget);
    expect(find.text('docs'), findsOneWidget);
    expect(find.text('README.md'), findsOneWidget);

    await tester.tap(find.byTooltip('关闭'));
    await tester.pumpAndSettle();
    expect(find.byType(ResourceDetailPanel), findsNothing);
  });

  testWidgets('expanding a mind map node loads exactly one more level',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);
    await tester.tap(find.text('项目主目录'));
    await tester.pumpAndSettle();

    // Selecting a folder reveals its hover toggle (tooltip 展开).
    await tester.tap(find.text('src'));
    await tester.pump(const Duration(milliseconds: 500));
    await tester.pumpAndSettle();
    expect(find.byTooltip('展开'), findsWidgets);

    await tester.tap(find.byTooltip('展开').first);
    await tester.pumpAndSettle();

    expect(api.listChildrenCalls, 2);
    expect(api.lastOpenedPath, isNull);
    expect(find.text('main.dart'), findsOneWidget);
    expect(find.text('widgets'), findsOneWidget);

    // The first 收起 belongs to the just-expanded node; collapsing hides its
    // children again.
    await tester.tap(find.byTooltip('收起').first);
    await tester.pumpAndSettle();
    expect(find.text('main.dart'), findsNothing);
  });

  testWidgets('double-clicking a mind map node opens it through the shell api',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);
    await tester.tap(find.text('项目主目录'));
    await tester.pumpAndSettle();

    final Finder node = find.text('docs');
    await tester.tap(node);
    await tester.pump(const Duration(milliseconds: 40));
    await tester.tap(node);
    await tester.pumpAndSettle();

    expect(api.openPathCalls, 1);
    expect(api.lastOpenedPath, r'D:\Workspace\resource-hub\docs');
  });

  testWidgets('a mind map node can be added as a resource from its context menu',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);
    await tester.tap(find.text('项目主目录'));
    await tester.pumpAndSettle();

    await tester.tap(find.text('docs'), buttons: kSecondaryMouseButton);
    await tester.pumpAndSettle();
    expect(find.text('添加为资源'), findsOneWidget);

    await tester.tap(find.text('添加为资源'));
    await tester.pumpAndSettle();

    expect(api.folders.first.path, r'D:\Workspace\resource-hub\docs');
    expect(find.textContaining('已添加资源：docs'), findsOneWidget);
  });

  testWidgets('zoom buttons change the mind map scale',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);
    await tester.tap(find.text('项目主目录'));
    await tester.pumpAndSettle();

    expect(find.text('100%'), findsOneWidget);
    await tester.tap(find.byTooltip('放大'));
    await tester.pumpAndSettle();
    expect(find.text('125%'), findsOneWidget);

    await tester.tap(find.byTooltip('缩小'));
    await tester.pumpAndSettle();
    expect(find.text('100%'), findsOneWidget);
  });

  testWidgets('Escape closes the details panel', (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);
    await tester.tap(find.text('项目主目录'));
    await tester.pumpAndSettle();
    expect(find.byType(ResourceDetailPanel), findsOneWidget);

    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
    expect(find.byType(ResourceDetailPanel), findsNothing);
  });

  testWidgets('clicking a blank area closes the details panel',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);
    await tester.tap(find.text('项目主目录'));
    await tester.pumpAndSettle();
    expect(find.byType(ResourceDetailPanel), findsOneWidget);

    // Empty space below the rows, far from the panel on the right.
    await tester.tapAt(const Offset(200, 900));
    await tester.pumpAndSettle();

    expect(find.byType(ResourceDetailPanel), findsNothing);
  });

  testWidgets('clicking inside the details panel keeps it open',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);
    await tester.tap(find.text('项目主目录'));
    await tester.pumpAndSettle();

    final Finder panelTitle = find.descendant(
      of: find.byType(ResourceDetailPanel),
      matching: find.text('项目主目录'),
    );
    await tester.tap(panelTitle.first);
    await tester.pumpAndSettle();

    expect(find.byType(ResourceDetailPanel), findsOneWidget);
  });

  testWidgets('file rows open an info panel without a mind map',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);

    await tester.tap(find.text('预算表 2026'));
    await tester.pumpAndSettle();

    expect(find.byType(ResourceDetailPanel), findsOneWidget);
    expect(find.byType(MindMap), findsNothing);
    expect(find.text(r'D:\Finance\budget.xlsx'), findsWidgets);
  });

  testWidgets('quick links hotkey opens the tree HUD and Escape returns',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);
    expect(find.byTooltip('新增资源'), findsOneWidget);

    api.emitHotkey('quickLinks');
    await tester.pumpAndSettle();

    // The full-window chrome is replaced by the compact tree panel.
    expect(find.byTooltip('新增资源'), findsNothing);
    expect(find.text('开发'), findsOneWidget);
    expect(find.text('GitHub'), findsOneWidget);
    expect(find.text('网站'), findsOneWidget);

    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
    expect(find.byTooltip('新增资源'), findsOneWidget);
  });

  testWidgets('quick HUD Enter opens the selected site and closes',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);

    api.emitHotkey('quickLinks');
    await tester.pumpAndSettle();
    // First selectable row is pre-selected; Enter activates it.
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();

    expect(api.openCalls, 1);
    expect(find.byTooltip('新增资源'), findsOneWidget);
  });

  testWidgets('quick folder tree expands lazily and search filters it',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);

    api.emitHotkey('quickFolders');
    await tester.pumpAndSettle();
    expect(find.text('项目主目录'), findsOneWidget);
    expect(find.text('文件夹'), findsOneWidget);

    // The first chevron belongs to the first expandable folder resource.
    await tester.tap(find.byIcon(Icons.chevron_right).first);
    await tester.pumpAndSettle();
    expect(api.listChildrenCalls, 1);
    expect(find.text('README.md'), findsOneWidget);

    await tester.enterText(find.byType(TextField), '预算');
    await tester.pumpAndSettle();
    expect(find.text('预算表 2026'), findsOneWidget);
    expect(find.text('项目主目录'), findsNothing);
  });

  testWidgets('quick HUD Tab switches between the two trees',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);

    api.emitHotkey('quickFolders');
    await tester.pumpAndSettle();
    expect(find.text('文件夹'), findsOneWidget);

    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    expect(find.text('网站'), findsOneWidget);
    expect(find.text('GitHub'), findsOneWidget);
  });

  testWidgets('clicking a quick HUD row opens it through the shell api',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);

    api.emitHotkey('quickLinks');
    await tester.pumpAndSettle();
    await tester.tap(find.text('GitHub'));
    await tester.pumpAndSettle();

    expect(api.openCalls, 1);
    expect(find.byTooltip('新增资源'), findsOneWidget);
  });

  testWidgets('runner quickDismissed notification closes the HUD',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);
    api.emitHotkey('quickLinks');
    await tester.pumpAndSettle();
    expect(find.byTooltip('新增资源'), findsNothing);

    await _emitQuickDismiss();
    await tester.pumpAndSettle();
    expect(find.byTooltip('新增资源'), findsOneWidget);
  });

  testWidgets('opened-from-tray dismiss hides the window before restoring it',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    final List<MethodCall> calls = <MethodCall>[];
    await pumpApp(
      tester,
      api: api,
      shellHandler: (MethodCall call) async {
        calls.add(call);
        if (call.method == 'isVisible') {
          return false; // the window was in the tray when the hotkey fired
        }
        return null;
      },
    );
    api.emitHotkey('quickLinks');
    await tester.pumpAndSettle();
    expect(find.byTooltip('新增资源'), findsNothing);

    await _emitQuickDismiss();
    await tester.pumpAndSettle();

    final MethodCall exit = calls.lastWhere(
      (MethodCall call) => call.method == 'exitQuickMode',
    );
    expect(
      (exit.arguments as Map<Object?, Object?>)['visibility'],
      'hide',
      reason: 'a tray-opened panel must hide before geometry is restored',
    );
    expect(find.byTooltip('新增资源'), findsOneWidget);
  });

  testWidgets('visible-window dismiss repaints before restoring geometry',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    final List<MethodCall> calls = <MethodCall>[];
    await pumpApp(
      tester,
      api: api,
      shellHandler: (MethodCall call) async {
        calls.add(call);
        if (call.method == 'isVisible') {
          return true; // the full window was visible when the panel opened
        }
        return null;
      },
    );
    api.emitHotkey('quickFolders');
    await tester.pumpAndSettle();
    expect(find.text('项目主目录'), findsOneWidget);

    await _emitQuickDismiss();
    await tester.pumpAndSettle();

    final MethodCall exit = calls.lastWhere(
      (MethodCall call) => call.method == 'exitQuickMode',
    );
    expect(
      (exit.arguments as Map<Object?, Object?>)['visibility'],
      'auto',
      reason: 'a visible window is restored after the full UI has repainted',
    );
    expect(find.byTooltip('新增资源'), findsOneWidget);
  });

  testWidgets('toggle-to-full from a tray-opened panel hides then shows',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    final List<MethodCall> calls = <MethodCall>[];
    await pumpApp(
      tester,
      api: api,
      shellHandler: (MethodCall call) async {
        calls.add(call);
        if (call.method == 'isVisible') {
          return false;
        }
        return null;
      },
    );
    api.emitHotkey('quickLinks');
    await tester.pumpAndSettle();
    expect(find.byTooltip('新增资源'), findsNothing);

    api.emitHotkey('toggle');
    await tester.pumpAndSettle();

    final List<String> methods =
        calls.map((MethodCall call) => call.method).toList();
    final int exitIndex = methods.lastIndexOf('exitQuickMode');
    final MethodCall exit = calls[exitIndex];
    expect((exit.arguments as Map<Object?, Object?>)['visibility'], 'hide');
    expect(
      methods.indexOf('show', exitIndex),
      greaterThan(exitIndex),
      reason: 'the full window is shown after the panel is gone',
    );
    expect(find.byTooltip('新增资源'), findsOneWidget);
  });

  testWidgets('clicking inside the quick panel keeps it open', (
    WidgetTester tester,
  ) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);
    api.emitHotkey('quickLinks');
    await tester.pumpAndSettle();
    expect(find.byTooltip('新增资源'), findsNothing);

    // Blank space inside the HUD must not dismiss it (Phase 18.1); only an
    // outside click (runner WM_ACTIVATE -> quickDismissed) closes the panel.
    await tester.tapAt(const Offset(800, 900));
    await tester.pumpAndSettle();
    expect(find.byTooltip('新增资源'), findsNothing);

    final TextField search = tester.widget<TextField>(
      find.byType(TextField).first,
    );
    expect(search.focusNode?.hasFocus, isTrue);

    await _emitQuickDismiss();
    await tester.pumpAndSettle();
    expect(find.byTooltip('新增资源'), findsOneWidget);
  });

  testWidgets('overflow menu syncs browser bookmarks and reports the result',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);

    await tester.tap(find.byTooltip('更多操作'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('同步浏览器书签'));
    await tester.pumpAndSettle();

    expect(api.syncBookmarkCalls, 1);
    expect(find.textContaining('同步完成'), findsOneWidget);
  });

  testWidgets('a background bookmark event refreshes the sites list',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);
    api.addBookmarkLink(
      const ResourceItem(
        id: 'event-1',
        name: 'Bookmarked Site',
        path: 'https://bookmarked.example',
        kind: ResourceKind.link,
        category: '书签栏',
      ),
    );

    api.emitBookmarkEvent(1);
    await tester.pumpAndSettle();
    expect(find.textContaining('已从浏览器同步'), findsOneWidget);

    await tester.tap(find.text('网站'));
    await tester.pumpAndSettle();
    expect(find.text('Bookmarked Site'), findsOneWidget);
  });

  testWidgets('settings exposes bookmark sync and persists the switch',
      (WidgetTester tester) async {
    final List<AppSettings> saved = <AppSettings>[];
    await pumpApp(
      tester,
      onSettingsChanged: (AppSettings settings) async => saved.add(settings),
    );
    await openSettings(tester);
    expect(find.text('浏览器书签同步'), findsOneWidget);
    expect(find.textContaining('已检测到 1 个浏览器配置'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey<String>('bookmark-sync-switch')));
    await tester.pumpAndSettle();
    expect(saved, isNotEmpty);
    expect(saved.last.bookmarkSyncEnabled, isFalse);
  });

  testWidgets('delete offers to remove the matching browser bookmark',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi()
      ..bookmarkMatchesResult = const <BookmarkMatch>[
        BookmarkMatch(
          url: 'https://github.com',
          title: 'GitHub',
          label: 'Chrome · Default',
        ),
      ]
      ..extensionConnected = true;
    final List<AppSettings> saved = <AppSettings>[];
    await pumpApp(
      tester,
      api: api,
      onSettingsChanged: (AppSettings settings) async => saved.add(settings),
    );

    await tester.tap(find.text('网站'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('GitHub'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('删除'));
    await tester.pumpAndSettle();

    expect(find.text('删除确认'), findsOneWidget);
    expect(find.byKey(const ValueKey<String>('delete-browser-checkbox')),
        findsOneWidget);
    await tester.tap(find.byKey(const ValueKey<String>('delete-browser-checkbox')));
    await tester.tap(find.byKey(const ValueKey<String>('delete-browser-remember')));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, '删除'));
    await tester.pumpAndSettle();

    expect(api.lastDeleteRemovedFromBrowser, isTrue);
    expect(saved.last.bookmarkDeleteMode, kBookmarkDeleteRemove);
    expect(find.text('GitHub'), findsNothing);
  });

  testWidgets('a browser-side unbookmark removes the synced resource',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi();
    await pumpApp(tester, api: api);

    api.emitBookmarkRemoved(1);
    await tester.pumpAndSettle();
    expect(find.textContaining('浏览器端取消了 1 个收藏'), findsOneWidget);
  });

  testWidgets('settings reports the browser extension connection',
      (WidgetTester tester) async {
    final FakeApi api = FakeApi()..extensionConnected = true;
    await pumpApp(tester, api: api);
    await openSettings(tester);
    expect(find.textContaining('浏览器扩展：已连接'), findsOneWidget);
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
/// Delivers the runner's "close the quick panel" notification.
Future<void> _emitQuickDismiss() {
  return TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
      .handlePlatformMessage(
    'resource_hub/window',
    const StandardMethodCodec().encodeMethodCall(
      MethodCall('quickDismissed'),
    ),
    (ByteData? _) {},
  );
}
