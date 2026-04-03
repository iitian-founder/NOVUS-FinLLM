# utils/pdf.py — PDF text extraction utilities for Novus FinLLM
"""
PDF text extraction using PyMuPDF (fitz).
"""

import fitz  # PyMuPDF


def extract_text_from_pdfs_from_bytes(files_data) -> str:
    """Extracts and combines text from a list of PDF file byte streams."""
    combined_text = ""
    for file_data in files_data:
        try:
            pdf_document = fitz.open(stream=file_data, filetype="pdf")
            for page_num in range(pdf_document.page_count):
                page = pdf_document.load_page(page_num)
                combined_text += page.get_text()
        except Exception as e:
            print(f"Error processing PDF file: {e}")
            continue
    return combined_text
