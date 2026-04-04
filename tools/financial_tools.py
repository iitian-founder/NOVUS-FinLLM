import json
from langchain_core.tools import tool
from typing import Annotated
from provess_client.make_request import get_company_id, get_report
from provess_client.clean_json import clean_single_report

@tool
def get_financial_report(company_name: str, report_name: str) -> str:
    """
    Get financial data reports for a given company.
    
    Args:
        company_name: The name of the company (e.g. 'Reliance Industries Ltd.')
        report_name: The internal name of the report to fetch. 
                     Common reports include: 
                     - 'income_expenditure_summary'
                     - 'Balance_Sheet_Summary'
                     - 'cash_flow'
                     - 'cash_flow_indirect_method'
                     - 'financial_ratios'
                     - 'equity_ownership'
    """
    try:
        # Get the internal Prowess company ID
        company_id = get_company_id(company_name)
    except Exception as e:
        return f"Error: Could not resolve company ID for '{company_name}'. Additional info: {e}"
        
    try:
        # Fetch the raw JSON from Prowess API
        raw_json_str = get_report(company_id, report_name)
        payload = json.loads(raw_json_str)
    except Exception as e:
        return f"Error: Failed to fetch report {report_name} for company {company_name}. Information: {e}"
        
    # Clean the payload into a readable PSV format for the LLM
    clean_psv = clean_single_report(company_name, report_name, payload)
    
    if clean_psv is None:
         return f"Error: The report {report_name} returned no usable data or had an error for {company_name}."
         
    return f"Data for {company_name} - {report_name}:\n\n{clean_psv}"
