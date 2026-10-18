# Phase 13 — 列表视图改用与网格视图相同的页面底色

- 日期：2026-10-18
- 触发：用户分别截了列表视图和网格视图，要求"把列表视图这个底色改成网格视图的底色"
- 范围：只改列表容器/表头底色

---

## 1. 问题

- **网格视图**：卡片（`surfaceContainerLowest`）直接放在页面底色（`scheme.surface`）上，没有外层卡片，空白区域就是页面底色。
- **列表视图**：整张表格被包在一个 `surfaceContainerLowest` 的白色面板里（带 `outlineVariant` 边框和圆角），
  表格和空白区域都是白色，和网格视图的页面底色明显不一致，也违反 Phase 7 定下的
  "不要给每个区域都套卡片，层级用发丝线" 规则。

## 2. 修改（`app/lib/widgets/resource_table.dart`）

- 删除表格外层的 `DecoratedBox`（白底 + 边框 + 圆角）和 `ClipRRect`，直接返回
  `Column(表头, Expanded(列表或空态))`；
- 表头底色从 `surfaceContainer` 改为 `scheme.surface`（与页面一致），只保留底部
  `outlineVariant` 发丝线；
- 行本身继续保持透明底（hover 用主色淡染、选中 `primaryContainer`、缺失路径用红色淡底），
  于是行和列表下方空白都落在页面底色上，和网格视图的空白区域完全一致；
- 空态占位仍居中在页面底色上；表格滚动、拖拽排序、右键菜单、列宽逻辑均未变。

现在两种视图的关系是：

```
页面 surface
├─ 网格：白色卡片 + 间距（卡片是内容单元）
└─ 列表：表头 + 行（行之间发丝线，选中/hover 才有填充）
```

## 3. 验证

| 项 | 结果 |
|---|---|
| `flutter analyze` | 0 issue |
| Flutter 测试 | **50 / 50**（没有改行为，现有布局/最小窗口测试覆盖） |
| 实机 | 列表背景与网格视图页面一致（`phase13-list-bg.png`）；表头不再是灰条 |
| `verify_shell.py` | 9/9 PASS |
| 发布包 | 47.9 MB，合并进 `release\ResourceHub-Desktop-20261017-1835\`，用户数据未变 |

## 4. 取舍

- 列表行现在是页面底色，只有选中/hover/缺失路径才上色；如果你想要"每行是白色卡片"，
  可以给 `_TableRow` 的默认背景改成 `surfaceContainerLowest` 并保留行间距，但那会回到
  "块状列表" 的视觉，和现在的 M3 留白风格不一致。
- 表格外框和圆角已去掉；如果需要弱边界，可以只在滚动区域加一条发丝分割线。
