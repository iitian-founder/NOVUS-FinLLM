"""Utilities for fetching and persisting concall transcripts."""

from __future__ import annotations

import calendar
import logging
import random
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence

import requests
from bs4 import BeautifulSoup
from requests import Response, Session
from requests.adapters import HTTPAdapter
from urllib.parse import unquote, urljoin, urlparse
from urllib3.util import Retry


LOGGER = logging.getLogger(__name__)
if not LOGGER.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


DOWNLOAD_ROOT = Path(r"G:\My Drive\concall transcripts")
BSE_API_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w"
NSE_BASE_URL = "https://www.nseindia.com"
NSE_API_URL = f"{NSE_BASE_URL}/api/corporate-announcements"
SCREENER_URL_TEMPLATES: tuple[str, str] = (
	"https://www.screener.in/company/{ticker}/consolidated/",
	"https://www.screener.in/company/{ticker}/",
)
SCREENER_KEYWORDS: tuple[str, ...] = ("transcript", "conference call", "concall")


@dataclass(frozen=True)
class QuarterRange:
	"""Represents the start and end dates for a financial quarter."""

	year: int
	quarter: int
	start: date
	end: date

	@property
	def label(self) -> str:
		return f"Q{self.quarter} {self.year}"


@dataclass(frozen=True)
class TranscriptMeta:
	"""Container for transcript metadata."""

	title: str
	url: str
	published_date: date
	source: str


def fetch_concall_transcripts_from_screener(
	ticker: str,
	root_directory: Optional[Path] = None,
) -> tuple[int, List[str]]:
	"""Fetch and persist Screener.in concall transcripts for the given ticker.

	Args:
		ticker: NSE/BSE symbol recognised by Screener (e.g. "KPENERGY").
		root_directory: Optional override for the download root.

	Returns:
		Tuple consisting of the count of newly saved transcripts and a list of
		period descriptors that could not be downloaded successfully.
	"""

	if not ticker or not ticker.strip():
		raise ValueError("Ticker must be a non-empty string.")

	normalized_ticker = ticker.strip().upper()
	session = _build_http_session()
	all_candidates: List[TranscriptMeta] = []
	company_name: Optional[str] = None

	for template in SCREENER_URL_TEMPLATES:
		url = template.format(ticker=normalized_ticker)
		LOGGER.info("Fetching Screener transcript listing: %s", url)
		_respectful_pause()
		response = _safe_get(session, url, timeout=30.0)
		if response is None:
			continue

		soup = BeautifulSoup(response.content, "html.parser")
		if company_name is None:
			company_name = _extract_company_name_from_soup(soup)

		candidates = _parse_screener_transcripts(soup, response.url)
		if candidates:
			LOGGER.info("Discovered %d potential transcripts at %s", len(candidates), url)
		all_candidates.extend(candidates)

	if not all_candidates:
		message = f"⚠️ No transcripts found for {normalized_ticker}"
		LOGGER.warning(message)
		print(message)
		return 0, []

	unique_candidates = _dedupe_transcripts(all_candidates)
	unique_candidates.sort(key=lambda meta: (meta.published_date, meta.title))

	company_dir = _ensure_company_directory(company_name or normalized_ticker, root=root_directory)
	LOGGER.info("Saving Screener transcripts for %s into %s", normalized_ticker, company_dir)

	saved_count = 0
	skipped_existing = 0
	missing_periods: set[str] = set()

	for meta in unique_candidates:
		target_base = _target_path(normalized_ticker, company_dir, meta)
		pdf_path = target_base.with_suffix(".pdf")
		txt_path = target_base.with_suffix(".txt")
		if pdf_path.exists() or txt_path.exists():
			skipped_existing += 1
			LOGGER.info(
				"Skipping already-downloaded Screener transcript %s",
				pdf_path.name if pdf_path.exists() else txt_path.name,
			)
			continue

		try:
			_respectful_pause()
			_download_and_save(session, meta, target_base)
			saved_count += 1
		except Exception as exc:  # pylint: disable=broad-except
			period_label = _period_label_from_meta(meta)
			missing_periods.add(period_label)
			LOGGER.warning(
				"Failed to persist Screener transcript %s (%s): %s",
				meta.url,
				period_label,
				exc,
			)

	missing_list = sorted(missing_periods)
	LOGGER.info(
		"Screener transcript summary for %s - saved: %d, skipped existing: %d, missing: %d",
		normalized_ticker,
		saved_count,
		skipped_existing,
		len(missing_list),
	)
	return saved_count, missing_list


