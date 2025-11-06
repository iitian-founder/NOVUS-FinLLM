"""
Batch Processor for giga-finanalytix Flask API

This script automates the generation of financial reports for Nifty 50 companies.
It processes transcript PDFs, calls the Flask API, and generates final PDF reports.

Usage:
    python batch_processor.py

Requirements:
    - Flask API running at http://localhost:5000
    - Transcript PDFs downloaded by scrapper.py
    - Required libraries: requests, weasyprint, markdown-it-py
"""

import time
from pathlib import Path
from typing import Dict, Optional, List
import requests
from markdown_it import MarkdownIt
from weasyprint import HTML


# ==================== Configuration ====================

API_BASE_URL = "http://localhost:5000"
SOURCE_DIR = Path(r"G:\My Drive\concall transcripts\nifty 50")
TARGET_DIR = Path(r"G:\My Drive\financial_reports\nifty_50")

# Mapping of actual folder names (from scrapper) to their correct stock tickers
# The keys are the exact folder names as they appear in the file system
# The values are the official NSE ticker symbols used by the API
FOLDER_TO_TICKER_MAP: Dict[str, str] = {
    "Adani_Enterprises_Ltd": "ADANIENT",
    "Adani_Ports_&_Special_Economic_Zone_Ltd": "ADANIPORTS",
    "Apollo_Hospitals_Enterprise_Ltd": "APOLLOHOSP",
    "Asian_Paints_Ltd": "ASIANPAINT",
    "Axis_Bank_Ltd": "AXISBANK",
    "Bajaj_Auto_Ltd": "BAJAJ-AUTO",
    "Bajaj_Finance_Ltd": "BAJFINANCE",
    "Bajaj_Finserv_Ltd": "BAJAJFINSV",
    "Bharat_Electronics_Ltd": "BEL",
    "Bharti_Airtel_Ltd": "BHARTIARTL",
    "Cipla_Ltd": "CIPLA",
    "Coal_India_Ltd": "COALINDIA",
    "Dr_Reddys_Laboratories_Ltd": "DRREDDY",
    "Eicher_Motors_Ltd": "EICHERMOT",
    "Eternal_Ltd": "ETERNAL",
    "Grasim_Industries_Ltd": "GRASIM",
    "HCL_Technologies_Ltd": "HCLTECH",
    "HDFC_Bank_Ltd": "HDFCBANK",
    "HDFC_Life_Insurance_Company_Ltd": "HDFCLIFE",
    "Hindalco_Industries_Ltd": "HINDALCO",
    "Hindustan_Unilever_Ltd": "HINDUNILVR",
    "ICICI_Bank_Ltd": "ICICIBANK",
    "Interglobe_Aviation_Ltd": "INDIGO",
    "Infosys_Ltd": "INFY",
    "ITC_Ltd": "ITC",
    "Jio_Financial_Services_Ltd": "JIOFIN",
    "JSW_Steel_Ltd": "JSWSTEEL",
    "Kotak_Mahindra_Bank_Ltd": "KOTAKBANK",
    "Larsen_&_Toubro_Ltd": "LT",
    "Mahindra_&_Mahindra_Ltd": "M&M",
    "Maruti_Suzuki_India_Ltd": "MARUTI",
    "Max_Healthcare_Institute_Ltd": "MAXHEALTH",
    "Nestle_India_Ltd": "NESTLEIND",
    "NTPC_Ltd": "NTPC",
    "Oil_&_Natural_Gas_Corpn_Ltd": "ONGC",
    "Power_Grid_Corporation_of_India_Ltd": "POWERGRID",
    "Reliance_Industries_Ltd": "RELIANCE",
    "SBI_Life_Insurance_Company_Ltd": "SBILIFE",
    "State_Bank_of_India": "SBIN",
    "Shriram_Finance_Ltd": "SHRIRAMFIN",
    "Sun_Pharmaceutical_Industries_Ltd": "SUNPHARMA",
    "Tata_Consultancy_Services_Ltd": "TCS",
    "Tata_Consumer_Products_Ltd": "TATACONSUM",
    "Tata_Motors_Ltd": "TATAMOTORS",
    "Tata_Steel_Ltd": "TATA_STEEL",
    "Tech_Mahindra_Ltd": "TECHM",
    "Titan_Company_Ltd": "TITAN",
    "Trent_Ltd": "TRENT",
    "UltraTech_Cement_Ltd": "ULTRACEMCO",
    "Wipro_Ltd": "WIPRO",
}

