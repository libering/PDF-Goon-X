# Requirements: pdf-goon-hardening

## 概要

修復已知 bugs、加固安全性、改善 core.py 的可測試性與架構。所有變更保持向後相容（相同輸入 → 相同輸出）。

## 約束條件

1. **保持模組化**：不合併模組、不增加模組間耦合。每個模組可獨立測試。
2. **DI 簽名不變**：`run: Callable[[list[str]], str]` 注入介面保持不變，下游模組無需修改。
3. **公開 API 不變**：`pdf_goon.process()` 的參數與回傳型態不變。
4. **現有測試全部通過**：任何步驟完成後，111 個現有測試不可失敗。

## 修復項目

### Bug Fixes

#### B1: 子圖索引解析錯誤

**問題**：`_finalize_page_files` 中 `re.search(r"-(\d+)", local_file.name)` 匹配到檔名中第一個 `-數字` 模式，而非結尾的文件索引。例如 `page_1_tmp-001.png` 捕捉到 `"1"` 而非 `"001"`。

**驗收標準**：
1. 當同一頁有多張提取圖片時，子圖命名正確使用文件尾部索引（如 `001_000.png`, `001_001.png`）
2. regex 錨定到 `-數字.副檔名$` 模式

#### B2: workspace 文件名碰撞

**問題**：提取模式用 `page_{page}_tmp` 前綴，渲染模式用 `page_{page}_tmp-{page}`。`workspace.glob(f"{local_prefix.name}*")` 會同時抓到兩者。

**驗收標準**：
1. 渲染模式使用獨立前綴（如 `render_{page}_tmp`），與提取前綴無 glob 重疊
2. 每頁只處理屬於該頁正確模式的檔案

#### B3: `!delete` 路徑過濾過寬

**問題**：`"!delete" not in str(f)` 是字串包含檢查，會誤排除路徑中碰巧包含 "!delete" 字串的合法檔案。

**驗收標準**：
1. 過濾改為檢查路徑組件（`f.parts`），只排除直接位於名為 `!delete` 的目錄下的檔案
2. 名稱包含 "!delete" 子字串但非目錄名的 PDF 不被排除

### Security

#### S1: subprocess 無 timeout（DoS 向量）

**問題**：`run_command` 中 `subprocess.run` 無 timeout 參數，惡意 PDF 可導致 Poppler 無限掛起。

**驗收標準**：
1. `run_command` 加入合理 timeout（預設 300 秒）
2. 超時後拋出 `SubprocessError` 並包含 "timeout" 描述
3. timeout 值可透過參數覆寫

#### S2: local directory tool 搜索加 allowlist

**問題**：`get_tool_path` 的 local directory 搜索可被利用做二進制植入攻擊。

**驗收標準**：
1. 只有已知工具名稱（pdfimages, pdfinfo, pdftocairo, pingo 及其 .exe 變體）允許走 local directory 搜索
2. 非 allowlist 的工具名稱跳過 local directory 搜索
3. 定義 `_ALLOWED_LOCAL_TOOLS: frozenset[str]` 常量

### Architecture

#### A1: `_process_page` 回傳結構化結果

**問題**：`_process_page` 透過檔案系統副作用溝通結果（回傳 None），無法追蹤每頁的成功/失敗狀態。

**驗收標準**：
1. `_process_page` 回傳新的 `PageResult` dataclass，包含 page number、mode used、files produced
2. `process_single_pdf` 收集 per-page 結果用於 verbose 報告
3. 外部行為不變（相同輸出檔案、相同 exit code）

#### A2: 消除 workspace glob 隱式合約

**問題**：`_finalize_page_files` 依賴 workspace glob + regex 解析檔名來找到檔案，與 extract/render 之間存在隱式合約。

**驗收標準**：
1. `_process_page` 直接使用 `extract_images` / `render_page` 回傳的 file list 傳入 `_finalize_page_files`
2. 不再依賴 workspace glob 來收集生成的檔案
3. 現有測試繼續通過
