# utils/formatters.py — Data normalization and formatting utilities for Novus FinLLM
"""
Transforms raw financial data into compact, LLM-friendly formats.
"""

import json as _json
import re as _re
import pandas as pd
import numpy as np

from scrapers.screener_html import extract_financial_data_from_html


def compact_financial_data_for_llm(pl_input, bs_input, years_count: int | None = None, return_json: bool = True):
    """
    Build a compact, clean JSON of financial data for LLM consumption using pandas & numpy.

    Inputs can be either:
    - HTML strings (as scraped from Screener tables), or
    - Dicts shaped like: { "YearLabel": { "Metric": value, ... }, ... } returned by extract_financial_data_from_html.

    Behavior:
    - Normalizes year columns; parses numeric years from labels like 'Mar 2023'.
    - If a TTM column exists, it is mapped to (max_year + 1) to keep chronological order stable years later.
    - Drops OPM% row if it exists and is all zeros across years.
    - Sorts columns by ascending year for both P&L and Balance Sheet independently.
    - Returns compact JSON with separate sections for profit_and_loss and balance_sheet.
    - years_count: number of historical years to include (most recent N), plus TTM if available.

    return_json=True returns a JSON string; otherwise returns a Python dict.
    """

    def _ensure_dict(data_or_html):
        if isinstance(data_or_html, str):
            return extract_financial_data_from_html(data_or_html)
        if isinstance(data_or_html, dict):
            return data_or_html
        return {}

    def _normalize_item_name(name: str) -> str:
        if not isinstance(name, str):
            return name
        n = name.replace('\u00a0', ' ').strip()
        n = n.rstrip('+').strip()
        n = n.replace(' %', '%')
        n = n.replace('% ', '%')
        return n

    def _dict_to_dataframe(year_to_items: dict) -> pd.DataFrame:
        if not year_to_items:
            return pd.DataFrame()
        frames = []
        for year_label, items in year_to_items.items():
            if not isinstance(items, dict):
                continue
            s = pd.Series(items, name=str(year_label))
            frames.append(s)
        if not frames:
            return pd.DataFrame()
        df = pd.concat(frames, axis=1)
        df.index = [_normalize_item_name(ix) for ix in df.index]
        df = df.apply(pd.to_numeric, errors='coerce')
        return df

    def _parse_year(label: str) -> tuple[int | None, bool]:
        """Return (year_int, is_ttm). If TTM detected, (None, True)."""
        if label is None:
            return None, False
        lbl = str(label).strip()
        if lbl.upper() == 'TTM' or 'TTM' in lbl.upper():
            return None, True
        m = _re.search(r'(19|20)\d{2}', lbl)
        if m:
            return int(m.group(0)), False
        return None, False

    def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        cols = list(df.columns)
        years = []
        ttm_present = False
        for c in cols:
            y, is_ttm = _parse_year(c)
            if is_ttm:
                ttm_present = True
            else:
                years.append(y)
        years = [y for y in years if isinstance(y, int)]
        if not years:
            df.columns = [str(c) for c in df.columns]
            return df
        max_year = max(years)
        col_map = {}
        for c in cols:
            y, is_ttm = _parse_year(c)
            if is_ttm:
                col_map[c] = str(max_year + 1)
            elif isinstance(y, int):
                col_map[c] = str(y)
            else:
                col_map[c] = str(c)
        df = df.rename(columns=col_map)

        def _key(c):
            try:
                return (0, int(c))
            except Exception:
                return (1, c)

        df = df.loc[:, ~df.columns.duplicated(keep='last')]
        df = df.reindex(columns=sorted(df.columns, key=_key))
        if ttm_present:
            df.attrs['ttm_col'] = str(max_year + 1)
        else:
            df.attrs['ttm_col'] = None
        return df

    def _drop_opm_if_all_zero(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        idx_matches = [ix for ix in df.index if 'OPM' in str(ix).upper() and '%' in str(ix)]
        for ix in idx_matches:
            row = df.loc[ix]
            if np.nan_to_num(row.values.astype(float), nan=0.0).sum() == 0.0:
                df = df.drop(index=ix)
        return df

    def _to_clean_json(df: pd.DataFrame) -> dict:
        if df.empty:
            return {"years": [], "data": {}}
        df_norm = _normalize_columns(df)
        df_norm = df_norm.replace([np.inf, -np.inf], np.nan)
        ttm_col = df_norm.attrs.get('ttm_col', None)
        numeric_cols = []
        for c in df_norm.columns:
            try:
                ci = int(c)
                if ttm_col is not None and str(c) == str(ttm_col):
                    continue
                numeric_cols.append(ci)
            except Exception:
                pass
        numeric_cols = sorted(set(numeric_cols))
        if years_count is not None and years_count > 0 and numeric_cols:
            selected_years = numeric_cols[-years_count:]
        else:
            selected_years = numeric_cols
        final_cols = [str(y) for y in selected_years]
        if ttm_col is not None and str(ttm_col) in df_norm.columns:
            final_cols.append(str(ttm_col))
        if set(final_cols) != set(df_norm.columns):
            existing = [c for c in final_cols if c in df_norm.columns]
            df_norm = df_norm.reindex(columns=existing)
        years_order = list(df_norm.columns)
        data_obj = {}
        for item in df_norm.index:
            series = df_norm.loc[item]
            values = []
            for v in series.tolist():
                if pd.isna(v):
                    values.append(None)
                else:
                    vv = float(v)
                    if abs(vv) < 1e-12:
                        vv = 0.0
                    values.append(vv)
            data_obj[str(item)] = values
        years_cast = []
        for idx, y in enumerate(years_order):
            if ttm_col is not None and str(y) == str(ttm_col):
                years_cast.append('TTM')
            else:
                try:
                    years_cast.append(int(y))
                except Exception:
                    years_cast.append(str(y))
        return {"years": years_cast, "data": data_obj}

    # 1) Convert inputs to DataFrames
    pl_dict = _ensure_dict(pl_input)
    bs_dict = _ensure_dict(bs_input)

    pl_df = _dict_to_dataframe(pl_dict)
    bs_df = _dict_to_dataframe(bs_dict)

    # 2) Clean up: drop OPM% rows if all zeros (P&L mostly)
    pl_df = _drop_opm_if_all_zero(pl_df)

    # 3) Normalize columns (years incl. TTM -> max_year + 1) and sort
    pl_json = _to_clean_json(pl_df)
    bs_json = _to_clean_json(bs_df)

    result = {
        "profit_and_loss": pl_json,
        "balance_sheet": bs_json,
    }

    if return_json:
        try:
            return _json.dumps(result, ensure_ascii=False)
        except Exception:
            return _json.dumps(_json.loads(_json.dumps(result, default=str)))
    return result
