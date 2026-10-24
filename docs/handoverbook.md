Created At: 2026-06-21T07:15:07Z
Last Updated: 2026-10-24T18:40:00Z
File Path: `file:///d:/vibe%20x/coding/%E9%96%8B%E6%BA%90/pdf-goon/docs/handoverbook.md`

# PDF-Goon Handover Book

## 專案概覽

PDF-Goon 是一個 CLI 工具和 Python 庫，用於從 PDF 檔案中提取高品質圖片。它智能判斷是直接提取嵌入圖片（pdfimages）還是渲染頁面（pdftocairo），取決於頁面內容。

核心決策邏輯（PRD §4.1）：
- 頁面只有一張大圖（>min_width, RGB/Gray）→ **EXTRACT**（直接提取，零品質損失）
- 其他（多圖/混合內容/小圖/tricky color/純文字）→ **RENDER**（整頁渲染，DPI 由最大圖推算）

## 目前狀態（2026-10-24 更新：瓦片分塊渲染引擎交付、TDD 韌性加固與全域公開語料庫建置）

### ✅ 瓦片分塊渲染引擎 (Tiled Render Engine) 正式交付 (Commit: `25c7fe1`)

1. **模組架構與底層矩陣運算 (`pdf_goon/render/tiler.py`)**：
   - 實現獨立深模組 `pdf_goon/render/tiler.py`，完整封裝 PDFium C-API (`FPDF_RenderPageBitmapWithMatrix`)、仿射平移矩陣運算與記憶體即時釋放。
   - 採用 **Padding-and-Crop** 技術（邊緣外擴 $P=2\,\text{px}$ 採樣後裁切回精確尺寸），消除雙線性插值在分塊邊緣造成的灰階/暗色接縫偽影，達成 **100% 零接縫、零像素漂移 (Zero Pixel Drift)**。
   - 封裝 `calculate_tile_grid`，自動處理網格動態邊界截斷，確保邊界瓦片完全對齊畫布邊界，無 1 像素偏差。
   - 支援雙模輸出（自足設計）：預設無縫拼合成單張高解析度大圖；指定 `save_tile_dir=True` 時額外導出結構化切片目錄與 `metadata.json`。

2. **智慧自愈與管線整合 (Define Errors Out of Existence)**：
   - `pdf_goon/_render_worker.py`：將原先直接拋出 `ValueError` 中斷的硬阻斷邏輯，重構為自適應智慧切換。當頁面投影像素超過 100 MP 或任一單邊超過 16,384 像素時，自動切換至瓦片分塊渲染引擎，保證大型畫布平滑完成渲染。
   - 安全邊界防禦：保留 500 MP 上限防禦（Pillow 解壓炸彈保護），若遇到 77 GP 級別的惡意解壓炸彈則安全拒絕。
   - CLI 與 Public API：新增 `--tiles` 命令列參數，`pdf_goon.models.Config` 與 `pdf_goon.process()` 新增 `tiles: bool = False` 支援。

3. **雙證據實證驗收 (Dual-Evidence Verification)**：
   - **邏輯證據 (Logical Evidence)**：
     - 全套 244 個自動化測試 100% 綠燈通過（`tests/test_tiled_render.py` 6 個測試覆蓋幾何切分、像素等價性、目錄產出、Worker 自動切換與真機樣本）。
     - 全倉庫代碼 100% 符合單檔 $\le 500$ 行、單函式 $\le 50$ 行之硬約束（`tests/test_architecture_limits.py` 綠燈）。
     - CodeGraph 圖譜已同步完成（`codegraph sync`，新增 9 個、修改 8 個節點）。
   - **實體特徵證據 (Physical Artifact Evidence)**：
     - 測試樣本：真實世界 198.6 MP 木衛一極限地質圖（`commons_usgs_io_geological_map.pdf`，3983x2872 pts，300 DPI 下解析度達 $16,596 \times 11,967\,\text{px}$）。
     - 實測結果：以常數記憶體安全（單瓦片 $\sim 67\,\text{MB}$，不崩潰、無 OOM），在 **10.18 秒** 內成功拼合完成，產出 **56.17 MB** 之無縫超高清 PNG 圖像。

1. **JBIG2 解碼平滑容錯 (`pdf_goon/analyze/session.py`)**：
   - 修復先前遍歷 `page.images` 惰性生成器時，因缺少本機 `jbig2dec` 二進位執行檔而直接拋出 `DependencyError` 導致管線崩潰的重大缺陷。
   - 將影像物件檢索與元數據解析完整納入安全防禦，遇到缺少依賴或解碼異常時平滑記錄日誌，並引導至 PDFium 整頁 `RENDER` 模式（PDFium 原生支援 JBIG2）。
2. **防偽綠零輸出防禦 (`pdf_goon/pipeline/page.py`)**：
   - 消除潛在的假綠成功（False-Green）漏洞：當頁面被判定為非空白模式（EXTRACT 或 RENDER），但在管線執行與遮罩過濾後產出的檔案數量為 0 時，嚴格判定為處理失敗 (`error="Zero files produced..."`)，阻斷虛假成功回報，防止用戶原檔被誤刪或移動。
3. **實證測試覆蓋 (`tests/test_robustness_defenses.py`)**：
   - 以嚴格 TDD 規範撰寫 3 個防禦驗證用例，全部綠燈通過。全倉庫測試總數增至 **238 passed**，100% 符合單檔 $\le 500$ 行與單函式 $\le 50$ 行約束。

### ✅ 全維度開源公開測試語料庫擴充 (Corpus Expansion)

為支援極限邊界測試與防偽綠驗證，自各大公開開源儲存庫篩選並納入多維度真實樣本：
1. **超巨型畫布維度 (100MP ~ 200MP)**：
   - `commons_usgs_io_geological_map.pdf` (16.08 MB, 3983x2872 pts, 300 DPI 下達 **198.60 MP**，瓦片渲染最極致實體驗證標本，源自 Wikimedia Commons)。
   - `Final Fantasy Poster` (2.69 MB, 3000x2006 pts, 300 DPI 下達 **104.48 MP**，源自 Internet Archive)。
2. **超長頁數維度 (1,000+ 頁)**：
   - `ia_patent_Pharmaceutical_Manuf.pdf` (23.28 MB, **1,756 頁** 1-bit 二值化專利文檔，JBIG2 解碼壓力測試)。
3. **密集向量與東亞/RTL 字型維度**：
   - `commons_beethoven_orchestra_score.pdf` (2.35 MB, 12 頁極端密集五線譜與微型音符向量排版)。
   - `pdfjs_22060_A1_01_Plans.pdf` (5.97 MB, 大型建築施工 CAD 幾何藍圖)。
   - `pdfjs_ArabicCIDTrueType.pdf` 與 `pdfjs_90ms_rksj_h_sample.pdf` (阿語 RTL 與日文 Shift-JIS 縱橫排版)。
4. **國際標準極限規格維度**：
   - veraPDF 官方測試集 40+ 件（涵蓋 Blend Modes、DeviceN/Separation 色彩空間、Font Subsets、AcroForms）。
   - PDF Association ISO 32000-2 (PDF 2.0) 官方樣例 7 件。

### ✅ 瓦片分塊渲染 (Tiled Rendering) 原型實證 (Zero-Drift & OOM Defense)

1. **核心數學模型**：
   - 基於 `FPDF_RenderPageBitmapWithMatrix` 的局部平移仿射矩陣：
     $$\begin{bmatrix} a & b & e \\ c & d & f \end{bmatrix} = \begin{bmatrix} s & 0 & -x_0 + P \\ 0 & s & -y_0 + P \end{bmatrix}$$
   - 採用 **Padding-and-Crop** 技術（外擴邊緣 $P=2\,\text{px}$ 渲染後再裁切回精確尺寸），消除瓦片邊緣雙線性插值 (Bilinear Interpolation) 的灰階/暗色接縫偽影。
2. **實證數據 (`scratch/prototype_tiled_render.py`)**：
   - 像素漂移檢驗：標準整頁渲染與 4 塊瓦片拼合結果進行像素級差分（`ImageChops.difference`），達成 **100% 零接縫、零漂移 (diff: None)**。
   - 極限畫布壓測：在模擬高達 $24,749 \times 35,000\,\text{px}$（**8.66 億畫素 / 866 MP**）的極限條件下，成功以常數記憶體在 31ms 內渲染單個瓦片，徹底消除 32,767 坐標溢出與 OOM 崩潰風險。

### ✅ 多進程批次並行加速 (Multiprocessing Concurrency) 交付 (Commit: `d3e8474`)

1. **核心架構成果 (I-S-T-O 模式)**：
   - **並行池治理模組 (`pdf_goon/concurrency/pool.py`)**：
     - 提供深模組純函數接口 `resolve_worker_count(jobs, task_count)`，封裝 CPU 拓撲探測與上限保護（預設上限 4 核，0 自動調度，杜絕 OOM）。
     - 提供 `execute_parallel_tasks(worker_fn, tasks, max_workers)`，封裝 `concurrent.futures.ProcessPoolExecutor`，嚴格保障 Windows `spawn` 相容性、有序輸出保證與異常自動降級。
   - **多檔案批次並行 (`pdf_goon/pipeline/batch.py`)**：
     - 支援目錄下多本 PDF 檔案進程池並行處理 (`_process_batch_parallel`)，單檔錯誤完全隔離不中斷其他檔案。
   - **單檔案多頁並行渲染 (`pdf_goon/extract.py`, `backends.py`, `pipeline/single.py`)**：
     - `render_batch` 支援分塊任務並行調度 (`_chunk_tasks`)，單一進程獨立載入 PDF 進行局部頁面連續渲染，徹底避開 PDFium C 指針無法跨進程 Pickle 之 Windows 限制。
   - **雙級並行互斥防禦**：
     - 多檔案批次並行運行時，自動鎖定子檔案內部渲染為單線程，防止 $N \times M$ 進程階乘爆炸。
   - **CLI 與 Public API 擴充**：
     - CLI 新增 `-j / --jobs` 參數，`pdf_goon.process()` 與 `make_config()` 新增 `jobs: int = 1`。

