import re

def _fget(data: dict, *keys, default=None):
    for k in keys:
        val = data.get(k)
        if val is not None:
            return val
        for dk, dv in data.items():
            if k.lower() in dk.lower():
                return dv
    return default

def _reverse_dcf(mcap, fcf, wacc=0.12, tg=0.05, years=10):
    if mcap <= 0 or fcf <= 0 or wacc <= tg:
        return None
    lo, hi = 0.0, 0.50
    for _ in range(100):
        mid = (lo + hi) / 2
        pv = sum(fcf * (1 + mid) ** t / (1 + wacc) ** t for t in range(1, years + 1))
        tv = fcf * (1 + mid) ** years * (1 + tg) / (wacc - tg)
        pv += tv / (1 + wacc) ** years
        if pv < mcap:
            lo = mid
        else:
            hi = mid
        if abs(hi - lo) < 0.0001:
            break
    return round((lo + hi) / 2, 4)

def _cross_ref(tables, item_a, item_b, table):
    tbl = tables.get(table, {})
    years = sorted(tbl.keys())
    data = {"item_a": item_a, "item_b": item_b, "comparison": []}
    for i in range(1, len(years)):
        y0, y1 = years[i-1], years[i]
        va0 = _fuzzy(tbl.get(y0, {}), item_a)
        va1 = _fuzzy(tbl.get(y1, {}), item_a)
        vb0 = _fuzzy(tbl.get(y0, {}), item_b)
        vb1 = _fuzzy(tbl.get(y1, {}), item_b)
        row = {"year": y1}
        if isinstance(va0, (int,float)) and isinstance(va1, (int,float)) and va0:
            row["a_growth"] = round(((va1 - va0) / abs(va0)) * 100, 1)
        if isinstance(vb0, (int,float)) and isinstance(vb1, (int,float)) and vb0:
            row["b_growth"] = round(((vb1 - vb0) / abs(vb0)) * 100, 1)
        if "a_growth" in row and "b_growth" in row:
            row["gap_pp"] = round(row["a_growth"] - row["b_growth"], 1)
            row["diverging"] = abs(row["gap_pp"]) > 15
        data["comparison"].append(row)
    return data

def _fuzzy(data: dict, key: str):
    if key in data:
        return data[key]
    for k, v in data.items():
        if key.lower() in k.lower():
            return v
    return None

def _search_guidance(doc, topic):
    patterns = [
        rf"(?i)(?:we expect|guidance|outlook|target|aim to|going forward).*?{re.escape(topic)}",
        rf"(?i){re.escape(topic)}.*?(?:we expect|guidance|outlook|target)",
    ]
    results = []
    for pat in patterns:
        for m in re.finditer(pat, doc):
            start = max(0, m.start() - 100)
            end = min(len(doc), m.end() + 300)
            results.append({"passage": doc[start:end].strip(), "type": "guidance"})
    return results[:5] or [{"passage": f"No guidance found for '{topic}'", "type": "none"}]

def _detect_hedging(doc, section):
    hedging_phrases = [
        "challenging environment", "one-time", "one time", "strategic investment",
        "going forward", "as I said", "let me clarify", "I think we need to",
        "it's too early to", "we'll have to wait", "difficult to predict",
        "cautiously optimistic", "calibrated approach", "headwinds",
    ]
    text = doc
    if section == "qa_only":
        qa_idx = doc.lower().find("question and answer")
        if qa_idx == -1:
            qa_idx = doc.lower().find("q&a")
        if qa_idx > 0:
            text = doc[qa_idx:]
    found = []
    for phrase in hedging_phrases:
        count = text.lower().count(phrase)
        if count > 0:
            idx = text.lower().find(phrase)
            context = text[max(0, idx-50):idx+len(phrase)+100].strip()
            found.append({"phrase": phrase, "count": count, "context": context})
    found.sort(key=lambda x: -x["count"])
    return found[:10] or [{"phrase": "No hedging language detected", "count": 0}]

def _search_competitive(doc, topic):
    keywords = topic.lower().split()
    paras = re.split(r'\n\s*\n', doc)
    scored = []
    for p in paras:
        if len(p.strip()) < 30:
            continue
        lower = p.lower()
        score = sum(lower.count(k) for k in keywords if len(k) > 2)
        if score > 0:
            scored.append((score, p.strip()[:800]))
    scored.sort(key=lambda x: -x[0])
    return [{"passage": p, "score": s} for s, p in scored[:3]] or [{"passage": "Not found", "score": 0}]

def _search_capital(doc, topic):
    return _search_competitive(doc, topic)  

def _search_governance(doc, topic):
    return _search_competitive(doc, topic)
