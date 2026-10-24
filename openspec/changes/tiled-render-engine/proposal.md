# Proposal: 瓦片分塊渲染引擎 (Tiled Render Engine)

## Why: 背景與問題陳述

在處理超大尺寸文檔（如歷史地圖、工程藍圖、大型遊戲海報）時，常規 300 DPI 整頁光柵化會產生巨大的像素畫布：
- 例如維基共享資源上的 USGS 木衛一地質圖（`commons_usgs_io_geological_map.pdf`）在 300 DPI 下高達 **198.60 MP**（$16,596 \times 11,966\,\text{px}$）。
- 整頁單次光柵化需要一次性分配近 800 MB ~ 1 GB 的 C-level 未壓縮 RGBA 緩衝區，在多進程並發環境下極易引發 OOM（記憶體耗盡）崩潰或 32,767 坐標溢出。
- 現有的 `MAX_RENDER_PIXELS = 100_000_000` 僅被動拋錯阻斷，缺乏優雅降級的自足分塊渲染能力。

## What: 解決方案與核心能力 (經過 Grill-me 對齊)

引入深模組架構的瓦片分塊渲染引擎（`pdf_goon/render/tiler.py`）：
1. **雙維度智慧觸發 + 參數控制**：
   - 當頁面投影預估像素超過 **100 MP**，或單邊像素超過 **16,384 px**（防止底層 16-bit 整數溢出）時，自動切換至瓦片分塊渲染。
   - CLI 與 Config 新增 `--tiles / tiles: bool = False` 參數：傳入時強制以瓦片模式處理並輸出瓦片切片目錄與元數據。
2. **仿射矩陣局部平移 (Affine Matrix Translation)**：
   - 使用 PDFium 原生 `FPDF_RenderPageBitmapWithMatrix` API，按預設 $4096 \times 4096\,\text{px}$ 網格計算局部平移矩陣：
     $$\begin{bmatrix} a & b & e \\ c & d & f \end{bmatrix} = \begin{bmatrix} s & 0 & -x_0 + P \\ 0 & s & -y_0 + P \end{bmatrix}$$
3. **Padding-and-Crop 無縫去痕**：
   - 瓦片渲染外擴邊緣 $P=2\,\text{px}$ 採樣，隨後精確裁切，徹底消除雙線性插值在邊界產生的灰階接縫偽影，達成 **100% 零漂移 (diff: None)**。
4. **雙模自足輸出形式**：
   - **預設模式**：自動將瓦片拼合為單張無損完整大圖（自動將 Pillow `Image.MAX_IMAGE_PIXELS` 安全擴容至 500 MP，並套用灰階正規化），維持原有 Public API 與輸出結構相容。
   - **--tiles 模式**：額外在輸出目錄產出結構化切片資料夾 `{stem}_page_{p:02d}_tiles/tile_r{r}_c{c}.png` 與 `metadata.json`，便於切片快速瀏覽或 DeepZoom 應用。

## Scope: 範圍邊界

- **涵蓋**：
  - 新增模組 `pdf_goon/render/tiler.py`。
  - 在 `pdf_goon/models.py` 的 `Config` 新增 `tiles: bool = False`。
  - 在 `pdf_goon/cli.py` 新增 `--tiles` 選項。
  - 在 `pdf_goon/_render_worker.py` 與 `backends.py` 做最小無侵入轉發。
  - 專屬測試 `tests/test_tiled_render.py` 與真實世界 198.6 MP 木衛一地質圖實證。
- **非目標 (Non-Goals)**：
  - 不修改 $< 100\,\text{MP}$ 的常規頁面渲染管線。
  - 不引入額外 C 擴展依賴。
