# Tasks: 瓦片分塊渲染引擎實施任務清單

- [x] 1. 設計與建立單元測試 `tests/test_tiled_render.py` (TDD Red)
  - [x] 1.1 測試瓦片網格坐標切分、矩陣偏移與外擴裁切邏輯
  - [x] 1.2 測試小頁面瓦片拼合與直接渲染之 100% 像素等價性 (diff == None)
  - [x] 1.3 測試 `--tiles` 切片目錄與 `metadata.json` 產出完整性
  - [x] 1.4 測試單檔 $\le 500$ 行與單函式 $\le 50$ 行架構約束
- [x] 2. 實作核心模組 `pdf_goon/render/tiler.py`
  - [x] 2.1 實作 `should_tile_render` 判斷器（100 MP、16,384 px 或 force_tiles）
  - [x] 2.2 實作 `_render_single_tile` 矩陣渲染與 C 記憶體即時銷毀
  - [x] 2.3 實作 `render_page_tiled` 網格迭代拼合、切片導出與灰階正規化
- [x] 3. 整合至 CLI 與渲染管線
  - [x] 3.1 在 `pdf_goon/models.py` 的 `Config` 新增 `tiles: bool = False`
  - [x] 3.2 在 `pdf_goon/cli.py` 新增 `--tiles` 命令列參數
  - [x] 3.3 在 `pdf_goon/_render_worker.py` 加入超閾值自動切換瓦片渲染
- [x] 4. 驗收與實證 (Dual-Evidence)
  - [x] 4.1 對真實世界 198.6 MP 木衛一地質圖（`commons_usgs_io_geological_map.pdf`）進行瓦片實測
  - [x] 4.2 驗證常數記憶體安全、零接縫與 0 崩潰
  - [x] 4.3 執行全套回歸測試與 CodeGraph 更新
