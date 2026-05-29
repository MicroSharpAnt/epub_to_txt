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
    return templates.TemplateResponse(request, "index.html")


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
        request,
        "index.html",
        {
            "error": error,
            "text": text,
            "output_filename": output_filename,
            "source_filename": source_filename,
        },
        status_code=status_code,
    )


def _safe_txt_filename(filename: str) -> str:
    name = Path(filename or "converted.txt").name
    name = re.sub(r"[\r\n\"\\/]+", "_", name).strip() or "converted.txt"
    if not name.lower().endswith(".txt"):
        name = f"{Path(name).stem or 'converted'}.txt"
    return name
