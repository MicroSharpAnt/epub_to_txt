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
        if not self._chunks or self._chunks[-1].endswith("\n\n"):
            return
        self._chunks.append("\n\n")


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