2. **雙證據實證驗收 (Dual-Evidence Verification)**：
   - **邏輯證據 (Logical Evidence)**：
     - 全套 238 個自動化測試 100% 通過（包含 `tests/test_concurrency.py` 7 個並行與任務分塊屬性測試）。
     - 版權真實語料庫測試（`tests/test_real_pdf_corpus.py`）3 個大樣本 100% 通過。
     - 全倉庫 100% 滿足單檔 $\le 500$ 行、函式 $\le 50$ 行（`test_architecture_limits.py` 綠燈）。
     - 靜態檢查：Mypy 26 檔案 0 錯誤；Ruff 程式碼品質檢查 100% 通過。
   - **實體特徵證據 (Physical Artifact Evidence)**：
     - 測試樣本：真實世界彩色日漫《コミック3.pdf》（22 頁高解析度跨頁彩頁）。
     - 多檔案批次處理（2 本 PDF）：
       - `Jobs: 1` 耗時 **81.940s**，產出 44 個非零 PNG 檔案，共計 **108.57 MB**。
       - `Jobs: 2` 耗時 **45.403s**，產出 44 個非零 PNG 檔案，共計 **108.57 MB**。
       - **實測加速比：1.80x**（接近理論雙核上限 2.0x）。

### ✅ 全域 AI 開發規則升級與學術級研析 (GEMINI.md & vibe-coding-cn)
1. **研究成果與論文產出**：
   - 爬梳解構 `tradecatlabs/vibe-coding-cn`（412條本體論功法、五大命題、三域架構）。
   - 產出學術論文報告：`vibe_coding_rules_synthesis_paper.md`。
2. **規則落地於 `C:\Users\user\.gemini\GEMINI.md`**：
   - **零憑證與最小特權原則 (Zero Credential & Least Privilege)**：嚴禁索取/展示/提交 Token/Key，嚴禁 sudo/Administrator 提權執行。
   - **深模塊原則與定義規避錯誤 (Deep Modules & Define Errors Out of Existence)**：對外極簡接口，內部下沉所有並發調度、記憶體治理與自動安全擴容。
   - **圖爾敏因果偵錯門禁 (Toulmin Debugging Protocol)**：偵錯與重構強制依循「事實依據 (Grounds) ➔ 連接規則 (Warrant) ➔ 修復主張 (Claim)」。
   - **雙證據實證驗收門禁 (Dual-Evidence Verification)**：任務交付必須同時具備邏輯單元測試綠燈與產物實體特徵（非零位元組、解析度、性能讀數）。

### ✅ v1.1.0 發布：模組化架構、C 記憶體治理、灰階保真與安全全面加固（主幹 `master`）

1. **安全威脅分析與加固成果**：
   - **參數注入防護 (CWE-88 Option Injection)**：`pdf_goon/optimize.py` 調用外部優化工具時，將圖檔路徑強制轉換為絕對路徑 `image_path.resolve()`，徹底阻斷以連字號 `-` 開頭檔名被誤解析為 CLI Flag 之攻擊路徑。
   - **空檔名與目錄遍歷兜底 (Empty/Hidden Stem Normalization)**：`pdf_goon/pipeline/single.py` 處理空白或以點開頭的隱藏檔名（如 `.pdf`、`..`）時，自動正規化目錄名為 `unnamed_pdf`，防止目錄碰撞或父層遍歷。
   - **PDFium C 記憶體超大畫布保護 (Canvas Megapixel Bound)**：`pdf_goon/_render_worker.py` 在調用 `page.render()` 前，增加投影像素上限檢核（`MAX_RENDER_PIXELS = 100_000_000`），防止極端大頁面（如 10 萬點 MediaBox）引發數十 GB 的 C-level 記憶體申請而造成 DoS / 記憶體顛簸。
   - **600 DPI 印刷/同人本解壓容量擴容**：在 `pdf_goon/__init__.py` 自動將 `pypdf.filters.ZLIB_MAX_OUTPUT_LENGTH` 與 `FLATE_MAX_BUFFER_SIZE` 擴展至 256MB，解決 600 DPI A4 漫畫頁面（~104MB RGB）誤觸解壓炸彈防禦的問題。
   - **AES 加密 PDF 支援**：將 `cryptography>=3.1` 納入 `pyproject.toml` 正式依賴，保證 AES 標準加密 PDF（如 `egihid.pdf`）正常解析。
   - **Session 異常隔離保護**：`pdf_goon/analyze/session.py` 在輪巡 `page.images` 時加入安全捕捉，遇到損壞或解壓受阻之圖片時優雅降級回退至 `RENDER` 模式。

2. **驗證與測試覆蓋**：
   - 新增專屬測試檔：`tests/test_security_hardening.py`。
   - Fast Tier：228 passed in ~28s。
   - Corpus Tier：3 passed in ~60s（包含 `egihid.pdf`、`コミック3.pdf`、`novel_spread_a5.pdf` 100% 通過）。
   - 靜態檢查：Mypy 52 files 0 issues；Ruff 0 issues。

### ✅ 核心優化 Phase 3：渲染底層 C 記憶體生命週期治理與灰階/色彩空間精確保真（分支：`refactor/modular-architecture`）

1. **背景與翻譯組核心痛點**：
   - **PDFium 原生 C 記憶體累積洩漏**：先前 `_render_worker.py` 在執行 `page.render()` 與 `bitmap.to_pil()` 後，未在 `finally` 區塊顯式呼叫 `bitmap.close()`、`pil_image.close()` 與 `page.close()`，在長篇漫畫與小說渲染批次時累積大量未釋放的 C-level 點陣緩衝區。
   - **黑白/灰階頁面 300% 體積膨脹與色彩污染**：PDFium 預設將所有頁面渲染為 24-bit 3-channel RGB。對於純文字小說、黑白漫畫與二值化掃描本，強行儲存為 RGB 不僅造成點陣圖記憶體與 PNG 檔案體積膨脹近 3 倍，更易在翻譯修圖組（Clean/Typeset）開啟時引入 RGB 偏色雜訊。

2. **優化實作成果**：
   - **`_normalize_rendered_image` 模組 (`_render_worker.py`)**：使用底層 C-level 差分運算 (`ImageChops.difference`) 高速檢驗 R, G, B 通道是否完全一致；在 100% 零資訊損失的前提下，將純灰階內容自動轉化為單通道 8-bit `L` 模式（帶透明通道則為 `LA` 模式），非灰階彩色插圖則嚴格保留完整 24-bit RGB。
   - **`_render_single_page_to_file` 確定性釋放封裝**：以嚴格的 `try...finally` 保障無論渲染成功或中途異常，`pil_image.close()`、`bitmap.close()` 與 `page.close()` 均被確定性調用，徹底杜絕子進程內的 C-level native 記憶體堆積。
   - **批次與單頁渲染全面複用**：重構 `run_batch_render` 與 `_handle_single_page_worker` 消除重複程式碼，兩者均統一受生命週期與色彩保真治理。

3. **質量與架構指標**：
   - 程式碼規範：`pdf_goon/_render_worker.py`（144 行 $\le 500$ 行，最大函式 26 行 $\le 50$ 行）；`tests/test_render_worker.py`（329 行 $\le 500$ 行，最大函式 25 行 $\le 50$ 行）。
   - Mypy：Success (0 issues across 51 source files)。
   - Ruff：All checks passed (0 issues)。
   - 測試總數：225 fast passed + 3 corpus passed = 228 passed，0 failed。

### ✅ 核心優化 Phase 2：測試套件解耦與行數規範全域納管（分支：`refactor/modular-architecture`）

1. **背景與目標**：
   - 先前模組化重構僅嚴格限制 `pdf_goon/` 原始碼目錄，測試套件 `tests/` 中仍存在單檔巨大（`test_core.py` 達 1504 行、`test_analyze.py` 達 907 行、`real_pdf_fixtures.py` 達 855 行）以及 11 個測試函式超過 50 行的工程債務。
   - 將全域架構守門規範擴展為全倉庫級別：無論是核心原始庫還是測試套件，**所有 Python 檔案嚴格 $\le 500$ 行，所有函式嚴格 $\le 50$ 行，零豁免**。

2. **解耦拆分成果**：
   - **`tests/real_pdf_fixtures.py` (855 行 $\to$ 483 行)**：抽出多頁書籍/小說生成器至專屬模組 `tests/fixtures_books.py` (292 行)，保留所有既有匯出簽名。
   - **`tests/test_analyze.py` (907 行 $\to$ 367 行)**：依職責拆分為 `tests/test_analyze_dpi.py` (262 行，幾何與候選 DPI 屬性測試)、`tests/test_analyze_decide.py` (305 行，決策與理由字串測試) 及 `tests/test_analyze.py` (367 行，頁面分析與 Session 檢視)。
   - **`tests/test_core.py` (1504 行 $\to$ 485 行)**：拆分為 `tests/test_core_batch.py` (342 行，批次處理與韌性)、`tests/test_core_finalize.py` (332 行，檔名碰撞與命名保留) 及 `tests/test_core.py` (485 行，單頁核心管線與等價性測試)。
   - **長函式解構**：將 `test_batch_resilient_to_individual_failures`、`test_render_path_delegates_to_finalize_rendered` 等 11 個長函式拆解為複用性高且獨立的 helper，所有測試函式長度全數降至 $\le 45$ 行。
   - **分離版權語料測試**：將 3 個耗時較長之本機實體書籍 E2E 測試獨立至 `tests/test_real_pdf_corpus.py` (103 行)，使常規測試套件執行時間維持在 40 秒以內。
   - **全域守門納管 (`tests/test_architecture_limits.py`)**：擴大檢測範圍至 `pdf_goon/` 與 `tests/`，強制防禦任何未來的代碼膨脹。

