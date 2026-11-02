"""Bounded local-file extraction for the test interface; original files are not saved."""

from io import BytesIO
from pathlib import PurePosixPath
from uuid import uuid4

from pypdf import PdfReader

from app.models import Document, Section
from scripts.ingest import chunks

MAX_BYTES = 10 * 1024 * 1024
MAX_CHARACTERS = 1_000_000
MAX_CHUNKS = 600


def extract_document(filename: str, data: bytes) -> Document:
    name = PurePosixPath(filename.replace("\\", "/")).name
    suffix = PurePosixPath(name).suffix.lower()
    if suffix not in {".pdf", ".txt", ".md"}:
        raise ValueError("Choose a PDF, TXT, or Markdown file.")
    if not data or len(data) > MAX_BYTES:
        raise ValueError("Choose a nonempty file no larger than 10 MB.")
    sections = []
    total = 0

    def add(text, page=None):
        nonlocal total
        text = text.replace("\x00", "").strip()
        total += len(text)
        if total > MAX_CHARACTERS:
            raise ValueError(
                "Document exceeds 1,000,000 extracted characters. Upload a smaller part."
            )
        if text:
            number = str(page or 1)
            sections.append(
                Section(
                    id=number,
                    number=number,
                    title=f"Page {page}" if page else name,
                    text=text,
                    page=page,
                )
            )

    if suffix == ".pdf":
        try:
            reader = PdfReader(BytesIO(data))
            if reader.is_encrypted:
                raise ValueError(
                    "Password-protected PDFs are not supported. Upload an unlocked copy."
                )
            if len(reader.pages) > 100:
                raise ValueError("PDF exceeds 100 pages. Upload a smaller part.")
            for number, page in enumerate(reader.pages, 1):
                add(page.extract_text() or "", number)
        except ValueError:
            raise
        except Exception:
            raise ValueError("Could not read this PDF. Upload a valid text-based PDF.") from None
    else:
        try:
            add(data.decode("utf-8-sig"))
        except UnicodeDecodeError:
            raise ValueError("Text files must use UTF-8 encoding.") from None
    if not sections:
        raise ValueError("No readable text found. Scanned PDFs need OCR before uploading.")
    if sum(sum(1 for _ in chunks(s.text)) for s in sections) > MAX_CHUNKS:
        raise ValueError("Document exceeds 600 text chunks. Upload a smaller part.")
    return Document(id=uuid4(), title=name, edition="Uploaded", sections=sections)