def fetch_and_save_concall_transcripts(company: str, save_to_drive: bool = False) -> None:
	"""Fetch and persist concall transcripts for the given company.

	Args:
		company: NSE/BSE ticker or company name used for discovery.
		save_to_drive: Optional future flag for cloud uploads. Currently logged only.
	"""

	if not company.strip():
		raise ValueError("Company name must be a non-empty string.")

	session = _build_http_session()
	company_dir = _ensure_company_directory(company)
	existing_index = _index_existing_transcripts(company_dir)

	if save_to_drive:
		LOGGER.info("save_to_drive=True requested; cloud upload hook not yet implemented.")

	ranges = list(_quarter_ranges(years=10))
	saved_count = 0
	skipped_existing = 0
	missing_quarters: List[QuarterRange] = []
	errors: List[str] = []

	for quarter_range in ranges:
		LOGGER.info("Processing %s", quarter_range.label)

		if _quarter_has_existing(quarter_range, existing_index):
			LOGGER.info(
				"Existing transcript detected for %s; skipping fetch.",
				quarter_range.label,
			)
			skipped_existing += 1
			continue

		transcripts = _fetch_transcripts_for_quarter(company, quarter_range, session)
		if not transcripts:
			missing_quarters.append(quarter_range)
			LOGGER.warning("No transcripts found for %s", quarter_range.label)
			continue

		for meta in transcripts:
			target_path = _target_path(company, company_dir, meta)
			if target_path.exists():
				LOGGER.info("Skipping existing file %s", target_path.name)
				skipped_existing += 1
				continue

			try:
				_respectful_pause()
				_download_and_save(session, meta, target_path)
				saved_count += 1
			except Exception as exc:  # pylint: disable=broad-except
				error_message = f"Failed to download {meta.url}: {exc}"
				LOGGER.error(error_message)
				errors.append(error_message)

	summary_parts = [
		f"Saved: {saved_count}",
		f"Skipped existing: {skipped_existing}",
		f"Missing quarters logged: {len(missing_quarters)}",
		f"Errors: {len(errors)}",
	]
	print("Transcripts fetch completed. " + " | ".join(summary_parts))

	if missing_quarters:
		for missing in missing_quarters:
			LOGGER.info("Missing transcript for %s", missing.label)

	if errors:
		LOGGER.info("Encountered the following download issues:")
		for err in errors:
			LOGGER.info("%s", err)


def _build_http_session() -> Session:
	session = requests.Session()
	retry_strategy = Retry(
		total=3,
		backoff_factor=0.8,
		status_forcelist=[429, 500, 502, 503, 504],
		allowed_methods=("GET", "HEAD"),
	)
	adapter = HTTPAdapter(max_retries=retry_strategy)
	session.mount("http://", adapter)
	session.mount("https://", adapter)
	session.headers.update(
		{
			"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
			" AppleWebKit/537.36 (KHTML, like Gecko)"
			" Chrome/128.0 Safari/537.36",
			"Accept-Language": "en-US,en;q=0.9",
			"Accept": "application/json, text/html, */*;q=0.8",
			"Connection": "keep-alive",
		}
	)
	return session


def _ensure_company_directory(company: str, *, root: Optional[Path] = None) -> Path:
	base_directory = root or DOWNLOAD_ROOT
	cleaned = re.sub(r'[<>:"/\\|?*]', "_", company.strip())
	normalized = re.sub(r"\s+", "_", cleaned)
	target_dir = base_directory / normalized
	target_dir.mkdir(parents=True, exist_ok=True)
	return target_dir


