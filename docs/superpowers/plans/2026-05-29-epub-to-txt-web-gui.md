# EPUB to TXT Web GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local browser GUI that uploads one EPUB file, extracts readable plain text, previews it, and downloads it as UTF-8 `.txt`.

**Architecture:** Keep EPUB parsing in `app/converter.py` with no FastAPI dependency. Keep HTTP upload, preview, and download behavior in `app/main.py`. Keep the interface in a single Jinja template and stylesheet so the app stays small and easy to run locally.

**Tech Stack:** Python 3, FastAPI, Jinja2, Uvicorn, pytest, FastAPI TestClient.

---

## File Structure

- `app/__init__.py`: package marker.
- `app/converter.py`: EPUB ZIP parsing, OPF spine resolution, HTML-to-text extraction, output filename derivation, conversion errors.
- `app/main.py`: FastAPI app, upload endpoint, download endpoint, template rendering, request-level validation.
- `app/templates/index.html`: upload form, error display, preview textarea, download form.
- `app/static/styles.css`: page and control styling.
- `tests/test_converter.py`: unit tests for EPUB conversion behavior.
- `tests/test_main.py`: route tests for upload success and request validation.
- `requirements.txt`: runtime and test dependencies.
- `README.md`: setup, run, test, and usage instructions.

## Task 1: Converter Test Harness And First Failing Test

**Files:**
- Create: `app/__init__.py`
- Create: `tests/test_converter.py`

- [ ] **Step 1: Create package marker**

Create `app/__init__.py` as an empty file.

- [ ] **Step 2: Write the failing ordered-spine conversion test**

Create `tests/test_converter.py` with:

```python
import zipfile
from io import BytesIO

from app.converter import convert_epub_bytes


def make_epub(chapters: list[tuple[str, str]], spine: list[str] | None = None) -> bytes:
    buffer = BytesIO()
    spine_ids = spine or [chapter_id for chapter_id, _ in chapters]

    manifest_items = "\n".join(
        f'<item id="{chapter_id}" href="{chapter_id}.xhtml" media-type="application/xhtml+xml"/>'
        for chapter_id, _ in chapters
    )
    spine_items = "\n".join(f'<itemref idref="{chapter_id}"/>' for chapter_id in spine_ids)

    with zipfile.ZipFile(buffer, "w") as epub:
        epub.writestr("mimetype", "application/epub+zip")
        epub.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""",
        )
        epub.writestr(
            "OEBPS/content.opf",
            f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <manifest>{manifest_items}</manifest>
  <spine>{spine_items}</spine>
</package>
""",
        )
        for chapter_id, html in chapters:
            epub.writestr(f"OEBPS/{chapter_id}.xhtml", html)

    return buffer.getvalue()


def test_converts_spine_items_in_reading_order():
    epub_bytes = make_epub(
        [
            ("chapter-one", "<html><body><h1>First</h1><p>One</p></body></html>"),
            ("chapter-two", "<html><body><h1>Second</h1><p>Two</p></body></html>"),
        ],
        spine=["chapter-two", "chapter-one"],
    )

    result = convert_epub_bytes(epub_bytes, "sample.epub")

    assert result.filename == "sample.txt"
    assert result.text == "Second\n\nTwo\n\nFirst\n\nOne"
```

- [ ] **Step 3: Run test to verify it fails**

Run:

```bash
pytest tests/test_converter.py::test_converts_spine_items_in_reading_order -v
```

Expected: FAIL because `app.converter` does not exist.

## Task 2: Minimal Converter Implementation

**Files:**
- Create: `app/converter.py`
- Test: `tests/test_converter.py`

- [ ] **Step 1: Implement the minimal converter**

Create `app/converter.py` with:

