# Phase 26 — 鼠标侧键快速面板

**日期**：2026-10-20
**版本**：v1.1.0
**需求**：用鼠标侧键（后退 / 前进）呼出快速面板，比找键盘快捷键更顺手。

## 方案

后端原本已经用 `RegisterHotKey` 注册三个全局热键，并通过 `hotkey` 事件把
`{"action": "quickLinks" | "quickFolders" | "toggle"}` 推给 Flutter。侧键不用新协议：
新增一个全局鼠标钩子，按下后发出同样的事件即可，UI 一行没改。

- 后侧键（XBUTTON1）→ `quickLinks`（网站面板）
- 前侧键（XBUTTON2）→ `quickFolders`（文件夹面板）
- 这两个键在浏览器 / 资源管理器里默认是后退 / 前进，所以钩子**吞掉**按下和抬起事件；
  不吞会出现「一边后退一边弹面板」。

## 实现

- 新文件 `backend/resource_hub_core/mousehook.py`：`WH_MOUSE_LL` 低级鼠标钩子，和
  `hotkey.py` 一样自带线程与消息泵；`SetWindowsHookExW` 需要回调对象一直活着，所以
  `_proc` 存在实例上（第一版没存，回调被 GC 后完全没有事件，就是靠实机脚本抓出来的）。
- `settings.py`：`mouseSideButtonsEnabled`（默认 `false`，JSON 同名 key）。
- `protocol.py`：`hotkey.start` 时若开关打开就启动钩子，返回结果多一个
  `mouseSideButtons: {enabled, registered, reason}`；`hotkey.stop` / `app.shutdown` 一并停掉。
  侧键开关和键盘热键开关相互独立：`globalHotkeyEnabled=false` 时侧键照样能用。
- Flutter：`AppSettings` 加字段，设置 → 快捷键组合下面加「鼠标侧键」开关。

## 验证

- 后端 335 个测试（新增 6 个：XBUTTON 映射 / 吞键规则、设置归一化、协议响应、
  与键盘热键独立启动）；Flutter 76 个测试（新增开关用例），`flutter analyze` 干净。
- 实机脚本 `migration/tools/verify_mouse_side_buttons.py`（真后端 + `SendInput` 合成侧键）：

```
[PASS] app_hello
[PASS] mouse_hook_registered: {"enabled": true, "registered": true, "reason": null}
[PASS] back_button_opens_quick_links
[PASS] forward_button_opens_quick_folders
```

- UI 端到端：按后侧键窗口变为 600×750 HUD，`Esc` 恢复到 1618×1072。

## 说明 / 限制

- 默认关闭：开启前侧键仍是浏览器后退 / 前进；如果鼠标驱动把侧键映射成普通按键
  （如 Alt+Left），钩子收不到 XBUTTON，需要在驱动里改回「后退 / 前进」。
- 目前固定映射，没有单独配置两个按钮；需要时再加两个设置项即可。
