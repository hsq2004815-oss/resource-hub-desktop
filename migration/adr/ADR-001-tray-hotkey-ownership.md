# ADR-001 — 托盘与全局热键归属、导入导出入口、数据覆盖风险

- 状态：**已接受**
- 日期：2026-10-17
- 决策者：接手 Phase 2 的开发侧
- 替代：`migration/phase1-audit.md` §6.1 R1 / R2 的技术判断与 §8.5 的三项待决问题

---

## 1. 背景

`migration/phase1-audit.md` §8.5 列出三项"阻塞第 2 阶段"的待决问题，其中第 2 项（托盘 + 全局热键归 Flutter 还是归 Python 后端）被标为"最大架构岔口，选错会导致第 4 阶段返工"。

审计给出的理由（§6.1 R1）是：

> 热键必须在原生消息循环线程注册。若 Python 后端变成无 UI 的子进程，它没有 Tk 消息循环了，**现有实现（`:657-708`）直接失效**，需要改用独立线程 + 自己的 `GetMessageW` 循环。

**这个判断与代码事实不符。** 复核 `GlobalHotkeyListener`（`resource_hub.pyw:657-708`）：

| 事实 | 代码位置 |
|---|---|
| 起独立 `threading.Thread(name="ResourceHubHotkey")` | `:670` |
| 线程内先 `PeekMessageW` 强制创建线程消息队列 | `:677` |
| 线程内 `GetCurrentThreadId` + `RegisterHotKey(None, ...)` | `:678-682` |
| 线程内自持 `GetMessageW` 循环接收 `WM_HOTKEY` | `:688-694` |
| 用 `PostThreadMessageW` 停止线程，`finally` 里 `UnregisterHotKey` | `:706`、`:696-700` |

即：**热键从一开始就不依赖 Tk 的消息循环**。`self.after(0, ...)` 只在托盘回调回主线程时才出现（`:1328`、`:1331`），那是托盘的问题，不是热键的问题。

因此原判断把一个"已被正确实现"的问题误判为"必须重写"。技术前提变了，决策随之改变。

## 2. 证据

`migration/probes/probe_headless_tray_hotkey.py` 用 `SourceFileLoader` 直接加载真实 `resource_hub.pyw`（**不创建任何 Tk root**），逐项验证。运行方式：

```
D:\miniconda3\python.exe migration/probes/probe_headless_tray_hotkey.py
```

实测结果（2026-10-17，本机 Windows 11 26200 / Python 3.13.11）：

| 探针 | 结果 | 观测值 |
|---|---|---|
| `import_without_tk_root` | 通过 | `tk._default_root=None` |
| `single_instance_mutex_headless` | 通过 | 首次 `acquire=True`，并发第二次 `False` |
| `hotkey_register_without_tk` | 通过 | `start() -> True`，线程名 `ResourceHubHotkey` |
| `hotkey_delivers_wm_hotkey` | 通过 | 模拟 `Ctrl+Alt+Shift+F12` 后队列收到 `'toggle'` |
| `hotkey_unregister_on_stop` | 通过 | `registered=False`，线程已退出 |
| `hotkey_reacquire_after_release` | 通过 | 同一组合立即二次注册成功，无需手工清理 |
| `tray_run_detached_without_tk` | 通过 | `pystray.Icon.run_detached()` → `visible=True` |

7/7 通过。这同时关闭了 §8.6 "托盘 / 全局热键在无 Tk 消息循环时能否存活 —— 第 2 阶段核心风险"。

**边界说明**：探针验证的是"注册 / 投递 / 注销 / 重注册 / 托盘可见"这几条机制，**没有**验证跨显示器 DPI 变化、长时间运行的句柄泄漏，也没有验证 Flutter 窗口作为前台窗口时 `SetForegroundWindow` 的抢占行为。这些留到 Phase 5 手工清单（§5.4 第 5、6、9 项）。

---

## 3. 决策

### D1 — 托盘、全局热键、单实例，全部归 Python 后端

**结论**：Flutter 前端只做 UI；托盘图标、`RegisterHotKey`、命名互斥体与唤醒事件全部留在 Python 进程。前端通过 IPC 订阅 `hotkey_pressed` / `toggle_window` 事件。

**理由**：

