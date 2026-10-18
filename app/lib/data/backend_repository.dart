/// Typed access to the Python backend.
///
/// Wraps [BackendClient] so the UI deals in models instead of JSON maps, and so
/// every protocol method appears exactly once. All methods throw
/// [BackendException] on structured failures — the caller decides how to show it.
library;

import '../models/resource_item.dart';
import '../platform/backend_client.dart';
import 'backend_models.dart';
import 'resource_api.dart';

export 'backend_models.dart';
export 'resource_api.dart';

class BackendRepository implements ResourceApi {
  BackendRepository(this.client);

  final BackendClient client;

  @override
  Stream<BackendEvent> get events => client.events;

  Future<BackendHello> hello() async {
    return BackendHello.fromJson(await client.call('app.hello'));
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
    final String effectiveQuery = query ?? '';
    final String effectiveCategory = category ?? kAllCategories;
    final Map<String, dynamic> labels = <String, dynamic>{};
    if (uncategorizedLabel != null) {
      labels['uncategorized'] = uncategorizedLabel;
    }
    if (favoriteMark != null) {
      labels['favoriteMark'] = favoriteMark;
    }
    final Map<String, dynamic> result = await client.call(
      'resources.list',
      <String, dynamic>{
        'mode': mode.name,
        if (effectiveQuery.isNotEmpty) 'query': effectiveQuery,
        if (effectiveCategory != kAllCategories) 'category': effectiveCategory,
        if (favoritesOnly == true) 'favoritesOnly': true,
        if (labels.isNotEmpty) 'labels': labels,
      },
    );
    return ResourceListPage.fromJson(result);
  }

  @override
  Future<ResourceItem> add(
    ViewMode mode, {
    required String name,
    required String target,
    String? category,
    String? note,
  }) async {
    final Map<String, dynamic> result = await client.call(
      'resources.add',
      <String, dynamic>{
        'mode': mode.name,
        'name': name,
        'target': target,
        'category': ?category,
        'note': note ?? '',
      },
    );
    return ResourceItem.fromJson(result['item'] as Map<String, dynamic>);
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
    final Map<String, dynamic> result = await client.call(
      'resources.update',
      <String, dynamic>{
        'mode': mode.name,
        'id': id,
        'name': name,
        'target': target,
        'category': ?category,
        'note': note ?? '',
      },
    );
    return ResourceItem.fromJson(result['item'] as Map<String, dynamic>);
  }

  @override
  Future<bool> delete(ViewMode mode, String id) async {
    final Map<String, dynamic> result = await client.call(
      'resources.delete',
      <String, dynamic>{'mode': mode.name, 'id': id},
    );
    return result['deleted'] as bool? ?? false;
  }

  @override
  Future<ResourceItem> setFavorite(ViewMode mode, String id, {bool? value}) async {
    final Map<String, dynamic> result = await client.call(
      'resources.favorite',
      <String, dynamic>{
        'mode': mode.name,
        'id': id,
        'value': ?value,
      },
    );
    return ResourceItem.fromJson(result['item'] as Map<String, dynamic>);
  }

  @override
  Future<List<ResourceItem>> reorder(ViewMode mode, List<String> ids) async {
    final Map<String, dynamic> result = await client.call(
      'resources.reorder',
      <String, dynamic>{'mode': mode.name, 'ids': ids},
    );
    return (result['items'] as List<dynamic>? ?? <dynamic>[])
        .map((dynamic e) => ResourceItem.fromJson(e as Map<String, dynamic>))
        .toList();
  }

  @override
  Future<void> open(ViewMode mode, String id) async {
    await client.call(
      'resources.open',
      <String, dynamic>{'mode': mode.name, 'id': id},
    );
  }

  @override
  Future<void> reveal(ViewMode mode, String id) async {
    await client.call(
      'resources.reveal',
      <String, dynamic>{'mode': mode.name, 'id': id},
    );
  }

  @override
  Future<PathCheckOutcome> checkPaths(ViewMode mode) async {
    final Map<String, dynamic> result = await client.call(
      'resources.checkPaths',
      <String, dynamic>{'mode': mode.name},
    );
    return PathCheckOutcome(
      supported: result['supported'] as bool? ?? false,
      total: result['total'] as int? ?? 0,
      missingIds: (result['missing'] as List<dynamic>? ?? <dynamic>[])
          .map((dynamic e) => e as String)
          .toList(),
    );
  }

  @override
  Future<DropOutcome> drop(List<String> paths) async {
    final Map<String, dynamic> result = await client.call(
      'resources.drop',
      <String, dynamic>{'paths': paths},
    );
    return DropOutcome(
      added: result['added'] as int? ?? 0,
      skipped: result['skipped'] as int? ?? 0,
      invalid: result['invalid'] as int? ?? 0,
    );
  }

  @override
  Future<List<Map<String, dynamic>>> export(ViewMode mode) async {
    final Map<String, dynamic> result = await client.call(
      'resources.export',
      <String, dynamic>{'mode': mode.name},
    );
    return (result['items'] as List<dynamic>? ?? <dynamic>[])
        .map((dynamic e) => e as Map<String, dynamic>)
        .toList();
  }

  @override
  Future<ImportOutcome> import(
    ViewMode mode,
    List<Map<String, dynamic>> items,
  ) async {
    final Map<String, dynamic> result = await client.call(
      'resources.import',
      <String, dynamic>{'mode': mode.name, 'items': items},
    );
    return ImportOutcome(
      imported: result['imported'] as int? ?? 0,
      skipped: result['skipped'] as int? ?? 0,
    );
  }

  Future<AppSettings> loadSettings() async {
    final Map<String, dynamic> result = await client.call('settings.get');
    return AppSettings.fromJson(result['settings'] as Map<String, dynamic>);
  }

  Future<AppSettings> saveSettings(AppSettings settings) async {
    final Map<String, dynamic> result = await client.call(
      'settings.set',
      <String, dynamic>{'settings': settings.toJson()},
    );
    return AppSettings.fromJson(result['settings'] as Map<String, dynamic>);
  }

  @override
  Future<bool> probeHotkey(String hotkeyId) async {
    final Map<String, dynamic> result = await client.call(
      'settings.probeHotkey',
      <String, dynamic>{'hotkeyId': hotkeyId},
    );
    return result['available'] as bool? ?? false;
  }

  @override
  Future<HotkeyStatus> startHotkey() async {
    final Map<String, dynamic> result = await client.call('hotkey.start');
    return HotkeyStatus(
      registered: result['registered'] as bool? ?? false,
      label: result['label'] as String? ?? '',
      reason: result['reason'] as String?,
    );
  }

  @override
  Future<void> stopHotkey() async {
    await client.call('hotkey.stop');
  }
}