```python
from __future__ import annotations

import posixpath
import re
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree


class EpubConversionError(Exception):
    """Raised when an EPUB cannot be converted into readable text."""


@dataclass(frozen=True)
class ConversionResult:
    filename: str
    text: str


class _TextExtractor(HTMLParser):
    BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "body",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
    }
    SKIP_TAGS = {"script", "style"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag in self.BLOCK_TAGS:
            self._append_newline()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag in self.BLOCK_TAGS:
            self._append_newline()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = re.sub(r"\s+", " ", data)
        if not text.strip():
            return
        if self._chunks and not self._chunks[-1].endswith((" ", "\n")):
            self._chunks.append(" ")
        self._chunks.append(text.strip())

    def text(self) -> str:
        return "".join(self._chunks)

    def _append_newline(self) -> None:
        if not self._chunks or self._chunks[-1].endswith("\n"):
            return
        self._chunks.append("\n")


def convert_epub_bytes(epub_bytes: bytes, source_filename: str) -> ConversionResult:
    try:
        with zipfile.ZipFile(BytesIO(epub_bytes)) as epub:
            opf_path = _find_opf_path(epub)
            document_paths = _find_spine_document_paths(epub, opf_path)
            sections = [_extract_document_text(epub, path) for path in document_paths]
    except zipfile.BadZipFile as exc:
        raise EpubConversionError("上传的文件不是有效的 EPUB。") from exc
    except KeyError as exc:
        raise EpubConversionError("EPUB 结构不完整，缺少必要文件。") from exc
    except ElementTree.ParseError as exc:
        raise EpubConversionError("EPUB 元数据格式无效。") from exc

    text = _normalize_text("\n\n".join(section for section in sections if section.strip()))
    if not text:
        raise EpubConversionError("这个 EPUB 没有可提取的文本内容。")

    return ConversionResult(filename=_txt_filename(source_filename), text=text)


def _find_opf_path(epub: zipfile.ZipFile) -> str:
    container_xml = epub.read("META-INF/container.xml")
    root = ElementTree.fromstring(container_xml)
    rootfile = _first_element(root, "rootfile")
    if rootfile is None:
        raise EpubConversionError("EPUB 缺少 OPF 包路径。")
    opf_path = rootfile.attrib.get("full-path", "").strip()
    if not opf_path:
        raise EpubConversionError("EPUB OPF 包路径为空。")
    return opf_path


def _find_spine_document_paths(epub: zipfile.ZipFile, opf_path: str) -> list[str]:
    package = ElementTree.fromstring(epub.read(opf_path))
    manifest = {
        item.attrib["id"]: item.attrib
        for item in _elements(package, "item")
        if "id" in item.attrib and "href" in item.attrib
    }
    spine_ids = [
        itemref.attrib["idref"]
        for itemref in _elements(package, "itemref")
        if "idref" in itemref.attrib
    ]
    if not manifest or not spine_ids:
        raise EpubConversionError("EPUB 缺少 manifest 或 spine。")

    base_dir = posixpath.dirname(opf_path)
    document_paths: list[str] = []
    for item_id in spine_ids:
        item = manifest.get(item_id)
        if item is None:
            continue
        media_type = item.get("media-type", "")
        href = item.get("href", "")
        if media_type not in {"application/xhtml+xml", "text/html"}:
            continue
        document_paths.append(posixpath.normpath(posixpath.join(base_dir, href)))

    if not document_paths:
        raise EpubConversionError("EPUB spine 中没有可读取的 HTML 文档。")
    return document_paths


def _extract_document_text(epub: zipfile.ZipFile, path: str) -> str:
    raw = epub.read(path)
    html = raw.decode("utf-8", errors="replace")
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return _normalize_text(parser.text())


def _normalize_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in normalized.split("\n")]

    output: list[str] = []
    previous_blank = False
    for line in lines:
        if line:
            output.append(line)
            previous_blank = False
        elif output and not previous_blank:
            output.append("")
            previous_blank = True
    return "\n".join(output).strip()


def _txt_filename(source_filename: str) -> str:
    stem = Path(source_filename or "converted").stem or "converted"
    return f"{stem}.txt"


def _elements(root: ElementTree.Element, local_name: str) -> list[ElementTree.Element]:
    return [element for element in root.iter() if _local_name(element.tag) == local_name]


def _first_element(root: ElementTree.Element, local_name: str) -> ElementTree.Element | None:
    return next((element for element in root.iter() if _local_name(element.tag) == local_name), None)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
```

- [ ] **Step 2: Run the first converter test to verify it passes**

Run:

```bash
pytest tests/test_converter.py::test_converts_spine_items_in_reading_order -v
```

Expected: PASS.

- [ ] **Step 3: Commit converter baseline**

Run:

```bash
git add app/__init__.py app/converter.py tests/test_converter.py
git commit -m "feat: add EPUB converter core"
```

## Task 3: Converter Edge Case Tests

