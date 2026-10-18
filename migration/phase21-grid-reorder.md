# Phase 21 — 网格视图拖动排序更顺滑

- 日期：2026-10-18
- 触发：用户反馈「网格视图的拖动交换顺序交互太僵硬，希望效果像列表视图一样舒服」。
- 结论：重写网格的拖动布局——不再只画一根 2px 插入线等松手后跳变，而是拖动过程中**卡片实时让位、
  带 180ms 动画**，拖动项变成虚线占位框，松手才提交顺序。

## 1. 之前为什么僵硬

旧实现用 `GridView.builder` 固定布局：拖动时只在目标卡片旁边画 2px 竖线，卡片本身不动；
松手后父组件重排列表，画面**瞬间跳变**。另外插入槽位依赖逐张卡片的 `RenderBox` 命中测试，
卡片动画/滚动时容易不准，所以只能一直保持"刚性的线 + 跳变"。

## 2. 新交互

- 拖动开始：被拖卡片变成**虚线圆角占位框**（中间有拖动手柄图标），实际卡片以半透明 ghost
  跟着鼠标（略微抬升、投影），光标变 `grabbing`；
- 拖动过程中：指针越过卡片中线时，本地显示列表**立即重排**，所有卡片用
  `AnimatedPositioned`（180ms / `easeOutCubic`）滑到新格子——和列表视图 `ReorderableListView`
  让位的手感一致；
- 松手：按最终的本地顺序提交一次 `onMoveItem`，父组件乐观更新 + 持久化（带 5 秒撤销）；
- 途中不写数据：本地重排只影响画面，保存只在松手时发生；
- 自动滚动保留并稍微加强（边缘 18px/帧），滚动时用指针坐标重新计算槽位；
- 槽位计算改成**指针坐标 + 网格几何**（列宽/行高），不再逐卡命中测试，动画过程中也稳定；
- 搜索过滤时仍禁用拖动；网格布局参数（最多 360 宽、132 高、间距 8）保持不变。

## 3. 实现要点

- `resource_grid.dart` 的 `_ResourceGridState`：
  - `_displayItems` 本地顺序列表，拖动时实时 `removeAt/insert`；
  - `build` 改为 `SingleChildScrollView + SizedBox + Stack`，几何由
    `LayoutBuilder` 按和原 `SliverGridDelegateWithMaxCrossAxisExtent` 相同的公式计算；
  - 每张卡片是带稳定 key 的 `AnimatedPositioned`；
  - 被拖卡片仍保留在树里（`Opacity(0)` + `IgnorePointer`），保证 `Draggable` 的拖动会话不被
    重建打断，上面叠 `_DragPlaceholder`；
  - 松手时 `finalIndex` 就是「移除被拖项后的目标下标」，直接传给 `onMoveItem`。
- 列表视图（`resource_table.dart` 的 `ReorderableListView`）没有改动。

## 4. 验证

| 项 | 结果 |
|---|---|
| Flutter 测试 | **70 / 70**（新增「拖动中显示实时占位、松手前不写数据」测试） |
| `flutter analyze` | 0 issue |
| 实机拖动 | 拖动中卡片实时让位、虚线占位框跟随；松手后顺序保存、状态栏「顺序已更新 + 撤销」 |
| 其他回归 | `verify_quick_panel` 10/10、`verify_shell` 9/9、`verify_context_menu` 10/10（本次未改相关逻辑） |

截图：`migration/screenshots/phase21-grid-before-drag.png`（拖动前）、
`phase21-grid-mid-drag.png`（拖动中：虚线占位 + 卡片让位 + ghost 跟随）、
`phase21-grid-after-drop.png`（松手后）。

## 5. 已知限制 / 后续

- 网格每行固定 132 高，卡片内容换行时仍按固定高度省略（原来的约束）；
- 拖动仍必须从卡片左上角的拖动手柄开始（和列表一致，避免误拖）；
- 大列表拖动时的自动滚动速度是固定值，后续可按列表长度做自适应。