1. 现有实现已经正确且可复用，重写没有收益。7 项探针证明它在无 Tk 环境下照常工作。
2. 反过来让 Flutter 接管，需要：写一个 Win32 插件、重做快捷键录制与冲突校验（`:1128-1161`、`:1057-1083`）、重做托盘菜单的本地化重建（`:1318`）、还要处理"Flutter 窗口销毁后热键归属"的问题。工作量明显更大，且要重新踩一遍已踩过的坑。
3. 单实例语义天然属于后端：`Local\Mytools.ResourceHub.SingleInstance` + `Local\Mytools.ResourceHub.WakeEvent`（`:69-70`）已经能"二次启动唤醒已有窗口"。前端若另起一套，两套会打架（§6.1 R5）。

**代价与约束**：

- 需要把托盘回调的 `self.after(0, ...)` 换成线程安全队列 → IPC 事件。这是**唯一**必须改的代码，约 3 行。
- 后端将是一个没有窗口的进程。`messagebox` / `filedialog`（§6.1 R3）确实不能再用，所有对话框搬到 Flutter 侧——这与 D1 不冲突，只是确认 R3 成立。
- 窗口显示/隐藏动画（`:1342-1480` 的 alpha 淡入淡出 + `SetForegroundWindow`）需要迁到 Flutter 侧或由后端发 Win32 消息驱动。**这是 Phase 5 的具体任务，不在本 ADR 裁决范围内**，但需注意原实现的 `topmost` 闪一下是为了绕过前台锁定，Flutter 侧重做时要保留这个技巧。

### D2 — 导入 / 导出：保留能力，补 UI 入口

**结论**：不删文档、不删代码，在 Phase 5 给列表工具栏加两个入口。

**理由**：

1. `export_current`（`:2827`）与 `import_current`（`:2841`）的实现是完整的，且带去重统计；删掉等于丢弃已验证逻辑。
2. `STRINGS` 里 **`export` / `import` 两个键已经存在**（`:325-614` 区段内），说明 UI 入口原本就在计划内，只是没接上。补入口的成本低于改文档 + 删代码。
3. README 已对用户宣称该能力，删文档属于能力回退。

**约束**：入口放在列表工具栏而非表单区；导入必须复用现有去重规则（`_comparable_value`），并在导入前备份当前文件（与 D3 共用同一套写盘逻辑）。

### D3 — 数据覆盖风险：本轮修复，且必须带备份

**结论**：修复。在 Phase 3 拆业务层时一并落地，规则如下：

1. 写盘改为 **临时文件 + `os.replace`**，不再 `path.write_text()` 直接覆盖（`:1823-1824`）。
2. 解析失败**不再静默返回 `[]`**。改为抛出可识别的错误，`_load_all_data` 遇到错误时**拒绝写入默认示例数据**（当前 `:1953-1958` 会用示例数据覆盖用户文件）。
3. 首次运行写示例数据的条件收紧为"文件不存在"，而不是"解析结果为空"。
4. 写盘前把原文件复制为 `*.bak`（保留最近 1 份），损坏时可手工恢复。

**理由**：这是一条真实的数据丢失路径——断电/崩溃导致 JSON 截断 → 下次启动解析失败 → 用示例数据覆盖 → 用户数据不可恢复。修复只影响"文件已损坏"这一条路径，正常路径行为不变，回归风险可控。

**约束**：这是**行为变更**，必须补测试（§5.2 的"空文件/损坏 JSON"用例要从"记录当前行为"改成"断言拒绝覆盖"）。

---

## 4. 对 Phase 1 审计的更正

| 审计条目 | 原判断 | 更正 |
|---|---|---|
| §6.1 R1 全局热键归属 | 现有实现"直接失效"，需改用独立线程 + 自有消息循环 | **判断错误**。现有实现已经是独立线程 + 自有 `GetMessageW` 循环（`:670`、`:688`），无需改动 |
| §6.1 R2 托盘归属 | 去掉 Tk 后"必须换成独立线程 + 线程安全队列" | 部分成立。pystray 本来就 `run_detached()` 在独立线程；需要改的只是回调从 `after()` 换成队列，**约 3 行** |
| §8.6 "托盘/热键无 Tk 能否存活" | 未验证，列为 Phase 2 核心风险 | **已验证通过**，见 §2 |
| §8.5 第 2 项 | 最大架构岔口 | 岔口已由实证关闭，选 Python 后端 |

## 5. 后续影响

- Phase 2（本阶段）：不受影响，纯 UI 设计系统，已交付。
- Phase 3：拆业务层时按 D3 改存储；托盘回调改队列。
- Phase 4：stdio JSON Lines 协议需要新增 `event` 通道（后端 → 前端单向推送），因为热键/托盘是**异步事件**而非请求-响应。原方案只定义了请求/响应，需补事件帧。
- Phase 5：补导入导出入口（D2）、窗口显隐动画与前台抢占（D1 遗留项）。
