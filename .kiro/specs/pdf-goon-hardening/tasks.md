# Tasks: pdf-goon-hardening

## 執行計劃

依 TDD 垂直切片順序排列。每個 task 是一個 RED→GREEN 循環。

- [x] 1. S1: subprocess timeout
  - [x] 1.1 RED: 寫測試 — `run_command` 超時時拋出含 "timeout" 描述的 `SubprocessError`
  - [x] 1.2 GREEN: 在 `run_command` 加入 `timeout` 參數，捕獲 `TimeoutExpired`，拋出 `SubprocessError`
  - [x] 1.3 驗證：所有 111 個現有測試仍通過

- [x] 2. S2: local directory allowlist
  - [x] 2.1 RED: 寫測試 — 非 allowlist 的工具名稱跳過 local directory 搜索
  - [x] 2.2 RED: 寫測試 — allowlist 內的工具名稱仍可從 local directory 找到
  - [x] 2.3 GREEN: 加入 `_ALLOWED_LOCAL_TOOLS` 常量，修改 `get_tool_path` 邏輯
  - [x] 2.4 驗證：所有現有測試仍通過

- [x] 3. B3: `!delete` 路徑過濾修復
  - [x] 3.1 RED: 寫測試 — 名稱包含 "!delete" 子字串但非目錄名的 PDF 不被排除
  - [x] 3.2 RED: 寫測試 — 位於 `!delete/` 目錄下的 PDF 仍被排除
  - [x] 3.3 GREEN: 改為 `"!delete" not in f.parts`
  - [x] 3.4 驗證：所有現有測試仍通過

- [x] 4. B1 + B2 + A2: 文件名碰撞與 glob 消除（緊密耦合，一起做）
  - [x] 4.1 RED: 寫測試 — 渲染文件不被提取 glob 誤捕
  - [x] 4.2 RED: 寫測試 — 多圖頁面子圖索引正確（`001_000.png`, `001_001.png`）
  - [x] 4.3 GREEN: 渲染改用 `render_{page}_tmp` 前綴
  - [x] 4.4 GREEN: `_process_page` 直接使用 extract/render 回傳的 file list
  - [x] 4.5 GREEN: 修復 `_finalize_page_files` 中第二個 regex 錨定到文件結尾
  - [x] 4.6 驗證：所有現有測試仍通過（含 integration tests）

- [ ] 5. A1: PageResult 結構化回傳
  - [x] 5.1 新增 `PageResult` dataclass 到 `models.py`
  - [x] 5.2 RED: 寫測試 — `_process_page` 回傳 `PageResult` 含正確 page_num 和 mode
  - [x] 5.3 GREEN: 修改 `_process_page` 回傳 `PageResult`
  - [x] 5.4 更新 `process_single_pdf` 收集 per-page 結果
  - [ ] 5.5 驗證：所有現有測試仍通過，外部行為不變

- [ ] 6. 最終驗證
  - [~] 6.1 執行完整測試套件（含 property tests）
  - [~] 6.2 執行 mypy type check
  - [~] 6.3 執行 ruff lint check
