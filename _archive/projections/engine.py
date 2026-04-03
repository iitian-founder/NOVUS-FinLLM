# projections/engine.py — Financial projection engine for Novus FinLLM
"""
DCF projections, PE estimation, stock price modeling, and market cap classification.
Contains all financial calculation logic extracted from the original logic.py.
"""

import re as _re
import json as _json
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import date, datetime, timedelta

from scrapers.screener_html import extract_financial_data_from_html


def calculate_financial_projections(
    assumptions,
    financial_data,
    qualitative_text,
    compact_financials=None,
    march31_prices: dict[int, float] | None = None,
    ticker: str | None = None,
    latest_price: float | None = None,
    sector_median_pe: float | None = None
):
    """
    Calculates future financial projections and interleaves them with qualitative analysis,
    returning a single HTML string.
    """
    print("Calculating financial projections and combining with analysis...")

    # Helper: basic Markdown-ish to HTML converter
    def _mdish_to_html(block: str) -> str:
        text = (block or "").strip()
        if not text:
            return ""
        lines = text.splitlines()
        html_parts = []
        in_ul = False
        in_ol = False
        bullet_re = _re.compile(r"^\s*[\-\*\+\u2022\u2013\u2014]\s+(.*)$")
        num_re = _re.compile(r"^\s*(\d+)[\.)\]]\s+(.*)$")

        def close_lists():
            nonlocal in_ul, in_ol
            if in_ul:
                html_parts.append("</ul>")
                in_ul = False
            if in_ol:
                html_parts.append("</ol>")
                in_ol = False

        for raw in lines:
            if not raw.strip():
                close_lists()
                continue
            m_b = bullet_re.match(raw)
            m_n = num_re.match(raw)
            if m_b:
                if not in_ul:
                    close_lists()
                    html_parts.append("<ul>")
                    in_ul = True
                content = m_b.group(1)
                content = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content)
                content = _re.sub(r"`([^`]+)`", r"<code>\1</code>", content)
                html_parts.append(f"<li>{content}</li>")
                continue
            if m_n:
                if not in_ol:
                    close_lists()
                    html_parts.append("<ol>")
                    in_ol = True
                content = m_n.group(2)
                content = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content)
                content = _re.sub(r"`([^`]+)`", r"<code>\1</code>", content)
                html_parts.append(f"<li>{content}</li>")
                continue
            close_lists()
            content = raw.strip()
            content = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", content)
            content = _re.sub(r"`([^`]+)`", r"<code>\1</code>", content)
            html_parts.append(f"<p>{content}</p>")

        close_lists()
        return "".join(html_parts)

    # Helper: parse qualitative assumptions text into per-case sections
    def parse_qualitative_assumptions_sections(full_text: str) -> dict:
        if not full_text:
            return {}

        def strip_all_fences(txt: str) -> str:
            t = txt.strip()
            t = _re.sub(r"^```[a-zA-Z0-9]*\s*\n", "", t)
            t = _re.sub(r"\n```\s*$", "", t)
            t = t.replace("```", "")
            return t

        text = strip_all_fences(full_text.replace("\r\n", "\n").replace("\r", "\n"))

        # Preferred path: split using explicit NEWSECTION cues
        cue_pattern = _re.compile(r"^\s*##NEWSECTION\{(base_case|bull_case|bear_case)\}##\s*$", _re.IGNORECASE | _re.MULTILINE)
        segments = []
        last = 0
        for m in cue_pattern.finditer(text):
            if m.start() > last:
                segments.append((None, text[last:m.start()]))
            segments.append((m.group(1).lower(), ""))
            last = m.end()
        if last < len(text):
            segments.append((None, text[last:]))

        if segments:
            acc = {"base_case": [], "bull_case": [], "bear_case": []}
            current = None
            for label, content in segments:
                if label in acc:
                    current = label
                    continue
                if current:
                    acc[current].append(content)
            by_case = {"base_case": None, "bull_case": None, "bear_case": None}
            for k, chunks in acc.items():
                block = strip_all_fences("".join(chunks).strip())
                if block:
                    html_block = _mdish_to_html(block)
                    by_case[k] = f'<div class="qualitative-analysis"><h3 class="text-gray-800 font-semibold mb-2">Assumptions & Rationale</h3>{html_block}</div>'
            if any(by_case.values()):
                return by_case

        lines = text.split("\n")
        heading_idx = []
        heading_re = _re.compile(r"^\s{0,3}#{2,6}\s+(.+)$")
        for i, ln in enumerate(lines):
            if heading_re.match(ln):
                heading_idx.append((i, ln.strip()))

        case_map = {"base_case": None, "bull_case": None, "bear_case": None}

        def is_case_heading(line: str, case_word: str) -> bool:
            lw = line.lower().replace("–", "-")
            return (case_word in lw) and ("case" in lw)

        case_starts = {}
        for idx, ln in heading_idx:
            if is_case_heading(ln, "base") and case_starts.get("base_case") is None:
                case_starts["base_case"] = idx
            if is_case_heading(ln, "bull") and case_starts.get("bull_case") is None:
                case_starts["bull_case"] = idx
            if is_case_heading(ln, "bear") and case_starts.get("bear_case") is None:
                case_starts["bear_case"] = idx

        plain_positions = []
        if not case_starts.get("base_case") or not case_starts.get("bull_case") or not case_starts.get("bear_case"):
            plain_heading_re = _re.compile(r"^(?:\s*(?:#{1,6}\s*)?)?(?:\*\*|__|`)?\\s*(?:the\s+)?(base|bull|bear)[\s\-–]?case(?:\s+assumptions?)?\\s*:?\s*(?:\*\*|__|`)?\\s*$", _re.IGNORECASE)
            for i, ln in enumerate(lines):
                s = (ln or "").strip()
                m = plain_heading_re.match(s)
                if m:
                    word = m.group(1).lower()
                    key = f"{word}_case"
                    if not case_starts.get(key):
                        case_starts[key] = i
                    plain_positions.append(i)

        heading_positions = sorted(set([i for i, _ in heading_idx] + plain_positions))

        def next_heading_after(i_start: int) -> int:
            for pos in heading_positions:
                if pos > i_start:
                    return pos
            return len(lines)

        def _strip_fences(block: str) -> str:
            b = block.strip()
            fence_re = _re.compile(r"^```[a-zA-Z0-9]*\s*\n([\s\S]*?)\n```\s*$")
            m = fence_re.match(b)
            if m:
                return m.group(1).strip()
            b = _re.sub(r"^```[a-zA-Z0-9]*\s*\n", "", b)
            b = _re.sub(r"\n```\s*$", "", b)
            return b

        for key, start in case_starts.items():
            if start is None:
                continue
            end = next_heading_after(start)
            block = "\n".join(lines[start + 1:end]).strip()
            block = _strip_fences(block)
            html_block = _mdish_to_html(block)
            case_map[key] = f'<div class="qualitative-analysis"><h3 class="text-gray-800 font-semibold mb-2">Assumptions & Rationale</h3>{html_block}</div>'

        if all(v is None for v in case_map.values()):
            for ck, human in [("base_case", "Base Case"), ("bull_case", "Bull Case"), ("bear_case", "Bear Case")]:
                pattern = _re.compile(rf"^\s*#{2,6}\s*{_re.escape(human)}[^\n]*?(?:Assumptions)?\s*$([\s\S]*?)(?=^\s*#{1,6}\s|\Z)", _re.IGNORECASE | _re.MULTILINE)
                m = pattern.search(text)
                if m:
                    html_block = _mdish_to_html(_strip_fences(m.group(1).strip()))
                    case_map[ck] = f'<div class="qualitative-analysis"><h3 class="text-gray-800 font-semibold mb-2">Assumptions & Rationale</h3>{html_block}</div>'
        return case_map

    # --- Calculation helpers ---
    def calculate_revenue_growth(revenue, growth_rate, years):
        growth_rate_decimal = growth_rate / 100
        projections = []
        for year in range(1, years + 1):
            projected_revenue = revenue * ((1 + growth_rate_decimal) ** year)
            projections.append(round(projected_revenue))
        return projections

    def calculate_ebitda(revenues, ebitda_margin):
        return [round(revenue * (ebitda_margin / 100)) for revenue in revenues]

    def calculate_pbt(ebitda_values, interest, depreciation):
        return [round(ebitda - interest - depreciation) for ebitda in ebitda_values]

    def calculate_pat(pbt_values, tax_rate):
        return [round(pbt * (1 - tax_rate / 100)) for pbt in pbt_values]

    def calculate_number_of_shares(pat_year0, eps_year0):
        if eps_year0 == 0:
            return 0
        return round(pat_year0 / eps_year0)

    def calculate_eps(pat_values, number_of_shares):
        eps_values = []
        for pat in pat_values:
            if number_of_shares == 0:
                eps = 0
            else:
                eps = pat / number_of_shares
            eps_values.append(round(eps, 2))
        return eps_values

    # --- Main Logic ---
    year0_ebitda = financial_data['Operating Profit'] + financial_data['Depreciation']
    num_shares = calculate_number_of_shares(financial_data['Net Profit+'], financial_data['EPS in Rs'])

    # Resolve latest price
    resolved_latest_price = None
    if latest_price is not None and np.isfinite(latest_price):
        resolved_latest_price = float(latest_price)
    elif march31_prices:
        try:
            latest_year = max(k for k, v in march31_prices.items() if v is not None)
            resolved_latest_price = float(march31_prices[latest_year]) if latest_year else None
        except Exception:
            resolved_latest_price = None
    elif ticker:
        try:
            resolved_latest_price = float(get_price_on_date(ticker, date.today().isoformat()))
        except Exception:
            resolved_latest_price = None

    # Determine company size for PE sensitivity
    try:
        comp_size = classify_market_cap_category(resolved_latest_price, num_shares) if resolved_latest_price else "midcap"
    except Exception:
        comp_size = "midcap"

    # Initialize HTML
    html_output = """
    <style>
        body { font-family: sans-serif; }
        .container { display: flex; flex-direction: column; gap: 30px; }
        .projection-table { border-collapse: collapse; width: 100%; box-shadow: 0 2px 5px rgba(0,0,0,0.1); margin-bottom: 15px; }
        .projection-table th, .projection-table td { border: 1px solid #ddd; padding: 10px; text-align: left; }
        .projection-table th { background-color: #f2f2f2; font-weight: bold; }
        .projection-table td:first-child { font-weight: bold; }
        .projection-table tr:nth-child(even) { background-color: #f9f9f9; }
        h2 { color: #333; border-bottom: 2px solid #f2f2f2; padding-bottom: 5px; }
        .qualitative-analysis { background-color: #fdfdfd; border-left: 4px solid #007bff; padding: 15px; margin-top: 10px; font-size: 0.9em; line-height: 1.6; }
    </style>
    <div class="container">
    """

    sections_by_case = parse_qualitative_assumptions_sections(qualitative_text)

    for case_name, case_assumptions in assumptions.items():
        title = case_name.replace('_', ' ').title()
        display_title = title if 'case' in title.lower() else f"{title} Case"

        growth_rate = case_assumptions['revenue_growth_cagr']
        ebitda_margin = case_assumptions['ebitda_margin']
        tax_rate = case_assumptions['tax_rate']

        revenues_proj = calculate_revenue_growth(financial_data['Sales+'], growth_rate, 3)
        ebitdas_proj = calculate_ebitda(revenues_proj, ebitda_margin)
        pbts_proj = calculate_pbt(ebitdas_proj, financial_data['Interest'], financial_data['Depreciation'])
        pats_proj = calculate_pat(pbts_proj, tax_rate)
        eps_proj = calculate_eps(pats_proj, num_shares)

        # EPS CAGR
        try:
            eps0 = float(financial_data['EPS in Rs'])
            eps_last = float(eps_proj[-1]) if eps_proj else eps0
            if eps0 > 0 and eps_last > 0:
                eps_cagr = ((eps_last / eps0) ** (1 / 3) - 1) * 100.0
            else:
                eps_cagr = 0.0
        except Exception:
            eps_cagr = 0.0

        # Past PE list
        past_pe_list = None
        if compact_financials is not None and march31_prices is not None:
            try:
                past_pe_list = build_past_pe_list_from_compact(compact_financials, march31_prices)
            except Exception:
                past_pe_list = None
        if not past_pe_list:
            this_year = date.today().year
            past_pe_list = [{"year": this_year - 3, "pe": 20.0, "eps": None},
                            {"year": this_year - 2, "pe": 20.0, "eps": None},
                            {"year": this_year - 1, "pe": 20.0, "eps": None}]

        try:
            projected_pe = estimate_future_pe(past_pe_list, eps_cagr, sector_median_pe=sector_median_pe, company_size=comp_size)
            if not np.isfinite(projected_pe) or projected_pe <= 0:
                projected_pe = 20.0
        except Exception:
            projected_pe = 20.0

        projected_prices = [round(float(e) * float(projected_pe), 2) if e is not None else None for e in eps_proj]

        year0_price = None
        try:
            if march31_prices:
                yr0 = max(march31_prices.keys()) if march31_prices else None
                v = march31_prices.get(yr0) if yr0 else None
                year0_price = float(v) if v is not None else None
        except Exception:
            year0_price = None
        if year0_price is None:
            year0_price = resolved_latest_price

        data_rows = {
            "Revenue": [financial_data['Sales+']] + revenues_proj,
            "EBITDA": [year0_ebitda] + ebitdas_proj,
            "PBT": [financial_data['Profit before tax']] + pbts_proj,
            "PAT": [financial_data['Net Profit+']] + pats_proj,
            "EPS": [financial_data['EPS in Rs']] + eps_proj,
            "Stock Price": [year0_price] + projected_prices
        }

        html_output += f"<div><h2>{display_title}</h2>"
        html_output += '<table class="projection-table">'
        html_output += "<tr><th>Metric</th><th>Year 0 (Actual)</th><th>Year 1 (Proj)</th><th>Year 2 (Proj)</th><th>Year 3 (Proj)</th></tr>"

        for metric, values in data_rows.items():
            def _fmt(v):
                if v is None:
                    return "-"
                try:
                    if isinstance(v, (int, np.integer)):
                        return f"{int(v):,}"
                    else:
                        return f"{float(v):,.2f}"
                except Exception:
                    return str(v)
            formatted_values = [_fmt(v) for v in values]
            html_output += f"<tr><td>{metric}</td><td>{formatted_values[0]}</td><td>{formatted_values[1]}</td><td>{formatted_values[2]}</td><td>{formatted_values[3]}</td></tr>"

        html_output += "</table>"

        qualitative_section_html = sections_by_case.get(case_name)
        if not qualitative_section_html:
            qualitative_section_html = "<div class='qualitative-analysis'><p style='color:#a00;'>Could not find the qualitative assumptions for this case.</p></div>"
        html_output += qualitative_section_html

        html_output += "</div>"

    html_output += "</div>"
    return html_output


