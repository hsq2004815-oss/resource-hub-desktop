# Phase 2 — Material 3 设计系统与桌面外壳

- 日期：2026-10-17
- 范围：`app/`（新增 Flutter 工程）
- 前置：`migration/phase1-audit.md`、`migration/adr/ADR-001-tray-hotkey-ownership.md`
- 原应用 `resource_hub.pyw` **未修改**

---

## 1. 结论

Phase 2 交付了一个**可构建、可运行、有测试**的 Windows Flutter 外壳，Material 3 设计系统完整落地，中英双语与亮/暗主题均已实机验证。

| 验证项 | 结果 |
|---|---|
| `flutter analyze` | No issues found |
| `flutter test` | **11 / 11 通过** |
| `flutter build windows --release` | 通过，产物 `app/build/windows/x64/runner/Release/resource_hub.exe` |
| 实机截图 | 浅色中文 / 暗色中文 / 浅色英文 各一张（`migration/screenshots/`） |
| 窗口尺寸 | 外框 1618×1072 物理 = 客户区 **1280×820 逻辑** @125% DPI，与原 `geometry("1280x820")` 一致 |
| 文案键对齐 | 142 键 × 2 语言，**零差异**（脚本校验，见 §5） |

**能力边界（不要高估）**：本阶段**没有**任何文件 I/O、网络、子进程、托盘、全局热键、单实例、拖拽、右键菜单的系统集成。表格里的 36 条记录是 `lib/demo/demo_data.dart` 现造的演示数据。「打开」「检测路径」「浏览」等按钮只更新状态栏文案。真实数据接入是 Phase 3/4 的工作。

---

## 2. 目录结构与分层

```
app/
  lib/
    main.dart                 应用入口、语言/主题状态、窗口标题同步
    design/
      app_tokens.dart         设计令牌（颜色/间距/圆角/尺寸/动效/字体）
      app_theme.dart          ThemeData 组装 + AppSemanticColors 扩展
    l10n/
      strings.g.dart          由 Python STRINGS 生成的 142 键表（勿手改）
      strings_scope.dart      InheritedWidget + context.l10n
      app_strings_ext.dart    仅新 UI 需要的键（主题标签、Phase 标记）
    models/
      resource_item.dart      ResourceItem / ViewMode / ResourceKind / PathState
    widgets/                  与业务无关的组件库
      app_button.dart         AppButton(4 变体) / ToolbarButton
      app_card.dart           AppCard / StatCard / SectionHeader / MetaChip / StatusPill
      app_fields.dart         AppTextField / AppSearchField / AppCategoryDropdown /
                              AppReadonlyValue / AppNoteBanner
      resource_table.dart     8 列表格 + 右键菜单 + 缺失路径标色
      status_bar.dart         AppStatusBar / AppEmptyState
    features/home/
      home_page.dart          外壳与状态（筛选、选中、收藏、编辑、删除确认）
      header_bar.dart         头部：标识区 / 4 个 chip / 模式切换 / 统计卡
      resource_form.dart      左栏表单
      resource_list_panel.dart 右栏：工具栏 / 筛选行 / 表格
      settings_dialog.dart    设置对话框（语言、主题可改；热键与开机启动只读）
    demo/demo_data.dart       演示数据（Phase 3 删除）
    platform/window_title.dart 窗口标题 MethodChannel 封装
    util/formatters.dart      时间/路径/字节格式化
  test/widget_test.dart       11 个测试
  windows/runner/             已改造，见 §6
```

依赖方向单一：`features → widgets → design`，`models` 与 `util` 不依赖 UI。`demo` 只在 `features` 层被引用，删除时不影响组件库。

---

## 3. 设计令牌与旧主题的映射

旧 `THEME` 字典（`resource_hub.pyw:298-312`）被映射到 Material 3 的 `ColorScheme` 角色，保证视觉连续：

| 旧键 | 旧值 | M3 角色（浅色） |
|---|---|---|
| `accent` | `#2F6FED` | `primary`（同时是 `ColorScheme.fromSeed` 的种子） |
| `accent_soft` | `#E5EFFF` | `primaryContainer` |
| `bg` | `#EEF2F7` | `surface` |
| `panel` | `#F8FBFF` | `surfaceContainerLow` |
| `panel_alt` | `#F2F6FC` | `surfaceContainer` |
| `panel_strong` | `#FFFFFF` | `surfaceContainerLowest` |
| `hero` | `#E9F1FF` | `surfaceContainerHigh`（头部背景） |
| `border` | `#D9E2EF` | `outlineVariant` |
| `ink` | `#162033` | `onSurface` |
| `muted` | `#5F6B7D` | `onSurfaceVariant` |
| `success` | `#23724F` | `AppSemanticColors.success` |
| `danger` | `#C14943` | `error` / `AppSemanticColors.danger` |

