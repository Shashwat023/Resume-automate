from app.services.resume import extract


def test_txt_extraction_decodes_utf8():
    text = extract.extract_text("resume.txt", "Jane Doe\nSoftware Engineer".encode())
    assert text == "Jane Doe\nSoftware Engineer"


def test_txt_extraction_strips_whitespace_and_returns_none_for_empty():
    assert extract.extract_text("resume.txt", b"   \n  ") is None


def test_unknown_extension_falls_back_to_plain_decode():
    text = extract.extract_text("resume.rtf", b"plain content")
    assert text == "plain content"


def test_no_extension_falls_back_to_plain_decode():
    text = extract.extract_text("resume", b"plain content")
    assert text == "plain content"


def test_invalid_utf8_bytes_never_raise():
    # errors="ignore" drops the undecodable bytes rather than raising —
    # the interesting case is that extract_text returns cleanly at all.
    result = extract.extract_text("resume.txt", b"\xff\xfe\x00\x01")
    assert result is None or isinstance(result, str)


def test_pdf_extraction_joins_page_text(monkeypatch):
    class FakePage:
        def __init__(self, text):
            self._text = text

        def extract_text(self):
            return self._text

    class FakeReader:
        def __init__(self, _buf):
            self.pages = [FakePage("Page one"), FakePage("Page two")]

    monkeypatch.setattr(extract, "PdfReader", FakeReader)

    text = extract.extract_text("resume.pdf", b"%PDF-fake")
    assert text == "Page one\nPage two"


def test_pdf_extraction_returns_none_on_corrupt_file(monkeypatch):
    class BoomReader:
        def __init__(self, _buf):
            raise ValueError("not a PDF")

    monkeypatch.setattr(extract, "PdfReader", BoomReader)

    assert extract.extract_text("resume.pdf", b"garbage") is None


def test_docx_extraction_joins_paragraphs(monkeypatch):
    class FakeParagraph:
        def __init__(self, text):
            self.text = text

    class FakeDocument:
        def __init__(self, _buf):
            self.paragraphs = [FakeParagraph("Jane Doe"), FakeParagraph("Engineer")]

    monkeypatch.setattr(extract, "Document", FakeDocument)

    text = extract.extract_text("resume.docx", b"PK-fake-docx")
    assert text == "Jane Doe\nEngineer"


def test_docx_extraction_returns_none_on_corrupt_file(monkeypatch):
    class BoomDocument:
        def __init__(self, _buf):
            raise ValueError("not a DOCX")

    monkeypatch.setattr(extract, "Document", BoomDocument)

    assert extract.extract_text("resume.docx", b"garbage") is None