def _index_existing_transcripts(company_dir: Path) -> List[tuple[date, Path]]:
	indexed: List[tuple[date, Path]] = []
	for path in company_dir.glob("*concall_*.*"):
		parsed_date = _date_from_filename(path.name)
		if parsed_date:
			indexed.append((parsed_date, path))
	return indexed


def _date_from_filename(filename: str) -> Optional[date]:
	try:
		date_part = filename.rsplit("_", maxsplit=1)[1].split(".")[0]
		return datetime.strptime(date_part, "%Y-%m-%d").date()
	except (IndexError, ValueError):
		return None


def _quarter_ranges(*, years: int) -> Iterable[QuarterRange]:
	today = date.today()
	end = _quarter_end(today.year, _quarter_from_month(today.year, today.month))

	for _ in range(years * 4):
		start = _quarter_start(end.year, _quarter_from_month(end.year, end.month))
		quarter = _quarter_from_month(end.year, end.month)
		yield QuarterRange(year=start.year, quarter=quarter, start=start, end=end)
		end = start - timedelta(days=1)


def _quarter_from_month(_year: int, month: int) -> int:
	return (month - 1) // 3 + 1


def _quarter_start(year: int, quarter: int) -> date:
	month = (quarter - 1) * 3 + 1
	return date(year, month, 1)


def _quarter_end(year: int, quarter: int) -> date:
	month = quarter * 3
	last_day = calendar.monthrange(year, month)[1]
	return date(year, month, last_day)


def _quarter_has_existing(quarter: QuarterRange, indexed: Sequence[tuple[date, Path]]) -> bool:
	for existing_date, _ in indexed:
		if quarter.start <= existing_date <= quarter.end:
			return True
	return False


def _fetch_transcripts_for_quarter(
	company: str,
	quarter_range: QuarterRange,
	session: Session,
) -> List[TranscriptMeta]:
	sources: List[Callable[[str, QuarterRange, Session], List[TranscriptMeta]]] = [
		_fetch_from_bse,
		_fetch_from_nse,
	]

	aggregated: List[TranscriptMeta] = []
	for loader in sources:
		try:
			_respectful_pause()
			aggregated.extend(loader(company, quarter_range, session))
		except Exception as exc:  # pylint: disable=broad-except
			LOGGER.warning("Source %s failed: %s", loader.__name__, exc)

	return _dedupe_transcripts(aggregated)


def _fetch_from_bse(company: str, quarter_range: QuarterRange, session: Session) -> List[TranscriptMeta]:
    # This API requires a POST request with a JSON payload and specific headers.
    
    # 1. This is the payload, which will be sent as JSON in the request body.
    payload = {
        "strCat": "-1",
        # 2. The API expects dates in YYYY-MM-DD format.
        "strPrevDate": quarter_range.start.strftime("%Y-%m-%d"),
        "strToDate": quarter_range.end.strftime("%Y-%m-%d"),
        "strScrip": "",  # Using keyword search as in your original code
        "strSearch": f"{company} concall", # Your keyword search
        "strType": "C", # Specifies "Corporate Announcements"
    }

    # 3. These headers are *required* by the BSE API for POST requests.
    post_headers = {
        'Origin': 'https://www.bseindia.com',
        'Referer': 'https://www.bseindia.com/',
        'Content-Type': 'application/json'
    }

    # 4. We cannot use _safe_get(). We must call session.post() directly.
    try:
        response = session.post(BSE_API_URL, json=payload, headers=post_headers, timeout=25.0)
        response.raise_for_status()
    except requests.RequestException as exc:
        LOGGER.warning("BSE POST request failed for %s: %s", company, exc)
        return []

    try:
        # 5. Renamed variable to 'data' to avoid conflict with 'payload'
        data = response.json()
    except ValueError:
        LOGGER.debug("Unexpected BSE response format for %s", company)
        return []

    # The rest of your parsing logic is correct
    records = _extract_json_records(data)
    transcripts: List[TranscriptMeta] = []
    for record in records:
        subject = (record.get("HEADLINE") or record.get("SUBJECT") or "").strip()
        if not subject:
            continue
        text_subject = subject.lower()
        if "concall" not in text_subject and "conference call" not in text_subject:
            continue

        file_url = (
            record.get("ATTACHMENTNAME")
            or record.get("FILEURL")
            or record.get("FILE")
            or record.get("MOREURL")
        )
        if not file_url:
            continue
        if not file_url.startswith("http"):
            file_url = "https://www.bseindia.com" + file_url

        published = _parse_date(
            record.get("NEWS_DT")
            or record.get("DT_TM")
            or record.get("DISSEMINATIONDATE")
        )
        if published is None:
            published = quarter_range.end

        transcripts.append(
            TranscriptMeta(
                title=subject,
                url=file_url,
                published_date=published,
                source="BSE",
            )
        )

    return transcripts


