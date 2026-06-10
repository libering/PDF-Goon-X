# Vibe Coding Principles

## Hard Rules

1. **File < 500 lines, Function < 50 lines** — 超過就拆
2. **一次只改一個模組** — 改動不應波及不相關模組
3. **新功能 = 新模組** — 不在現有文件裡堆程式碼
4. **接口先行** — 先定義公開 API，再寫實作
5. **小步迭代** — 反饋速率是速度上限，永遠不接太大的任務

## Before Coding

- **Grill Session**：開始前問清楚 — 想要什麼？不想要什麼？影響哪些模組？怎麼驗證成功？
- **Shared Language**：使用專案 PRD / handoverbook 中的統一術語命名一切

## While Coding

- Make it work -> Make it right -> Make it fast
- 單一職責：一個函數只做一件事
- DRY：重複邏輯提取為共用函數
- 能用成熟輪子就不自己寫（Glue Coding）
- 注釋解釋「為什麼」，不是「怎麼做」

## Debug

- 只給：預期 vs 實際 + 最小複現
- 兩次失敗就換方向，不做增量補丁
