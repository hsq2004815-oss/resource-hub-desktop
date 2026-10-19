# Phase 24 — 快速面板在主窗口最大化时变全屏（修复）

- 日期：2026-10-19
- 触发：用户反馈「有时候用快捷键打开快速面板，界面变得特别大，我只需要一个小小的」，
  并附了一张面板几乎铺满屏幕的截图。
- 结论：**只有主窗口处于最大化状态时才会复现**。`EnterQuickMode` 只处理了最小化
  （`IsIconic`），没有处理最大化（`IsZoomed`）；Windows 对最大化窗口会忽略
  `SetWindowPos` 的尺寸参数，于是 HUD 的 480×600 逻辑尺寸被应用到了「还原尺寸」上，
  面板变成和主窗口一样大。

## 1. 根因

`FlutterWindow::EnterQuickMode` 原流程：

1. 如果窗口最小化 → `ShowWindow(SW_RESTORE)`；
2. 保存 `GetWindowRect()` / 窗口样式；
3. 去掉标题栏、边框，改成 `WS_POPUP + WS_EX_TOOLWINDOW`；
4. `SetWindowPos(..., 480*DPI/96, 600*DPI/96, SWP_FRAMECHANGED | SWP_SHOWWINDOW)`。

问题出在第 4 步：**窗口处于最大化时，`SetWindowPos` 不会按请求的宽高改窗口**，而是先把
最大化状态解除、回落到「还原位置/尺寸」（本机是 1618×1072）。实测：

| 场景 | 修复前 HUD 窗口 |
|---|---|
| 主窗口普通大小 | 600×750（正常） |
| 主窗口最大化 | **1618×1072（全屏大小）** |

这也解释了为什么「有时候」才出现——用户把主窗口最大化之后再用快捷键就会中招。

## 2. 修复

- `flutter_window.h` 新增 `quick_saved_maximized_`，记录进入 HUD 前窗口是否最大化。
- `EnterQuickMode`：
  - 用 `IsZoomed(handle)` 判断最大化，若是则先 `ShowWindow(SW_RESTORE)`，再保存
    「还原尺寸」和样式；
  - 这样后面的 `SetWindowPos` 才能真正把窗口缩成 480×600 逻辑像素。
- `ExitQuickMode`：
  - 如果进入前是最大化，恢复样式/尺寸后用 `ShowWindow(SW_SHOWMAXIMIZED)` 把主窗口
    还原成最大化状态，而不是变成「和最大化一样大的普通窗口」；
  - 隐藏路径（`visibility=hide`，窗口本就不可见时）保持原逻辑，下次从托盘显示时尺寸
    可能回落为普通大小（已知的小取舍，不影响主流程）。

## 3. 验证

新增实机回归脚本 `migration/tools/verify_quick_panel_size.py`，在临时发布包 + 示例数据
上跑 6 项检查（125% DPI，期望 HUD 600×750）：

```powershell
D:\miniconda3\python.exe migration\tools\verify_quick_panel_size.py `
    --build release\ResourceHub-Desktop-20261019-0650
```

```
expected HUD size: 600x750
[PASS] hud_from_normal_is_small: 600x750 toolwindow=True
[PASS] close_restores_normal_window: 1618x1072
[PASS] hud_from_maximized_is_small: 600x750 (was maximized=True)
[PASS] close_from_hud_restores_maximized: maximized=True
[PASS] second_hud_from_maximized_is_small: 600x750
[PASS] second_close_restores_maximized: maximized=True
6/6 passed
```

修复前后对照（同一台机器、同一版程序）：

| 检查 | 修复前 | 修复后 |
|---|---|---|
| 普通窗口打开 HUD | 600×750 | 600×750 |
| **最大化窗口打开 HUD** | **1618×1072** | **600×750** |
| 关闭 HUD 后主窗口 | 普通大小、非最大化 | **恢复最大化** |

## 4. 发布

- 代码：`app/windows/runner/flutter_window.{cpp,h}`
- 构建：`release\ResourceHub-Desktop-20261019-0650`（Flutter 前端重新编译；后端未改）
- 免安装包：`Drawer-v1.0.5-win64.zip`（GitHub Release v1.0.5）
- 未改数据格式/协议，升级只需替换程序文件夹里的程序文件（保留 json 数据）。
