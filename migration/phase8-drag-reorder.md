# Phase 8 — 手动拖动排序（Drag to reorder）

- 日期：2026-10-18
- 触发：用户要求"将存的资源拖动排序"，并明确**先交互定方案、满意后再写代码**
- 范围：新增排序交互 + 一条协议方法；`folders.json` / `sites.json` 格式不变，其余业务逻辑不动
- 设计结论来自两轮选择题确认（见 §1）

---

## 1. 最终设计（与用户确认）

| 议题 | 结论 |
|---|---|
| 收藏置顶 | **取消**：收藏只是一颗星 +「只看收藏」筛选，不再自动跳到最前 |
| 排序范围 | 每个数据集（网站 / 本地资源）一份**全局顺序**；分类筛选、只看收藏只是查看方式 |
| 搜索中拖动 | **禁用**（搜索结果是稀疏子集，位置不可见）；分类筛选/只看收藏可拖 |
| 支持视图 | **列表 + 网格**都支持，共用同一顺序 |
| 抓取方式 | **统一用手柄**：列表行首 `⋮⋮`、网格卡片左上角，均为 hover 淡入；整行/整卡不直接拖 |
| 多选拖动 | 只移动被抓取的那一条（当前 UI 本身是单选高亮） |
| 收藏/取消收藏 | 条目**原地不动**（只切换星标） |
| 新增资源 | 仍插到列表顶部 |
| 升级迁移 | 首次启动把"收藏在前 + 原相对顺序"**一次性固化**进 JSON，升级瞬间视觉不变 |
| 恢复入口 | 工具条 `⋮` 菜单提供「按添加时间排序」（一次性重排，可撤销） |
| 撤销 | 状态栏右侧「撤销」按钮，5 秒；只撤销最近一次 |

## 2. 数据设计：零新增字段

**列表顺序 = JSON 数组顺序。** Phase 7 之前 UI 每次渲染都做一次"收藏优先"的稳定排序，
所以数组顺序只在收藏区/普通区内部可见；Phase 8 把这次排序拿掉，数组顺序成为唯一事实来源：

- 不需要 `sortIndex` 字段，不需要数据格式迁移；
- 导出/导入、`.bak`、原子写原样保留顺序；
- 旧版 `resource_hub.pyw` 读写顺序完全兼容（它仍会**显示**时把收藏排前，这是唯一差异）。

### 一次性迁移

Phase 8 第一次启动时，对两个数据集按「收藏在前、各自内部保持原相对顺序」稳定排序后写回
（同时生成 `.bak`），用户升级后第一眼看到的就是原来的顺序，之后顺序完全由拖动决定。

标记写在数据目录的 `.resourcehub-meta.json`（`{"orderVersion": 1}`），**不能放 `settings.json`**：
旧版 Python 应用保存设置时按白名单重写文件，会丢掉未知键，标记一丢迁移就会再跑一次，
把用户手动排好的收藏重新顶上去。标记文件旧版不会碰。若标记存在但损坏，则**跳过迁移**并修复标记
（重跑迁移破坏手动顺序的代价更大）。

## 3. 后端 / 协议

新增唯一方法：

```
→ {"id": 3, "method": "resources.reorder", "params": {"mode": "folders", "ids": ["f3","f1","f2"]}}
← {"id": 3, "ok": true, "result": {"items": [...]}}
```

- `ids` 必须是当前集合 id 的一个**完整排列**（不多、不少、不重复），否则返回
  `operation_failed` + key `reorder_failed`，不写盘；
- 只改数组顺序，`id` / `category` / `favorite` / `createdAt` 一律不变；
- 顺序未变时直接返回，不产生写盘（避免无谓的 `.bak`/落盘）。

改动：`service.py`（去掉 `visible()` 的收藏优先排序、新增 `reorder()` 与控制字段迁移）、
`protocol.py`（`resources.reorder` handler）。`models.py` / `storage.py` 未动。

## 4. UI 实现要点

**列表**（`widgets/resource_table.dart`）

- `ListView` → `ReorderableListView.builder`（`buildDefaultDragHandles: false`，行首自绘手柄）；
- 用 `onReorderItem`（Flutter 3.41+ 的替代品，newIndex 已按"移除后"语义修正）；
- 拖动中整行浮起（`proxyDecorator` 阴影 + `surfaceContainerHigh`），松手 150ms 落位；
- 表头加 28px 手柄占位列，保证表头与行对齐。

**网格**（`widgets/resource_grid.dart`）

- Flutter 没有 `ReorderableGridView`，自研：手柄触发 `Draggable`，回调根据指针位置在卡片上的
  x/中心关系计算插入槽（指针落到间隙时取最近卡片），目标位置画 2px 主色竖线；