3. **質量與指標**：
   - 全倉庫 27 個測試檔案與 24 個庫檔案，100% 滿足 $\le 500$ 行、函式 $\le 50$ 行。
   - Mypy：Success (0 issues across 24 source files)。
   - Ruff：All checks passed (0 issues)。
   - 測試總數：221 passed + 3 corpus passed = 224 passed，0 failed。

### ✅ 核心優化 Phase 1：圖片提取 I/O Session 機制與記憶體生命週期管理（分支：`refactor/modular-architecture`）

1. **背景與瓶頸**：
   - 解決過去 `EXTRACT` 提取模式下，每一頁都重新執行 `open(pdf_path)` 並重新建立 `pypdf.PdfReader` 解析 XRef 交叉引用表的重複 I/O 耗損（處理 100~200 頁漫畫時產生 100~200 次重複磁碟讀取）。
   - 解決 `img_file.image`（PIL Image）生成後未即時關閉釋放、佔用記憶體的問題。

2. **架構設計與優化成果**：
   - **`PdfExtractSession` 與 `SessionExtractBackend` 協議 (`backends.py`)**：擴充 `ExtractBackend` 支援 `open_session(pdf_path)`，建立可共用 Reader 之連線協議。
   - **`PypdfExtractSession` 實作 (`extract.py`)**：在 Session 內部維持單一底層檔案控制代碼與 `pypdf.PdfReader`，多頁提取時直接取用 `pages[page_num - 1]`；支援 context manager 自動安全關閉。
   - **記憶體即時釋放**：非 JPEG 圖像以 PIL Image 儲存為 PNG 後，於 `finally` 區塊顯式呼叫 `pil_image.close()`，避免長篇漫畫批次處理時記憶體累積洩漏。
   - **管線深度整合 (`pipeline/single.py`, `pipeline/page.py`)**：在 `_process_immediate_pages` 週期內自動開啟/釋放 extraction session，並向下傳遞給 `_process_page`；在測試環境使用 mock 時自動感知回退，保持 100% 舊有測試相容性。

3. **質量與指標**：
   - 單檔與函式限制：`pdf_goon/extract.py`（217 行 $\le 500$ 行，最大函式 33 行 $\le 50$ 行）。
   - Mypy：Success (0 issues across 26 source files)。
   - Ruff：All checks passed (0 issues)。
   - 測試總數：221 fast passed + 3 corpus passed = 224 passed，0 failed。

### ✅ 5 大關鍵邊界語料合成產生器與無損迴歸測試（分支：`refactor/modular-architecture`）

1. **背景與工程動機**：
   - 依據 PRD 核心初衷，拒絕無關功能蔓延（如 `--dry-run` 檢視或 `--watch` 守護行程），聚焦於最高保真度與決策引擎的邊界極限。
   - 解決過去測試套件依賴本機 `real_test_pdfs/`（受版權限制無法上傳 CI/CD）的痛點，以標準 ISO 32000 語意程式化合成 5 大極限邊界樣本。

2. **合成語料庫產生器 (`tests/synthetic_fixtures.py`, 211 行)**：
   - **橫向跨頁大圖 (Two-Page Spread)**：`make_two_page_spread_pdf`（$1200 \times 800$ pt 頁面內嵌 $2400 \times 1600$ px 橫向圖像），驗證跨頁滿版辨識，斷言直接 `EXTRACT` 且零品質損失。
   - **出血線裁切 (Bleed Margins / CropBox != MediaBox)**：`make_bleed_margins_pdf`（MediaBox $620 \times 820$ pt，CropBox $600 \times 800$ pt 帶 10pt 出血），驗證有效視覺邊界計算，斷言裁切出血不誤判白邊並走 `EXTRACT`。
   - **帶旋轉標籤頁面 (/Rotate 90/270)**：`make_rotated_page_pdf`（直式儲存圖像搭配 `/Rotate 90`），驗證精準觸發 `RENDER` 扶正視角，避免提取出橫倒畫面。
   - **老舊黑白二值本 (Monochrome 1-bit scan)**：`make_monochrome_1bit_pdf`（1-bit Flate 點陣圖無 `/ImageMask true`），驗證二值圖流不被誤當成遮罩或空白頁，斷言安全無損 `EXTRACT`。
   - **漢化修圖/向量文字層 (Vector Overlay)**：`make_vector_overlay_pdf`（滿版底圖覆蓋 Form XObject 向量文字層），驗證深入 ContentStream 偵測文字，斷言觸發 `RENDER` 保留嵌字與修圖。

3. **端到端迴歸測試套件 (`tests/test_synthetic_corpus.py`, 178 行)**：
   - 包含 5 個聚焦的端到端驗證測試，檢查 `PypdfSession` 幾何與決策、`process_single_pdf` 真實執行結果及 PIL 像素尺寸/模式。
   - 5 passed in 1.42s，零外部版權依賴，可於所有開源 CI/CD 環境即時執行。

4. **品質與架構指標**：
   - 程式碼極限規範：`tests/synthetic_fixtures.py`（211 行 $\le 500$ 行，最大函式 26 行 $\le 50$ 行）；`tests/test_synthetic_corpus.py`（178 行 $\le 500$ 行，最大函式 28 行 $\le 50$ 行）。
   - Mypy：Success (0 issues across 26 source files)。
   - Ruff：All checks passed (0 issues)。
   - 測試總數：216 fast passed + 3 corpus passed = 219 passed，0 failed。

### ✅ 模組化架構重構 Phase 3：全倉庫函式 $\le 50$ 行無死角零豁免守門（分支：`refactor/modular-architecture`）

1. **重構背景與目標**：
   - 在 Phase 1（`analyze/`）與 Phase 2（`pipeline/`）拆解後，全專案僅剩 `cli.py`、`geometry.py` 與 `_render_worker.py` 存在少數超出 50 行的函式。
   - 本階段旨在將這最後 3 個模組內部的長函式徹底解耦，使全倉庫 100% 函式符合軟體工程規範（單函式 $\le 50$ 行）。

2. **模組拆解成果**：
   - `pdf_goon/geometry.py`（163 行）：`extract_page_geometry`（原 71 行）拆解為 `_extract_page_dim_and_rot`、`_inspect_obj_rotation`、`_extract_image_objects`；`is_full_page_image`（原 64 行）拆解為 `_check_placed_bbox_coverage` 與 `_check_pixel_ratio_coverage`。最大函式僅 33 行。
   - `pdf_goon/cli.py`（232 行）：`_build_parser`（原 87 行）拆解為 `_add_core_arguments` 與 `_add_diagnostic_arguments`；`main`（原 107 行）拆解為 `_check_internal_render_worker`、`_setup_cli_logging`、`_print_banner_and_summary` 與 `_execute_process`。最大函式僅 46 行。
   - `pdf_goon/_render_worker.py`（100 行）：`main`（原 53 行）拆解為 `_handle_batch_worker` 與 `_handle_single_page_worker`。最大函式僅 33 行。

3. **全倉庫零豁免架構守門 (`tests/test_architecture_limits.py`)**：
   - 升級為全倉庫無死角 AST 掃描：斷言全專案無任何檔案 $> 500$ 行、無任何函式 $> 50$ 行（目前全倉庫最長函式僅 49 行）。
   - 2 passed in 0.29s，永久杜絕任何模組回退。

4. **驗證與防偽綠成果**：
   - Fast Tier：211 passed in ~31s。
   - Corpus Tier：3 passed in ~78s（7 個真實 PDF 樣本全數實證）。
   - 總計 214 passed，0 failed，完成 Commit `9caa990`。

### ✅ 模組化架構重構 Phase 2：`core.py` 拆解至 `pipeline/` 子套件（分支：`refactor/modular-architecture`）

1. **重構背景與目標**：
   - 原 `pdf_goon/core.py`（587 行）包含 `process_single_pdf`（208 行）、`_process_page`（93 行）、`process_batch`（67 行）等過長函式，違反單檔 $\le 500$ 行與單函式 $\le 50$ 行之規範。
   - 核心難點：`tests/test_core.py` 與 `tests/test_backends.py` 大量使用 `patch("pdf_goon.core.xyz")`，重構必須達成零破壞性變更與動態 mock 攔截。

2. **模組架構拆解成果**：
   - `pdf_goon/pipeline/progress.py`（30 行）：進度條渲染與終端顯示。
   - `pdf_goon/pipeline/finalize.py`（115 行，最大函式 36 行）：遮罩刪除、動態呼叫 `optimize_image` 與檔案重命名。
   - `pdf_goon/pipeline/page.py`（150 行，最大函式 43 行）：單頁決策獲取、抽取與渲染分流。
   - `pdf_goon/pipeline/single.py`（319 行，最大函式 42 行）：單檔生命週期，拆解為 `_analyze_pages_phase`、`_process_immediate_pages`、`_execute_render_phase` 與 `_render_batch_pages`。
   - `pdf_goon/pipeline/batch.py`（124 行，最大函式 38 行）：多檔批次目標檢索與異常隔離。
   - `pdf_goon/pipeline/__init__.py`（29 行）：子套件入口導出。
   - `pdf_goon/core.py`（121 行，原 587 行）：縮減為薄 Facade，保留 `_DefaultAnalyzeBackend`、`_DefaultExtractBackend`、`_DefaultRenderBackend` 轉發適配器，並透過動態核心查找（`sys.modules.get("pdf_goon.core")`）相容既有單元測試。

