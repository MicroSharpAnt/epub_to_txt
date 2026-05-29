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