def estimate_future_pe(
    past_pe_list,
    future_eps_cagr,
    sector_median_pe=None,
    company_size="midcap"
):
    """
    Estimate future P/E ratio combining:
    - Base P/E from historical median
    - Adjustment by delta between projected EPS CAGR and trailing 3Y EPS CAGR

    Returns: float projected P/E, rounded to 2 decimals.
    """

    def _extract_series(past_list):
        pe_vals = []
        eps_vals = []
        years = []

        def _append(year, pe, eps):
            years.append(year)
            pe_vals.append(pe)
            eps_vals.append(eps)

        for item in (past_list or []):
            if isinstance(item, dict):
                y = item.get('year') or item.get('fy') or item.get('FY')
                pe = item.get('pe') if 'pe' in item else item.get('PE')
                eps = (
                    item.get('eps') if 'eps' in item else
                    item.get('EPS') if 'EPS' in item else
                    item.get('eps_in_rs') if 'eps_in_rs' in item else
                    item.get('EPS in Rs')
                )
                if pe is not None or eps is not None:
                    _append(y, pe, eps)
            elif isinstance(item, (tuple, list)):
                y = None
                pe = None
                eps = None
                if len(item) >= 3:
                    y = item[0]
                    pe = item[1]
                    eps = item[2]
                elif len(item) == 2:
                    first = item[0]
                    second = item[1]
                    if isinstance(first, (int, float)) and 1900 <= int(first) <= 2100:
                        y = int(first)
                        eps = second
                    else:
                        pe = first
                        eps = second
                elif len(item) == 1:
                    pe = item[0]
                _append(y, pe, eps)
            else:
                try:
                    val = float(item)
                    _append(None, val, None)
                except Exception:
                    pass

        if any(y is not None for y in years):
            order = sorted(range(len(years)), key=lambda i: (float('inf') if years[i] is None else years[i]))
            pe_vals = [pe_vals[i] for i in order]
            eps_vals = [eps_vals[i] for i in order]
            years = [years[i] for i in order]

        return pe_vals, eps_vals, years

    def _compute_trailing_cagr(eps_series, trailing_years=3):
        seq = [float(x) for x in eps_series if x is not None and np.isfinite(x)]
        if len(seq) < 2:
            return 0.0
        last = seq[-1]
        idx_back = max(0, len(seq) - 1 - trailing_years)
        span = (len(seq) - 1) - idx_back
        first = seq[idx_back]
        if first > 0 and last > 0 and span > 0:
            try:
                cagr = (last / first) ** (1.0 / span) - 1.0
                return float(cagr * 100.0)
            except Exception:
                pass
        logs = []
        for i in range(1, len(seq)):
            a, b = seq[i - 1], seq[i]
            if a is not None and b is not None and a > 0 and b > 0:
                try:
                    logs.append(np.log(b / a))
                except Exception:
                    continue
        if not logs:
            return 0.0
        geo = np.exp(np.mean(logs)) - 1.0
        return float(geo * 100.0)

    pe_series, eps_series, _years = _extract_series(past_pe_list)

    pe_clean = [float(v) for v in pe_series if v is not None and np.isfinite(v)]
    base_pe = np.median(pe_clean) if pe_clean else (np.median(past_pe_list) if past_pe_list else 0.0)

    past_eps_cagr = _compute_trailing_cagr(eps_series, trailing_years=3) if any(v is not None for v in eps_series) else 0.0

    size_map = {"smallcap": 1.2, "midcap": 1.0, "largecap": 0.6}
    k = size_map.get(company_size.lower(), 1.0)

    growth_delta = (float(future_eps_cagr) - float(past_eps_cagr)) / 100.0

    projected_pe = base_pe * (1.0 + k * growth_delta)
    projected_pe = np.clip(projected_pe, base_pe * 0.7, base_pe * 1.3) if base_pe > 0 else projected_pe

    if sector_median_pe is not None and np.isfinite(sector_median_pe):
        lower_bound, upper_bound = sector_median_pe * 0.7, sector_median_pe * 1.3
        projected_pe = np.clip(projected_pe, lower_bound, upper_bound)

    return round(float(projected_pe), 2)


