---
change: tiled-render-engine
design-doc: docs/superpowers/specs/2026-10-24-tiled-render-engine-design.md
base-ref: 1f76089a54b6c85ac3c7f7544351c409bfb218cc
---

# Implementation Plan: 瓦片分塊渲染引擎 (Tiled Render Engine)

## 任務架構與步驟拆解

### Task 1: 建立 TDD 測試套件 `tests/test_tiled_render.py` (Red)
- **目標**：界定瓦片劃分、矩陣平移、外擴裁切與輸出完整性。
- **子任務**：
  - [x] 1.1 測試 `_calculate_tile_grid` 網格切分與邊界動態截斷邏輯。
  - [x] 1.2 測試小頁面瓦片拼合與直接渲染之 100% 像素等價性 (`ImageChops.difference == None`)。
  - [x] 1.3 測試 `save_tile_dir=True` 時切片資料夾與 `metadata.json` 產出完整性。
  - [x] 1.4 測試 `pdf_goon/render/tiler.py` 符合單檔 $\le 500$ 行與單函式 $\le 50$ 行約束。

### Task 2: 實作核心模組 `pdf_goon/render/tiler.py` (Green)
- **目標**：高內聚深模組，封裝所有底層 PDFium C-API 與幾何矩陣運算。
- **子任務**：
  - [x] 2.1 實作 `should_tile_render(page_info, dpi, threshold_pixels=100_000_000, force_tiles=False)`。
  - [x] 2.2 實作 `_render_single_tile`：矩陣平移、外擴採樣、C 點陣圖填白 (0xFFFFFFFF) 與 `FPDFBitmap_Destroy` 確定性釋放。
  - [x] 2.3 實作 `render_page_tiled`：大圖畫布拼接、Pillow 500 MP 閥值放寬、灰階正規化與切片目錄導出。

### Task 3: 擴充 CLI、Config 與渲染管線整合
- **目標**：無縫串接至 PDF-Goon 主流程與命令列介面。
- **子任務**：
  - [x] 3.1 在 `pdf_goon/models.py` 的 `Config` 新增 `tiles: bool = False`。
  - [x] 3.2 在 `pdf_goon/cli.py` 新增 `--tiles` 命令列參數。
  - [x] 3.3 在 `pdf_goon/_render_worker.py` 的 `_render_single_page_to_file` 整合 `should_tile_render` 自動切換。

### Task 4: 雙證據實證驗收 (Dual-Evidence Verification)
- **目標**：提供邏輯綠燈與真實物理產物雙重證據。
- **子任務**：
  - [x] 4.1 對真實世界 198.6 MP 木衛一地質圖（`commons_usgs_io_geological_map.pdf`）執行瓦片渲染實測。
  - [x] 4.2 測量並記錄記憶體開銷（常數安全，不崩潰）與產物尺寸。
  - [x] 4.3 執行完整回歸測試（全套 pytest）與單元架構規範驗證。

### Task 5: 更新 CodeGraph 知識圖譜索引
- **目標**：同步倉庫 symbol 索引，保持代碼導航最新。
- **子任務**：
  - [x] 5.1 執行 CodeGraph 重新索引與檢驗。
