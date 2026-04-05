"""
clean_json.py
=============
Cleans the raw Prowess API JSON (nifty50_raw.json) into pipe-delimited tables
(one per company × report combination) and saves them all into:

    nifty50_clean/
        <Company Name>/
            <report_name>.psv        ← pipe-separated values

A master index file  nifty50_clean/index.txt  lists every output file.

Usage
-----
    python clean_json.py                       # default: reads nifty50_raw.json
    python clean_json.py my_raw.json           # custom input path
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sanitise(value: object) -> str:
    """Convert any cell value to a clean string."""
    if value is None:
        return ""
    s = str(value).strip()
    # remove internal pipes to avoid breaking the delimiter
    s = s.replace("|", "/")
    # collapse whitespace
    s = re.sub(r"\s+", " ", s)
    return s


def _format_number(val: str) -> str:
    """Turn '43447.000000' → '43,447.00' for readability."""
    try:
        f = float(val)
        # If it looks like an integer (e.g. 43447.0), strip decimal part
        if f == int(f):
            return f"{int(f):,}"
        return f"{f:,.2f}"
    except (ValueError, TypeError):
        return val


def rows_to_psv(meta: dict, head: list[list], data: list[list]) -> str:
    """
    Convert the Prowess head + data structure into a pipe-separated string.

    The Prowess JSON has:
        head  → list of [col0_label, col1_label, … colN_label]  (multiple rows)
        data  → list of [row_label, val1, val2, … valN]
    """
    lines: list[str] = []

    # ── Meta block ──────────────────────────────────────────────────────────
    lines.append("# META")
    for k, v in meta.items():
        lines.append(f"# {k}: {_sanitise(v)}")
    lines.append("")

    # ── Header rows ─────────────────────────────────────────────────────────
    for hrow in head:
        lines.append("|".join(_sanitise(c) for c in hrow))

    # ── Data rows ───────────────────────────────────────────────────────────
    for drow in data:
        cells = []
        for i, cell in enumerate(drow):
            s = _sanitise(cell)
            # format numeric cells (skip index 0 which is the row label)
            if i > 0 and s:
                s = _format_number(s)
            cells.append(s)
        lines.append("|".join(cells))

    return "\n".join(lines)


def clean_single_report(company: str, report: str, payload: dict) -> str | None:
    """
    Extract head / data from a Prowess report payload and return PSV text.
    Returns None if the payload has no usable table data.
    """
    if payload.get("parse_error") or payload.get("error"):
        return None

    meta = payload.get("meta", {})
    if meta.get("errno", 0) != 0:
        return None

    head = payload.get("head", [])
    data = payload.get("data", [])

    if not data:
        return None

    return rows_to_psv(meta, head, data)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def clean(raw_path: Path, out_dir: Path) -> list[Path]:
    """
    Read raw_path JSON, produce PSV files under out_dir.
    Returns list of written file paths.
    """
    with raw_path.open(encoding="utf-8") as f:
        raw: dict[str, dict[str, dict]] = json.load(f)

    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    skipped: list[str] = []

    for company, reports in raw.items():
        # make a safe directory name from the company name
        safe_co = re.sub(r'[\\/:*?"<>|]', "_", company).strip()
        co_dir = out_dir / safe_co
        co_dir.mkdir(parents=True, exist_ok=True)

        for report_name, payload in reports.items():
            psv = clean_single_report(company, report_name, payload)
            if psv is None:
                skipped.append(f"{company}/{report_name}")
                continue

            out_file = co_dir / f"{report_name}.psv"
            out_file.write_text(psv, encoding="utf-8")
            written.append(out_file)
            print(f"  [OK]  {out_file.relative_to(out_dir.parent)}")

    # ── Index ────────────────────────────────────────────────────────────────
    index_path = out_dir / "index.txt"
    with index_path.open("w", encoding="utf-8") as idx:
        idx.write(f"# Prowess Nifty-50 cleaned tables\n")
        idx.write(f"# Source: {raw_path.name}\n\n")
        for p in written:
            idx.write(str(p.relative_to(out_dir)) + "\n")
        if skipped:
            idx.write("\n# Skipped (no data / error):\n")
            for s in skipped:
                idx.write(f"#   {s}\n")

    if skipped:
        print(f"\n  [SKIP] {len(skipped)} report(s) had no data or errors.")

    print(f"\n[DONE] {len(written)} PSV file(s) → {out_dir}")
    print(f"       Index → {index_path}")
    return written


# ─────────────────────────────────────────────────────────────────────────────
# Test / demo helper
# ─────────────────────────────────────────────────────────────────────────────

def run_test(raw_path: Path, out_dir: Path) -> None:
    """Run clean() and print a preview of every generated PSV file."""
    print("=" * 70)
    print("  clean_json.py – TEST RUN")
    print("=" * 70)
    written = clean(raw_path, out_dir)
    print()
    print("=" * 70)
    print("  PREVIEW (first 10 lines of each file)")
    print("=" * 70)
    for fp in written:
        print(f"\n▶ {fp.relative_to(out_dir.parent)}")
        print("─" * 60)
        lines = fp.read_text(encoding="utf-8").splitlines()
        for line in lines[:10]:
            print(line)
        if len(lines) > 10:
            print(f"  … ({len(lines) - 10} more lines)")


if __name__ == "__main__":
    base = Path(__file__).resolve().parent
    raw_path = Path(sys.argv[1]) if len(sys.argv) > 1 else base / "nifty50_raw.json"
    out_dir  = base / "nifty50_clean"

    if not raw_path.exists():
        print(f"[ERROR] Raw JSON not found: {raw_path}")
        print("        Run fetch_nifty50.py first.")
        sys.exit(1)

    run_test(raw_path, out_dir)