def get_price_on_date(ticker: str, target_date: str):
    """Fetches the stock price for a given ticker on a specific date."""
    data = yf.download(ticker, period="1y")
    data.index = pd.to_datetime(data.index)
    price_on_date = data.loc[data.index.date == pd.to_datetime(target_date).date(), 'Close']

    if not price_on_date.empty:
        return price_on_date.iloc[0]
    else:
        raise ValueError(f"No data available for {ticker} on {target_date}")


def get_march31_prices_last_5_years(ticker: str, years_count: int = 5) -> dict[int, float]:
    """
    Return a dictionary of stock prices on March 31 for the latest N fiscal years.
    Keys: fiscal year as int (e.g., 2025), Values: closing price (float).
    """
    results: dict[int, float] = {}

    today = date.today()
    latest_fy = today.year if date(today.year, 3, 31) <= today else today.year - 1
    target_years = [latest_fy - i for i in range(years_count)]

    def _price_via_yf_window(tkr: str, d: date, back_days: int = 10) -> float | None:
        start_dt = d - timedelta(days=back_days)
        end_dt = d + timedelta(days=1)
        try:
            df = yf.download(tkr, start=start_dt.isoformat(), end=end_dt.isoformat(), progress=False)
            if df is None or df.empty:
                return None
            df.index = pd.to_datetime(df.index)
            df_on_or_before = df[df.index.date <= d]
            if df_on_or_before.empty:
                return None
            return float(df_on_or_before['Close'].iloc[-1])
        except Exception:
            return None

    for yr in target_years:
        target = date(yr, 3, 31)
        got_price = None
        try:
            got_price = float(get_price_on_date(ticker, target.isoformat()))
        except Exception:
            got_price = None

        if got_price is None:
            got_price = _price_via_yf_window(ticker, target, back_days=14)

        if got_price is None:
            got_price = _price_via_yf_window(ticker, target, back_days=35)

        if got_price is not None:
            results[yr] = round(got_price, 4)
        else:
            results[yr] = None

    return results