**Files:**
- Modify: `tests/test_converter.py`
- Modify: `app/converter.py`

- [ ] **Step 1: Add failing edge case tests**

Append to `tests/test_converter.py`:

```python
import pytest

from app.converter import EpubConversionError


def test_cleans_html_entities_scripts_and_repeated_whitespace():
    epub_bytes = make_epub(
        [
            (
                "chapter",
                """
                <html>
                  <head><style>.hidden { display: none; }</style></head>
                  <body>
                    <h1>Tom &amp; Jerry</h1>
                    <script>ignoreMe()</script>
                    <p>  spaced
                       text  </p>
                    <p>Second&nbsp;paragraph</p>
                  </body>
                </html>
                """,
            )
        ]
    )

    result = convert_epub_bytes(epub_bytes, "entities.epub")

    assert result.text == "Tom & Jerry\n\nspaced text\n\nSecond paragraph"


def test_invalid_zip_raises_conversion_error():
    with pytest.raises(EpubConversionError, match="不是有效的 EPUB"):
        convert_epub_bytes(b"not an epub", "broken.epub")


def test_missing_package_metadata_raises_conversion_error():
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as epub:
        epub.writestr("mimetype", "application/epub+zip")

    with pytest.raises(EpubConversionError, match="结构不完整"):
        convert_epub_bytes(buffer.getvalue(), "missing.epub")
```

- [ ] **Step 2: Run edge case tests to verify failures**

Run:

```bash
pytest tests/test_converter.py -v
```

Expected: the whitespace/entity test may fail if `&nbsp;` remains a non-breaking space; errors should identify converter behavior, not test import errors.

- [ ] **Step 3: Update normalization for non-breaking spaces if needed**

If the whitespace/entity test fails on non-breaking spaces, update `_normalize_text` in `app/converter.py`:

```python
def _normalize_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in normalized.split("\n")]

    output: list[str] = []
    previous_blank = False
    for line in lines:
        if line:
            output.append(line)
            previous_blank = False
        elif output and not previous_blank:
            output.append("")
            previous_blank = True
    return "\n".join(output).strip()
```

- [ ] **Step 4: Run converter tests to verify they pass**

Run:

```bash
pytest tests/test_converter.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit converter test coverage**

Run:

```bash
git add app/converter.py tests/test_converter.py
git commit -m "test: cover EPUB converter edge cases"
```

## Task 4: Web Route Tests

**Files:**
- Create: `tests/test_main.py`
- Create: `requirements.txt`

- [ ] **Step 1: Add dependencies**

Create `requirements.txt` with:

```text
fastapi
httpx
jinja2
python-multipart
pytest
uvicorn[standard]
```

- [ ] **Step 2: Add failing route tests**

Create `tests/test_main.py` with:

```python
from fastapi.testclient import TestClient

from app.main import app
from tests.test_converter import make_epub


client = TestClient(app)


def test_upload_valid_epub_shows_preview_and_download_filename():
    epub_bytes = make_epub(
        [("chapter", "<html><body><h1>标题</h1><p>正文内容</p></body></html>")]
    )

    response = client.post(
        "/convert",
        files={"file": ("book.epub", epub_bytes, "application/epub+zip")},
    )

    assert response.status_code == 200
    assert "标题" in response.text
    assert "正文内容" in response.text
    assert "book.txt" in response.text


def test_upload_rejects_non_epub_filename():
    response = client.post(
        "/convert",
        files={"file": ("book.txt", b"plain text", "text/plain")},
    )

    assert response.status_code == 400
    assert "请选择 .epub 文件" in response.text


def test_download_returns_text_attachment():
    response = client.post(
        "/download",
        data={"filename": "book.txt", "text": "第一章\n\n正文"},
    )

    assert response.status_code == 200
    assert response.text == "第一章\n\n正文"
    assert response.headers["content-type"].startswith("text/plain")
    assert "attachment" in response.headers["content-disposition"]
    assert "book.txt" in response.headers["content-disposition"]
```

- [ ] **Step 3: Run route tests to verify they fail**

Run:

```bash
pytest tests/test_main.py -v
```

Expected: FAIL because `app.main` does not exist.

## Task 5: FastAPI Web App And Template

**Files:**
- Create: `app/main.py`
- Create: `app/templates/index.html`
- Create: `app/static/styles.css`
- Test: `tests/test_main.py`

- [ ] **Step 1: Implement FastAPI routes**

Create `app/main.py` with:

```python
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.converter import EpubConversionError, convert_epub_bytes


