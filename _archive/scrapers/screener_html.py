# scrapers/screener_html.py — Screener.in HTML scraping & table extraction
"""
Scrapes and parses financial statement tables from Screener.in.
Provides P&L and Balance Sheet HTML tables, plus structured data extraction.
"""

import requests
from bs4 import BeautifulSoup


def _parse_statements_from_soup(soup: BeautifulSoup) -> tuple[str | None, str | None]:
    """Helper function to extract tables from a BeautifulSoup object."""
    # Find the Profit & Loss table
    profit_loss_section = soup.find('section', id='profit-loss')
    profit_loss_html = None
    if profit_loss_section:
        profit_loss_table = profit_loss_section.find('table', class_='data-table')
        if profit_loss_table:
            profit_loss_html = str(profit_loss_table)

    # Find the Balance Sheet table
    balance_sheet_section = soup.find('section', id='balance-sheet')
    balance_sheet_html = None
    if balance_sheet_section:
        balance_sheet_table = balance_sheet_section.find('table', class_='data-table')
        if balance_sheet_table:
            balance_sheet_html = str(balance_sheet_table)

    if not profit_loss_html:
        print("Warning: Profit & Loss section/table not found on the page.")
    if not balance_sheet_html:
        print("Warning: Balance Sheet section/table not found on the page.")

    return profit_loss_html, balance_sheet_html


def get_yearly_financial_statements_html(ticker: str) -> tuple[str | None, str | None]:
    """
    Fetches and extracts yearly financial statements for a given ticker.
    It automatically tries both consolidated and standalone URLs and validates
    that the found tables actually contain data.
    """
    urls_to_try = [
        f"https://www.screener.in/company/{ticker}/consolidated/",
        f"https://www.screener.in/company/{ticker}/"
    ]

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    for url in urls_to_try:
        try:
            print(f"Attempting to fetch data from: {url}")
            response = requests.get(url, headers=headers)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')
            pl_html, bs_html = _parse_statements_from_soup(soup)

            if pl_html and bs_html:
                pl_data = extract_financial_data_from_html(pl_html)

                if pl_data and pl_data.keys():
                    print("✅ Successfully found valid financial statements.")
                    return pl_html, bs_html
                else:
                    print("⚠️ Found tables, but they contain no data. Trying next URL...")
            else:
                print("Could not find the required tables, trying next URL...")

        except requests.exceptions.RequestException as e:
            print(f"❌ A network error occurred for {url}: {e}. Trying next URL...")
            continue

    print(f"Error: Failed to retrieve valid data for {ticker} from all attempted sources.")
    return None, None


def extract_financial_data_from_html(html: str) -> dict[str, dict[str, float]]:
    """
    Parses the HTML of a financial statement table and extracts the data.
    Returns a dict keyed by year label, each containing metric -> value mappings.
    """
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table', class_='data-table')

    if not table:
        print("Error: No data table found in the provided HTML.")
        return {}

    # Extract headers (years)
    headers = table.find('thead').find_all('th')[1:]
    years = [header.get_text(strip=True) for header in headers]

    data = {year: {} for year in years}

    # Extract rows
    rows = table.find('tbody').find_all('tr')
    for row in rows:
        cols = row.find_all('td')
        if not cols or len(cols) < 2:
            continue

        item_name = cols[0].get_text(strip=True).replace('.', '')
        if not item_name:
            continue

        for i, col in enumerate(cols[1:]):
            if i < len(years):
                year = years[i]
                value_str = col.get_text(strip=True).replace(',', '').replace('₹', '')
                try:
                    value = float(value_str) if value_str not in ('-', '') else 0.0
                except ValueError:
                    value = 0.0
                data[year][item_name] = value

    return data