`ColorScheme` 未建模但业务需要的颜色（成功、警告、危险、收藏星、失效路径行底色）收在 `AppSemanticColors`（`ThemeExtension`），亮暗两套，`context.semantic` 访问。

暗色不继承旧值，改由种子色推导，仅固定 surface 层级与 `primary` 以保证可读性。

其余令牌：间距 4 基数（4/8/12/16/20/24/32）、圆角 6/8/10/12/16/pill、控件高 40（紧凑 32）、表格行高 44、表头 38、侧栏 340（对齐旧 `left_panel`）。

字体 `Microsoft YaHei UI`，回退链 `Microsoft YaHei → Segoe UI → PingFang SC → Noto Sans CJK SC`。

---

## 4. 组件清单与旧控件对照

| 组件 | 替代的旧实现 | 说明 |
|---|---|---|
| `AppButton` | `RoundedButton`（`tk.Canvas` + Pillow 逐态位图，`:711`） | 4 变体：primary / secondary / ghost / danger |
| `ToolbarButton` | 列表 topbar 6 个按钮（`:2120-2133`） | 34×34，带 `selected` 态（用于"只看收藏"） |
| `StatCard` | `total` / `categories` / `visible` 三张卡（`:2018`） | 图标底色随语义色 |
| `MetaChip` | 头部 4 个 chip（`:1970-1987`） | |
| `SectionHeader` | 表单标题 + 列表标题/副标题（`:2135`） | |
| `StatusPill` | 分类/状态的内联标记 | 长文案自动省略，不溢出 |
| `AppTextField` / `AppSearchField` | `name_entry` / `path_entry` / `search_entry` | 搜索框 pill 形，带清除按钮 |
| `AppCategoryDropdown` | `ttk.Combobox`（分类与筛选） | 支持哨兵值→本地化标签映射 |
| `AppReadonlyValue` | `added_value` 只读标签 | |
| `AppNoteBanner` | `data_note` 提示块 | |
| `ResourceTable` | `ttk.Treeview` 8 列（`:2165`） | 手写表格：比例列宽、行 hover、选中、失效行标红、右键菜单、双击打开 |
| `AppStatusBar` | `status_label`（`:2334`） | 4 种语气 |
| `AppEmptyState` | `empty_label` | 加图标与副提示 |

未移植：`RoundedButton` 的位图渲染逻辑（Material 原生提供）、窗口淡入淡出动画（Phase 5）。

---

## 5. 多语言

`strings.g.dart` **不是手写的**。`migration/tools/gen_strings_dart.py` 用 `ast` 解析 `resource_hub.pyw` 的 `STRINGS` 字面量并生成 Dart 常量表：

```
D:\miniconda3\python.exe migration/tools/gen_strings_dart.py
```

生成结果：`zh` 142 键、`en` 142 键，`keys_only_in_zh=[]`、`keys_only_in_en=[]`。

- 占位符沿用 Python 的 `{0}` / `{1}`，由 `AppStrings.t(key, args)` 替换
- 缺键回退顺序与旧 `t()` 一致：当前语言 → 中文 → 键名本身
- **新 UI 独有的键**（`settings_theme`、`theme_light/system/dark`、`demo_badge` 等）放在 `app_strings_ext.dart` 的 `kAppOnlyStrings`，通过 `t.tx(key)` 访问，不污染生成文件

> 为什么不直接改 Python 的 `STRINGS`：迁移期原应用必须保持可用，任何改动都要双向维护。等 Phase 6 原应用下线后再合并。

---

## 6. 原生 runner 改动（`windows/runner/`）

| 文件 | 改动 | 原因 |
|---|---|---|
| `main.cpp` | 客户区 `1280×820`；标题改为转义写法 | 对齐 `geometry("1280x820")`；避免源码编码问题 |
| `win32_window.cpp` | `AdjustWindowRectExForDpi` 把客户区尺寸换算成外框；`WM_GETMINMAXINFO` 强制最小客户区 `1180×760` | 对齐 `minsize(1180,760)`；Tk 未声明 DPI 感知，`geometry()` 是逻辑像素，Flutter 侧同语义 |
| `flutter_window.cpp/.h` | 新增 `resource_hub/window` 方法通道，方法 `setTitle` | 窗口标题必须跟随语言（旧应用用 `self.title(self.t("window_title"))`）。Phase 5 的显示/隐藏也走这条通道 |
| `resources/app_icon.ico` | 替换为仓库根 `DesktopShortcut.ico` | 复用既有图标 |

