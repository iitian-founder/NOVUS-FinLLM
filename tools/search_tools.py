import os
import json
import requests
from langchain_core.tools import tool

# ---------------------------------------------------------------------------
# 1. Tavily Broad Search
# ---------------------------------------------------------------------------

@tool
def tavily_broad_search(query: str, limit: int = 5) -> str:
    """
    Use Tavily to perform a broad web search.
    Use this FIRST to identify relevant sources, macro trends, and recent news articles.
    Returns snippets and the source URLs.

    Args:
        query: The search query.
        limit: Number of results to return (max 10).
    """
    try:
        from tavily import TavilyClient
    except ImportError:
        return "Error: tavily-python is not installed. Run: pip install tavily-python"

    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return "Error: TAVILY_API_KEY environment variable not set."

    client = TavilyClient(api_key=api_key)

    response = client.search(
        query=query,
        search_depth="advanced",
        topic="general",
        max_results=limit,
        include_answer=True,
    )

    results = response.get("results", [])
    answer = response.get("answer", "")

    parts = [f"Tavily search results for: '{query}'\n"]

    if answer:
        parts.append(f"**Summary:** {answer}\n")

    if not results:
        parts.append("No results found.")
        return "\n".join(parts)

    for i, item in enumerate(results, 1):
        title = item.get("title", "No title")
        url = item.get("url", "")
        content = item.get("content", "").strip()
        score = item.get("score", 0)
        parts.append(
            f"{i}. **{title}**\n"
            f"   URL: {url}\n"
            f"   Relevance: {score:.2f}\n"
            f"   {content[:400]}{'...' if len(content) > 400 else ''}"
        )

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# 2. Firecrawl: Scrape a single URL
# ---------------------------------------------------------------------------

@tool
def firecrawl_scrape_url(url: str) -> str:
    """
    Use Firecrawl to deeply scrape and extract full markdown content from a specific URL.
    Use this SECOND, passing in URLs discovered by tavily_broad_search to verify exact numbers and cite the source.

    Args:
        url: The specific web page URL to scrape.
    """
    from firecrawl import FirecrawlApp
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        return "Error: FIRECRAWL_API_KEY environment variable not set."
    client = FirecrawlApp(api_key=api_key)
    result = client.scrape_url(url, formats=["markdown"])
    markdown = result.get("markdown") or ""
    meta = result.get("metadata", {})
    source = meta.get("sourceURL") or meta.get("url") or url
    title = meta.get("title", "")
    header = f"# {title}\nSource: {source}\n\n" if title else f"Source: {source}\n\n"
    return header + markdown


# ---------------------------------------------------------------------------
# 3. Firecrawl Web Search
# ---------------------------------------------------------------------------

@tool
def firecrawl_web_search(query: str, limit: int = 5) -> str:
    """
    Use Firecrawl to search the web and retrieve full page content from results.
    Returns structured search results with titles, URLs, descriptions, and scraped content.

    Args:
        query: The search query (supports operators like site:, intitle:, \"exact phrase\").
        limit: Maximum number of results to return (default 5).
    """
    from firecrawl import FirecrawlApp
    api_key = os.environ.get("FIRECRAWL_API_KEY")
    if not api_key:
        return "Error: FIRECRAWL_API_KEY environment variable not set."
    client = FirecrawlApp(api_key=api_key)
    response = client.search(query, limit=limit)
    # Handle both dict and object responses
    if isinstance(response, dict):
        web_results = response.get("data") or response.get("results") or []
    else:
        web_results = getattr(response, "data", None) or getattr(response, "results", [])

    if not web_results:
        return f"No results found for query: '{query}'"

    output_parts = [f"Firecrawl search results for: '{query}'\n"]
    for i, item in enumerate(web_results, 1):
        if isinstance(item, dict):
            title = item.get("title", "No title")
            url = item.get("url", "")
            description = item.get("description", "")
        else:
            title = getattr(item, "title", "No title") or "No title"
            url = getattr(item, "url", "")
            description = getattr(item, "description", "") or ""
        output_parts.append(
            f"{i}. **{title}**\n"
            f"   URL: {url}\n"
            f"   {description}"
        )
    return "\n".join(output_parts)


# ---------------------------------------------------------------------------
# 4. AlphaVantage News & Sentiment
# ---------------------------------------------------------------------------

