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

1. **C 記憶體即時銷毀**：單次迴圈僅持有單個瓦片點陣圖，在 `try...finally` 內調用 `pdfium_c.FPDFBitmap_Destroy(bitmap)`。
2. **Pillow 像素安全擴容**：在拼合大圖前，局部將 `PIL.Image.MAX_IMAGE_PIXELS` 設為 500,000,000，防止觸發 `DecompressionBombError`。
3. **色彩保真正規化**：拼合產物套用 `_normalize_rendered_image`，純黑白/灰階內容轉為 `L` 模式，彩圖保留 `RGB`。
