# Phase 20 — 产品改名：「常用资源工具」→「抽屉 Drawer」

- 日期：2026-10-18
- 触发：用户觉得「常用资源工具」名字太土，希望换一个时尚一点的名字；讨论后选定 **抽屉 / Drawer**。
- 范围：**只改显示名**，不改 exe 文件名、数据文件路径、注册表键路径、单实例互斥名等内部标识；
  因此没有数据迁移风险，旧数据/设置/扩展协议都原样兼容。

## 1. 名字映射

| 位置 | 旧 | 新 |
|---|---|---|
| 窗口标题（中） | 常用资源工具 | **抽屉** |
| 窗口标题（英） | Resource Hub Desktop | **Drawer** |
| 托盘图标提示 | Resource Hub | **抽屉 Drawer** |
| 右键菜单（文件夹图标） | 添加到常用资源工具 | **添加到抽屉** |
| 右键菜单（文件夹内空白处） | 添加当前文件夹到常用资源工具 | **添加当前文件夹到抽屉** |
| 浏览器扩展名 | Resource Hub 书签桥 | **抽屉书签桥**（v1.1.0） |
| 开机启动快捷方式 | `Resource Hub.lnk` | **`抽屉.lnk`**（旧快捷方式自动删除） |
| 发布包说明/文档标题 | Resource Hub | **抽屉 Drawer** |
| exe 文件名 / 数据文件 / 注册表键路径 / 扩展目录名 | `resource_hub.exe` 等 | **保持不变**（技术标识） |
| 单实例互斥名 / 后端协议 / HTTP bridge 的 `app: resource-hub` | 不变 | 不变（兼容） |

## 2. 实现

- Dart：`window_title` 走 `app_strings_ext.dart` 的 app-only 翻译（`抽屉` / `Drawer`），
  `main.dart` 用 `strings.tx('window_title')`（窗口标题 + MaterialApp title）；生成的
  `strings.g.dart` 不改（它是旧 Python 字符串表的镜像）。
- Runner：
  - `flutter_window.cpp` 托盘提示改为「抽屉 Drawer」；
  - `main.cpp` 窗口初始标题用 `\u62BD\u5C49`（Flutter 启动后按语言覆盖）；
  - `native_shell.cpp`：
    - 右键菜单文案改为「添加到抽屉」/「添加当前文件夹到抽屉」（注册表键路径不变，下次启动自动覆盖旧文案）；
    - 开机启动快捷方式改名为 `抽屉.lnk`，`SetLaunchAtStartup(true)` 时删除旧的 `Resource Hub.lnk`，
      关闭时两个都删；
  - `Runner.rc` 的 FileDescription/ProductName 改为 `Drawer`（文件属性里可见）；
- 扩展：`manifest.json` 名称/描述/default_title 改为「抽屉书签桥」，版本 1.1.0；日志前缀改「[抽屉]」；
  `check_protocol.py` 同步期望值。
- 文档：根 README / 发布包 README / 迁移索引改用新名字；历史阶段文档保留旧文案并加注。

## 3. 验证

| 项 | 结果 |
|---|---|
| 窗口标题实测 | `GetWindowTextW` → **抽屉** |
| 右键菜单注册表 | 「添加到抽屉」/「添加当前文件夹到抽屉」两个入口都正确 |
| 开机启动快捷方式迁移 | 启动后 Startup 目录：`Resource Hub.lnk` 消失、`抽屉.lnk` 出现 |
| `verify_context_menu.py` | **10 / 10 PASS**（含两个入口的 label/command 校验） |
| `verify_quick_panel.py` | 10 / 10 PASS |
| `verify_shell.py` | 9 / 9 PASS |
| Flutter 测试 | 69 / 69（窗口标题是原生标题栏，不受文本测试影响） |
| 扩展自检 | `check_protocol.py` 52 PASS，manifest 名称/版本校验通过 |
| 后端 | 271 / 271（本次未改协议/数据） |

截图：`migration/screenshots/phase20-title.png`（标题栏显示「抽屉」）。

## 4. 注意事项

- 浏览器扩展如果已经加载：Chrome/Edge 需要到扩展管理页点一次 **重新加载**（或重启浏览器）才会看到
  新名称「抽屉书签桥」；功能与端口协议完全不变，不重新加载也能继续用。
- 右键菜单文案在下次启动工具时自动更新，无需手动操作。
- 开机启动：如果之前开着，启动一次后旧 `Resource Hub.lnk` 会被清掉并换成 `抽屉.lnk`。
- 想彻底改名（exe、安装目录、注册表键路径、扩展目录）需要额外做数据/快捷方式/单实例迁移，本次
  按用户选择没有做；当前显示名与内部名分离，后续需要时可以作为单独 Phase 完成。
