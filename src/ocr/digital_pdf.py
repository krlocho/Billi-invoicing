import pdfplumber

from src.ocr.base import BankStatementResult, OCRStrategy


class DigitalPDFExtractor(OCRStrategy):
    """Extract text from digitally-generated PDFs (no OCR needed)."""

    def extract(self, pdf_path: str) -> BankStatementResult:
        pages_text = []
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        pages_text.append(text)
        except Exception as e:
            return BankStatementResult(raw_text="", errors=[str(e)])

        raw_text = "\n".join(pages_text)

        if not raw_text.strip():
            return BankStatementResult(raw_text="", errors=["No text extracted from PDF"])

        return BankStatementResult(raw_text=raw_text, transactions=[])