@tool
def news_search_alpha_vantage(tickers: str, topics: str = None) -> str:
    """
    Search for latest news and sentiment for given tickers using AlphaVantage API.

    Args:
        tickers: String of comma-separated tickers to search for (e.g. 'AAPL,MSFT').
        topics: Optional financial topics (e.g. 'technology,manufacturing,earnings').
    """
    api_key = os.environ.get("ALPHAVANTAGE_API_KEY")
    if not api_key:
        return "Error: ALPHAVANTAGE_API_KEY environment variable not set."

    base_url = "https://www.alphavantage.co/query"
    params = {
        "function": "NEWS_SENTIMENT",
        "tickers": tickers,
        "sort": "LATEST",
        "limit": 10,
        "apikey": api_key,
    }
    if topics:
        params["topics"] = topics

    try:
        resp = requests.get(base_url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.Timeout:
        return "Error: AlphaVantage API request timed out."
    except requests.exceptions.RequestException as e:
        return f"Error: AlphaVantage API request failed: {e}"

    # Handle API-level errors
    if "Information" in data:
        return f"AlphaVantage API Info: {data['Information']}"
    if "Note" in data:
        return f"AlphaVantage Rate Limit: {data['Note']}"
    if "Error Message" in data:
        return f"AlphaVantage Error: {data['Error Message']}"

    feed = data.get("feed", [])
    sentiment_score_avg = data.get("sentiment_score_definition", "")

    if not feed:
        return f"No news found for tickers: '{tickers}'" + (f" topics: '{topics}'" if topics else "")

    parts = [f"AlphaVantage News & Sentiment for: {tickers}" + (f" | Topics: {topics}" if topics else "") + "\n"]

    for article in feed[:8]:  # Cap at 8 for readability
        title = article.get("title", "No title")
        source = article.get("source", "")
        url = article.get("url", "")
        time_pub = article.get("time_published", "")
        overall_sentiment = article.get("overall_sentiment_label", "N/A")
        overall_score = article.get("overall_sentiment_score", "N/A")
        summary = article.get("summary", "").strip()

        # Per-ticker sentiment
        ticker_sentiments = article.get("ticker_sentiment", [])
        ticker_info = []
        for t in ticker_sentiments:
            if t.get("ticker") in tickers.split(","):
                label = t.get("ticker_sentiment_label", "N/A")
                score = t.get("ticker_sentiment_score", "N/A")
                ticker_info.append(f"{t['ticker']}: {label} ({score})")

        parts.append(
            f"**{title}**\n"
            f"   Source: {source} | Published: {time_pub}\n"
            f"   Overall Sentiment: {overall_sentiment} (score: {overall_score})\n"
            + (f"   Ticker Sentiment: {', '.join(ticker_info)}\n" if ticker_info else "")
            + f"   Summary: {summary[:300]}{'...' if len(summary) > 300 else ''}\n"
            f"   URL: {url}"
        )

    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# 5. X (Twitter) Social Search  — via tweepy v2
# ---------------------------------------------------------------------------

@tool
def x_social_search(query: str, limit: int = 10) -> str:
    """
    Search for recent tweets and sentiment on X (formerly Twitter) for a given topic or ticker.
    Requires X_BEARER_TOKEN environment variable (from developer.x.com).

    Args:
        query: The search query (e.g. '$AAPL' or 'Apple product launch').
                 Retweets are automatically excluded.
        limit: The maximum number of tweets to retrieve (10-100).
    """
    try:
        import tweepy
    except ImportError:
        return "Error: tweepy is not installed. Run: pip install tweepy"

    bearer_token = os.environ.get("X_BEARER_TOKEN")
    if not bearer_token:
        return "Error: X_BEARER_TOKEN environment variable not set."

    # Clamp limit to tweepy's allowed range [10, 100]
    max_results = max(10, min(int(limit), 100))

    # Append -is:retweet to exclude retweets for cleaner signal
    clean_query = query.strip()
    if "-is:retweet" not in clean_query:
        clean_query += " -is:retweet"

    client = tweepy.Client(bearer_token=bearer_token, wait_on_rate_limit=True)

    try:
        response = client.search_recent_tweets(
            query=clean_query,
            max_results=max_results,
            tweet_fields=["created_at", "author_id", "public_metrics", "lang"],
        )
    except tweepy.TweepyException as e:
        return f"Error: X API request failed: {e}"

    tweets = response.data
    if not tweets:
        return f"No recent tweets found for query: '{query}'"

    parts = [f"X (Twitter) search results for: '{query}' — {len(tweets)} tweets\n"]

    for i, tweet in enumerate(tweets, 1):
        metrics = tweet.public_metrics or {}
        likes = metrics.get("like_count", 0)
        retweets = metrics.get("retweet_count", 0)
        replies = metrics.get("reply_count", 0)
        created = str(tweet.created_at)[:16] if tweet.created_at else "N/A"
        text = tweet.text.replace("\n", " ")

        parts.append(
            f"{i}. [{created}] {text}\n"
            f"   👍 {likes} likes | 🔁 {retweets} retweets | 💬 {replies} replies"
        )

    return "\n\n".join(parts)