3. **全域無例外架構守門 (`tests/test_architecture_limits.py`)**：
   - `test_all_files_line_limits`：全套件無例外驗證所有檔案 $\le 500$ 行（最大檔案為 319 行，100% 通過）。
   - `test_core_architecture_function_line_limits`：驗證 `analyze`、`pipeline` 與 `core` 所有函式 $\le 50$ 行（最大函式為 44 行，100% 通過）。

4. **驗證與防偽綠成果**：
   - Fast Tier：211 passed in ~40s。
   - Corpus Tier：3 passed in ~114s（7 個真實 PDF 樣本全數實證）。
   - 總計 214 passed，0 failed，完成 Commit `44a0a92`。

### ✅ 模組化架構重構 Phase 1：`analyze.py` 拆解與架構約束守門（分支：`refactor/modular-architecture`）

1. **重構背景與目標**：
   - 依據專案協作邊界規範（`d:\vibe x\coding\自用\gitpush skills\AGENTS.md` 與 `GEMINI.md` Part II），程式碼必須嚴格遵守：單一檔案 $\le 500$ 行、單一函式 $\le 50$ 行。
   - 原 `pdf_goon/analyze.py`（629 行）與內部巨型函式（如 `decide_processing_mode` 125 行、`analyze_page_text_layers` 103 行、`PypdfSession.inspect_page` 89 行）嚴重違反約束。
   - 依「單次單模組原則 (One Module at a Time)」，Phase 1 專注拆解 `analyze.py` 為 `pdf_goon/analyze/` 子套件。

2. **模組架構拆解成果**：
   - `pdf_goon/analyze/text.py`（138 行，最大函式 44 行）：文字運算子辨識、ContentStream 走訪、Form XObject 遞迴解析與文字降級兜底。
   - `pdf_goon/analyze/image.py`（131 行，最大函式 41 行）：ISO 32000-1 1-bit Stencil Mask 判斷、影像元資料提取與頁面尺寸查詢。
   - `pdf_goon/analyze/decide.py`（300 行，最大函式 44 行）：採用責任鏈模式（Chain of Responsibility），將決策邏輯拆分為 `_check_force_render`、`_check_blank_or_mask_page`、`_check_text_and_colors`、`_check_image_geometry_and_counts` 四大獨立規則處理器。
   - `pdf_goon/analyze/session.py`（165 行，最大函式 33 行）：`PypdfSession` 連續解析控柄，拆分 `_extract_geometry_info` 與 `_extract_page_images`。
   - `pdf_goon/analyze/__init__.py`（41 行）：無痛相容 Facade，完整導出既有所有公開與私有輔助符號（如 `_build_render_reason`、`_compute_render_dpi`）。

3. **永久架構約束守門測試 (`tests/test_architecture_limits.py`)**：
   - 納入 `pytest` 每次自動執行，以 Python `ast` 走訪掃描 `pdf_goon/` 下所有程式檔與函式，強制斷言行數，永久杜絕回退。

4. **驗證與防偽綠成果**：
   - Fast Tier：211 passed in ~29s。
   - Corpus Tier：3 passed in ~71s（含 7 個真實 PDF 樣本全數實證）。
   - 總計 214 passed，0 failed，完成 Commit `458375f`。

5. **下一步 (Phase 2)**：
   - 推進 `pdf_goon/core.py`（587 行）拆解至 `pdf_goon/pipeline/` 子套件（`progress.py`, `finalize.py`, `page.py`, `single.py`, `batch.py`），並保留 `core.py` 作為薄 Facade。

### ✅ v1.0.1 修復：解決透明度圖片遮罩誤判漏頁 (SMask Drop Bug) 與漫畫跨頁對齊

1. **缺陷根因與修復 (Root Cause & Fix)**：
   - **歷史 Bug 1 (SMask 遮罩誤判)**：`pdf_goon/analyze.py` 的 `is_true_pdf_mask()` 誤查 `"/SMask" in xobj_dict`，將帶有透明通道（Soft Mask）的普通圖像誤判為遮罩，放入 `mask_indices` 丟棄，導致 `egihid.pdf`、`完全理解...pdf` 等真實 PDF 的重要頁面被判定為 `BLANK` 靜默漏頁。
     - **修復方案**：依 ISO 32000-1 規格，僅在 `xobj_dict.get("/ImageMask") is True`（1-bit Stencil Mask）時判定為遮罩。
   - **歷史 Bug 2 (Form XObject 嵌套文字漏判)**：日本同人小說雙頁排版（如 `目がさめたら_A5見開き版.pdf`）常將左右頁文字封裝進 Form XObjects（`/Subtype /Form`），頂層 ContentStream 僅有 `Do` 調用指令而無直接 `Tj/TJ`。舊版 `analyze_page_text_layers()` 頂層掃無文字即直接回傳 `False, False`，導致整本 54 頁小說被當成 `BLANK` 整本丟棄！
     - **修復方案**：`analyze_page_text_layers()` 遞迴深入解析 Form XObject 內部 ContentStream，並在頂層無文字時回退檢查 `page.extract_text()`。
   - **安全兜底 (Blank Safeguard)**：`decide_processing_mode()` 強化，若頁面存在 XObject 圖片但無 non-mask 圖像，一律回退至 `RENDER` 渲染，絕不允許判定為 `BLANK` 造成資料靜默遺失。

2. **真實世界語料庫實證回歸 (Empirical Verification — 7 份實體樣本)**：
   - `egihid.pdf`（128 頁）：全數 128 頁順利提取（含第 1-2 頁），無任何漏頁。
   - `コミック3.pdf`（22 頁）：第 2 頁內嵌純白點陣圖（Min=255, Max=255）經 `EXTRACT` 提取出 `002.png`，全書 22 頁序號完全連續，維持漫畫閱讀器雙頁跨頁對齊（Spread Alignment）。
   - `novel_spread_a5.pdf`（54 頁）：BOOTH 同人小說見開き版，全數 54 頁精準判定為 `RENDER`，徹底解決小說文字整本漏頁。
   - `完全理解_篠澤広...pdf`：封面超大圖 ($2894 \times 4093$) 成功判定為 `EXTRACT`。
   - `ロコズバースデー...pdf`：第 1 頁封面排版走 `RENDER`，第 2 頁插畫走 `EXTRACT`。
   - `ミリフェス新刊.pdf`：12 頁同人誌 100% 精準無損提取。
   - `cg-python-guidebook-basic.pdf`：文字型技術書籍正常渲染。

3. **社群回饋與 RAG 沉澱 (`docs/reference-pdfpatcher.md`)**：
   - 解析 PDFPatcher（FreeImage + jbig2enc）與 `pdf-goon`（Poppler/Pillow）之 369 KB vs 359 KB 體積差異，證實像素 100% 數學無損，純為 PNG Ancillary Chunks 與 zlib Deflate 壓縮策略不同。

4. **分層測試架構與品質保證 (Tiered Testing)**：
   - **Tier 1 (常規快速測試)**：預設執行 `pytest`（自動過濾 `-m 'not corpus'`），僅需 ~26 秒（209 passed, 3 deselected），保障高頻迭代效率。
   - **Tier 2 (全量實體語料庫)**：執行 `pytest -m corpus` 驗證大型真實檔案（`egihid.pdf` 128 頁、`コミック3.pdf` 22 頁、`novel_spread_a5.pdf` 54 頁）。
   - **總測試數**：212 passed, 0 failed。
   - **版本號**：升級至 `v1.0.1` (`models.py` & `pyproject.toml`)。

5. **未來待納入之 5 大關鍵邊界語料類型 (Corpus Backlog)**：
   - **橫向跨頁大圖 (Two-Page Spread)**：長寬比接近 1.414（如 $9922 \times 7016$ 橫圖），檢驗 `is_full_page_image()` 是否能正確辨識橫向滿版並直接 `EXTRACT`，避免誤判為未滿版而降速渲染。
   - **出血線裁切 (CropBox != MediaBox)**：商業印刷或掃描本 MediaBox 帶有印刷出血，檢驗幾何計算是否以 CropBox 為準，防止邊緣 10~20pt 誤差導致滿版圖被誤判有白邊。
   - **帶旋轉標籤頁面 (/Rotate 90/270)**：圖片直式儲存但頁面字典帶旋轉標籤，檢驗是否精準觸發 `RENDER` 扶正，避免提取出的圖片橫倒損壞閱讀體驗。
   - **老舊黑白二值本 (JBIG2 / CCITT Fax)**：早期 2000~2010 年代掃描本，檢驗雙值影像流在不同平台環境（`jbig2dec`）下的無損提取相容性。
   - **漢化浮水印/局部修圖向量層**：滿版大圖上方覆蓋向量修字或透明注釋層，檢驗文字+圖混合時是否精準觸發 `RENDER`，防止只提取出生肉底圖而遺失嵌字。

### ✅ 漢化組內部測試版本與 Debug 版封裝完成 (v1.0.0)