def _fetch_from_nse(company: str, quarter_range: QuarterRange, session: Session) -> List[TranscriptMeta]:
	_ensure_nse_session(session)
	params = {
		"index": "equities",
		"from_date": quarter_range.start.strftime("%d-%m-%Y"),
		"to_date": quarter_range.end.strftime("%d-%m-%Y"),
		"symbol": company.upper(),
	}
	response = _safe_get(
		session,
		NSE_API_URL,
		params=params,
		headers={"Referer": NSE_BASE_URL},
	)
	if response is None:
		return []

	try:
		payload = response.json()
	except ValueError:
		LOGGER.debug("Unexpected NSE response format for %s", company)
		return []

	data = payload.get("data") or payload.get("announcements") or []
	transcripts: List[TranscriptMeta] = []
	for item in data:
		description = (item.get("desc") or item.get("subject") or "").strip()
		lower_desc = description.lower()
		if "transcript" not in lower_desc and "conference call" not in lower_desc:
			continue

		attachment = item.get("attchmntFile") or item.get("pdf") or item.get("attachment")
		if not attachment:
			continue
		if not attachment.startswith("http"):
			attachment = NSE_BASE_URL + attachment

		published = _parse_date(
			item.get("attchmntDt")
			or item.get("publishDate")
			or item.get("postedDate")
			or item.get("dissemDT")
		)
		if published is None:
			published = quarter_range.end

		transcripts.append(
			TranscriptMeta(
				title=description or f"NSE announcement {company}",
				url=attachment,
				published_date=published,
				source="NSE",
			)
		)

	return transcripts


def _ensure_nse_session(session: Session) -> None:
	if session.cookies.get("nsit"):
		return
	_safe_get(session, NSE_BASE_URL)


def _safe_get(
	session: Session,
	url: str,
	params: Optional[dict[str, str]] = None,
	headers: Optional[dict[str, str]] = None,
	timeout: float = 25.0,
) -> Optional[Response]:
	try:
		response = session.get(url, params=params, headers=headers, timeout=timeout)
		response.raise_for_status()
		return response
	except requests.RequestException as exc:
		LOGGER.warning("Request failed for %s: %s", url, exc)
		return None


def _extract_json_records(payload: object) -> List[dict]:
	if isinstance(payload, list):
		return [item for item in payload if isinstance(item, dict)]
	if isinstance(payload, dict):
		for key in ("Table", "Rows", "data", "announcements"):
			if key in payload and isinstance(payload[key], list):
				return [item for item in payload[key] if isinstance(item, dict)]
	return []


def _dedupe_transcripts(transcripts: Sequence[TranscriptMeta]) -> List[TranscriptMeta]:
	seen: set[str] = set()
	unique: List[TranscriptMeta] = []
	for transcript in transcripts:
		if transcript.url in seen:
			continue
		seen.add(transcript.url)
		unique.append(transcript)
	return unique


def _target_path(company: str, company_dir: Path, meta: TranscriptMeta) -> Path:
	normalized_company = company.strip().upper().replace(" ", "")
	filename = f"{normalized_company}-concall_{meta.published_date.isoformat()}"
	extension = ".pdf" if meta.url.lower().endswith(".pdf") else ".txt"
	return company_dir / f"{filename}{extension}"


