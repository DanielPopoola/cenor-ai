import io

import pytest
from docx import Document

from candidate_profile.errors import CVExtractionError
from candidate_profile.extraction import extract_cv_text


def _docx_bytes(paragraphs: list[str]) -> bytes:
    doc = Document()
    for p in paragraphs:
        doc.add_paragraph(p)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_extracts_text_from_valid_docx():
    data = _docx_bytes(["Ada Lovelace", "Software Engineer", "Python, Go"])
    text = extract_cv_text(data, "resume.docx")
    assert "Ada Lovelace" in text
    assert "Python, Go" in text


def test_rejects_unsupported_file_extension():
    with pytest.raises(CVExtractionError):
        extract_cv_text(b"hello", "resume.txt")


def test_rejects_corrupted_docx():
    with pytest.raises(CVExtractionError):
        extract_cv_text(b"this is not a real docx file", "resume.docx")


def test_rejects_empty_docx():
    data = _docx_bytes([])
    with pytest.raises(CVExtractionError):
        extract_cv_text(data, "resume.docx")


def test_rejects_corrupted_pdf():
    with pytest.raises(CVExtractionError):
        extract_cv_text(b"%PDF-1.4 not actually valid pdf bytes", "resume.pdf")


def test_case_insensitive_extension_matching():
    data = _docx_bytes(["Some content"])
    text = extract_cv_text(data, "RESUME.DOCX")
    assert "Some content" in text
