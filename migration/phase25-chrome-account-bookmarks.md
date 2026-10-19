# Phase 25 — Chrome 账号书签同步修复

**日期**：2026-10-19
**版本**：v1.0.6
**症状**：Edge 书签能正常同步，Chrome 书签怎么点「立即同步」都不进来；主界面看不到新收藏的网站。

## 根因

`backend/resource_hub_core/bookmarks.py` 发现浏览器配置目录时，只认每个 profile 目录下的
`Bookmarks` 文件：

```python
_bookmarks_filename = "Bookmarks"
candidate = profile_dir / _bookmarks_filename
```

但 Chrome 在**登录账号并开启书签同步**后，把书签写进 `AccountBookmarks`（本地明文 JSON，
结构仍然是 Chrome 的 `roots` / `bookmark_bar` / `other` / `synced` 格式），并且可能根本不写
`Bookmarks`。于是：

- Chrome 的 `Default` 有 `Bookmarks`（2 条旧书签）→ 被读到了；
- 实际在用的 `Profile 1` 只有 `AccountBookmarks`（5 条，含刚收藏的小众软件）→ 被直接跳过；
- 同目录的 `EncryptedAccountBookmarks2` 是账户书签的加密副本，不能/不需要解析。

所以用户看到的是「Edge 行、Chrome 不行」。

## 修复

1. 新增 `_PROFILE_BOOKMARK_FILENAMES = ("AccountBookmarks", "Bookmarks")`，发现配置时按顺序
   找出**所有**可读文件；
2. 同一 profile 同时存在两个文件时把它们**合并读取**（Chrome 自己的 UI 也是合并展示的），
   同步时再按 URL 去重；
3. `BookmarkProfile.paths` 保存文件元组（`.path` 保留为主文件的兼容属性），watcher 的
   mtime/size 快照会同时盯着两个文件，任一变化都会触发同步；
4. 自定义书签目录（`bookmarkCustomDir`）也接受 `AccountBookmarks` 文件路径；
5. 新增 3 个后端测试：只读 `AccountBookmarks` 的 profile 能被发现、两个文件会合并、自定义目录
   指向 `AccountBookmarks` 可用。后端测试数 326 → 329。

## 验证（实机）

修复后对真实浏览器数据运行 `discover_profiles`：

```
Chrome · Default  -> ['AccountBookmarks', 'Bookmarks']
Chrome · Profile 1 -> ['AccountBookmarks']
Edge · Default    -> ['Bookmarks']
total entries: 35
```

重启应用后 watcher 首次同步自动补齐了 17 条 Chrome 书签（`.resourcehub-meta.json` 的
`seenUrls` 16 → 33），`sites.json` 里出现了 `https://www.appinn.com/`、`https://meta.appinn.net/`
等 7 条小众软件相关收藏，资源总数 33。

## 发布

- 后端重新打包（PyInstaller onedir）后替换到用户当前安装目录并重启验证；
- v1.0.6 分发包与 GitHub Release 使用同一份修复后的后端；
- 回归：`cd backend; D:\miniconda3\python.exe -m unittest discover -s tests -t .` → 329 tests OK (1 skipped)。

## 相关文件

- `backend/resource_hub_core/bookmarks.py`
- `backend/tests/test_bookmarks.py`
- `build/backend-exe/`（PyInstaller 构建目录，不提交）