app = FastAPI(title="EPUB to TXT")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/convert", response_class=HTMLResponse)
async def convert(request: Request, file: UploadFile = File(...)) -> HTMLResponse:
    filename = file.filename or ""
    if not filename.lower().endswith(".epub"):
        return _page(request, error="请选择 .epub 文件。", status_code=400)

    try:
        result = convert_epub_bytes(await file.read(), filename)
    except EpubConversionError as exc:
        return _page(request, error=str(exc), status_code=400)
    except Exception:
        return _page(request, error="转换失败，请检查 EPUB 文件后重试。", status_code=500)

    return _page(
        request,
        text=result.text,
        output_filename=result.filename,
        source_filename=filename,
    )


@app.post("/download")
async def download(filename: str = Form(...), text: str = Form(...)) -> Response:
    safe_filename = _safe_txt_filename(filename)
    quoted = quote(safe_filename)
    return Response(
        text,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{safe_filename}"; filename*=UTF-8\'\'{quoted}'
            )
        },
    )


def _page(
    request: Request,
    *,
    error: str | None = None,
    text: str | None = None,
    output_filename: str | None = None,
    source_filename: str | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "error": error,
            "text": text,
            "output_filename": output_filename,
            "source_filename": source_filename,
        },
        status_code=status_code,
    )


def _safe_txt_filename(filename: str) -> str:
    name = Path(filename or "converted.txt").name
    name = re.sub(r"[\r\n\"\\\\/]+", "_", name).strip() or "converted.txt"
    if not name.lower().endswith(".txt"):
        name = f"{Path(name).stem or 'converted'}.txt"
    return name
```

- [ ] **Step 2: Create HTML template**

Create `app/templates/index.html` with:

```html
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>EPUB 转 TXT</title>
    <link rel="stylesheet" href="{{ url_for('static', path='/styles.css') }}" />
  </head>
  <body>
    <main class="shell">
      <section class="panel">
        <div class="heading">
          <p class="eyebrow">EPUB to TXT</p>
          <h1>EPUB 转 TXT</h1>
        </div>

        <form class="upload" action="/convert" method="post" enctype="multipart/form-data">
          <label class="file-picker">
            <span>选择 EPUB 文件</span>
            <input type="file" name="file" accept=".epub,application/epub+zip" required />
          </label>
          <button type="submit">转换</button>
        </form>

        {% if error %}
          <p class="alert" role="alert">{{ error }}</p>
        {% endif %}

        {% if text %}
          <section class="result" aria-label="转换结果">
            <div class="result-bar">
              <div>
                <p class="label">输出文件</p>
                <h2>{{ output_filename }}</h2>
              </div>
              <form action="/download" method="post">
                <input type="hidden" name="filename" value="{{ output_filename }}" />
                <textarea name="text" class="hidden-text">{{ text }}</textarea>
                <button type="submit">下载 TXT</button>
              </form>
            </div>
            <textarea class="preview" readonly>{{ text }}</textarea>
          </section>
        {% endif %}
      </section>
    </main>
  </body>
