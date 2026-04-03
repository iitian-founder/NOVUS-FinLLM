import fitz

def test_pdf():
    try:
        with open("test.pdf", 'rb') as f:
            pdf_bytes = f.read()
        print(f"File size: {len(pdf_bytes)} bytes")
        
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = ""
        for page_num in range(pdf_doc.page_count):
            page = pdf_doc.load_page(page_num)
            page_text = page.get_text().strip()
            text += page_text
            
        print(f"Extracted {len(text)} characters of text.")
        if len(text) == 0:
            print("No text could be extracted!")
        else:
            print("Preview:", text[:200])
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_pdf()
