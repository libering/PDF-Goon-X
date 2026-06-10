# Design: pdf-goon-hardening

## 設計原則

- 最小化修改範圍：每個修復獨立、可逐步合併
- 向後相容：相同輸入 → 相同輸出檔案
- TDD 垂直切片：一個行為一個測試→實作循環
- 現有測試必須繼續通過
- **保持模組化**：每個模組職責單一、可獨立測試，模組間透過函式簽名和型別溝通，不增加耦合

## 變更設計

### B1: 修復子圖索引 regex

**現狀**：
```python
# core.py:_finalize_page_files
match = re.search(r"-(\d+)\.(?:png|jpg|jpeg)$", local_file.name, re.IGNORECASE)
# ...
sub_idx = re.search(r"-(\d+)", local_file.name)  # ← 這個有 bug
```

**修復**：第二個 regex 也錨定到文件結尾：
```python
sub_idx = re.search(r"-(\d+)\.[^.]+$", local_file.name)
```

### B2: 消除 workspace 文件名碰撞

**現狀**：
```python
local_prefix = workspace / f"page_{page}_tmp"      # extraction
target_prefix = workspace / f"page_{page}_tmp-{page}"  # rendering
# glob: workspace.glob(f"{local_prefix.name}*") → catches both
```

**修復**：渲染使用獨立前綴模式：
```python
local_prefix = workspace / f"page_{page}_tmp"       # extraction (unchanged)
render_prefix = workspace / f"render_{page}_tmp"    # rendering (new prefix)
```

搭配 A2（直接使用回傳的 file list），glob 不再被使用。

### B3: 修復 `!delete` 路徑過濾

**現狀**：
```python
pdf_files = [f for f in sorted(...) if "!delete" not in str(f)]
```

**修復**：
```python
pdf_files = [f for f in sorted(...) if "!delete" not in f.parts]
```

### S1: 加入 subprocess timeout

**修改 `tools.py:run_command`**：
```python
_DEFAULT_TIMEOUT: int = 300  # 5 minutes

def run_command(cmd: list[str], *, timeout: int = _DEFAULT_TIMEOUT) -> str:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise SubprocessError(
            tool=cmd[0],
            exit_code=-1,
            stderr=f"Process timed out after {timeout}s",
        ) from exc
    # ... rest unchanged
```

**模組化考量**：
- `run: Callable[[list[str]], str]` DI 簽名不變 — 下游模組（analyze, extract, optimize）無需修改
- timeout 是 `run_command` 實作細節，不洩漏到 caller 介面
- 需要覆寫 timeout 的場景（如測試、大型 PDF）可透過 `functools.partial(run_command, timeout=600)` 傳入

### S2: local directory allowlist

**修改 `tools.py:get_tool_path`**：
```python
_ALLOWED_LOCAL_TOOLS: frozenset[str] = frozenset({
    "pdfimages", "pdfimages.exe",
    "pdfinfo", "pdfinfo.exe",
    "pdftocairo", "pdftocairo.exe",
    "pingo", "pingo.exe",
    "oxipng", "oxipng.exe",
    "jpegoptim", "jpegoptim.exe",
})

def get_tool_path(tool_name: str) -> str:
    # 1. PyInstaller bundle (unchanged)
    if hasattr(sys, "_MEIPASS"):
        bundled = Path(sys._MEIPASS) / tool_name
        if bundled.exists():
            return str(bundled)

    # 2. Local directory — only for allowed tools
    if tool_name in _ALLOWED_LOCAL_TOOLS:
        local = Path(__file__).parent / tool_name
        if local.exists():
            return str(local)

    # 3. System PATH (unchanged)
    found = shutil.which(tool_name)
    if found:
        return found

    return tool_name
```

### A1: PageResult dataclass

**新增到 `models.py`**：
```python
@dataclass(frozen=True)
class PageResult:
    """Outcome of processing a single PDF page."""
    page_num: int
    mode: ProcessingMode
    files_produced: tuple[Path, ...]  # tuple for frozen dataclass
    error: str | None = None
```

**修改 `core.py:_process_page`**：回傳 `PageResult` 而非 `None`。

**模組化考量**：
- `PageResult` 定義在 `models.py`（所有資料型別的唯一位置），不新增模組
- `_process_page` 仍是 `core.py` 的私有函式，只是回傳型態更明確
- 不改變 `process_single_pdf` 的公開簽名 — `ProcessResult` 仍是外部介面
- per-page 結果只在 core.py 內部使用，不洩漏到 public API

### A2: 消除 glob 依賴

**修改 `core.py:_process_page`**：
```python
# Before (uses glob):
generated_files = sorted(workspace.glob(f"{local_prefix.name}*"))
_finalize_page_files(generated_files, ...)

# After (uses return value from extract/render):
if decision.mode == ProcessingMode.EXTRACT:
    generated_files = extract_images(pdf_path, page, local_prefix)
else:
    generated_files = render_page(pdf_path, page, render_prefix, decision.dpi, page_info)

output_files = _finalize_page_files(generated_files, ...)
```

**模組化考量**：
- `extract_images` 和 `render_page` 已有回傳 `list[Path]` — 這是它們的公開合約，早已存在
- 修改只在 core.py 的消費方式：從「glob 猜測」改為「信任回傳值」
- extract.py 和 optimize.py 不受影響，保持各自職責獨立
- `_finalize_page_files` 的簽名不變（接收 `list[Path]`），只是資料來源更可靠

## 模組影響範圍

| 模組 | 變更類型 |
|------|---------|
| `models.py` | 新增 `PageResult`、新增 `_DEFAULT_TIMEOUT` |
| `tools.py` | 加 timeout、加 allowlist |
| `core.py` | 修復 B1/B2/B3、重構 A1/A2 |
| `tests/` | 新增行為測試 |

## 執行順序（TDD 垂直切片）

1. S1 (timeout) — 獨立、低風險、不影響其他模組
2. S2 (allowlist) — 獨立、低風險
3. B3 (!delete 過濾) — 獨立、一行修復
4. B1 + B2 + A2 — 這三個緊密相關，一起做：修復 regex、改前綴、用 file list 取代 glob
5. A1 (PageResult) — 在 B1/B2/A2 之後，因為 `_process_page` 的回傳型態改了

每步都是：寫測試（RED）→ 最小實作（GREEN）→ 驗證所有現有測試仍通過。
