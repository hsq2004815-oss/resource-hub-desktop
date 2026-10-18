// End-to-end test for BackendClient against the real Python backend.
//
// Spawns `python ../backend/main.py <tempdir>` and speaks the JSON Lines
// protocol over actual pipes, so this covers UTF-8 encoding, LF framing and
// request/response correlation — the parts a pure Dart fake cannot exercise.
//
// Skipped when no Python interpreter is available. The backend uses only the
// standard library, so any Python >= 3.11 works (no virtualenv needed).

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:resource_hub/platform/backend_client.dart';

String? _findPython() {
  final String? override = Platform.environment['RH_PYTHON'];
  if (override != null && override.isNotEmpty) {
    return override;
  }
  for (final String candidate in <String>['python', 'python3']) {
    try {
      final ProcessResult result = Process.runSync(candidate, <String>['--version']);
      if (result.exitCode == 0) {
        return candidate;
      }
    } on ProcessException {
      continue;
    }
  }
  return null;
}

void main() {
  final String? python = _findPython();
  final String backendScript =
      File('../backend/main.py').absolute.path;

  if (python == null || !File(backendScript).existsSync()) {
    test('backend integration', () {}, skip: 'python or backend/main.py not found');
    return;
  }

  late Directory tempDir;
  late BackendClient client;

  setUpAll(() async {
    tempDir = await Directory.systemTemp.createTemp('rh-backend-test');
    client = await BackendClient.start(
      executable: python,
      scriptPath: backendScript,
      baseDir: tempDir.path,
    );
  });

  tearDownAll(() async {
    await client.close();
    await tempDir.delete(recursive: true);
  });

  test('app.hello reports protocol version and data status', () async {
    final Map<String, dynamic> result = await client.call('app.hello');
    expect(result['protocolVersion'], 1);
    expect(result['dataStatus'], 'ok');
    expect(result['loadError'], isNull);
    expect(result['methods'], contains('resources.list'));
  });

  test('resources.list seeds sample data on first run', () async {
    final Map<String, dynamic> result =
        await client.call('resources.list', <String, dynamic>{'mode': 'links'});
    expect(result['total'], 2);
    final List<dynamic> items = result['items'] as List<dynamic>;
    expect(items.length, 2);
    expect((items.first as Map<String, dynamic>)['url'], startsWith('https://'));
  });

  test('add round-trips Chinese text through real pipes', () async {
    final Map<String, dynamic> added = await client.call(
      'resources.add',
      <String, dynamic>{
        'mode': 'links',
        'name': '内部知识库',
        'target': 'wiki.example.com',
        'note': '中文备注',
      },
    );
    final Map<String, dynamic> item = added['item'] as Map<String, dynamic>;
    expect(item['name'], '内部知识库');
    expect(item['url'], 'https://wiki.example.com');

    final Map<String, dynamic> listed =
        await client.call('resources.list', <String, dynamic>{'mode': 'links'});
    final List<dynamic> items = listed['items'] as List<dynamic>;
    expect(
      items.map((dynamic e) => (e as Map<String, dynamic>)['name']),
      contains('内部知识库'),
    );
  });

  test('structured errors surface code and i18n key', () async {
    await expectLater(
      client.call(
        'resources.add',
        <String, dynamic>{'mode': 'links', 'name': '', 'target': 'https://a.test'},
      ),
      throwsA(
        isA<BackendException>()
            .having((BackendException e) => e.code, 'code', 'validation')
            .having((BackendException e) => e.key, 'key', 'enter_link_name'),
      ),
    );
  });

  test('unknown method is reported, not crashed on', () async {
    await expectLater(
      client.call('resources.nope'),
      throwsA(
        isA<BackendException>()
            .having((BackendException e) => e.code, 'code', 'unknown_method'),
      ),
    );
  });

  test('settings round-trip', () async {
    final Map<String, dynamic> saved = await client.call(
      'settings.set',
      <String, dynamic>{
        'settings': <String, dynamic>{'language': 'en', 'globalHotkeyId': 'control+shift+q'},
      },
    );
    final Map<String, dynamic> settings = saved['settings'] as Map<String, dynamic>;
    expect(settings['language'], 'en');
    expect(settings['globalHotkeyId'], 'Ctrl + Shift + Q');

    final Map<String, dynamic> loaded = await client.call('settings.get');
    expect((loaded['settings'] as Map<String, dynamic>)['language'], 'en');
  });

  test('close() shuts the backend down', () async {
    final BackendClient other = await BackendClient.start(
      executable: python,
      scriptPath: backendScript,
      baseDir: tempDir.path,
    );
    await other.close();
    expect(
      () => other.call('app.hello'),
      throwsA(isA<StateError>()),
    );
  });
}