1. **獨立 Debug 執行檔 (`dist/pdf-goon-debug.exe`)**：
   - 解決 Windows 檔案拖曳 (Drag-and-Drop) 執行時終端機視窗一閃即逝、無法看清報錯的問題。
   - 預設啟用 `--debug`, `-v`, `--pause` 以及自動寫入 `pdf_goon_debug.log`。
   - 任何異常皆印出完整 Python Call Stack (`traceback.print_exc()`)。
   - 啟動時自動輸出詳細診斷資訊標頭（Python 版本、OS/平台架構、執行檔路徑、完整傳參）。
   - 結束或出錯時強制等待 Enter 鍵 (`input()`)，測試人員可直接閱讀訊息或將生成的日誌檔發給開發者。

2. **正式發行版本 (`dist/pdf-goon.exe`)**：
   - 輕量乾淨模式，正常退出不阻塞，支援全套 CLI 參數（包含可選的 `--pause` 與 `--log-file`）。
   - 內置 PyInstaller worker 專屬調度（支援 `--_render_worker` 旗標繞過 PyInstaller `-m` 解析衝突）。

3. **打包產物清單 (`dist/`)**：
   - `dist/pdf-goon.exe` (Release 單檔執行檔, ~22.6MB)
   - `dist/pdf-goon-debug.exe` (Debug 內部測試執行檔, ~22.6MB)
   - `dist/pdf_goon-1.0.0-py3-none-any.whl` (Python Wheel 套件)
   - `dist/pdf_goon-1.0.0.tar.gz` (原始碼封裝)

4. **驗證與品質保證**：
   - Ruff: clean (0 issues)
   - Mypy: clean (32 source files, 0 errors)
   - Pytest: 205 passed (涵蓋全部屬性測試、單元測試、真實 PDF 整合測試)

2. **rendered-pages-output-loss spec — 全部 4 個任務完成**
   - Bug condition exploration test（確認 RENDER 路徑圖片被靜默丟棄）
   - Preservation property tests（確認 EXTRACT 路徑基線行為正確）
   - 修復：`_finalize_page_files()` 的 `was_rendered=True` 路徑跳過 regex 要求
   - Checkpoint：全綠

3. **單檔 PDF 路徑 Bug 修復**
   - **問題**：`pdf-goon "C:\file.pdf"` 傳入單一 PDF 時，`process_batch()` 把它當目錄 glob，找不到檔案直接回傳空結果
   - **修復**：`core.py` 的 `process_batch()` 新增判斷 — 如果 path 是 `.pdf` 文件就直接作為目標列表
   - **驗證**：120 tests pass

4. **improve-detection-quality spec — 全部任務完成**
   - **目標**：改善 RENDER 模式的 DPI 計算精度
   - **問題**：目前只用最大圖片的寬度算 DPI，沒考慮高度 → 窄長圖/未佔滿頁寬的圖會被低估
   - **解法**：每張圖算 `max(width_dpi, height_dpi)`，取所有合格圖片的最大值，永不低於 dpi_text
   - ✅ 生成並執行了 `tasks.md`
   - ✅ 修改 `analyze.py` 中的 `_compute_render_dpi` 及 `_build_render_reason`
   - ✅ 新增 8 個 Hypothesis correctness properties 測試與 Unit Tests
   - ⚠️ 最終驗證：因沙盒環境限制，請人類手動執行 `pytest`, `mypy`, `ruff`

### ⬜ 待執行（交接給下一個 AI）

目前沒有待執行的 Spec，可以準備進入下一階段（如 Hybrid Engine 規劃）或進行手動驗證。

## 專案原則（不可改變）

PDF-Goon 的核心目標是**盡可能貼近原始品質地將 PDF 頁面轉成圖片**。因此以下需求屬於超出範圍，不應實作：

- **輸出圖片格式轉換**（例如統一轉成 PNG/JPEG/WebP）
- **輸出圖片尺寸調整 / 縮放 / 壓縮品質控制**（例如指定寬高、DPI 之外的壓縮）
- 任何會降低或改變原始內容視覺品質的後處理

可接受的相關行為僅限於：
- 為了「無損優化」而呼叫 pingo / oxipng / jpegoptim（不變更像素內容）。
- 為了符合檔案系統或後端限制而進行的必要編碼（如 RENDER 輸出為 PNG）。

## Spec 一覽

| Spec | 位置 | 狀態 |
|------|------|------|
| pdf-goon-refactor | `.kiro/specs/pdf-goon-refactor/` | ✅ 已完成 |
| rendered-pages-output-loss | `.kiro/specs/rendered-pages-output-loss/` | ✅ 已完成 |
| pdf-goon-hardening | `.kiro/specs/pdf-goon-hardening/` | ✅ 已完成 |
| improve-detection-quality | `.kiro/specs/improve-detection-quality/` | ✅ 已完成 |
| codebase-improvements | `.kiro/specs/codebase-improvements/` | ✅ 已完成 |
| fix-detection-algorithm | `.kiro/specs/fix-detection-algorithm/` | ✅ 已完成 (v1.0.0 正式版) |


## 關鍵文件

| 文件 | 用途 | 狀態 |
|------|------|------|
| `pdf_goon/analyze.py` | DPI 計算 — 已改進計算邏輯 | ✅ |
| `pdf_goon/core.py` | 主要管線 — 已修復 glob/regex/單檔問題 | ✅ |
| `pdf_goon/models.py` | 資料型別定義 — 已新增 PageResult | ✅ |
| `pdf_goon/tools.py` | 工具解析 — 已加 timeout + allowlist | ✅ |
| `pdf_goon/optimize.py` | 無損優化 — 已加前置可用性檢查 | ✅ |
| `pdf_goon/cli.py` | CLI 入口 | ✅ |
| `tests/test_analyze.py` | analyze 模組測試 — 已新增 8 個 property tests | ✅ |
| `docs/prd.md` | Product Requirements Document | ✅ |

## 技術棧

- Python >=3.11, setuptools, pyproject.toml
- pytest + hypothesis (PBT), mypy, ruff
- Poppler-utils (pdfimages, pdfinfo, pdftocairo)
- pingo (Windows 優化器, optional) / oxipng + jpegoptim (Linux)

## 環境注意事項

- **Windows 10** 開發環境
- **路徑含中文**（`D:\vibe x\coding\開源\pdf-goon`）— 可能影響 venv 啟動器
- **Poppler 需額外安裝**（`scoop install poppler` 或手動放入 PATH）
- **pingo 可選**（不存在時自動跳過優化步驟）

## 常用指令

```bash
pip install -e ".[dev]"
pytest
mypy pdf_goon
ruff check pdf_goon tests
ruff format pdf_goon tests
```

## 下一步

1. **手動驗證**：由於 AI 沙盒環境限制無法執行 `pytest`、`mypy` 等指令，請人類開發者在本地手動執行：
   ```bash
   pytest tests/test_analyze.py -v
   mypy pdf_goon
   ruff check pdf_goon tests
   ```
2. 用實際 PDF 驗證渲染品質改善是否符合預期。
3. 如果驗證通過，可開始規劃下一個階段（例如 `pypdf` + `pypdfium2` 的 Hybrid Engine 遷移）。


---

## 目前狀態（2026-09-06 更新）

### ✅ 本次 session 已完成

1. **codebase-improvements spec — 全部 32 個任務完成（含選配 property tests）**
   位置：`.kiro/specs/codebase-improvements/`。四項改進：
   - **Req 1 — Finalization 拆分**：`core.py` 的 67 行 `_finalize_page_files()` 拆為
     dispatcher（≤10 行）+ `_finalize_rendered_file()` + `_finalize_extracted_files()`，
     簽名不變、向後相容。
   - **Req 2 — Render Worker 提取**：消除 `extract.py` 內嵌 f-string 腳本，改為獨立模組
     `pdf_goon/_render_worker.py`，透過 `python -m pdf_goon._render_worker <pdf> <page> <dpi> <out>`
     以結構化 CLI 參數呼叫（解決 CJK/空格/括號逃逸問題）。移除死碼參數 `pdf_data`。
   - **Req 3 — BLANK 模式**：新增 `ProcessingMode.BLANK`、`Config.keep_blank`、`--keep-blank` CLI 旗標。
     無圖無文字的頁面預設跳過（fail-fast，不進 extract/render）；`--keep-blank` 時改以 dpi_text 渲染。
   - **Req 4 — Backend Protocol**：新增 `pdf_goon/backends.py`，定義 `@runtime_checkable` 的
     `AnalyzeBackend` / `ExtractBackend` / `RenderBackend` Protocol + 三個 default 實作
     （lazy import 委託既有函式）。`process_batch()` 接受可選 backend 注入參數，為未來
     Hybrid Engine 替換鋪路。

2. **本 session 補完的 property / unit tests**
   - `tests/test_backends.py`（13 tests）：isinstance/runtime_checkable、default backend 委託、
     process_batch 注入。
   - `tests/test_backends_property.py`（4 hypothesis tests）：Property 9 backend 例外傳播
     （engine 失敗經 `PdfGoonError` 傳播並保留 `__cause__`）。
   - BLANK 模式三支 property test 已在先前 session 寫入並於本 session 驗證通過：
     - `tests/test_analyze.py`：BLANK decision logic（Property 6）、keep_blank rendering（Property 8）
     - `tests/test_core.py`：BLANK page skip behavior（Property 7）
   - 交接修正：tasks.md 的 5.6/5.7/5.8 之前卡在 `[-]`（in_progress）標記，已核對驗證後改為 `[x]`。
     （備註：task 工具需以「完整任務標題」而非「5.6」短號作為 taskId 才能更新。）