def classify_market_cap_category(latest_price: float, number_of_shares: float | int) -> str:
    """
    Classify the company as 'smallcap', 'midcap', or 'largecap' based on market cap (INR crores).
    """
    try:
        price = float(latest_price)
        shares = float(number_of_shares)
    except Exception as e:
        raise ValueError(f"Invalid inputs. latest_price and number_of_shares must be numeric. Details: {e}")

    if not np.isfinite(price) or not np.isfinite(shares) or price <= 0 or shares <= 0:
        raise ValueError("latest_price and number_of_shares must be positive finite numbers")

    market_cap_rs = price * shares
    market_cap_cr = market_cap_rs / 1e7

    if market_cap_cr < 5000:
        return "smallcap"
    elif market_cap_cr <= 20000:
        return "midcap"
    else:
        return "largecap"


def compute_yearly_pe_from_compact(financials_compact, march31_prices: dict[int, float]) -> dict[int, float]:
    """
    Build a dictionary of P/E ratios by fiscal year using compact financials and March 31 prices.
    """
    if isinstance(financials_compact, str):
        try:
            fin = _json.loads(financials_compact)
        except Exception as e:
            raise ValueError(f"Invalid compact financials JSON: {e}")
    elif isinstance(financials_compact, dict):
        fin = financials_compact
    else:
        raise ValueError("financials_compact must be a JSON string or dict")

    pl = (fin or {}).get("profit_and_loss") or {}
    years = list(pl.get("years") or [])
    data = pl.get("data") or {}

    if not years or not data:
        return {}

    eps_key_candidates = ["EPS in Rs", "EPS"]
    eps_key = None
    for k in eps_key_candidates:
        if k in data:
            eps_key = k
            break
    if eps_key is None:
        for k in data.keys():
            if isinstance(k, str) and "eps" in k.lower():
                eps_key = k
                break
    if eps_key is None:
        return {}

    eps_series = list(data.get(eps_key) or [])
    pe_by_year: dict[int, float] = {}
    for idx, yr in enumerate(years):
        if isinstance(yr, str):
            continue
        try:
            yr_int = int(yr)
        except Exception:
            continue
        if idx >= len(eps_series):
            continue
        eps_val = eps_series[idx]
        if eps_val is None:
            continue
        try:
            eps_f = float(eps_val)
        except Exception:
            continue
        if not np.isfinite(eps_f) or eps_f <= 0:
            continue
        price = march31_prices.get(yr_int)
        if price is None:
            continue
        try:
            p = float(price)
        except Exception:
            continue
        if not np.isfinite(p) or p <= 0:
            continue
        pe = p / eps_f
        pe_by_year[yr_int] = round(float(pe), 2)

    return pe_by_year