</html>
```

- [ ] **Step 3: Create stylesheet**

Create `app/static/styles.css` with:

```css
:root {
  color-scheme: light;
  --bg: #f6f4ef;
  --surface: #fffaf1;
  --ink: #1d2525;
  --muted: #62706c;
  --line: #d8ded7;
  --accent: #126b5d;
  --accent-dark: #0d4d43;
  --error-bg: #fff0ed;
  --error: #9d2f24;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-height: 100vh;
  background: linear-gradient(135deg, #f6f4ef 0%, #e9f1ee 50%, #f7efe7 100%);
  color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.shell {
  width: min(980px, calc(100% - 32px));
  margin: 0 auto;
  padding: 56px 0;
}

.panel {
  background: rgba(255, 250, 241, 0.92);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: 0 24px 80px rgba(32, 44, 42, 0.14);
  padding: 32px;
}

.heading {
  margin-bottom: 24px;
}

.eyebrow,
.label {
  color: var(--muted);
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0;
  margin: 0 0 6px;
  text-transform: uppercase;
}

h1,
h2 {
  margin: 0;
}

h1 {
  font-size: 34px;
  line-height: 1.15;
}

h2 {
  font-size: 20px;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.upload {
  align-items: stretch;
  display: grid;
  gap: 12px;
  grid-template-columns: 1fr auto;
}

.file-picker {
  align-items: center;
  background: #ffffff;
  border: 1px solid var(--line);
  border-radius: 8px;
  display: flex;
  gap: 14px;
  min-height: 52px;
  padding: 10px 14px;
}

.file-picker span {
  color: var(--muted);
  flex: 0 0 auto;
  font-size: 14px;
  font-weight: 700;
}

input[type="file"] {
  min-width: 0;
  width: 100%;
}

button {
  background: var(--accent);
  border: 0;
  border-radius: 8px;
  color: #ffffff;
  cursor: pointer;
  font-size: 15px;
  font-weight: 800;
  min-height: 52px;
  padding: 0 22px;
}

button:hover {
  background: var(--accent-dark);
}

.alert {
  background: var(--error-bg);
  border: 1px solid rgba(157, 47, 36, 0.24);
  border-radius: 8px;
  color: var(--error);
  font-weight: 700;
  margin: 18px 0 0;
  padding: 12px 14px;
}

.result {
  border-top: 1px solid var(--line);
  margin-top: 28px;
  padding-top: 24px;
}

.result-bar {
  align-items: center;
  display: flex;
  gap: 16px;
  justify-content: space-between;
  margin-bottom: 14px;
}

.hidden-text {
  display: none;
}

.preview {
  background: #ffffff;
  border: 1px solid var(--line);
  border-radius: 8px;
  color: var(--ink);
  font: 15px/1.7 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  min-height: 420px;
  padding: 18px;
  resize: vertical;
  width: 100%;
}

@media (max-width: 700px) {
  .shell {
    width: min(100% - 20px, 980px);
    padding: 24px 0;
  }

  .panel {
    padding: 20px;
  }

  h1 {
    font-size: 28px;
  }

  .upload,
  .result-bar {
    align-items: stretch;
    display: flex;
    flex-direction: column;
  }
}
```

- [ ] **Step 4: Run route tests to verify they pass**

Run:

```bash
pytest tests/test_main.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit web app**

Run:

```bash
git add app/main.py app/templates/index.html app/static/styles.css requirements.txt tests/test_main.py
git commit -m "feat: add EPUB converter web UI"
```

## Task 6: Documentation And Full Verification

**Files:**
- Create: `README.md`
- Modify: no production files unless verification reveals a defect.

- [ ] **Step 1: Write README**

Create `README.md` with:

```markdown
# EPUB 转 TXT

本项目是一个本地 Web 小工具，用于把 `.epub` 电子书转换成 UTF-8 `.txt` 文本。

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 启动

```bash
uvicorn app.main:app --reload
```

打开：

```text
http://127.0.0.1:8000
```

## 使用

1. 在页面中选择一个 `.epub` 文件。
2. 点击“转换”。
3. 查看文本预览。
4. 点击“下载 TXT”保存转换结果。

## 测试

```bash
pytest
```

## 说明

- 转换顺序遵循 EPUB 的 spine 阅读顺序。
- 支持常见 XHTML/HTML 章节内容。
- 不包含 OCR，因此图片扫描版 EPUB 无法提取正文。
```

- [ ] **Step 2: Run full test suite**

Run:

```bash
pytest -v
```

Expected: PASS.

- [ ] **Step 3: Start local server**

Run:

```bash
uvicorn app.main:app --reload
```

Expected: server listens on `http://127.0.0.1:8000`.

- [ ] **Step 4: Verify GUI in browser**

Open `http://127.0.0.1:8000` and confirm:

- Upload controls are visible.
- Text does not overlap at desktop and mobile widths.
- A minimal EPUB upload shows preview text.
- Download action returns a `.txt` attachment.

- [ ] **Step 5: Commit documentation**

Run:

```bash
git add README.md
git commit -m "docs: add usage instructions"
```

## Self-Review

- Spec coverage: converter core, GUI upload, preview, download, error handling, tests, and README are covered by Tasks 1-6.
- Marker scan: no incomplete-work markers remain in this plan.
- Type consistency: `ConversionResult.filename`, `ConversionResult.text`, `convert_epub_bytes`, and `EpubConversionError` are named consistently across converter, routes, and tests.
