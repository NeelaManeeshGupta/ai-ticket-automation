import os
import logging
from pathlib import Path
from typing import List
from schemas.email_schemas import EmailAttachment

logger = logging.getLogger(__name__)

class OCRService:
    """Extracts text content from images, PDFs, and log attachments."""

    def __init__(self):
        self._init_ocr_engine()

    def _init_ocr_engine(self):
        """Initializes RapidOCR engine if available, or logs fallback mode."""
        self.ocr_engine = None
        try:
            from rapidocr_onnxruntime import RapidOCR
            self.ocr_engine = RapidOCR()
            logger.info("RapidOCR engine initialized successfully.")
        except Exception as e:
            logger.info(f"RapidOCR engine not available ({e}). Using image/text inspection fallback.")

    def extract_text_from_attachments(self, attachments: List[EmailAttachment]) -> str:
        """Processes a list of email attachments and returns combined OCR text."""
        extracted_texts = []

        for att in attachments:
            file_path = att.file_path
            filename = att.filename
            
            if not os.path.exists(file_path):
                logger.warning(f"Attachment file not found: {file_path}")
                continue

            logger.info(f"Processing attachment for OCR: {filename} ({att.content_type})")
            
            ext = Path(file_path).suffix.lower()

            try:
                if ext in ['.png', '.jpg', '.jpeg', '.bmp']:
                    text = self.extract_from_image(file_path)
                elif ext == '.pdf':
                    text = self.extract_from_pdf(file_path)
                elif ext in ['.txt', '.log', '.trc', '.out']:
                    text = self.extract_from_text_file(file_path)
                else:
                    text = f"Unsupported attachment extension '{ext}'. File saved at {filename}."

                if text.strip():
                    extracted_texts.append(f"--- Attachment: {filename} ---\n{text.strip()}")
            except Exception as e:
                logger.error(f"Error processing attachment {filename}: {str(e)}")
                extracted_texts.append(f"--- Attachment: {filename} (Error processing file) ---")

        return "\n\n".join(extracted_texts)

    def extract_from_image(self, image_path: str) -> str:
        """Extracts text from PNG/JPG image using RapidOCR or fallback heuristics."""
        if self.ocr_engine:
            try:
                result, _ = self.ocr_engine(image_path)
                if result:
                    lines = [line[1] for line in result if line and len(line) > 1]
                    return "\n".join(lines)
            except Exception as e:
                logger.error(f"RapidOCR execution failed on {image_path}: {str(e)}")

        # Fallback reading / basic image inspection
        try:
            from PIL import Image
            img = Image.open(image_path)
            # Try pytesseract if installed
            try:
                import pytesseract
                text = pytesseract.image_to_string(img)
                if text.strip():
                    return text.strip()
            except Exception:
                pass
            return f"[Attached Screenshot Image: {Path(image_path).name} (Resolution: {img.width}x{img.height})]"
        except Exception as e:
            return f"[Attachment Image File: {Path(image_path).name}]"

    def extract_from_pdf(self, pdf_path: str) -> str:
        """Extracts text from PDF document using PyPDF."""
        try:
            import pypdf
            reader = pypdf.PdfReader(pdf_path)
            text_pages = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_pages.append(page_text)
            
            if text_pages:
                return "\n".join(text_pages)
        except Exception as e:
            logger.warning(f"PyPDF extraction failed for {pdf_path}: {str(e)}")

        return "[PDF document processed - text extraction unavailable or scanned PDF]"

    def extract_from_text_file(self, file_path: str) -> str:
        """Extracts text directly from log/text files."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read(4096)
        except Exception as e:
            return f"[Error reading text file: {str(e)}]"

    def get_image_attachment_parts(self, attachments: List[EmailAttachment]) -> List[dict]:
        """Loads image attachment files as raw byte payloads for Gemini multimodal API calls."""
        image_parts = []
        for att in attachments:
            file_path = att.file_path
            if not os.path.exists(file_path):
                continue
            ext = Path(file_path).suffix.lower()
            if ext in ['.png', '.jpg', '.jpeg', '.webp']:
                mime_type = att.content_type if att.content_type and '/' in att.content_type else f"image/{ext.replace('.', '')}"
                try:
                    with open(file_path, 'rb') as f:
                        file_bytes = f.read()
                    image_parts.append({
                        "mime_type": mime_type,
                        "data": file_bytes,
                        "filename": att.filename
                    })
                except Exception as e:
                    logger.error(f"Failed to read image bytes for {file_path}: {e}")
        return image_parts

ocr_service = OCRService()