def _download_and_save(session: Session, meta: TranscriptMeta, target_path: Path) -> None:
	response = _safe_get(session, meta.url, timeout=60.0)
	if response is None:
		raise RuntimeError("Download failed")
	if not response.content:
		raise RuntimeError("Downloaded content is empty")

	content_type = (response.headers.get("Content-Type") or "").lower()
	if "pdf" in content_type or meta.url.lower().endswith(".pdf"):
		target_path = target_path.with_suffix(".pdf")
		target_path.write_bytes(response.content)
		return

	target_path = target_path.with_suffix(".txt")
	text_content = _html_to_text(response)
	target_path.write_text(text_content, encoding="utf-8")


def _html_to_text(response: Response) -> str:
	content_type = (response.headers.get("Content-Type") or "").lower()
	text = response.text
	if "html" not in content_type and "xml" not in content_type and "htm" not in response.url.lower():
		return text

	soup = BeautifulSoup(response.content, "html.parser")
	for script in soup(["script", "style"]):
		script.decompose()
	cleaned_lines = [line.strip() for line in soup.get_text(separator="\n").splitlines() if line.strip()]
	if cleaned_lines:
		return "\n".join(cleaned_lines)
	return text


def _parse_date(value: Optional[str]) -> Optional[date]:
	if not value:
		return None

	candidates = [
		"%d %b %Y",
		"%Y-%m-%d",
		"%d-%m-%Y",
		"%d/%m/%Y",
		"%Y/%m/%d",
		"%d-%b-%Y",
		"%Y%m%d",
		"%Y-%m-%dT%H:%M:%S",
		"%d %B %Y",
	]

	for fmt in candidates:
		try:
			return datetime.strptime(value.strip(), fmt).date()
		except ValueError:
			continue
	return None


def _respectful_pause(min_seconds: float = 0.6, max_seconds: float = 1.4) -> None:
	delay = random.uniform(min_seconds, max_seconds)
	time.sleep(delay)


def _extract_company_name_from_soup(soup: BeautifulSoup) -> Optional[str]:
	heading = soup.find("h1")
	if heading:
		text = heading.get_text(strip=True)
		if text:
			return text
	title_meta = soup.find("meta", attrs={"property": "og:title"})
	if title_meta and title_meta.get("content"):
		return title_meta["content"].split("|")[0].strip()
	return None


def _parse_screener_transcripts(soup: BeautifulSoup, base_url: str) -> List[TranscriptMeta]:
	transcripts: List[TranscriptMeta] = []
	base_components = urlparse(base_url)
	for anchor in soup.find_all("a", href=True):
		href = anchor["href"].strip()
		if not href or href.startswith("#"):
			continue
		lower_href = href.lower()
		if lower_href.startswith("javascript:") or lower_href.startswith("mailto:"):
			continue
		absolute_url = urljoin(base_url, href)
		components = urlparse(absolute_url)
		if components.scheme not in {"http", "https"}:
			continue
		if components.netloc == base_components.netloc and components.path == base_components.path and components.fragment:
			continue

		visible_text = anchor.get_text(" ", strip=True)
		parent_text = anchor.parent.get_text(" ", strip=True) if anchor.parent else ""
		descriptor = " ".join(part for part in (visible_text, parent_text, href) if part)
		if not _contains_transcript_keyword(descriptor):
			continue

		path_segment = unquote(components.path.rsplit("/", maxsplit=1)[-1]) if components.path else ""
		title = visible_text or path_segment.replace("-", " ") or "Screener concall transcript"
		context_blob = " ".join(part for part in (descriptor, path_segment) if part)
		published = (
			_extract_published_date(context_blob)
			or _extract_published_date(title)
			or date.today()
		)
		transcripts.append(
			TranscriptMeta(
				title=title,
				url=absolute_url,
				published_date=published,
				source="Screener",
			)
		)

	return transcripts


def _contains_transcript_keyword(text: str) -> bool:
	if not text:
		return False
	lower_text = text.lower()
	return any(keyword in lower_text for keyword in SCREENER_KEYWORDS)