def build_past_pe_list_from_compact(financials_compact, march31_prices: dict[int, float]) -> list[dict]:
    """
    Build a list of dicts with year, pe, eps suitable for estimate_future_pe.
    """
    pe_by_year = compute_yearly_pe_from_compact(financials_compact, march31_prices)
    if isinstance(financials_compact, str):
        fin = _json.loads(financials_compact)
    else:
        fin = financials_compact
    pl = (fin or {}).get("profit_and_loss") or {}
    years = list(pl.get("years") or [])
    data = pl.get("data") or {}

    eps_key = None
    for k in ("EPS in Rs", "EPS"):
        if k in data:
            eps_key = k
            break
    if eps_key is None:
        for k in data.keys():
            if isinstance(k, str) and "eps" in k.lower():
                eps_key = k
                break
    eps_series = list(data.get(eps_key) or [])

    out = []
    for idx, yr in enumerate(years):
        if isinstance(yr, str):
            continue
        try:
            yr_int = int(yr)
        except Exception:
            continue
        if yr_int not in pe_by_year:
            continue
        if idx >= len(eps_series):
            continue
        eps_val = eps_series[idx]
        try:
            eps_f = float(eps_val) if eps_val is not None else None
        except Exception:
            eps_f = None
        out.append({"year": yr_int, "pe": pe_by_year[yr_int], "eps": eps_f})

    out.sort(key=lambda d: d.get("year", 0))
    return out
