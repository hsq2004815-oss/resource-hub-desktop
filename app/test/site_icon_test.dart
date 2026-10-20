import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:resource_hub/models/resource_item.dart';
import 'package:resource_hub/widgets/site_icon.dart';

/// 1x1 transparent PNG.
const String _pngBase64 =
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk'
    'YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==';

ResourceItem _link(String url) => ResourceItem(
      id: 'l1',
      name: 'GitHub',
      path: url,
      kind: ResourceKind.link,
    );

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: Center(child: child)));

void main() {
  testWidgets('falls back to the generic glyph without a cached icon',
      (WidgetTester tester) async {
    FaviconIndex.update(const <String, String>{});
    await tester.pumpWidget(_wrap(SiteIcon(
      item: _link('https://github.com/'),
      fallback: Icons.link,
      size: 20,
    )));
    expect(find.byIcon(Icons.link), findsOneWidget);
    expect(find.byType(Image), findsNothing);
  });

  testWidgets('renders the cached file once the host has an icon',
      (WidgetTester tester) async {
    final Directory dir = await tester.runAsync(
      () => Directory.systemTemp.createTemp('favicon-test'),
    ) as Directory;
    addTearDown(() {
      // The decoded image may still hold the file open on Windows.
      PaintingBinding.instance.imageCache
        ..clear()
        ..clearLiveImages();
      try {
        dir.deleteSync(recursive: true);
      } catch (_) {}
    });
    final File file = File('${dir.path}${Platform.pathSeparator}github.png')
      ..writeAsBytesSync(base64Decode(_pngBase64));
    FaviconIndex.update(<String, String>{'github.com': file.path});
    addTearDown(() => FaviconIndex.update(const <String, String>{}));

    await tester.pumpWidget(_wrap(SiteIcon(
      item: _link('https://github.com/'),
      fallback: Icons.link,
      size: 20,
    )));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pump();

    expect(find.byType(Image), findsOneWidget);
    expect(find.byIcon(Icons.link), findsNothing);
  });

  test('only links, and only their host, resolve to an icon', () {
    FaviconIndex.update(<String, String>{'github.com': r'C:\icons\a.png'});
    expect(FaviconIndex.pathFor(_link('https://GitHub.com/x'), FaviconIndex.icons.value),
        r'C:\icons\a.png');
    expect(FaviconIndex.pathFor(_link('https://gitlab.com/x'), FaviconIndex.icons.value),
        isNull);
    final ResourceItem folder = ResourceItem(
      id: 'f1',
      name: 'docs',
      path: r'C:\docs',
      kind: ResourceKind.folder,
    );
    expect(FaviconIndex.pathFor(folder, FaviconIndex.icons.value), isNull);
    FaviconIndex.update(const <String, String>{});
  });
}
