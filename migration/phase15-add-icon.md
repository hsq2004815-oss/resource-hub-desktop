# Phase 15 — 新增资源改为圆形加号图标按钮

- 日期：2026-10-18
- 触发：用户截图"新增资源"按钮后要求"改成一个圆里面一个加号，不要这四个字了"
- 范围：只改主操作按钮形态

---

## 1. 变更（`app/lib/features/home/resource_list_panel.dart`）

- 原来的 `FilledButton.icon`（文字「新增资源 / 新增网站」+ 加号）改为 **M3 圆形填充图标按钮**：

```dart
IconButton.filled(
  tooltip: t.t(isLinks ? 'form_add_link' : 'form_add_folder'),
  onPressed: onAdd,
  icon: const Icon(Icons.add, size: 20),
  style: IconButton.styleFrom(
    minimumSize: const Size(40, 40),
    padding: EdgeInsets.zero,
    shape: const CircleBorder(),
  ),
)
```

- 40×40 主色圆、白色 20px 加号；**文字标签只保留在 tooltip / 无障碍语义里**
  （悬停显示「新增资源」或「新增网站」，随当前标签页切换），不再占据头部宽度。
- 仍是页面上唯一的主色填充操作，符合"主操作只用主色"的规则；点击行为不变（打开原 `ResourceForm` 对话框）。
- 头部因此更紧凑，模式切换/视图切换右侧留白更多。

## 2. 测试调整

原来测试点击文字 `新增资源` 打开表单，现在改成点击 tooltip：

```dart
await tester.tap(find.byTooltip('新增资源'));
```

涉及 3 个测试（打开编辑器、提交表单、校验错误回显），其余不变。

## 3. 验证

| 项 | 结果 |
|---|---|
| `flutter analyze` | 0 issue |
| Flutter 测试 | **50 / 50** |
| 实机 | 头部右侧显示蓝色圆形加号（`phase15-add-icon.png`），悬停 tooltip 为「新增资源」 |
| `verify_shell.py` | 9/9 PASS |
| 发布包 | 47.9 MB，合并进 `release\ResourceHub-Desktop-20261017-1835\`，用户数据未变 |

## 4. 说明

- 圆形按钮直径 40px（M3 filled icon button 标准），比普通图标按钮（34–36px）略大，保持主操作的视觉权重；
- 如果后续觉得 40 太大，可以调 `minimumSize` 与图标尺寸；`FilledButton` 全局样式（Phase 12）仍用于对话框里的文字按钮。
