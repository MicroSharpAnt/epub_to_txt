import zipfile
from io import BytesIO

import pytest

from app.converter import EpubConversionError, convert_epub_bytes


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


def test_cleans_html_entities_nav_scripts_and_repeated_whitespace():
    epub_bytes = make_epub(
        [
            (
                "chapter",
                """
                <html>
                  <head><style>.hidden { display: none; }</style></head>
                  <body>
                    <nav>Table of contents</nav>
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