# Polling configuration
POLL_INTERVAL_SECONDS = 5
MAX_POLL_ATTEMPTS = 120  # 10 minutes maximum


# ==================== Helper Functions ====================

def find_latest_pdf(folder_path: Path) -> Optional[Path]:
    """
    Find the most recent PDF file in the given folder.

    Args:
        folder_path: Path to the folder containing PDF files

    Returns:
        Path to the latest PDF file, or None if no PDFs found
    """
    pdf_files: List[Path] = list(folder_path.glob("*.pdf"))
    
    if not pdf_files:
        return None
    
    # Find the PDF with the latest modification time
    latest_pdf = max(pdf_files, key=lambda p: p.stat().st_mtime)
    return latest_pdf


def submit_report_generation(ticker: str, pdf_path: Path) -> Optional[str]:
    """
    Submit a report generation request to the Flask API.

    Args:
        ticker: Stock ticker symbol
        pdf_path: Path to the transcript PDF file

    Returns:
        Job ID if successful, None otherwise
    """
    url = f"{API_BASE_URL}/generate_report"
    
    try:
        with open(pdf_path, "rb") as pdf_file:
            # API expects "files" (plural) as per app.py: request.files.getlist('files')
            files = {"files": (pdf_path.name, pdf_file, "application/pdf")}
            data = {"ticker": ticker}
            
            print(f"  Submitting {pdf_path.name} to API...")
            response = requests.post(url, data=data, files=files, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            job_id = result.get("job_id")
            
            if job_id:
                print(f"  Job submitted successfully. Job ID: {job_id}")
                return job_id
            else:
                print(f"  Error: No job_id in response")
                return None
                
    except requests.exceptions.RequestException as e:
        print(f"  Error submitting request: {e}")
        return None
    except Exception as e:
        print(f"  Unexpected error: {e}")
        return None


def poll_job_status(job_id: str) -> Optional[Dict]:
    """
    Poll the job status endpoint until the job is completed or fails.

    Args:
        job_id: The job ID to poll

    Returns:
        Job result dictionary if successful, None otherwise
    """
    url = f"{API_BASE_URL}/job_status/{job_id}"
    attempts = 0
    
    while attempts < MAX_POLL_ATTEMPTS:
        try:
            print(f"  Polling job status (attempt {attempts + 1})...")
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            result = response.json()
            status = result.get("status")
            
            if status == "completed":
                print(f"  Job completed successfully!")
                return result.get("result")
            elif status == "failed":
                error = result.get("error", "Unknown error")
                print(f"  Job failed: {error}")
                return None
            elif status in ["queued", "pending", "processing", "started"]:
                print(f"  Job status: {status}. Waiting...")
                time.sleep(POLL_INTERVAL_SECONDS)
                attempts += 1
            else:
                print(f"  Unknown status: {status}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"  Error polling job status: {e}")
            time.sleep(POLL_INTERVAL_SECONDS)
            attempts += 1
        except Exception as e:
            print(f"  Unexpected error: {e}")
            return None
    
    print(f"  Timeout: Job did not complete after {MAX_POLL_ATTEMPTS} attempts")
    return None


def assemble_html_report(result: Dict, ticker: str) -> str:
    """
    Assemble the JSON result into a complete HTML document.
    Matches the frontend's report structure from index.html.

    Args:
        result: Dictionary containing report sections
        ticker: Stock ticker symbol for the report title

    Returns:
        Complete HTML string
    """
    md = MarkdownIt()
    
    # Define the sections matching frontend's structure
    # These match the keys returned by the backend and displayed in index.html
    sections = [
        ("businessModel", "1. Business Model Summary"),
        ("keyQuarterlyUpdates", "2. Key Quarterly Updates"),
        ("managementCommentary", "3. Management Commentary Insights"),
        ("financialProjections", "4. AI-Powered Financial Projections"),
        ("risksUncertainties", "5. Risks & Uncertainties"),
        ("promptSet", "6. AI Prompt Set for Deeper Analysis"),
    ]
    
    html_parts = []
    
    for key, title in sections:
        content = result.get(key, "")
        
        if not content:
            html_parts.append(f'<div id="{key}"><h2>{title}</h2><p>Not available.</p></div>')
            continue
        
        # financialProjections is already HTML, others are Markdown
        if key == "financialProjections":
            html_content = content
        else:
            html_content = md.render(content)
        
        html_parts.append(f'<div id="{key}"><h2>{title}</h2>{html_content}</div>')
    
    # Combine all sections into a complete HTML document
    html_body = "\n\n".join(html_parts)
    
    complete_html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Financial Analysis Report: {ticker}</title>
    <style>
        @page {{
            size: letter;
            margin: 0.5in;
        }}
        
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #1a202c;
            background-color: white;
            margin: 0;
            padding: 20px;
        }}
        
        h1 {{
            font-size: 2rem;
            font-weight: 700;
            color: #1a202c;
            border-bottom: 3px solid #3b82f6;
            padding-bottom: 12px;
            margin-bottom: 24px;
            page-break-after: avoid;
        }}
        
        h2 {{
            font-size: 1.5rem;
            font-weight: 600;
            color: #1a202c;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 8px;
            margin-top: 32px;
            margin-bottom: 16px;
            page-break-after: avoid;
        }}
        
        h3 {{
            font-size: 1.25rem;
            font-weight: 600;
            color: #2d3748;
            margin-top: 20px;
            margin-bottom: 10px;
            page-break-after: avoid;
        }}
        
        h4 {{
            font-size: 1.1rem;
            font-weight: 600;
            color: #4a5568;
            margin-top: 16px;
            margin-bottom: 8px;
            page-break-after: avoid;
        }}
        
        p {{
            margin: 10px 0;
            color: #2d3748;
        }}
        
        ul, ol {{
            margin: 10px 0 16px 20px;
            padding-left: 20px;
        }}
        
        ul {{
            list-style-type: disc;
        }}
        
        ol {{
            list-style-type: decimal;
        }}
        
        li {{
            margin: 6px 0;
            color: #2d3748;
        }}
        
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 20px 0;
            page-break-inside: avoid;
            font-size: 0.9rem;
        }}
        
        th, td {{
            border: 1px solid #cbd5e0;
            padding: 10px;
            text-align: left;
        }}
        
        th {{
            background-color: #edf2f7;
            font-weight: 600;
            color: #2d3748;
        }}
        
        tr:nth-child(even) {{
            background-color: #f7fafc;
        }}
        
        code {{
            background-color: #f3f4f6;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'Courier New', Consolas, Monaco, monospace;
            font-size: 0.9em;
            color: #e53e3e;
        }}
        
        pre {{
            background-color: #f3f4f6;
            padding: 12px;
            border-radius: 6px;
            overflow-x: auto;
            margin: 16px 0;
        }}
        
        pre code {{
            background-color: transparent;
            padding: 0;
            color: #2d3748;
        }}
        
        blockquote {{
            border-left: 4px solid #cbd5e0;
            padding-left: 16px;
            margin: 20px 0;
            color: #4a5568;
            font-style: italic;
        }}
        
        strong {{
            font-weight: 600;
            color: #1a202c;
        }}
        
        em {{
            font-style: italic;
        }}
        
        a {{
            color: #3b82f6;
            text-decoration: none;
        }}
        
        a:hover {{
            text-decoration: underline;
        }}
        
        /* Qualitative analysis styling matching frontend */
        .qualitative-analysis {{
            background-color: #fdfdfd;
            border-left: 4px solid #3b82f6;
            padding: 12px 14px;
            margin-top: 10px;
            font-size: 0.95rem;
            line-height: 1.6;
        }}
        
        .qualitative-analysis ul {{
            list-style: disc;
            padding-left: 20px;
            margin: 4px 0 8px 0;
        }}
        
        .qualitative-analysis ol {{
            list-style: decimal;
            padding-left: 20px;
            margin: 4px 0 8px 0;
        }}
        
        .qualitative-analysis li {{
            margin: 2px 0;
        }}
        
        .qualitative-analysis p {{
            margin: 4px 0;
        }}
        
        /* Disclaimer styling */
        .disclaimer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #e2e8f0;
            font-size: 0.75rem;
            color: #718096;
            text-align: center;
        }}
        
        /* Page break control */
        .page-break {{
            page-break-before: always;
        }}
        
        div[id] {{
            page-break-inside: avoid;
        }}
    </style>
