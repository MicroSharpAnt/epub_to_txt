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
