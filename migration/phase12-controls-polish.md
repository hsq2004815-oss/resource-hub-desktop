# Phase 12 — 控件打磨（新增资源按钮 + 分类筛选宽度）

- 日期：2026-10-18
- 触发：用户截图反馈「新增资源按钮没有做好，字体都不清晰，请参考谷歌组件重新做」「全部分类按钮太宽了」
- 范围：只改控件样式/尺寸，不动业务逻辑

---

## 1. 新增资源按钮（Material 3 Filled Button）

原实现是 `FilledButton.icon` + 主题里的 `13px / w600 / 8px 圆角 / 16px 横向 padding`，
在 125% Windows 缩放下中文白字显得挤、发虚，也不像标准 M3 按钮。

改为按 Material 3 filled button 规格重做（`app/lib/design/app_theme.dart` 的 `_filledStyle`）：

| 属性 | 新值 | 说明 |
|---|---|---|
| 高度 | `40` | M3 默认按钮高度（`minimumSize: Size(64, 40)`） |
| 圆角 | `StadiumBorder` | M3 全圆角（之前的 8px 圆角偏 Tk 风格） |
| 横向 padding | `20` | 图标与文字不再拥挤 |
| 字号 / 字重 | `14 / w600`，`height 1.2`，`letterSpacing 0.1` | 中文标签更清晰（原 13px） |
| 图标 | `18px` | 与 14px 标签比例正确 |
| density | `VisualDensity.standard` | 不再被 compact 压缩 |

该样式对所有 `FilledButton` 生效，包括对话框里的「保存」按钮，视觉统一。
按钮文字仍是 `form_add_folder`（新增资源）/ `form_add_link`（新增网站），只改样式。

## 2. 分类筛选宽度

`AppCategoryDropdown` 是 M3 `DropdownMenu`（`width` 必须显式给，否则会按最宽项撑开）。
工作区里的宽度从 **190 → 150**：图标 +「全部分类」+ 箭头刚好放下，长分类名仍会省略号截断，
搜索框因此多出 40px 宽度。

## 3. 验证

| 项 | 结果 |
|---|---|
| `flutter analyze` | 0 issue |
| Flutter 测试 | **50 / 50**（无功能/文案变化，现有布局测试覆盖最小窗口 1180×760） |
| 实机 | 新按钮为 M3 全圆角、字号更大更清晰；分类筛选明显变窄（`phase12-controls.png`） |
| `verify_shell.py` | 9/9 PASS |
| 发布包 | 47.9 MB，合并进 `release\ResourceHub-Desktop-20261017-1835\`，用户数据未变 |

截图：`phase12-controls.png`。

## 4. 说明

- 字体仍然使用 `Microsoft YaHei UI`（系统字体），字号加大到 14px + `w600` 后中文渲染明显更实；
  没有引入第三方字体，保持零依赖。
- 如果还觉得按钮偏大/偏小，可以再调 `_filledStyle` 的 `minimumSize` 与字号，或只给「新增资源」单独覆写样式。
