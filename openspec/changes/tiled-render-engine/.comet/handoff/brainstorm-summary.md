# Brainstorm Summary

- Change: tiled-render-engine
- Date: 2026-10-24

## 確認的技術方案

1. **雙維度智慧觸發 + 參數控制**：
   - 總像素預估 > 100 MP，或單邊像素 > 16,384 px 時自動啟用瓦片分塊渲染。
   - CLI 與 Config 支援 `--tiles` 參數：強制瓦片渲染並額外產出結構化切片目錄與 `metadata.json`。
2. **仿射矩陣局部平移與 Padding-and-Crop**：
   - 基於 `FPDF_RenderPageBitmapWithMatrix`，瓦片尺寸預設 4096 x 4096 px，外擴邊界 $P=2\,\text{px}$ 採樣後精確裁切，實測 100% 零接縫、零漂移 (diff: None)。
   - 邊緣瓦片採用動態精確截斷，緩衝區與頁面邊界 100% 嚴密貼合。
3. **極致常數記憶體與並行隔離**：
   - 單頁內部嚴格序列渲染單個瓦片，即時銷毀 C 點陣圖 (`FPDFBitmap_Destroy`)，單頁 C 記憶體鎖定在 64MB 內，不與外部進程池產生巢狀死鎖。
4. **全屬性視覺保真**：
   - C 點陣圖渲染前強制填白 (0xFFFFFFFF)，消除透黑失真，與 ISO 標準紙張背景完全一致。
   - 啟用全屬性保真旗標（包含 `FPDF_ANNOT` 標註圖層與最高品質抗鋸齒）。
   - 拼合大圖在安全擴容 Pillow 像素門檻 (500 MP) 後儲存，並調用 `_normalize_rendered_image` 自動無損灰階正規化。

## 關鍵取捨與風險

- 取捨：未加 `--tiles` 時拼合單張大圖（維持 API 相容性）；加上 `--tiles` 額外儲存切片目錄（方便切片閱讀）。
- 防禦：巨圖拼合對 Pillow 施加 500 MP 上限保護，防止 `DecompressionBombError`。

## 測試策略

- 網格切分、矩陣偏移、邊緣裁切單元測試。
- 100% 像素差分等價性驗證 (`ImageChops.difference == None`)。
- 198.6 MP 真實木衛一地質圖（`commons_usgs_io_geological_map.pdf`）常數記憶體實測。
- 全倉庫單檔 $\le 500$ 行、單函式 $\le 50$ 行架構守門測試。

## Spec Patch

無。
