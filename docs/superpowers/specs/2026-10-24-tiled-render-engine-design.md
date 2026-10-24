---
comet_change: tiled-render-engine
role: technical-design
canonical_spec: openspec
---

# Technical Design Doc: 瓦片分塊渲染引擎 (Tiled Render Engine)

## 1. 系統定位與目標架構

為解決 100 MP ~ 200 MP 超巨型畫布（如地質圖、藍圖、海報）在常規 300 DPI 下光柵化引發 OOM 崩潰或 16-bit 坐標溢出的痛點，本設計在 `pdf_goon/render/tiler.py` 中實現深模組瓦片分塊渲染引擎。

### 核心職責劃分
- **`pdf_goon/render/tiler.py`（新增深模組）**：
  - 封裝瓦片網格幾何劃分、動態邊緣截斷與坐標平移仿射矩陣。
  - 封裝單個瓦片 C-level 點陣圖創建、填白底、矩陣光柵化與確定性銷毀。
  - 封裝大圖畫布拼接、切片目錄儲存與 metadata.json 生成。
- **`pdf_goon/_render_worker.py`（最小轉發）**：
  - 在調用 `page.render()` 前，調用 `should_tile_render` 進行雙維度偵測。
  - 若命中則委託給 `render_page_tiled`，否則走現有常規快速渲染。
- **`pdf_goon/models.py` & `cli.py`**：
  - 增加 `--tiles` 參數與 `Config.tiles: bool = False`。

---

## 2. 幾何變換與數學模型

### 2.1 坐標系統與仿射矩陣
PDF 點陣裝置坐標系由左上角原點 $(0,0)$ 向右向向下遞增。
在縮放比例 $s = \text{dpi} / 72.0$ 下：
- 頁面總像素尺寸：$W = \lfloor w_{\text{pts}} \cdot s \rfloor, H = \lfloor h_{\text{pts}} \cdot s \rfloor$。
- 對於步長為 $T$（預設 4096）的網格，第 $(r, c)$ 個瓦片的有效區域為 $[x_0, x_1) \times [y_0, y_1)$，其中：
  $$x_0 = c \cdot T, \quad x_1 = \min(W, x_0 + T)$$
  $$y_0 = r \cdot T, \quad y_1 = \min(H, y_0 + T)$$

### 2.2 Padding-and-Crop 去痕技術
雙線性插值在無邊界的瓦片邊緣會將未採樣區域視為純黑（0x00000000），產生 1~2 像素的暗色接縫接合偽影。
我們採用外擴採樣技術：
- 外擴寬高：$P = 2\,\text{px}$。
- 採樣點陣圖緩衝區大小：
  $$w_{\text{buf}} = (x_1 - x_0) + 2P, \quad h_{\text{buf}} = (y_1 - y_0) + 2P$$
- 裝置空間平移量：
  $$e = -x_0 + P, \quad f = -y_0 + P$$
- 傳入 PDFium 之仿射變換矩陣：
  $$\mathbf{M} = \begin{bmatrix} s & 0 & e \\ 0 & s & f \end{bmatrix}$$
- 裁切提取：
  渲染完成後，自緩衝區裁切出精確內部區域 $[P, P) \sim [P + (x_1 - x_0), P + (y_1 - y_0))$，粘貼至大圖 $(x_0, y_0)$ 處。

---

## 3. 記憶體治理與生命週期

1. **常數記憶體循環**：
   單頁內部嚴格序列循環渲染瓦片：
   ```python
   for row, col in grid:
       bitmap = pdfium_c.FPDFBitmap_CreateEx(w_buf, h_buf, FPDFBitmap_BGRx, None, 0)
       try:
           pdfium_c.FPDFBitmap_FillRect(bitmap, 0, 0, w_buf, h_buf, 0xFFFFFFFF)
           pdfium_c.FPDF_RenderPageBitmapWithMatrix(bitmap, page_handle, matrix, cliplabel, flags)
           tile_img = _bitmap_to_pil_and_crop(bitmap, w_buf, h_buf, padding, tile_w, tile_h)
           canvas.paste(tile_img, (x0, y0))
           if save_tile_dir:
               tile_img.save(tile_dir / f"tile_r{row:02d}_c{col:02d}.png")
       finally:
           pdfium_c.FPDFBitmap_Destroy(bitmap)
   ```
   單一瓦片 C 記憶體僅：$4100 \times 4100 \times 4 \approx 67.2\,\text{MB}$。
2. **Pillow 大圖安全閥值擴容**：
   在存檔階段，透過區域性安全上下文調控：
   `Image.MAX_IMAGE_PIXELS = 500_000_000`。
3. **色彩保真正規化**：
   拼合完成後，呼叫專案既有的 `_normalize_rendered_image(canvas)`，純黑白/灰階地圖自動轉為單通道 `L` 模式，彩圖保留 `RGB`。

---

## 4. 雙模輸出與切片目錄規範

- **未指定 `--tiles`**：僅輸出拼合後的完整單張圖片（支援所有現有優化與管線流程）。
- **指定 `--tiles`**：除拼合大圖外，在輸出目錄下建立子目錄：
  `{stem}_page_{p:02d}_tiles/`
  包含：
  - `tile_r{row:02d}_c{col:02d}.png`
  - `metadata.json`（記錄原尺寸、DPI、瓦片網格與坐標清單）。

---

## 5. 實證驗收策略 (Dual-Evidence)

1. **邏輯證據**：
   - 網格劃分、動態截斷、矩陣偏移算法單元測試。
   - 小頁面瓦片拼合與直接渲染進行像素級差分（`ImageChops.difference`），diff 必須為 None。
   - `--tiles` 目錄與 `metadata.json` 完整性測試。
   - 架構行數限制（單檔 $\le 500$ 行、單函式 $\le 50$ 行）100% 綠燈。
2. **實體特徵證據**：
   - 使用 `commons_usgs_io_geological_map.pdf`（198.6 MP）實跑瓦片渲染：
     - 常數記憶體安全，無 OOM。
     - 產出有效非零位元組點陣大圖與結構化切片目錄。