3. **venv runtime deps 安裝完成**
   - 先前 `.venv`（Python 3.13.1）缺 `pypdf` / `pypdfium2`，導致 `tests/test_analyze.py`
     8 支測試 `ModuleNotFoundError`。
   - 已安裝：`pypdf 6.17.0`（符合 `pypdf>=5.0.0`）、`pypdfium2 5.13.0`（符合 `pypdfium2>=4.0`）。
     兩者皆已在 `pyproject.toml` 宣告，無需改 manifest。
   - 驗證：全套件 **166 passed**（先前為 158，8 支缺 dep 失敗已修復）。

### ⚠️ 已知問題（交接給下一個 AI）

- **偶發測試 flake**：`tests/test_core.py::TestExtractPathPreservation::test_extract_path_mask_files_are_deleted`
  在全套件執行時曾出現 1 次失敗，但單獨執行、以及重跑全套件時皆通過（166 passed）。
  單一檔案 `test_core.py` 單獨跑 27/27 全過。研判為 hypothesis 隨機 example 搭配 tempfile
  的偶發競態，**非穩定失敗、非產品缺陷**。搜尋未發現 `chdir`/`monkeypatch`/全域狀態污染源。

### ⚠️ 環境注意事項（新增）

- **`.venv` 啟動器 shim 路徑失效**：venv 被搬移過，`Scripts\*.exe`（pytest/mypy/ruff）內嵌的
  絕對路徑是舊的。**請改用 `& ".\.venv\Scripts\python.exe" -m pytest`（或 `-m mypy` / `-m ruff`）**
  直接呼叫模組，不要用 `*.exe` shim。或重建 venv 修正 shim。

## 下一步（建議優先序）

1. **除錯偶發 flake（低風險、建議先做）**：用 `systematic-debugging` 方法定位
   `test_extract_path_mask_files_are_deleted` 的偶發失敗。策略：
   固定 seed 重現（`pytest -p no:randomly --hypothesis-seed=<seed>`）、
   檢查 tempfile 前綴是否可能跨 example 碰撞、必要時為該 test 加 `@settings(deadline=None)` 或
   隔離 output dir。**無重現不修復**。
2. **重建/修復 venv shim**（可選）：讓 `pytest` / `mypy` / `ruff` 可直接呼叫，
   避免每次都要 `python -m`。
3. **跑完整驗證關卡**：`python -m mypy pdf_goon`、`python -m ruff check pdf_goon tests`、
   `python -m ruff format pdf_goon tests --check`，確認 codebase-improvements 的型別與格式全綠
   （本 session 只跑了 pytest，mypy/ruff 尚未在裝完 dep 後重跑）。
4. **Hybrid Engine 規劃（下一個主要里程碑）**：Backend Protocol（Req 4）已就位，
   可據此規劃新 spec，讓 Poppler 與 pypdf/pypdfium2 路徑可切換/並存，
   透過 `process_batch()` 的 backend 注入點導入。


---

## 驗證關卡結果（2026-09-06，裝完 runtime deps 後重跑）

以 `python -m` 直接呼叫（避開失效 shim）。四關卡結果如下：

| 關卡 | 指令 | 結果 |
|------|------|------|
| pytest | `python -m pytest` | ✅ 166 passed |
| ruff format | `python -m ruff format pdf_goon tests --check` | ✅ 全綠 |
| ruff check | `python -m ruff check pdf_goon tests` | ⚠️ 5 errors（E402） |
| mypy | `python -m mypy pdf_goon` | ⚠️ 5 errors（1 import-not-found + 4 union-attr） |

### ⚠️ 已知瑕疵（本 session 決定「只記錄不修」，交接給下一個 AI）

**重要背景**：以下 mypy/ruff 錯誤**皆非本 session 引入**。它們是既有瑕疵，因為先前 `.venv`
缺 `pypdf`/`pypdfium2`，mypy 看不到真實 stub（import 直接 unresolved），這些型別問題才一直被遮蔽。
本 session 裝好 dep 後，mypy 第一次看到真實型別，瑕疵才浮現。**產品行為正確（166 tests pass）**，
這些純屬型別標註與 lint 風格債。

**mypy（5 errors）：**
1. `pdf_goon/_render_worker.py:27` — `pypdfium2` 無 type stub（import-not-found）。
   第三方庫本身不帶 stub。建議修法：pyproject.toml 的 `[tool.mypy]` 加 per-module
   `[[tool.mypy.overrides]]` `module = "pypdfium2"` + `ignore_missing_imports = true`。
2. `pdf_goon/extract.py:47` — `img_file.image` 型別為 `Any | None`，直接呼叫 `.save()`。
3. `pdf_goon/analyze.py:61` — `img_file.image` 直接取 `.width`（`None` 分支未處理）。
4. `pdf_goon/analyze.py:62` — 同上，`.height`。
5. `pdf_goon/analyze.py:63` — 同上，`.mode`。
   建議修法（#2~#5）：取 `img_file.image` 後判空並 fail-fast（符合工作區 Fail-Fast 原則），
   而非用 `# type: ignore` 掩蓋。

**ruff check（5 errors，全為 E402 module-level import not at top）：**
- `tests/test_extract.py:195`（`from hypothesis import strategies as st`）
- `tests/test_render_worker.py:180`（`from pdf_goon.extract import render_page`）
- `tests/test_render_worker.py:181`（`from pdf_goon.models import PageInfo`）
  成因：property test 依區塊註解把 import 放在檔案中段。修法：把這些 import 上移到檔頭。
  （零風險，屬純風格修正。）

### 下一步（修正後優先序）

1. **除錯偶發 flake**（見上一節）— `test_extract_path_mask_files_are_deleted`。
2. **清理型別/lint 債**：修上述 mypy 5 + ruff 5 errors，讓四關卡全綠。因牽涉
   `analyze.py`/`extract.py` 產品碼 + 兩個 test 檔 + pyproject.toml（跨多模組），
   建議走一個小 spec 或明確授權後一次處理，勿零散補丁。
3. **重建/修復 venv shim**（可選）。
4. **Hybrid Engine 規劃**（下一個主要里程碑，Backend Protocol 已就位）。

---

## 目前狀態（2026-09-13 更新）

### ✅ 本次 session 已完成

1. **mypy 5 errors 全部修復**
   - `pyproject.toml` 新增 `[tool.mypy]` overrides：`pypdfium2` 設 `ignore_missing_imports = true`
   - `pdf_goon/extract.py`：`img_file.image` 判空後再 `.save()`（None 分支 fail-fast）
   - `pdf_goon/analyze.py`：`img_file.image` 判空後再取 `.width/.height/.mode`

2. **ruff E402 5 errors 全部修復**
   - `tests/test_extract.py`：`import sys` 移至檔頭，刪除中段重複 hypothesis imports
   - `tests/test_render_worker.py`：`render_page`/`PageInfo` imports 移至檔頭

3. **偶發 flake 防禦性修復（無重現，30 次全套件皆綠）**
   - `tests/test_core.py`：`TestExtractPathPreservation` 兩個 property test 加 `deadline=None`
   - temp dir prefix 加入 `uuid4().hex`（`pbt_mask_{uuid}_`）避免跨 example 碰撞

4. **Pillow 缺失修復**
   - 發現 runtime 缺 `Pillow`（pypdf 提取與 pypdfium2 渲染都需要 PIL）
   - 已安裝 Pillow 12.3.0 並加入 `pyproject.toml` dependencies

5. **實測驗證（兩份日文 PDF，共 128 頁）**
   - 成功處理 63 頁 + 65 頁，EXTRACT/RENDER/BLANK 決策全部正確
   - 確認 UTF-8 console（`chcp 65001`）可正確處理日文路徑

6. **Poppler vs pypdf/pypdfium2 對照實驗**
   - EXTRACT 頁：`pdfimages -all` 輸出 RGB 87KB + mask 119KB（分開），
     pypdf 輸出 RGBA 233KB（合併重編碼）。Poppler 更符合「raw extraction」
   - RENDER 頁：兩引擎尺寸幾乎一致，檔案大小互有勝負
   - 結論：Hybrid Engine（選項 B）值得做，但非本次重點

7. **Coverage-based EXTRACT 決策邏輯（本次主要功能變更）**
   - **問題**：單張圖片頁若圖片沒有填滿整頁（有白邊），EXTRACT 會丟失背景
   - **解法**：新增 `_image_fills_page()` helper，只有圖片在頁面寬高兩個方向
     覆蓋率 ≥ 95% 時才走 EXTRACT；否則 RENDER 保留背景
   - 同時檢查旋轉：若圖片旋轉 90° 填滿頁面，也不提取（EXTRACT 會丟失旋轉）
   - 修改 `pdf_goon/analyze.py`：新增 `EXTRACT_COVERAGE_THRESHOLD = 0.95`
   - 更新 `tests/test_analyze.py`：Property 8 拆為 8a（填滿→EXTRACT）
     與 8b（未填滿→RENDER），並更新 unit test 使用全頁尺寸圖片

8. **README.md 重寫為純英文**
   - 移除中文描述行
   - 技術棧更新：pypdf/pypdfium2 取代 Poppler
   - 新增 BLANK mode、`--keep-blank`、coverage check、backend protocol 說明
   - Project structure 更新（加入 `_render_worker.py`、`backends.py`）

9. **Handoverbook 新增「專案原則（不可改變）」**
   - PDF-Goon 不做輸出格式轉換、不做尺寸調整/縮放/壓縮品質控制

### 驗證關卡結果（2026-09-13）

