// Unit tests for the export/import file format.
//
// Plain `test` (not `testWidgets`): the widget-test binding runs in a fake-async
// zone without a real event loop, so `dart:io` futures never complete there.
// This file exercises the same file format the legacy app wrote.

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:resource_hub/util/json_backup.dart';

void main() {
  late Directory temp;

  setUp(() async {
    temp = await Directory.systemTemp.createTemp('rh-json-backup');
  });

  tearDown(() async {
    await temp.delete(recursive: true);
  });

  String path(String name) => '${temp.path}${Platform.pathSeparator}$name';

  test('writes the legacy format: UTF-8, indent 2, no ASCII escaping', () async {
    final String target = path('backup.json');
    await JsonBackup.write(target, <Map<String, dynamic>>[
      <String, dynamic>{
        'name': '设计资源',
        'path': r'D:\资源\设计',
        'kind': 'folder',
        'category': '__uncategorized__',
        'favorite': false,
        'note': '中文备注',
      },
    ]);

    final String raw = await File(target).readAsString(encoding: utf8);
    expect(raw, contains('"设计资源"'));
    expect(raw, isNot(contains(r'\u8bbe')));
    expect(raw, contains('\n    ')); // indent=2 puts keys two levels deep
    expect(jsonDecode(raw), isA<List<dynamic>>());
  });

  test('round-trips a collection without losing fields', () async {
    final String target = path('roundtrip.json');
    final List<Map<String, dynamic>> items = <Map<String, dynamic>>[
      <String, dynamic>{
        'name': 'GitHub',
        'url': 'https://github.com',
        'category': '开发',
        'favorite': true,
        'note': '代码托管',
      },
      <String, dynamic>{
        'name': '下载',
        'path': r'C:\Users\me\Downloads',
        'kind': 'folder',
      },
    ];

    await JsonBackup.write(target, items);
    final List<Map<String, dynamic>> loaded = await JsonBackup.read(target);

    expect(loaded, hasLength(2));
    expect(loaded.first['name'], 'GitHub');
    expect(loaded.first['favorite'], isTrue);
    expect(loaded.last['path'], r'C:\Users\me\Downloads');
  });

  test('rejects files that are not a JSON array of objects', () async {
    final String notArray = path('object.json');
    await File(notArray).writeAsString('{"name": "x"}');
    await expectLater(JsonBackup.read(notArray), throwsFormatException);

    final String notJson = path('broken.json');
    await File(notJson).writeAsString('not json at all');
    await expectLater(JsonBackup.read(notJson), throwsFormatException);

    final String wrongItems = path('numbers.json');
    await File(wrongItems).writeAsString('[1, 2, 3]');
    await expectLater(JsonBackup.read(wrongItems), throwsFormatException);
  });
}
