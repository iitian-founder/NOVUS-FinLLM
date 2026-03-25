"""
Module for generating institutional-grade PDF reports ("Light-Mode Quant" aesthetic)
using WeasyPrint. 
"""
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration
import io
import datetime

def generate_quant_pdf(ticker: str, content_html: str) -> bytes:
    """
    Wraps the raw report HTML inside a strictly styled HTML document
    and renders a PDF via WeasyPrint.
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # The HTML wrapper structure
    document_html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>{ticker} Report</title>
        <link href="https://fonts.googleapis.com/css2?family=Merriweather:ital,wght@0,300;0,400;0,700;1,400&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
        <style>
            @page {{
                size: letter portrait;
                margin: 1.5in 1in 1in 1in;
                
                @top-left {{
                    content: "NOVUS FINANCIAL FORENSICS";
                    font-family: 'JetBrains Mono', monospace;
                    font-size: 10pt;
                    font-weight: bold;
                    color: #111827;
                }}
                @top-center {{
                    content: "{ticker}";
                    font-family: 'JetBrains Mono', monospace;
                    font-size: 10pt;
                    font-weight: bold;
                    color: #00E599;
                }}
                @top-right {{
                    content: "CONFIDENTIAL / INTERNAL USE ONLY";
                    font-family: 'JetBrains Mono', monospace;
                    font-size: 9pt;
                    font-weight: bold;
                    color: #DC2626; /* Muted Red */
                }}
                @bottom-left {{
                    content: "Generated: {timestamp}";
                    font-family: 'JetBrains Mono', monospace;
                    font-size: 8pt;
                    color: #6B7280;
                }}
                @bottom-right {{
                    content: "Page " counter(page) " of " counter(pages);
                    font-family: 'JetBrains Mono', monospace;
                    font-size: 8pt;
                    color: #6B7280;
                }}
            }}

            body {{
                font-family: 'Merriweather', 'PT Serif', serif;
                font-size: 10.5pt;
                line-height: 1.6;
                color: #111827;
                background-color: #FFFFFF;
                margin: 0;
                padding: 0;
            }}

            h1, h2, h3, h4, h5, h6 {{
                font-family: 'JetBrains Mono', monospace;
                color: #111827;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                page-break-after: avoid;
            }}

            h1 {{
                font-size: 20pt;
                border-bottom: 2px solid #111827;
                padding-bottom: 8pt;
                margin-top: 0;
                margin-bottom: 16pt;
            }}

            h2 {{
                font-size: 14pt;
                color: #111827;
                border-bottom: 1px dashed #00E599;
                padding-bottom: 4pt;
                margin-top: 24pt;
                margin-bottom: 12pt;
            }}

            h3 {{
                font-size: 11pt;
                color: #374151;
                margin-top: 16pt;
                margin-bottom: 8pt;
            }}

            p {{
                margin-top: 0;
                margin-bottom: 12pt;
            }}

            /* Monospace formatting for metrics and tickers */
            code, pre, .ticker, .calc-badge {{
                font-family: 'JetBrains Mono', monospace;
                font-size: 0.9em;
            }}

            /* Terminal Badges - Adapted for Print (Stark Black and White with Teal outline) */
            .calc-badge {{
                color: #111827;
                font-weight: 700;
                border: 1px solid #00E599;
                padding: 1pt 3pt;
                border-radius: 2pt;
                background-color: #F3F4F6;
            }}

            blockquote {{
                border-left: 3px solid #00E599;
                margin: 12pt 0;
                padding: 8pt 12pt;
                background-color: #F9FAFB;
                font-style: italic;
                color: #4B5563;
            }}

            /* ── Data Tables (Strict Quant Formatting) ── */
            table {{
                width: 100%;
                border-collapse: collapse;
                margin: 16pt 0;
                font-family: 'JetBrains Mono', monospace;
                font-size: 9pt;
                font-variant-numeric: tabular-nums;
            }}

            th, td {{
                border: 1px solid #D1D5DB;
                padding: 6pt 8pt;
            }}

            th {{
                background-color: #F3F4F6;
                color: #111827;
                font-weight: 700;
                text-align: right;
                border-bottom: 2px solid #00E599; /* Subtle accent */
            }}

            /* First column usually contains text/metric names, so left-align it */
            th:first-child, td:first-child {{
                text-align: left;
                font-weight: 700;
            }}

            /* Right-align all numerical data columns */
            td {{
                text-align: right;
            }}

            /* Zebra striping for readability */
            tr:nth-child(even) {{
                background-color: #F9FAFB;
            }}

            /* Print hints to prevent bad page breaks */
            table, tr, td, th, tbody, thead, tfoot {{
                page-break-inside: avoid;
            }}

            ul, ol {{
                margin-bottom: 12pt;
                padding-left: 20pt;
            }}

            li {{
                margin-bottom: 4pt;
            }}
        </style>
    </head>
    <body>
        <!-- The frontend pre-rendered HTML gets injected here -->
        {content_html}
    </body>
    </html>
    """
    
    # Render PDF in memory
    font_config = FontConfiguration()
    html = HTML(string=document_html)
    
    # We load standard CSS so normal element displays work
    pdf_bytes = html.write_pdf(font_config=font_config)
    
    return pdf_bytes