- 反馈为整卡大小的 ghost，`dragAnchorStrategy` 用卡片的 `globalToLocal` 保持抓取偏移；
- 靠近上下边缘 44px 内自动滚动（16ms 定时器，越近越快），滚动时重新计算插入槽；
- 拖动中的卡片降到 45% 透明度。

**共享**

- `widgets/reorder_grip.dart`：hover 淡入 + `grab` 光标 + Tooltip（可用："拖动排序"；
  不可用："清空搜索后可拖动排序"），两视图共用；
- 排序只在 `_canReorder`（无搜索词、未在保存、非只读）时为 true，手柄变灰不可拖；
- 乐观更新：先在本地重排，再发 `resources.reorder`；失败回滚并提示"排序保存失败，已恢复原顺序"；
- 撤销：状态栏 `撤销` 按钮 5 秒，把上一份 id 顺序再存一次；任何新的状态消息都会让撤销消失；
- 键盘：选中行后 `Alt + ↑/↓` 移动一格（搜索中同样禁用）；
- 新文案全部走 `l10n/app_strings_ext.dart`（`strings.g.dart` 未动）。

新增文件：`widgets/reorder_grip.dart`。
改动：`resource_table.dart`、`resource_grid.dart`、`resource_list_panel.dart`（`⋮` 更多菜单）、
`home_page.dart`（排序状态机/撤销/键盘）、`status_bar.dart`（复用 `trailing` 槽位，无改动）、
`data/resource_api.dart`、`data/backend_repository.dart`、`l10n/app_strings_ext.dart`。

## 5. 验证

| 项 | 结果 |
|---|---|
| `flutter analyze` | 0 issue |
| Flutter 测试 | **40 / 40**（29 外壳 + 8 协议 + 3 JSON 备份） |
| 新增 Flutter 测试 | 收藏不再置顶、列表拖动+撤销、搜索禁拖、网格拖动、按添加时间排序、Alt+↓ 键盘移动、失败回滚 |
| 后端测试 | **152 / 152**（原 138 + 14：reorder 校验/持久化/幂等 + 迁移 6 项） |
| 协议端到端 | Dart 真实子进程测试新增 `resources.reorder` 往返；`_list`/`reorder` 顺序一致 |
| 迁移 | 旧数据首次加载顺序与升级前一致；手动排序后重启不被重新置顶；损坏标记跳过迁移 |
| 实机 | 见 §6 |

## 6. 实机验证

- 发布包 **47.8 MB**，合并进 `release\ResourceHub-Desktop-20261017-1835\`（保留用户的
  `sites.json` / `folders.json` / `settings.json`）；启动后数据目录生成
  `.resourcehub-meta.json`（`{"orderVersion": 1}`），既有顺序保持不变。
- **真实鼠标拖动**：用 SendInput 级鼠标事件把第一行拖到第二行下方，`folders.json` 立即写入新顺序，
  状态栏显示"顺序已更新" + 右侧「撤销」——见 `phase8-after-drag.png`。
- **撤销按钮**：拖动成功后出现在状态栏右侧（`phase8-undo.png`）；行为由 widget 测试断言
  （`dragging a list row saves the order and can be undone`）。
- **网格**：切到网格后卡片悬浮出现手柄和「拖动排序」提示（`phase8-grid-hover.png`）。
- `verify_shell.py` **9/9 PASS**（关窗→托盘、全局热键唤回、二次启动唤醒、WM_DROPFILES 子窗口拖入）。
- 截图：`phase8-list-hover.png`（列表悬停手柄）、`phase8-after-drag.png`（拖动后顺序与撤销）、
  `phase8-grid-hover.png`（网格手柄）、`phase8-app.png`（合并后的实机窗口）。

> 实机验证时顺带确认：拖动后 `folders.json` 的 `.bak` 保留拖动前顺序，符合原有原子写约定。

## 7. 已知取舍 / 未做

- **收藏不再置顶**是有意的行为变化；旧版 exe 打开时仍把收藏显示在前（数据顺序不受影响）。
- 拖拽只改顺序，不改分类/收藏；跨"网站 / 资源"两个数据集不能互拖。
- 网格拖动的自动滚动只在指针处于边缘时按帧推进；拖到窗口外再回来需要重新移动指针。
- 键盘排序、拖动排序都要求无搜索词；分类筛选下拖动只保证"当前筛选结果内"的相对顺序，
  清空筛选后全局邻居可能变化（这是"筛选时可拖"的固有语义）。
- 多选整块拖动未做（当前 UI 是单选高亮，无多选模型）。
- 未提供按名称/大小排序；"恢复"入口只有"按添加时间排序"。
