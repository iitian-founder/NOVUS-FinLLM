from pdf_export import generate_quant_pdf

dummy_html = """
<div>
    <h1>TEST REPORT</h1>
    <h2>FINANCIAL PROJECTIONS</h2>
    <table>
        <tr><th>Metric</th><th>2023</th><th>2024</th></tr>
        <tr><td>Revenue</td><td>100</td><td>110</td></tr>
    </table>
</div>
"""
try:
    pdf_bytes = generate_quant_pdf("TEST", dummy_html)
    with open("test.pdf", 'wb') as f:
        f.write(pdf_bytes)
    print("SUCCESS")
except Exception as e:
    print(f"FAILED: {e}")
