import io

import cv2
import numpy as np
import pytesseract
from pdf2image import convert_from_path

from src.ocr.base import BankStatementResult, OCRStrategy


class TesseractExtractor(OCRStrategy):
    """OCR extraction for scanned PDF bank statements."""

    def extract(self, pdf_path: str) -> BankStatementResult:
        try:
            images = convert_from_path(pdf_path, dpi=300)
        except Exception as e:
            return BankStatementResult(raw_text="", errors=[f"PDF to image failed: {e}"])

        pages_text = []
        for img in images:
            img_array = np.array(img)
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            # Binarization for better OCR
            _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            text = pytesseract.image_to_string(thresh, lang="spa+eng")
            if text.strip():
                pages_text.append(text)

        raw_text = "\n".join(pages_text)

        if not raw_text.strip():
            return BankStatementResult(raw_text="", errors=["No text extracted via OCR"])

        return BankStatementResult(raw_text=raw_text, transactions=[])
