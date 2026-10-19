# Phase 23 — 思维导图拖动修复（画布拖动更跟手）

- 日期：2026-10-18
- 触发：用户截了文件夹详情面板的思维导图，反馈「拖动似乎还不够丝滑，经常会有拖动没反应；
  应该是鼠标按住除了文件夹（节点卡片）以外的位置就可以丝滑地拖动」。
- 结论：不是手感调参问题，而是**命中测试 bug**：连线绘制用的 `CustomPaint` 默认把整块内容矩形都
  当成可命中区域，抢走了画布背景的平移手势；再加上每次拖动都整树重建，才出现「大多数位置拖不动、
  偶尔拖得动但发涩」。

## 1. 根因

`mind_map.dart` 的结构是：最底层 `GestureDetector` 负责空白画布平移，上层 `Transform` 里放内容
（连线 `CustomPaint` + 节点卡片）。但 Flutter 的 `RenderCustomPaint.hitTestSelf` 是：

```dart
bool hitTestSelf(Offset position) {
  return _painter != null && (_painter!.hitTest(position) ?? true);
}
```

`CustomPainter.hitTest` 默认返回 `null` → 变成 `true` → **整个内容矩形（尺寸 = 地图内容大小）都被连线
层挡住**。于是：

| 拖动起点 | 修复前 |
|---|---|
| 内容矩形以外的空白（地图四周留白） | 能拖（所以偶尔有反应） |
| 内容矩形以内、节点之间的空白（层级间隙/上下留白） | **被 `_EdgePainter` 吞掉，完全没反应** |
| 节点卡片上 | 只触发选中的 tap，不平移 |
| 20px 的小折叠按钮上 | 只触发展开/收起 |

思维导图内容通常占满面板，所以用户实际拖到的绝大多数点都在内容矩形里 → 「经常没反应」。

第二个问题是流畅度：拖动时每帧 `setState` → `build` → `_layout()` 用 `TextPainter` 重新测量
**每个节点**的宽度，然后重建所有节点 widget；鼠标事件 100+ Hz 时明显掉帧。

## 2. 修复

### 2.1 命中测试（关键）

```dart
class _EdgePainter extends CustomPainter {
  // 连线只是装饰，不能接管指针；否则内容矩形内的空白全部拖不动。
  @override
  bool? hitTest(Offset position) => false;
  ...
}
```

这样连线层不再吞事件，空白处会继续冒泡到背景平移 `GestureDetector`。

### 2.2 去除死区：节点/占位/折叠按钮也参与平移

节点卡片、折叠按钮、加载/空目录/出错占位符的 `GestureDetector` 都加上了同一组
`onPanStart/onPanUpdate/onPanEnd/onPanCancel`（增量直接加到偏移量）。单击/双击/右键/展开收起的
语义不变：选中仍在 `onTapDown` 立刻发生，只有超过拖动阈值才变成平移。

### 2.3 拖动跟手

- `dragStartBehavior: DragStartBehavior.down`：鼠标平移阈值是
  `kPrecisePointerPanSlop = 2`，默认 `.start` 会把阈值内的位移丢掉；改成 `.down` 后
  按下第一像素就开始累计位移。
- 光标反馈：画布 `grab`、拖动中 `grabbing`、节点/折叠按钮 `click`。

### 2.4 拖动不再重建节点树

- 缩放/平移从 `State` 字段改成 `ValueNotifier<_MapView>`（`_zoom`/`_offset` 变成 getter），
  `ValueListenableBuilder` 只包住 `Transform`：拖动时只重建这一个包装层，节点树不动。
- 内容外包 `RepaintBoundary`，平移/缩放只改图层变换，不重绘节点。
- 布局缓存 `_layoutDirty`：只有展开/折叠/加载/主题变化才重新跑 `_layout()`（`TextPainter` 测量），
  平移时不再重复测量。

## 3. 代码改动

| 文件 | 改动 |
|---|---|
| `app/lib/widgets/mind_map.dart` | `_EdgePainter.hitTest => false`；`_view` notifier + `ValueListenableBuilder`/`RepaintBoundary`；`_layoutDirty` 缓存；`dragStartBehavior.down`；节点/占位/折叠按钮平移；grab/grabbing 光标；内容层加 `mind-map-content` key（测试定位用） |
| `app/test/widget_test.dart` | 新增 2 个回归测试：①空白画布（内容矩形内）拖动平移；②从节点卡片拖动也平移且不触发打开 |
| `migration/tools/verify_mind_map_drag.py` | 实机回归脚本：临时复制发布包 + 造数据 + 截图测像素位移 |

## 4. 验证

### 4.1 Flutter

```powershell
cd app; F:\flutter\bin\flutter.bat analyze          # No issues found!
F:\flutter\bin\flutter.bat test                     # 75/75 passed（原 73 + 新增 2）
```

两个新测试的断言：`tester.startGesture(..., kind: mouse)` 分 6 步拖动 (±46/±30) 后，
节点屏幕坐标位移与拖拽位移一致（误差 ≤1.5px），并确认没有触发打开/重复列目录。
回归意义：修复前两条都会失败（空白点被连线层吞掉、节点拖动无位移）。

### 4.2 实机像素验证

`verify_mind_map_drag.py` 把发布包复制到临时目录、写入一条指向 `qa-tree` 的文件夹资源并启动，
点击第一行打开思维导图；对 4 个起点各做「拖 (+60,+40) 再拖回来」：

| 起点 | 说明 | 旧包 `20261018-2320` | 新包 `20261018-2215` |
|---|---|---|---|
| `control` | 内容矩形左侧空白（修复前也能拖） | moved 0.065（能拖，但拖回不精确，因为回程起点落进内容矩形被吞） | moved 0.070 / restored 0.000 |
| `margin_above` | 节点上方留白，**在内容矩形内** | **moved 0.000（完全没反应）** | moved 0.070 / restored 0.000 |
| `root_card` | 根节点卡片上 | moved 0.005（只是 hover 高亮） | moved 0.070 / restored 0.000 |
| `column_gap` | 根节点与子节点列之间的空白，**在内容矩形内** | moved 0.005（只是 hover 高亮） | moved 0.070 / restored 0.000 |

结论：旧包 3/4 起点拖不动（只有内容外的 control 能动），新包 4/4 起点都能平移且能精确拖回，
像素位移 = 鼠标位移（125% DPI 下 60/40 物理像素）。截图见
`migration/screenshots/phase23-drag-{old,new}-margin_above-{before,after}.png` 与
`phase23-panel.png`。

```powershell
# 新包应全过（4/4）
D:\miniconda3\python.exe migration\tools\verify_mind_map_drag.py `
    --build release\ResourceHub-Desktop-20261018-2215 --label new
# 旧包应复现问题（control 能动、其余 3 个拖不动），用于回归对比
D:\miniconda3\python.exe migration\tools\verify_mind_map_drag.py `
    --build release\ResourceHub-Desktop-20261018-2320 --label old --expect fail
```

脚本用 `SetWindowPos(TOPMOST)` 把 QA 窗口置顶，避免截图被其它窗口遮挡；临时目录用完即删，
不动真实数据、不写注册表。

## 5. 备注

- 现在**按住节点卡片拖动也会平移**（单击仍选中、双击仍打开、右键菜单不变）。这是为了消灭
  「内容矩形内全是死区」；若后续觉得节点上拖动应保留给别的交互，再单独加阈值即可。
- 滚轮平移、`Ctrl+滚轮` 缩放、双击空白 Fit、工具栏 ±/Fit、方向键选择等原有交互未改。
- 内部命名/数据格式均未改，无迁移。
