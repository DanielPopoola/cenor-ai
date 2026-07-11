import io

import pypdf
from docx import Document

from candidate_profile.errors import CVExtractionError


def extract_cv_text(file_bytes: bytes, filename: str) -> str:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""

    if suffix == "pdf":
        return _extract_pdf(file_bytes)
    if suffix == "docx":
        return _extract_docx(file_bytes)

    raise CVExtractionError(
        f"Unsupported file type '.{suffix}' — only .pdf and .docx are accepted"
    )


def _extract_pdf(file_bytes: bytes) -> str:
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as e:
        raise CVExtractionError("Couldn't open the PDF — it may be corrupted") from e

    if not text.strip():
        raise CVExtractionError(
            "No extractable text found in the PDF (it may be a scanned "
            "image — scanned CVs aren't supported yet)"
        )
    return text


def _extract_docx(file_bytes: bytes) -> str:
    try:
        document = Document(io.BytesIO(file_bytes))
        text = "\n".join(p.text for p in document.paragraphs)
    except Exception as e:
        raise CVExtractionError(
            "Couldn't open the .docx file — it may be corrupted"
        ) from e

    if not text.strip():
        raise CVExtractionError("The .docx file appears to be empty")
    return text
