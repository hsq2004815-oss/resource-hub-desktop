# Phase 3 — 拆出无 UI 的 Python 业务层

- 日期：2026-10-17
- 新增：`backend/`（`resource_hub_core` 包 + 101 个测试）
- 前置：`migration/phase1-audit.md`、`migration/adr/ADR-001-tray-hotkey-ownership.md`、`migration/phase2-design-system.md`
- 原应用 `resource_hub.pyw` **未修改**

---

## 1. 结论

业务逻辑已从 2916 行的 Tk 单文件中拆出，成为**零 UI 依赖**的 `resource_hub_core` 包：导入它不会创建 Tk root，也不会加载 pystray。

| 验证项 | 结果 |
|---|---|
| `python -m unittest discover -s tests -t .` | **101 / 101 通过**（2.7 s） |
| 真实数据加载 | `sites.json` 14/14、`folders.json` 11/11，字段无损 |
| 真实设置加载 | `Ctrl + Space`、`launchAtStartup=True` 正确解析 |
| 真实路径检测 | 11 条资源，0 条失效 |
| 第三方依赖 | **零**（只用标准库 `json / os / pathlib / ctypes / threading`） |

**这不是"搬运"，是重构**：审计 §4.3 已经指出，原代码约 2000 行是 UI 与业务交织。拆出的部分只包含可判定、可测试的规则，UI 状态（选中行、表单编辑态、状态栏文案）全部留在前端。

---

## 2. 文件构成

```
backend/
  resource_hub_core/
    __init__.py     公开 API
    normalize.py    纯函数：URL/路径规范化、去重键、热键解析、时间格式化
    models.py       Site / Folder 数据类 + 归一化 + 完整性判定
    storage.py      原子写、备份、损坏检测（ADR-001 D3）
    settings.py     Settings 模型 + 容错加载
    service.py      ResourceService：增删改查、筛选、路径检测、导入导出
    hotkey.py       GlobalHotkeyListener（无 Tk）+ 组合可用性探测
  tests/            101 个用例
  README.md
```

依赖方向：`service → models → normalize`，`storage` 被 `service` 与 `settings` 共用。没有任何反向依赖。

---

## 3. 移植对照

| 旧实现（`resource_hub.pyw`） | 新位置 | 说明 |
|---|---|---|
| `parse_hotkey_id` `:224` | `normalize.parse_hotkey_id` | 含 26 个命名键、A–Z、0–9、F1–F24、别名表 |
| `_normalize_url` `:1893` | `normalize.normalize_url` | 补 `https://` |
| `_normalize_folder_path` `:1901` | `normalize.normalize_folder_path` | `expandvars` + `expanduser` |
| `_comparable_value` `:1906` | `normalize.comparable_value` | 去重键 |
| `format_added` `:2238` | `normalize.format_added` | 解析失败原样返回 |
| `_normalize_site` `:1914` | `models.Site.normalize` | 哨兵归一化、`favorite` 强制 bool |
| `_normalize_folder` `:1928` | `models.Folder.normalize` | `kind` 推断、兼容旧 `url` 字段 |
| `_load_json` / `_write_json` `:1815` | `storage.JsonFileStore` | **行为已改**，见 §4 |
| `_load_all_data` `:1950` | `service.load` | **行为已改**，见 §4 |
| `_normalize_settings` `:1829` | `settings.Settings.normalize` | 非法值回落默认 |
| `save_current` `:2759` | `service.add` / `service.update` | 校验顺序一致，错误键一致 |
| `delete_selected` `:2683` | `service.delete` | |
| `toggle_favorite_selected` `:2658` | `service.toggle_favorite` | |
| `add_dropped_resources` `:2270` | `service.add_dropped` | |
| `check_paths` `:2672` | `service.check_paths` | links 模式返回 `supported=False` |
| `refresh_view` 的筛选与排序 `:2520` | `service.visible` | 收藏置顶用稳定排序 |
| `export_current` `:2827` | `service.export_payload` | |
| `import_current` `:2841` | `service.import_payload` | **替换**语义，非合并 |
| `GlobalHotkeyListener` `:657` | `hotkey.GlobalHotkeyListener` | 回调取代队列，其余逐行等价 |

**没有移植**：`pystray` 托盘适配。它需要一个真实的后端进程宿主，属于 Phase 4/5 的组装工作，本阶段只把已验证过的热键线程搬了过来。

---

## 4. 行为变更（仅 ADR-001 D3 授权的部分）

这四处是**故意**与旧行为不同，其余全部保持一致：

| # | 旧行为 | 新行为 | 理由 |
|---|---|---|---|
| 1 | `_write_json` 直接 `write_text` 覆盖 | 临时文件 + `flush` + `fsync` + `os.replace` | 断电/崩溃不会留下截断文件 |
| 2 | 解析失败静默返回 `[]` | 抛 `CorruptDataError`，**不写文件** | 旧路径会用示例数据覆盖用户文件 |
| 3 | 列表为空就写入示例数据 | 只有**文件不存在**才写示例 | 旧行为会把用户删掉的条目"复活" |
| 4 | 无备份 | 每次写前复制 `<name>.bak`（保留最近 1 份） | 损坏时可手工恢复 |

