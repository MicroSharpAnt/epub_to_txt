# EPUB to TXT Web GUI Design

## Goal

Build a local web application that converts uploaded EPUB files into UTF-8 plain text. The user opens a browser page, uploads one `.epub` file, previews the extracted text, and downloads a `.txt` file.

## Scope

Included:

- Single-file EPUB upload through a local web page.
- Server-side EPUB parsing.
- Ordered text extraction from EPUB spine items.
- HTML/XHTML tag removal and entity decoding.
- Whitespace normalization suitable for readable plain text.
- Text preview in the browser.
- Download of the converted `.txt` file.
- Clear error messages for invalid EPUB files and conversion failures.
- Focused automated tests for the conversion logic.

Excluded:

- Batch folder conversion.
- User accounts, persistent storage, or cloud deployment.
- OCR for image-only EPUB content.
- Advanced formatting preservation such as footnote linking, tables, or Markdown output.

## Recommended Approach

Use FastAPI for the local web server, Jinja2 for the page template, and standard Python EPUB parsing with `zipfile` plus XML/HTML parsing helpers. This keeps the tool small and easy to run while still separating the user interface from the conversion logic.

## Architecture

Project layout:

```text
app/
  main.py
  converter.py
  templates/
    index.html
  static/
    styles.css
tests/
  test_converter.py
requirements.txt
README.md
```

`app/converter.py` owns all EPUB-to-text behavior. It accepts EPUB bytes and returns a conversion result containing the output filename and text. It does not depend on FastAPI, which makes it straightforward to test.

`app/main.py` owns HTTP behavior. It renders the upload page, validates uploads at the request boundary, calls the converter, and returns either the page with a preview or a downloadable text response.

The browser page stays simple: file input, convert button, error area, preview area, and download action after a successful conversion.

## Data Flow

1. The user opens the local web page.
2. The user chooses one `.epub` file and submits the form.
3. FastAPI reads the uploaded bytes and passes them to the converter.
4. The converter opens the EPUB as a ZIP archive.
5. The converter reads `META-INF/container.xml` to find the OPF package file.
6. The converter reads the OPF manifest and spine to identify reading-order document files.
7. Each XHTML/HTML spine item is parsed into text.
8. The converter joins sections with blank lines and normalizes repeated whitespace.
9. The page shows a preview and stores the converted text for download.

## Conversion Rules

- Output encoding is UTF-8.
- The output filename is based on the uploaded filename with a `.txt` suffix.
- Spine order determines chapter order.
- Script, style, nav noise, and HTML tags are excluded from the output.
- HTML entities are decoded.
- Paragraph-like blocks create line breaks.
- Repeated blank lines collapse to at most two consecutive newlines.
- Leading and trailing whitespace is removed from the final text.
- Empty converted output is treated as a conversion error with a clear message.

## Error Handling

The application reports actionable messages for:

- No file selected.
- Non-EPUB filename.
- Invalid ZIP or malformed EPUB structure.
- Missing OPF package, manifest, or spine.
- EPUB files that contain no extractable text.

Unexpected exceptions are caught at the route boundary and shown as a generic conversion failure while tests cover expected converter errors directly.

## Testing

Automated tests focus on `app/converter.py`:

- Valid minimal EPUB converts spine items in order.
- HTML tags and entities are cleaned into readable text.
- Repeated whitespace and blank lines are normalized.
- Invalid ZIP input raises a conversion error.
- EPUB missing required package metadata raises a conversion error.

Route tests are optional for the first version because the main risk is parsing correctness, not framework behavior.

## Run Experience

The README will document:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

## Acceptance Criteria

- A user can start the local server and open the GUI in a browser.
- Uploading a valid EPUB shows a text preview.
- The converted `.txt` can be downloaded.
- Invalid EPUB inputs produce clear page-level errors.
- Converter tests pass with `pytest`.
