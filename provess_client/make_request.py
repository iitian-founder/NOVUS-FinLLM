import os
from functools import lru_cache
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

_DATA_FILE = Path(__file__).resolve().parent / "cpy_cin_code.dt 2"


@lru_cache(maxsize=1)
def _company_name_to_co_code() -> dict[str, int]:
    mapping: dict[str, int] = {}
    with _DATA_FILE.open(encoding="utf-8", errors="replace") as f:
        next(f, None)  # skip header
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.rsplit("|", 2)
            if len(parts) != 3:
                continue
            name, co_code_str, _cin = parts
            key = name.strip().casefold()
            if key not in mapping:
                mapping[key] = int(co_code_str)
    return mapping


def get_report(company_id,report_name): # company_id is the id of the company in the registry (company_code in the registry.py file)                   
    url= 'https://prowess.cmie.com/api/getreport'
    json_batchfile= 'equity_ownership.json'
    mydata= { 'apikey': os.getenv('PROWESS_API_KEY'), 'company': company_id, 'format': 'json' }
    batch_file_path = Path(__file__).resolve().parent / "batch_files" / f"{report_name}.json"
    myfile= { 'batchfile': batch_file_path.open('rb') }
    response= requests.post(url, data = mydata, files = myfile)
    return response.text


def get_company_id(company_name: str) -> int:
    """Resolve Prowess `co_code` from the local `cpy_cin_code.dt 2` dump (case-insensitive name match)."""
    key = company_name.strip().casefold()
    if not key:
        raise ValueError("company_name must be non-empty")
    table = _company_name_to_co_code()
    try:
        return table[key]
    except KeyError as e:
        raise ValueError(f"Unknown company name: {company_name!r}") from e

if __name__ == "__main__":
   # print(get_report(get_company_id('Reliance Industries Ltd.'),'income_expenditure_summary'))
    print(get_report(get_company_id('Tata Steel Ltd.'),'income_expenditure_summary'))