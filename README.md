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
