import sys
from pathlib import Path

# Provide access to root modules
base_dir = Path(__file__).resolve().parent.parent
if str(base_dir) not in sys.path:
    sys.path.append(str(base_dir))

# Import Universal Tools
from tools.financial_tools import get_financial_report
from tools.search_tools import tavily_broad_search, firecrawl_scrape_url, firecrawl_web_search, news_search_alpha_vantage, x_social_search
from tools.rag_tools import search_company_documents
from tools.math_tools import calculate_cagr, project_future_value, calculate_margin

# Grouping tools by use-case so specific nodes can bind only what they need
ORCHESTRATOR_TOOLS = [
    get_financial_report, 
    search_company_documents
]

RESEARCHER_TOOLS = [
    tavily_broad_search,
    firecrawl_scrape_url,
    firecrawl_web_search,
    news_search_alpha_vantage,
    x_social_search
]

SYNTHESIZER_TOOLS = [
    calculate_cagr,
    project_future_value,
    calculate_margin
]