---

## 7. 开发过程中发现并修复的缺陷

这些都是实测/测试暴露的真实问题，不是预想项：

| # | 缺陷 | 发现方式 | 修复 |
|---|---|---|---|
| 1 | `StatusPill` 在固定宽状态列溢出 14px（"路径失效" 4 个汉字放不下） | 首个 widget 测试即抛 `RenderFlex overflowed` | 文本改 `Flexible` + 省略；状态列 84 → 100 |
| 2 | 分类下拉把存储哨兵 `__uncategorized__` 直接显示给用户 | 实机截图 | `labelBuilder` 映射；补回归测试断言界面不出现 `__` 哨兵 |
| 3 | **暗色主题下所有标题不可见**（"新增资源""已保存资源"消失） | 实机暗色截图 | 根因：`Typography.material2021().black` 是浅色文字主题，近黑默认色在深底上不可读。改为 `.apply(bodyColor/displayColor: onSurface)`；补对比度回归测试 |
| 4 | 表单分类下拉只有 ~110px 宽，与上方输入框不对齐 | 实机截图 | `DropdownMenu` 会忽略外层 `SizedBox` 的紧约束、按最宽条目收缩；改为显式传 `width` |
| 5 | 英文下表头 `Favorite` 被截成 `Fa...`、筛选框 `All Categories` 被截断 | 实机英文截图 | 收藏列 48 → 96，筛选框 172 → 210 |
| 6 | 窗口标题不随语言切换（英文界面仍是"常用资源工具"） | 实机英文截图 | 新增原生方法通道，Dart 侧在语言变化时同步标题 |
| 7 | 表单内容超出面板高度但无滚动条 | 实机截图（底部提示被切） | `Scrollbar` + 独立 `ScrollController` |

**一个方法论教训**：`flutter test` 使用方块等宽的测试字体（每字符宽 = 字号），**无法复现真实字形宽度导致的截断**。我曾写了一个"表头不截断"的断言，它在真实字体下会误报。已改为只断言不抛布局异常，截断判断交给实机截图。

---

## 8. 环境注意事项

- **`flutter test` 会被系统代理打断**。本机环境带 `HTTP_PROXY` 时，`flutter_tester` 的 localhost WebSocket 握手失败，报 `Invalid WebSocket upgrade request`。运行测试前需清空代理：
  ```
  export HTTP_PROXY= HTTPS_PROXY= NO_PROXY=localhost,127.0.0.1
  ```
- **截图工具**：`migration/tools/capture_window.py`。两个坑已内置处理：(1) 进程必须在查询坐标**之前**声明 per-monitor-v2 DPI 感知，否则拿到虚拟化坐标、只抓到窗口的一部分；(2) 截图前需把窗口临时置顶，否则抓到的是别的窗口。
- **截图变体**：`app/lib/main.dart` 的 `InitialUiState` 支持 `RH_THEME=light|dark|system` 与 `RH_LANG=zh|en`，一次构建即可产出全部变体，无需用模拟点击驱动 UI（模拟点击在本机对 Flutter 窗口不可靠）。

---

## 9. 已知缺口 → Phase 3 入口

| 缺口 | 归属 |
|---|---|
| 数据层：读 `sites.json` / `folders.json` / `settings.json` | Phase 3 |
| 按 ADR-001 D3 改存储：临时文件 + `os.replace`、解析失败拒绝覆盖、`.bak` 备份 | Phase 3 |
| 托盘回调 `self.after()` → 线程安全队列 | Phase 3 |
| stdio JSON Lines 协议 + **事件通道**（热键/托盘是异步事件，原方案只有请求-响应） | Phase 4 |
| 拖拽入窗、双击打开、定位、真实路径检测、导入导出入口 | Phase 5 |
| 窗口淡入淡出与前台抢占（保留 `topmost` 闪烁技巧） | Phase 5 |
| 设置里的热键录制与冲突校验 | Phase 5 |
| 删除 `lib/demo/`，接真实数据 | Phase 3 末 |
| 表头截断的自动化回归 | 需要真实字体度量；当前靠截图人工确认 |

---

## 10. 如何运行

```powershell
cd E:\Mytools\ResourceHub-GitHub-Ready\app
flutter pub get
flutter run -d windows          # 开发
flutter test                    # 11 个测试（先清空代理）
flutter build windows --release # 产物在 build\windows\x64\runner\Release\
```

重新生成字符串表（改了 Python `STRINGS` 之后）：

```powershell
D:\miniconda3\python.exe ..\migration\tools\gen_strings_dart.py
```
