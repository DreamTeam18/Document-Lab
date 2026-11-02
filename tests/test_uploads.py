from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.api import app, storage
from app.config import settings
from app.uploads import extract_document


def pdf_bytes(text=None, encrypted=False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=300)
    if text:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 20 200 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_text_and_pdf_extraction():
    doc = extract_document("../../notes.txt", b"\xef\xbb\xbfLabels are blue.")
    assert doc.title == "notes.txt"
    assert doc.sections[0].text == "Labels are blue."
    pdf = extract_document("manual.pdf", pdf_bytes("Labels are blue."))
    assert pdf.sections[0].page == 1
    assert "Labels are blue." in pdf.sections[0].text
    assert extract_document("notes.md", b"# Notes").sections[0].text == "# Notes"


@pytest.mark.parametrize(
    "name,data,message",
    [
        ("a.exe", b"text", "Choose a PDF"),
        ("a.txt", b"", "nonempty"),
        ("a.txt", b"\xff", "UTF-8"),
        ("a.txt", b"   ", "No readable text"),
        ("a.txt", b"a" * 1000001, "1,000,000"),
        ("a.pdf", b"bad pdf", "valid text-based PDF"),
        ("a.pdf", pdf_bytes(), "No readable text"),
        ("a.pdf", pdf_bytes(encrypted=True), "Password-protected"),
    ],
)
def test_upload_validation(name, data, message):
    with pytest.raises(ValueError, match=message):
        extract_document(name, data)


def test_upload_api(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    settings.cache_clear()
    calls = []

    async def fake_ingest(document, config, providers):
        from scripts.ingest import chunks

        calls.append(document)
        assert config.upload_timeout_seconds == 1800
        return sum(sum(1 for _ in chunks(section.text)) for section in document.sections)

    monkeypatch.setattr("app.api.ingest", fake_ingest)
    app.dependency_overrides[storage] = lambda: object()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/documents/upload?filename=notes.txt", content=b"Labels are blue."
            )
            assert response.status_code == 201
            assert response.json()["chunks"] == 1
            assert calls[0].sections[0].text == "Labels are blue."
            assert client.post("/documents/upload?filename=bad.txt", content=b"").status_code == 422
            assert (
                client.post(
                    "/documents/upload?filename=big.txt", content=b"a" * (10 * 1024 * 1024 + 1)
                ).status_code
                == 413
            )
            assert len(calls) == 1
            response = client.post(
                "/documents/upload?filename=100-pages.pdf", content=hundred_page_pdf()
            )
            assert response.status_code == 201
            assert response.json()["chunks"] == 500
            assert len(calls[1].sections) == 100
    finally:
        app.dependency_overrides.clear()
        settings.cache_clear()


def hundred_page_pdf(page_count=100):
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(pdf_bytes("Archive labels are blue. " * 400)))
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_page(reader.pages[0])
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_dense_hundred_page_pdf():
    from scripts.ingest import chunks

    document = extract_document("100-page-manual.pdf", hundred_page_pdf())
    assert len(document.sections) == 100
    assert [s.page for s in document.sections] == list(range(1, 101))
    assert sum(len(s.text) for s in document.sections) > 900_000
    assert sum(sum(1 for _ in chunks(s.text)) for s in document.sections) == 500


def test_pdf_page_limit():
    with pytest.raises(ValueError, match="100 pages"):
        extract_document("101-pages.pdf", hundred_page_pdf(101))
