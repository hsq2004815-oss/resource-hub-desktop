/// Strings that only the Flutter UI needs.
///
/// `strings.g.dart` is generated from the legacy Python `STRINGS` dict and must
/// stay a faithful copy — editing `resource_hub.pyw` is out of scope for the
/// migration. Anything the new UI adds on top (theme labels, phase banners) lives
/// here instead, and [AppStringsExtra.tx] falls back to the generated table so
/// callers never need to know which source a key came from.
library;

import 'strings.g.dart';

const Map<String, Map<String, String>> kAppOnlyStrings =
    <String, Map<String, String>>{
  'zh': <String, String>{
    'settings_theme': '外观主题',
    'theme_light': '浅色',
    'theme_system': '跟随系统',
    'theme_dark': '深色',
    'settings_pending_note': '全局热键与开机启动将在后端接入后提供编辑入口，'
        '当前展示的是原应用中的取值。',
    'demo_badge': 'Phase 2 · 设计系统预览（未接后端，数据为演示数据）',
    'backend_connecting': '正在连接后端…',
    'backend_failed_title': '后端启动失败',
    'backend_failed_hint': '应用需要 Python 3.11+ 才能读写数据。',
    'retry': '重试',
    'data_corrupt_title': '数据文件无法读取',
    'data_corrupt_body': '为避免覆盖原有内容，已停止读写。'
        '请检查 sites.json / folders.json 是否完整，修复后重启应用。',
    'read_only_badge': '只读',
    'data_corrupt': '数据文件损坏，已停止读写。',
    'browse_pending': '文件选择器尚未接入（下一步完成）。',
    'view_list': '列表视图',
    'view_grid': '网格视图',
    'hotkey_registered': '全局热键已生效：{0}',
    'hotkey_unavailable_reason': '全局热键 {0} 被其他程序占用，暂不可用。',
  },
  'en': <String, String>{
    'settings_theme': 'Appearance',
    'theme_light': 'Light',
    'theme_system': 'System',
    'theme_dark': 'Dark',
    'settings_pending_note': 'Global hotkey and launch-at-startup become editable '
        'once the backend is wired in. The values shown are from the original app.',
    'demo_badge': 'Phase 2 · Design system preview (no backend, demo data)',
    'backend_connecting': 'Connecting to the backend…',
    'backend_failed_title': 'Backend failed to start',
    'backend_failed_hint': 'The app needs Python 3.11+ to read and write data.',
    'retry': 'Retry',
    'data_corrupt_title': 'Data files cannot be read',
    'data_corrupt_body': 'Reading and writing have been stopped so the existing '
        'files are not overwritten. Check sites.json / folders.json, then restart.',
    'read_only_badge': 'Read-only',
    'data_corrupt': 'Data files are corrupt; reading and writing are stopped.',
    'browse_pending': 'File picker not wired yet (next step).',
    'view_list': 'List view',
    'view_grid': 'Grid view',
    'hotkey_registered': 'Global hotkey active: {0}',
    'hotkey_unavailable_reason': 'Global hotkey {0} is taken by another app.',
  },
};

extension AppStringsExtra on AppStrings {
  /// Looks up an app-only key, falling back to the generated table.
  ///
  /// Supports the same `{0}` / `{1}` placeholders as [AppStrings.t].
  String tx(String key, [List<Object?> args = const <Object?>[]]) {
    final String raw = kAppOnlyStrings[language.code]?[key] ??
        kAppOnlyStrings['zh']?[key] ??
        t(key);
    if (args.isEmpty) {
      return raw;
    }
    String out = raw;
    for (int i = 0; i < args.length; i++) {
      out = out.replaceAll('{$i}', '${args[i] ?? ''}');
    }
    return out;
  }
}
