from langchain_core.tools import tool

@tool
def web_search(query: str) -> str:
    """
    Simulates a Web Search tool (e.g. Tavily/Serper).
    Used to gather open-web information on macro factors, company news, and consumer trends.
    """
    # TODO: Implement actual web search (e.g. using Tavily or Google Search API)
    return f"Simulated web search results for query: '{query}'"

@tool
def news_search_alpha_vantage(tickers: str, topics: str = None) -> str:
    """
    Search for latest news and sentiment for given tickers using AlphaVantage API.
    
    Args:
        tickers: String of comma-separated tickers to search for (e.g. 'AAPL,MSFT').
        topics: Optional financial topics (e.g. 'technology,manufacturing').
    """
    # TODO: Implement AlphaVantage News & Sentiment API
    return f"Simulated AlphaVantage news highlights for {tickers} related to {topics or 'all topics'}."