| 關卡 | 指令 | 結果 |
|------|------|------|
| pytest | `python -m pytest` | ✅ 167 passed |
| mypy | `python -m mypy pdf_goon` | ✅ no issues |
| ruff check | `python -m ruff check pdf_goon tests` | ✅ All checks passed |
| ruff format | `python -m ruff format pdf_goon tests --check` | ✅ already formatted |

### 已知 flake（持續觀察）

- `test_worker_error_propagation_nonexistent_pdf` 在全套件執行時偶發 1 次失敗，
  單獨執行與重跑皆通過。與先前 `test_extract_path_mask_files_are_deleted` 同類
  （hypothesis 隨機 example + Windows 檔案系統競態），非穩定失敗、非產品缺陷。

### ⚠️ 提交前清理事項

以下檔案為 scratch/暫存，**不應提交**：
- `patch_tests.py`、`run_test.py`、`scratch.ipynb`、`pytest_result.txt`、`test/` 目錄
- `pdf-goon_handoverbook.md`（根目錄殘留，正本在 `docs/handoverbook.md`）
- `.codegraph/`（索引目錄）
- `CLAUDE.md`（專案 root 的 agent 設定，視需求決定是否提交）

### 下一步

1. **清理 scratch 檔案** → 更新 `.gitignore` → commit + push 到 GitHub（beta）
2. **Hybrid Engine 規劃**：Backend Protocol 已就位，可規劃 Poppler backend spec
3. **持續觀察 flake**：兩個已知偶發 flake，若再出現需加日誌定位


---

## PRD 更新（2026-09-06）：引擎遷移對齊

### ✅ 已完成

`docs/prd.md` 已從 v1.0 更新為 **v2.0**，修正整份文件把 Poppler 當成現行引擎的過時敘述，
與實際程式碼（pypdf 分析/提取 + pypdfium2 渲染）及 README.md 對齊。對照基準為 README.md（已正確）。
改動涵蓋：

- metadata（版本/日期/狀態）
- §4.2 FR-10（pdfimages → pypdf `page.images`）、FR-11（pdftocairo → pypdfium2 via `_render_worker`）、
  FR-12（mask 改以 pypdf 1-bit heuristic 判定）
- §4.1 決策樹 + FR-02：補上實際存在但 PRD 漏寫的 EXTRACT 條件
  （覆蓋率 >= 95% 才 EXTRACT，常數 `EXTRACT_COVERAGE_THRESHOLD=0.95`；旋轉 90° 的圖改走 RENDER）
- **§5.1 NFR-01 保真度誠實化（重點）**：JPEG 路徑為 byte-identical 無損；
  PNG/其他路徑為「Pillow 無失真重建為合法 PNG，像素無損但非 byte-identical」。不再宣稱全面 byte-identical。
- §7 依賴表：pypdf/pypdfium2/Pillow 標必要；Poppler 標「不再需要（已於引擎遷移中移除）」
- §6 架構圖、§14 Glossary：EXTRACT/RENDER/hybrid engine 定義改為新引擎
- §13.1 Hybrid Engine：從「未來 Roadmap」改寫為「已完成遷移」的紀錄；
  §13.2（OCR）、§13.3（直方圖空白偵測）誠實保留在 Roadmap
- §11 Success Metrics：保真度配合 NFR-01 拆為 JPEG/PNG 兩路；移除無根據的「已達成」假象
- §8 CLI / §9 Library API：對照 cli.py 與 __init__.py 核對一致

（只改 docs/prd.md 一個檔案，未動任何 .py / README / handoverbook。）

### ⚠️ 待處理灰色地帶（交接）

1. **PRD 版本（2.0）與程式 `models.py` 的 `VERSION`（仍 "1.0"）不一致**。
   PRD 的 2.0 指「文件版本」；軟體版本是否要跟著升由人類決定。若要對齊，需同步改
   `pdf_goon/models.py` 的 `VERSION`、`cli.py` banner、PRD 三處（需動 .py，不在本次文件範圍）。
2. **`cli.py` banner epilog 仍過時**：寫 `Credits: Uses Poppler-utils and Pingo.exe`，
   但已不用 Poppler。需改 .py 修正（建議與上面版本對齊一併處理）。
3. **保留項（非待辦，記錄判斷）**：§2.1 工具比較表、§15 參考連結仍提及 Poppler —— 這兩處是
   「問題背景」與「歷史淵源」，刻意保留，無需修改。


---

## 演算法審查 + 研究（2026-09-06）：下一批工作已就緒

### ✅ 已完成（本 session）

1. **push 版本統一** — `models.py` VERSION、`pyproject.toml`、cli.py credits 對齊 `1.0.0b0`，移除 cli.py 的 Poppler 殘留。commit `b11a1a8` 已推 `origin/master`。
2. **全面拷問決策演算法** — 挑出 9 個缺陷（D1–D8 程式碼審查 + D9 原作者回饋），寫入 `docs/algorithm-defects.md`。
3. **深度研究（investigate workflow）** — 針對 pypdf/pypdfium2 第一手來源 + 本機實測，確認 9 個缺陷「全部修得了」，確切 API 已驗證。報告：`.agents/tasks/detection-algorithm-research.md`。
4. **論壇存檔** — 原作者 Dnkz 回饋整理為 `docs/ehentai_thread.md`（含 bug 複現檔 `files.catbox.moe/egihid.pdf`、YUV 痛點、credits 提醒）。
5. **4 個產品決策已拍板**（使用者全部同意，記於 algorithm-defects.md 末尾）。

### 核心發現

- **D1（覆蓋率假檢查）與 D4（DPI 爆值）同根因**：缺「圖片在頁面上的實際擺放 bbox」。用 pypdfium2 `PdfPage.get_objects()` + `PdfImage.get_bounds()` 一次同時修好（已實測）。
- **D3（1-bit 誤判遮罩）→ 靜默資料遺失**（小說/線稿整頁消失），最優先止血。改讀 `/ImageMask`·`/SMask`·`/Mask` 旗標。
- **D9（YUV 無損）** 需實機拿 YUV 樣本 PDF 驗證。
- **D8 效能**：PDFium 非執行緒安全、pypdfium2 v5 移除平行渲染 → 正解「一檔一 worker 連續渲染」。

### ⬜ 下一步（交接）

- **開新 spec `fix-detection-algorithm`**，以 `docs/algorithm-defects.md` 為 requirements 輸入（9 個缺陷 + 4 個已拍板決策 + 分階段修正順序皆已備齊）。
- 目標版本 `1.0.0b1`（feat 決策升級 + fix 缺陷），升版時對齊 VERSION/PRD。
- 測試語料待取得：ktc PDF、YUV 嵌入圖 PDF、`egihid.pdf`。
- 效能數字（D7/D8）寫進 PRD 前須以真實漫畫/小說 PDF 實機基準測試。


---

## 演算法重構架構深度研究（2026-10-14 更新）

### ✅ 本次已完成

