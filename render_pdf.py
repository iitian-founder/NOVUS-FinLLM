import fitz # PyMuPDF
doc = fitz.open("test.pdf")
page = doc.load_page(0)
pix = page.get_pixmap(dpi=150)
pix.save("/Users/shauryaiitd/.gemini/antigravity/brain/0c0ccf68-edcf-4a20-bc86-095330fb010e/test_pdf_demo.png")
print("Saved PNG")
