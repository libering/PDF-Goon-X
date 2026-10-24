# Comet Design Handoff

- Change: tiled-render-engine
- Phase: design
- Mode: compact
- Context hash: 5d6baaae4d18aee19a8fdee7dcc45d35b54b9a8dffb24e766bc3b1ced3e85883

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/tiled-render-engine/proposal.md

- Source: openspec/changes/tiled-render-engine/proposal.md
- Lines: 1-35
- SHA256: c24a3b986fca67d9f0cd7455896c5b0057595b1d0b9b8d6a640599d86fc05e80

```md
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
```

## openspec/changes/tiled-render-engine/design.md

- Source: openspec/changes/tiled-render-engine/design.md
- Lines: 1-83
- SHA256: c972e070f584ed144fcfdaa8108339e588f724b97e9bc4784b33a7994bdae36a

[TRUNCATED]

```md
# Design: 瓦片分塊渲染引擎高層架構設計

## 1. 架構決策與深模組原則 (Deep Module)

遵循深模組原則：對外暴露極簡函數接口，內部封裝所有網格劃分、坐標矩陣變換、外擴裁切、C-level 記憶體即時銷毀與切片目錄導出。

### 外部接口契約 (`pdf_goon/render/tiler.py`)
```python
def should_tile_render(
    page_info: PageInfo,
    dpi: float,
    threshold_pixels: int = 100_000_000,
    force_tiles: bool = False,
) -> bool:
    """判斷頁面在目標 DPI 下是否需要啟用瓦片分塊渲染。

    觸發條件：
    1. force_tiles 為 True
    2. 總像素預估 > threshold_pixels (100 MP)
    3. 單邊像素預估 > 16,384 px (防止 16-bit 坐標溢出)
    """

def render_page_tiled(
    page: Any,
    target_path: Path,
    dpi: float,
    page_info: PageInfo,
    tile_size: int = 4096,
    padding: int = 2,
    save_tile_dir: bool = False,
) -> list[Path]:
    """以瓦片分塊方式渲染超大頁面。

    返回產出檔案清單：
    - 始終包含拼合後的大圖 target_path
    - 若 save_tile_dir 為 True，額外包含切片目錄與 metadata.json
    """
```

## 2. 幾何變換與坐標系模型

### 坐標對齊
PDFium 的裝置坐標為由上而下（Y 正向朝下）。
在縮放比例 $s = \text{dpi} / 72.0$ 下：
- 虛擬畫布總寬高：$W = \lfloor w_{\text{pts}} \cdot s \rfloor, H = \lfloor h_{\text{pts}} \cdot s \rfloor$。
- 瓦片網格切分：
  步長為 `tile_size`（預設 4096），外擴邊界 $P = 2\,\text{px}$。
- 對於網格單元 $[x_0, x_1) \times [y_0, y_1)$：
  - 緩衝區尺寸：$w_{\text{buf}} = (x_1 - x_0) + 2P, h_{\text{buf}} = (y_1 - y_0) + 2P$。
  - 平移偏移：$e = -x_0 + P, f = -y_0 + P$。
  - 矩陣參數：
    `matrix = pdfium_c.FS_MATRIX(a=s, b=0.0, c=0.0, d=s, e=e, f=f)`。
  - 裁切復原：
    `tile_cropped = tile_raw.crop((P, P, P + (x1 - x0), P + (y1 - y0)))`。

## 3. 切片目錄規格與元數據結構

當 `save_tile_dir=True` 時：
- 目錄路徑：`target_path.parent / f"{target_path.stem}_tiles"`。
- 切片命名：`tile_r{row:02d}_c{col:02d}.png`。
- 元數據檔案：`metadata.json`：
  ```json
  {
    "page_width_pts": 3983.1,
    "page_height_pts": 2872.0,
    "dpi": 300,
    "total_width_px": 16596,
    "total_height_px": 11966,
    "tile_size": 4096,
    "padding": 2,
    "rows": 3,
    "cols": 5,
    "tiles": [
      {"row": 0, "col": 0, "x": 0, "y": 0, "w": 4096, "h": 4096, "file": "tile_r00_c00.png"}
    ]
  }
  ```

## 4. 記憶體治理與安全邊界防禦

```

Full source: openspec/changes/tiled-render-engine/design.md

## openspec/changes/tiled-render-engine/tasks.md

- Source: openspec/changes/tiled-render-engine/tasks.md
- Lines: 1-19
- SHA256: 30079d487dad931343e253555845f9157262319639e1c40edb837b0f8c1e2c74

```md
# Tasks: 瓦片分塊渲染引擎實施任務清單

- [ ] 1. 設計與建立單元測試 `tests/test_tiled_render.py` (TDD Red)
  - [ ] 1.1 測試瓦片網格坐標切分、矩陣偏移與外擴裁切邏輯
  - [ ] 1.2 測試小頁面瓦片拼合與直接渲染之 100% 像素等價性 (diff == None)
  - [ ] 1.3 測試 `--tiles` 切片目錄與 `metadata.json` 產出完整性
  - [ ] 1.4 測試單檔 $\le 500$ 行與單函式 $\le 50$ 行架構約束
- [ ] 2. 實作核心模組 `pdf_goon/render/tiler.py`
  - [ ] 2.1 實作 `should_tile_render` 判斷器（100 MP、16,384 px 或 force_tiles）
  - [ ] 2.2 實作 `render_single_tile` 矩陣渲染與 C 記憶體即時銷毀
  - [ ] 2.3 實作 `render_page_tiled` 網格迭代拼合、切片導出與灰階正規化
- [ ] 3. 整合至 CLI 與渲染管線
  - [ ] 3.1 在 `pdf_goon/models.py` 的 `Config` 新增 `tiles: bool = False`
  - [ ] 3.2 在 `pdf_goon/cli.py` 新增 `--tiles` 命令列參數
  - [ ] 3.3 在 `pdf_goon/_render_worker.py` 加入超閾值自動切換瓦片渲染
- [ ] 4. 驗收與實證 (Dual-Evidence)
  - [ ] 4.1 對真實世界 198.6 MP 木衛一地質圖（`commons_usgs_io_geological_map.pdf`）進行瓦片實測
  - [ ] 4.2 驗證常數記憶體安全、零接縫與 0 崩潰
  - [ ] 4.3 執行全套回歸測試與 CodeGraph 更新
```