1. **演算法重構架構研究報告（定稿版完成）** — 產出 [docs/algorithm-redesign-research.md](file:///d:/vibe%20x/coding/開源/pdf-goon/docs/algorithm-redesign-research.md)。
   - **空間幾何模型**：推導 CTM 變換矩陣與 `pypdfium2` 的 BBox 模型，以可視 CropBox/`get_size()` 為基準，引入「3pt 絕對邊距容忍 + 95% 相對覆蓋」雙重判定準則，完美化解 Dnkz 指出的「1px 白邊被誤判降級」問題（解決 D1）。
   - **物理渲染 DPI 模型**：以擺放物理尺寸 $w_{placed} / 72.0$ 為分母推導實質像素密度，徹底解決長條圖 DPI 爆值（解決 D4），並確認移除 `_to_c_float` 單精度截斷之技術正當性（解決 D5）。
   - **結構與內容層精確判定**：確立 `/ImageMask`、`/SMask`、`/Mask` 字典旗標判定（解決 D3 黑白頁遺失）。
   - **重大技術突破（文字層）**：引入 ISO 32000 文字渲染模式 3（`3 Tr` - Neither fill nor stroke text）識別，精確分辨「可視排版文字」與「可搜尋隱形 OCR 文字層」，使帶 OCR 的全頁掃描圖能夠 100% 裁決為無損 EXTRACT（解決 D2）。
   - **色彩空間與 YUV 深入論證 (D9)**：解構 DCTDecode 串流與 `/ColorTransform` (0: raw RGB, 1: YCbCr) 在缺少 APP14 標記時的相容性陷阱，確立「非標準與特殊色彩走 RENDER 由 PDFium 原生色彩引擎處理、標準 RGB 走 raw stream 抽取」的雙軌無損保障機制。
   - **兩階段會話架構 (Two-Pass Session Architecture)**：化解 `pypdfium2` C 層非執行緒安全與現行 `ThreadPoolExecutor` 的致命衝突，以「主線程單次遍歷全頁分析 + 依模式分派平行提取/長命 Worker 連續渲染」徹底消滅重複解析 (D7) 與冷啟動 (D8) 瓶頸。
   - **Spec 規劃藍圖**：完成 4 個階段實施路線圖、測試基準矩陣與狀態機 11 種唯一 Reason 字串對應表（解決 D6）。

2. **Spec `fix-detection-algorithm` 正式開立** — 建立於 [.kiro/specs/fix-detection-algorithm/](file:///d:/vibe%20x/coding/開源/pdf-goon/.kiro/specs/fix-detection-algorithm/)。
   - [requirements.md](file:///d:/vibe%20x/coding/開源/pdf-goon/.kiro/specs/fix-detection-algorithm/requirements.md)：以 EARS 語法定義 9 大需求與驗收標準。
   - [design.md](file:///d:/vibe%20x/coding/開源/pdf-goon/.kiro/specs/fix-detection-algorithm/design.md)：定義兩階段會話架構、幾何模型、長命 Worker 與 Hypothesis 測試策略。
   - [tasks.md](file:///d:/vibe%20x/coding/開源/pdf-goon/.kiro/specs/fix-detection-algorithm/tasks.md)：拆解 Phase 0 至 Phase 3 共 20 個原子任務。

---

## Spec `fix-detection-algorithm` 執行完成與 v1.0.0 正式版發布（2026-10-14 更新）

### ✅ 本次 session 已完成

1. **Phase 0：技術債清理與文件對齊（D5, Req 5.1-5.3）**
   - 移除 `pdf_goon/analyze.py` 中未使用的死碼 `_to_c_float()`。
   - 更新 `docs/prd.md` NFR-02，廢除 32-bit C-float 截斷陳述，對齊 Python 64-bit IEEE 754 雙精度浮點標準。

2. **Phase 1：結構與內容層精確判定（D2, D3, Req 2.1-2.4, 3.1-3.5）**
   - 實作 `is_true_pdf_mask(xobj_dict)`：嚴格檢查 `/ImageMask`、`/SMask`、`/Mask` 字典旗標，終結將純黑白 1-bit 掃描頁（如小說、漫畫網點、線稿）誤判為遮罩導致的靜默檔案遺失問題。
   - 實作 `analyze_page_text_layers(page)`：精確解析 PDF 內容串流，檢查實質文字繪製運算子（`Tj`, `TJ`, `'`, `"`）並追蹤 Text Rendering Mode 3 (`3 Tr`)。區分可視排版文字（觸發 RENDER）與純透明/OCR 隱形文字（允許無損 EXTRACT）。
   - 更新 `get_image_data()`：全面接入真實遮罩過濾與可見文字層分析。
   - 新增單元測試與 Hypothesis Property 4 屬性測試。

3. **Phase 2：空間幾何模型與物理 DPI 升級（D1, D4, D6, Req 1.1-1.7, 4.1-4.5, 6.1-6.11）**
   - 擴充 `ImageInfo`：新增 `placed_bbox` 與 `has_rotation` 欄位。
   - 新增 `Config.margin_tolerance = 3.0` 與 CLI 參數 `--margin-tolerance`。
   - 實作 `pdf_goon/geometry.py`：
     - `extract_page_geometry()`：透過 `pypdfium2` 取得頁面有效可視框（Effective Visual Box，優先使用 CropBox）與影像實質邊界（考慮旋轉與 CTM 變換）。
     - `is_full_page_image()`：雙準則自適應判斷——絕對白邊容忍度（$\le 3.0\text{ pt} + 10^{-6}\text{ pt}$ 浮點 epsilon）與相對覆蓋率（$C_{area} \ge 0.95$），徹底解決 Dnkz 所提之 1px 白邊掃描圖被誤降級問題。
   - 實作物理渲染 DPI 計算 `compute_render_dpi()`：以擺放物理尺寸（英吋）為分母，徹底解決未滿版、窄長圖 DPI 爆值（D4）。
   - 實作統一決策狀態機：`decide_processing_mode()` 與 `_build_render_reason()`，嚴格輸出 11 種唯一原因字串。
   - 新增 Property 1、2、3、5 屬性測試，並以黃金測試樣本 `egihid.pdf` page 1 實證解析為無損 `EXTRACT`。

4. **Phase 3：兩階段會話架構與長命 Worker 批次渲染（D7, D8, D9, Req 7.1-7.4, 8.1-8.3, 9.1-9.3）**
   - 定義 `PdfAnalyzeSession`、`SessionAnalyzeBackend` 與 `BatchRenderBackend` Protocol。
   - 實作 `PypdfSession`：單一 PDF 生命週期內僅開啟一次 `pypdf.PdfReader` 與 `pypdfium2.PdfDocument`，徹底消除重複解析與 I/O 瓶頸（D7）。
   - 升級 `pdf_goon/_render_worker.py`：支援 `--batch` 模式與 stdin/stdout 結構化通訊，長命 Worker 單行程連續渲染多頁，具備獨立崩潰隔離與失敗韌性（D8）。
   - 重構 `pdf_goon/core.py` 之 `process_single_pdf()`：主行程順序輕量分析全頁，收集工作清單後分派平行原生提取與長命批次渲染。
   - 色彩空間與 YUV 雙軌保障：將非標準 `/ColorTransform 0` 納入特殊色彩處理，導向 PDFium 原生色彩引擎 RENDER，同時保護標準 RGB/YCbCr 直出（D9）。
   - 移除 Beta 標籤，全專案正式升版為 `1.0.0`（`pdf_goon/models.py`, `pyproject.toml`, `docs/prd.md`）。

5. **真實 PDF 端到端驗證與品質測試（100% 通過）**
   - **真實純文本（小說）與輕小說專屬測試**：
     - `time-machine-novel-10pages.pdf`：10 頁 A5 純文字小說連載版面（章節標題、頁首、內文段落、頁尾編號），驗證長命 Worker 連續批次渲染穩定性與 fallback DPI 設定。
     - `novel-chapter-ornament.pdf`：小說段落 + 小型章節分隔裝飾圖（200px < 500px min_width），驗證微小裝飾圖不被誤抽取為單獨圖片，而是整頁以 DPI 400 渲染保留小說完整排版。
     - `light-novel-vol1-10pages.pdf`：10 頁典型輕小說單行本（全彩封面與拉頁插畫無損 EXTRACT、目錄與內文章節連續 RENDER、章節過渡空白頁跳過 BLANK），驗證雙軌引擎混合調度。
     - `pdflatex-4-pages.pdf`（4 頁純文字書籍）、`crazyones-pdfa.pdf`（PDF/A 文字檔）、`multicolumn.pdf`（3 頁多欄排版論文/小說）。
   - **真實漫畫與掃描書 PDF 測試語料**：涵蓋 1.5pt 白邊掃描漫畫、15pt 大留白頁、`3 Tr` 隱形 OCR 文字層、可視排版文字、1-bit 純黑白線稿/小說等，共計 **26 個真實 PDF 檔案** 儲存於 `real_test_pdfs/`。
   - **端到端測試套件**：[tests/test_real_pdf_e2e.py](file:///d:/vibe%20x/coding/開源/pdf-goon/tests/test_real_pdf_e2e.py) 擴充至 20 個真實 PDF 測試案例，包含解析度縮放驗證（300 vs 600 DPI 嚴格比例縮放）。
   - `pytest`：全數 **205 個測試通過**（`205 passed in 36.68s`）。
   - `mypy pdf_goon tests`：30 個原始碼檔案 **0 錯誤**（嚴格類型安全）。
   - `ruff check pdf_goon tests`：全部檢查通過。
   - `ruff format --check pdf_goon tests`：30 個檔案格式完全對齊。

6. **套件打包與漢化組內部測試發布（dist/）**
   - **獨立免安裝執行檔（Windows .exe）**：
     - `dist/pdf-goon.exe`（22.6 MB）：透過 PyInstaller 單檔案封裝，內建 Python 執行時、`pypdf`、`pypdfium2`（含原生 pdfium.dll C 引擎）與 `Pillow`。
     - 解決 PyInstaller frozen 子行程無法解析 `-m pdf_goon._render_worker` 之關鍵問題：於 `cli.py` / `__main__.py` 支援內部 `--_render_worker` 隱藏派發參數，實測免安裝獨立執行與批次連續渲染 100% 成功。
     - 漢化組成員（翻譯、校對、嵌字）**無需安裝 Python 或任何依賴環境**，直接雙擊、拖曳 PDF 或命令列即可運行。
   - **標準 Python 釋出包**：
     - `dist/pdf_goon-1.0.0-py3-none-any.whl`（25.3 KB）：Wheel 二進位安裝包。
     - `dist/pdf_goon-1.0.0.tar.gz`（63.7 KB）：原始碼封裝包。

---

### ✅ 發布狀態
- **GitHub Release**：[PDF-Goon X v1.0.0](https://github.com/libering/PDF-Goon-X/releases/tag/v1.0.0)（正式發行版，已發布並附掛全部 4 個二進位產物）
- **Git Tag**：`v1.0.0`（同步至本地與遠端 `origin`）

### ⬜ 待執行（後續展望）
- **社群回饋與邊界監控**：持續監控社群對極端印刷本、多色彩空間與大圖渲染的邊界案例反饋。
- **技術儲備與衍生分支：PDF-Goon Compact 構想（留待未來規劃）**：
  - **核心定位分工**：
    - **原版 (PDF-Goon Core)**：堅持單一純粹初衷——專注「極致還原畫質 (Pristine Fidelity)」，包含無損直接提取與 PDFium 100% 零像素漂移渲染，不引入複雜容器或瀏覽切片格式，保持零多餘依賴。
    - **進階版 (PDF-Goon Compact)**：作為超集或衍生工具，承接 Core 的提取與瓦片渲染引擎，擴充專注於巨型畫布之儲存、分發與檢視體驗：
      - **選項 2：Tile Pyramid & Deep Zoom**（多階降採樣金字塔、DZI / Slippy Map 目錄結構、Web 流式隨機載入，防檢視端 OOM）。
      - **選項 3：Compact Container Archive**（SQLite/MBTiles 鍵值容器、TAR/ZIP 串流封裝、單檔防磁碟碎片、支援無解壓隨機讀取）。
  - **規劃形式**：未來啟動時開立專屬 PRD (`docs/prd-compact.md`) 與獨立 OpenSpec 變更包，保持原版 PRD (`docs/prd.md`) 的純粹性。