</head>
<body>
    <h1>Financial Analysis Report: {ticker.upper()}</h1>
    
    {html_body}
    
    <div class="disclaimer">
        <p><strong>Disclaimer:</strong> This report was generated using AI models based on publicly available data. 
        It is intended for informational purposes only and is not investment advice. 
        Please verify any forward-looking statements with official company filings.</p>
    </div>
</body>
</html>
"""
    
    return complete_html


def convert_html_to_pdf(html_content: str, output_path: Path) -> bool:
    """
    Convert HTML content to a PDF file using WeasyPrint.
    Uses optimized settings for better rendering of complex HTML/CSS.

    Args:
        html_content: Complete HTML string
        output_path: Path where the PDF should be saved

    Returns:
        True if successful, False otherwise
    """
    try:
        print(f"  Converting HTML to PDF...")
        
        # Create HTML object with the content
        html_doc = HTML(string=html_content)
        
        # Write PDF with optimized settings
        html_doc.write_pdf(
            output_path,
            stylesheets=None,  # Use only embedded styles
            presentational_hints=True,  # Respect HTML styling attributes
            optimize_images=True,  # Optimize image sizes
        )
        
        print(f"  PDF saved successfully: {output_path}")
        return True
    except Exception as e:
        print(f"  Error converting to PDF: {e}")
        import traceback
        print(f"  Traceback: {traceback.format_exc()}")
        return False


def process_ticker(folder_name: str, ticker: str) -> bool:
    """
    Process a single ticker: find PDF, submit to API, poll for result, generate PDF.

    Args:
        folder_name: Name of the folder containing transcripts
        ticker: Stock ticker symbol

    Returns:
        True if processing was successful, False otherwise
    """
    print(f"\nProcessing {ticker}...")
    
    # Check if folder exists
    transcript_folder_path = SOURCE_DIR / folder_name
    if not transcript_folder_path.exists():
        print(f"  Warning: Folder not found: {transcript_folder_path}")
        return False
    
    # Find latest PDF
    latest_pdf = find_latest_pdf(transcript_folder_path)
    if latest_pdf is None:
        print(f"  Warning: No PDF files found in {transcript_folder_path}")
        return False
    
    print(f"  Found latest PDF: {latest_pdf.name}")
    
    # Submit report generation request
    job_id = submit_report_generation(ticker, latest_pdf)
    if job_id is None:
        print(f"  Failed to submit report generation for {ticker}")
        return False
    
    # Poll for job completion
    result = poll_job_status(job_id)
    if result is None:
        print(f"  Failed to retrieve completed report for {ticker}")
        return False
    
    # Assemble HTML report
    print(f"  Assembling HTML report...")
    html_content = assemble_html_report(result, ticker)
    
    # Convert to PDF
    output_pdf_path = TARGET_DIR / f"{ticker}.pdf"
    success = convert_html_to_pdf(html_content, output_pdf_path)
    
    if success:
        print(f"  ✓ Successfully processed {ticker}")
    else:
        print(f"  ✗ Failed to save PDF for {ticker}")
    
    return success


# ==================== Main Function ====================

def main() -> None:
    """
    Main entry point for the batch processor.
    Iterates through all tickers and processes them.
    """
    print("=" * 60)
    print("Giga-Finanalytix Batch Processor")
    print("=" * 60)
    print(f"Source Directory: {SOURCE_DIR}")
    print(f"Target Directory: {TARGET_DIR}")
    print(f"API Base URL: {API_BASE_URL}")
    print(f"Total Companies: {len(FOLDER_TO_TICKER_MAP)}")
    print("=" * 60)
    
    # Ensure target directory exists
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\nTarget directory ready: {TARGET_DIR}")
    
    # Process each ticker
    successful = 0
    failed = 0
    
    for folder_name, ticker in FOLDER_TO_TICKER_MAP.items():
        success = process_ticker(folder_name, ticker)
        
        if success:
            successful += 1
        else:
            failed += 1
    
    # Print summary
    print("\n" + "=" * 60)
    print("Batch Processing Complete")
    print("=" * 60)
    print(f"Total: {len(FOLDER_TO_TICKER_MAP)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print("=" * 60)


if __name__ == "__main__":
    main()
