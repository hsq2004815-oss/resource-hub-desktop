# Phase 10 — 删除内容区顶部栏（设置移到工具栏）

- 日期：2026-10-18
- 触发：用户看完 Phase 9 的界面后反馈"这个顶部还是看起来不好，直接删了吧，设置换个地方放置"
- 范围：**只改布局**；不碰 `backend/`、数据格式、面板/mind map 逻辑

---

## 1. 变更

- 删除 `app/lib/features/home/app_top_bar.dart`（Phase 7 的 56px 栏：应用图标 + 短标题 + 设置齿轮）。
- `HomePage` 的 Column 从 `[AppTopBar, 工作区, 状态栏]` 变为 `[工作区, 状态栏]`：
  内容直接开始于原生 Windows 标题栏下方，列表垂直空间增加 56px，层级只剩一道状态栏细线。
- **设置入口**移到工作区第二行工具栏最右侧：`ToolbarButton(Icons.settings_outlined, tooltip=设置)`，
  由 `ResourceListPanel` 的 `onOpenSettings` 回调打开原 `SettingsDialog`；语言/主题/热键/开机启动都在里面。
- 窗口标题仍由原生标题栏显示"常用资源工具"（runner 固定标题，不依赖 Dart UI），所以删掉内容区标题不会丢窗口名。
- 测试同步：
  - 删除 `AppTopBar` 的 import 与断言；
  - 新断言：内容区没有"常用资源工具"文案、工作区标题 `已保存资源` 的 y 坐标 < 120（即没有 56px 栏）、
    工具栏存在「设置」按钮且能打开设置对话框；
  - `openSettings` helper 仍用 tooltip「设置」定位，其它测试不变。
- 新增截图：`phase10-no-top-bar.png`（新布局）、`phase10-settings.png`（工具栏齿轮打开设置）、`phase10-app.png`。

## 2. 验证

| 项 | 结果 |
|---|---|
| `flutter analyze` | 0 issue |
| Flutter 测试 | **50 / 50**（只改写 1 个顶部栏测试，新增"内容区无顶部栏 / 设置进工具栏"断言；数量不变） |
| 最小窗口 1180×760 | 现有 widget 测试覆盖，无溢出（工具栏仍放得下搜索/筛选/图标/设置） |
| 实机 | 启动直接看到工作区；点工具栏齿轮打开设置对话框（截图）；`verify_shell.py` **9/9 PASS** |
| 发布包 | 47.9 MB，合并进 `release\ResourceHub-Desktop-20261017-1835\`，用户数据未变 |

## 3. 已知取舍

- 没有菜单栏，也没有快捷键（后续可加 `Ctrl+,` 打开设置）。
- 与 Phase 7 文档里的"56px AppTopBar"描述冲突，以本文件为准；Phase 7 文档只作历史记录。