对应的回归测试：`test_storage.py` 的 4 个 D3 用例 + `test_service.LoadTests` 的 3 个用例。

---

## 5. 刻意保留的旧行为（parity quirks）

这些看起来像 bug，但为了 Phase 5 能与旧应用逐条对照，**保留原样**并写进测试固定下来：

| 行为 | 位置 | 备注 |
|---|---|---|
| 大写协议被拒绝：`HTTPS://x` → `invalid_link_path` | `service._validate` | 旧代码用大小写敏感的 `startswith` |
| `http://a` 与 `https://a` 不算重复 | `comparable_value` | 去重键包含协议 |
| `favorite: "false"` 被当作 `True` | `Site.normalize` | `bool("false")` 为真；客户端只发真布尔值 |
| 批量拖入的顺序是输入的反序 | `service.add_dropped` | 旧代码循环 `insert(0, ...)` |
| 导入是**替换**而不是合并 | `service.import_payload` | 旧 `import_current` 直接赋值 |
| 文件夹必须存在才能保存 | `service._validate` | 旧 `save_current` 的 `invalid_folder_path` |

如果后续决定修掉其中任何一条，应当先改测试、再改实现，并在本表上标注。

---

## 6. 一个设计决定：错误用 i18n 键传递

`ValidationError` / `DuplicateError` 携带的是**旧的文案键**（`enter_link_name`、`duplicate_folder_path` 等），不是自然语言。

原因：`strings.g.dart` 已经是从 Python `STRINGS` 生成的 142 键表。后端如果返回中文句子，前端就无法切换语言，还会出现两套文案。现在前端只需 `t.t(err.key)`，语言切换、文案修订全部走同一条链路。

---

## 7. 测试覆盖分布

| 文件 | 用例 | 覆盖内容 |
|---|---|---|
| `test_normalize.py` | 24 | URL/路径规范化、去重键、热键解析（合法/别名/非法/F 键/命名键）、时间格式化 |
| `test_models.py` | 17 | 分类哨兵、字段默认值、`favorite` 强制、完整性判定、`kind` 推断（真实文件系统）、`url`→`path` 兼容 |
| `test_storage.py` | 10 | 缺失/空/损坏文件、UTF-8 往返、indent、`.bak`、无残留临时文件、写失败保留原文件 |
| `test_settings.py` | 12 | 默认值、非法语言/热键回落、热键规范化、bool 严格性、往返 |
| `test_service.py` | 34 | 首运行、空文件不复活、损坏不覆盖、增删改查、校验顺序、去重、筛选排序、路径检测、拖入、导入导出、分类重命名 |
| `test_hotkey.py` | 3 | 注册/释放/重注册、回调异常不杀消息泵、非法组合；组合被占用时 skip |

热键的**端到端**验证（含模拟按键触发 `WM_HOTKEY`）不在单元测试里，仍由 `migration/probes/probe_headless_tray_hotkey.py` 承担——单元测试只保证线程生命周期与注册语义。

---

## 8. 如何运行

```powershell
cd E:\Mytools\ResourceHub-GitHub-Ready\backend
D:\miniconda3\python.exe -m unittest discover -s tests -t . -v
```

要求 Python ≥ 3.11（用到 `X | Y` 类型写法与 `dataclass(slots=True)`）。本机 `D:\miniconda3\python.exe` 为 3.13.11，**不需要**任何第三方包。

只读核对真实数据（不修改仓库文件）：

```python
from pathlib import Path
from resource_hub_core import ResourceService
svc = ResourceService(Path(r"E:\Mytools\ResourceHub-GitHub-Ready"))
svc.load()
```

> 注意：`ResourceService.load()` 在**文件缺失**时会写入示例数据。指向真实目录前请确认 `sites.json` / `folders.json` 存在，或先复制到临时目录。

---

## 9. 留给 Phase 4 的接口

协议层需要的入口都已就绪：

| 协议方法（拟定） | 后端调用 |
|---|---|
| `resources.list` | `service.visible(mode, query=…, category=…, favorites_only=…)` |
| `resources.add` / `update` / `delete` | `service.add` / `update` / `delete` |
| `resources.favorite` | `service.set_favorite` |
| `resources.categories` | `service.categories` |
| `resources.checkPaths` | `service.check_paths` |
| `resources.export` / `import` | `service.export_payload` / `import_payload` |
| `settings.get` / `settings.set` | `SettingsStore.load` / `save` |
| `event.hotkey` / `event.trayToggle` | `GlobalHotkeyListener(on_press=…)` → 事件帧 |

**已知缺口**：协议只有请求-响应，而热键与托盘是异步事件，需要补事件帧（ADR-001 §5 已记录）。另外 `CorruptDataError` 需要在协议里映射成一个可识别的错误码，让前端能提示"数据文件损坏，已停止写入"，而不是静默失败。