def _extract_published_date(text: str) -> Optional[date]:
	if not text:
		return None
	normalized = re.sub(r"[_,]", " ", text)
	iso_match = re.search(r"(20\d{2}|19\d{2})[-/.](0[1-9]|1[0-2])[-/.]([0-3]\d)", normalized)
	if iso_match:
		year, month, day = map(int, iso_match.groups())
		possible = _make_date(year, month, day)
		if possible:
			return possible

	dmy_match = re.search(r"([0-3]?\d)[-/.](0[1-9]|1[0-2])[-/.](20\d{2}|19\d{2})", normalized)
	if dmy_match:
		day, month, year = map(int, dmy_match.groups())
		possible = _make_date(year, month, day)
		if possible:
			return possible

	month_day_match = re.search(
		r"([0-3]?\d)\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(20\d{2}|19\d{2})",
		normalized,
		re.IGNORECASE,
	)
	if month_day_match:
		day = int(month_day_match.group(1))
		month = _month_name_to_number(month_day_match.group(2))
		year = int(month_day_match.group(3))
		if month:
			possible = _make_date(year, month, day)
			if possible:
				return possible

	month_year_match = re.search(
		r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(20\d{2}|19\d{2})",
		normalized,
		re.IGNORECASE,
	)
	if month_year_match:
		month = _month_name_to_number(month_year_match.group(1))
		year = int(month_year_match.group(2))
		if month:
			last_day = calendar.monthrange(year, month)[1]
			return date(year, month, last_day)

	quarter_info = _detect_fiscal_quarter(normalized)
	if quarter_info:
		quarter, fiscal_year = quarter_info
		possible = _resolve_fiscal_quarter_end(fiscal_year, quarter)
		if possible:
			return possible

	return None


def _detect_fiscal_quarter(text: str) -> Optional[tuple[int, int]]:
	patterns = (
		(re.compile(r"Q\s*([1-4])\s*F[Yy]\s*([0-9][0-9A-Za-z\-/]*)", re.IGNORECASE), 1, 2),
		(re.compile(r"Q([1-4])FY([0-9][0-9A-Za-z\-/]*)", re.IGNORECASE), 1, 2),
		(re.compile(r"F[Yy]([0-9][0-9A-Za-z\-/]*)\s*Q\s*([1-4])", re.IGNORECASE), 2, 1),
	)
	for pattern, quarter_index, fiscal_index in patterns:
		match = pattern.search(text)
		if not match:
			continue
		quarter = int(match.group(quarter_index))
		fiscal_year = _normalize_fy_year(match.group(fiscal_index))
		if fiscal_year is not None:
			return quarter, fiscal_year
	return None


def _normalize_fy_year(token: str) -> Optional[int]:
	if not token:
		return None
	digits = re.findall(r"\d{2,4}", token)
	if not digits:
		return None
	candidate = digits[-1]
	value = int(candidate)
	if len(candidate) == 2:
		value += 2000
	return value


def _resolve_fiscal_quarter_end(fy_year: int, quarter: int) -> Optional[date]:
	if quarter not in (1, 2, 3, 4):
		return None
	if quarter == 4:
		year = fy_year
		month = 3
	else:
		year = fy_year - 1
		month = {1: 6, 2: 9, 3: 12}[quarter]
	day = calendar.monthrange(year, month)[1]
	return date(year, month, day)


def _month_name_to_number(name: str) -> Optional[int]:
	if not name:
		return None
	lower_name = name.strip().lower()
	for index, month_name in enumerate(calendar.month_name):
		if month_name and month_name.lower().startswith(lower_name):
			return index
	for index, month_name in enumerate(calendar.month_abbr):
		if month_name and month_name.lower().startswith(lower_name):
			return index
	return None


def _make_date(year: int, month: int, day: int) -> Optional[date]:
	try:
		return date(year, month, day)
	except ValueError:
		return None


def _period_label_from_meta(meta: TranscriptMeta) -> str:
	for source_text in (meta.title, meta.url):
		if not source_text:
			continue
		info = _detect_fiscal_quarter(source_text)
		if info:
			quarter, fy_year = info
			return f"Q{quarter} FY{fy_year}"
	return meta.published_date.isoformat()


