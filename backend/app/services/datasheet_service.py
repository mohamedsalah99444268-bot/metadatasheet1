from __future__ import annotations

import html as html_lib
import ipaddress
import logging
import re
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import httpx
from sqlalchemy.orm import Session

from ..config import load_settings
from ..models import DatasheetDownload, Document
from .document_service import DocumentIngestError, ingest_pdf_bytes

logger = logging.getLogger(__name__)

SEARCH_URL = "https://html.duckduckgo.com/html/"
USER_AGENT = "SmartDatasheetAI/0.1 local-datasheet-research"

MANUFACTURER_ALIASES = {
    "st": "stmicroelectronics",
    "stm": "stmicroelectronics",
    "ti": "texas instruments",
    "texas instruments incorporated": "texas instruments",
    "adi": "analog devices",
    "linear technology": "analog devices",
    "maxim integrated": "analog devices",
    "nxp semiconductors": "nxp",
    "microchip technology": "microchip",
    "atmel": "microchip",
    "infineon technologies": "infineon",
    "cypress semiconductor": "infineon",
    "nordic semiconductor": "nordic semiconductor",
}

OFFICIAL_DOMAINS = {
    "stmicroelectronics": {"st.com", "stmicroelectronics.com"},
    "texas instruments": {"ti.com"},
    "analog devices": {"analog.com"},
    "nxp": {"nxp.com"},
    "microchip": {"microchip.com"},
    "infineon": {"infineon.com"},
    "onsemi": {"onsemi.com"},
    "nordic semiconductor": {"nordicsemi.com"},
    "espressif": {"espressif.com"},
    "renesas": {"renesas.com"},
    "silicon labs": {"silabs.com"},
    "broadcom": {"broadcom.com"},
    "avago technologies": {"broadcom.com"},
    "intel": {"intel.com"},
    "amd": {"amd.com"},
    "xilinx": {"amd.com"},
    "qualcomm": {"qualcomm.com"},
    "mediatek": {"mediatek.com"},
    "murata": {"murata.com"},
    "vishay": {"vishay.com"},
    "bourns": {"bourns.com"},
    "te connectivity": {"te.com"},
    "molex": {"molex.com"},
    "lattice semiconductor": {"latticesemi.com"},
    "samsung": {"samsung.com"},
    "toshiba": {"toshiba.com"},
}

BLOCKED_DOMAIN_SUFFIXES = (
    "alldatasheet.com",
    "datasheetarchive.com",
    "datasheetcatalog.com",
    "digikey.com",
    "mouser.com",
    "rs-online.com",
    "farnell.com",
    "newark.com",
    "octopart.com",
    "snapeda.com",
    "ultralibrarian.com",
)


class DatasheetServiceError(Exception):
    pass


@dataclass(frozen=True)
class DatasheetCandidate:
    url: str
    title: str
    source_domain: str
    score: int
    filename: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "source_domain": self.source_domain,
            "score": self.score,
            "filename": self.filename,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "DatasheetCandidate":
        return cls(
            url=str(value["url"]),
            title=str(value.get("title") or ""),
            source_domain=str(value.get("source_domain") or _host(str(value["url"]))),
            score=int(value.get("score") or 0),
            filename=value.get("filename"),
        )


@dataclass(frozen=True)
class DatasheetDownloadResult:
    download_id: int
    document_id: int
    source_url: str
    filename: str
    download_status: str
    sha256: str
    is_duplicate: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "download_id": self.download_id,
            "document_id": self.document_id,
            "source_url": self.source_url,
            "filename": self.filename,
            "download_status": self.download_status,
            "sha256": self.sha256,
            "is_duplicate": self.is_duplicate,
            "message": self.message,
        }


@dataclass(frozen=True)
class FetchedResource:
    data: bytes
    final_url: str
    headers: dict[str, str]

    @property
    def text(self) -> str:
        return self.data.decode("utf-8", errors="ignore")


@dataclass(frozen=True)
class FetchedPdf:
    data: bytes
    filename: str
    source_url: str


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _canonical_manufacturer(value: str) -> str:
    normalized = _normalize_text(value)
    return MANUFACTURER_ALIASES.get(normalized, normalized)


def _part_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _source_key(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/").lower()
    query = parsed.query.lower()
    return f"{parsed.hostname.lower() if parsed.hostname else ''}{path}?{query}"[:500]


def _is_official_host(host: str, domains: set[str] | list[str]) -> bool:
    if not host:
        return False
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def official_domains_for(manufacturer: str) -> list[str]:
    canonical = _canonical_manufacturer(manufacturer)
    domains = set(OFFICIAL_DOMAINS.get(canonical, set()))
    for entry in load_settings().official_datasheet_domains:
        if "=" in entry:
            key, values = entry.split("=", 1)
            configured_key = _canonical_manufacturer(key)
            if configured_key == canonical or canonical.startswith(f"{configured_key} "):
                domains.update(part.strip().lower().lstrip(".") for part in values.split("|") if part.strip())
        else:
            domains.add(entry)
    return sorted(domain for domain in domains if domain)


def _assert_public_host(host: str) -> None:
    if not host or host in {"localhost", "127.0.0.1", "::1"}:
        raise DatasheetServiceError("Local datasheet URLs are not allowed.")
    try:
        address = ipaddress.ip_address(host)
        if not address.is_global:
            raise DatasheetServiceError("Private datasheet URLs are not allowed.")
        return
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError as exc:
        raise DatasheetServiceError("The official datasheet host could not be resolved.") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise DatasheetServiceError("Private datasheet URLs are not allowed.")


def validate_official_url(url: str, domains: set[str] | list[str]) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise DatasheetServiceError("Only public HTTPS datasheet URLs are accepted.")
    if any(host == suffix or host.endswith(f".{suffix}") for suffix in BLOCKED_DOMAIN_SUFFIXES):
        raise DatasheetServiceError("Third-party datasheet mirrors are not accepted.")
    if not _is_official_host(host, domains):
        raise DatasheetServiceError("The datasheet URL is not on a configured official manufacturer domain.")
    _assert_public_host(host)
    return url


def _unwrap_ddg_url(value: str) -> str | None:
    if value.startswith("//"):
        value = f"https:{value}"
    parsed = urlparse(value)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [None])[0]
        return unquote(target) if target else None
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return value
    return None


def _anchor_parts(page: str):
    for match in re.finditer(r"<a\b([^>]*)>(.*?)</a>", page, re.IGNORECASE | re.DOTALL):
        attrs = match.group(1) or ""
        inner = match.group(2) or ""
        href_match = re.search(r"href\s*=\s*[\"']([^\"']+)[\"']", attrs, re.IGNORECASE)
        if not href_match:
            continue
        yield attrs, html_lib.unescape(href_match.group(1)), inner


def _parse_search_results(page: str) -> list[tuple[str, str]]:
    results = []
    for attrs, href, inner in _anchor_parts(page):
        if "result__a" not in attrs:
            continue
        url = _unwrap_ddg_url(href)
        if not url:
            continue
        title = html_lib.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
        results.append((url, title))
    return results


def _score_candidate(url: str, title: str, part_key: str, domains: set[str] | list[str]) -> int | None:
    url_key = _part_key(url)
    title_key = _part_key(title)
    if part_key not in url_key and part_key not in title_key:
        return None
    host = _host(url)
    if any(host == suffix or host.endswith(f".{suffix}") for suffix in BLOCKED_DOMAIN_SUFFIXES):
        return None
    if not _is_official_host(host, domains):
        return None
    score = 0
    if any(host == domain for domain in domains):
        score += 100
    else:
        score += 80
    path = urlparse(url).path.lower()
    if "datasheet" in path or "data-sheet" in path:
        score += 25
    if path.endswith(".pdf"):
        score += 35
    if "pdf" in title.lower():
        score += 10
    if part_key in url_key:
        score += 15
    return score


def candidate_from_url(url: str, title: str = "Verified datasheet URL") -> DatasheetCandidate:
    return DatasheetCandidate(
        url=url,
        title=title,
        source_domain=_host(url),
        score=100,
        filename=Path(urlparse(url).path).name or None,
    )


def coerce_candidate(value: DatasheetCandidate | dict[str, Any]) -> DatasheetCandidate:
    if isinstance(value, DatasheetCandidate):
        return value
    return DatasheetCandidate.from_dict(value)


def search_official_datasheets(
    manufacturer: str,
    part_number: str,
    client: httpx.Client | Any | None = None,
) -> list[DatasheetCandidate]:
    manufacturer = manufacturer.strip()
    part_number = part_number.strip()
    if not manufacturer or not part_number:
        return []
    domains = official_domains_for(manufacturer)
    if not domains:
        raise DatasheetServiceError("No official datasheet source is configured for this manufacturer.")

    query = f'"{part_number}" datasheet ' + " OR ".join(f"site:{domain}" for domain in domains)
    client = client or httpx.Client()
    try:
        response = client.get(
            SEARCH_URL,
            params={"q": query, "kl": "us-en"},
            headers={"User-Agent": USER_AGENT},
            timeout=load_settings().datasheet_search_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        logger.warning("Official datasheet search failed: %s", exc)
        raise DatasheetServiceError("Official datasheet search is unavailable right now.") from exc

    if response.status_code >= 400:
        raise DatasheetServiceError("Official datasheet search is unavailable right now.")

    part_key = _part_key(part_number)
    candidates = []
    for url, title in _parse_search_results(response.text):
        score = _score_candidate(url, title, part_key, domains)
        if score is None:
            continue
        candidates.append(
            DatasheetCandidate(
                url=url,
                title=title,
                source_domain=_host(url),
                score=score,
                filename=Path(urlparse(url).path).name or None,
            )
        )
    return sorted(candidates, key=lambda item: (-item.score, item.url))[:8]


def _looks_like_pdf(data: bytes) -> bool:
    return data[:1024].find(b"%PDF-") != -1


def _looks_like_html(data: bytes) -> bool:
    sample = data[:512].lstrip().lower()
    return sample.startswith(b"<!doctype") or sample.startswith(b"<html")


def _fetch_resource(
    client: httpx.Client | Any,
    url: str,
    domains: set[str] | list[str],
) -> FetchedResource:
    validate_official_url(url, domains)
    settings = load_settings()
    chunks: list[bytes] = []
    total = 0
    try:
        with client.stream(
            "GET",
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.1"},
            timeout=settings.datasheet_download_timeout_seconds,
            follow_redirects=True,
        ) as response:
            if response.status_code >= 400:
                raise DatasheetServiceError(f"The official datasheet source returned HTTP {response.status_code}.")
            final_url = str(getattr(response, "url", url))
            validate_official_url(final_url, domains)
            headers = {str(key).lower(): str(value) for key, value in dict(response.headers or {}).items()}
            declared_length = headers.get("content-length")
            if declared_length and declared_length.isdigit() and int(declared_length) > settings.datasheet_max_download_bytes:
                raise DatasheetServiceError("The official datasheet exceeds the local download size limit.")
            for chunk in response.iter_bytes(chunk_size=65536):
                total += len(chunk)
                if total > settings.datasheet_max_download_bytes:
                    raise DatasheetServiceError("The official datasheet exceeds the local download size limit.")
                chunks.append(chunk)
    except httpx.HTTPError as exc:
        logger.warning("Official datasheet download failed for %s: %s", url, exc)
        raise DatasheetServiceError("The official datasheet could not be downloaded.") from exc
    return FetchedResource(b"".join(chunks), final_url, headers)


def _filename_from_headers(headers: dict[str, str], url: str, fallback: str) -> str:
    disposition = headers.get("content-disposition", "")
    match = re.search(r"filename\*?=(?:UTF-8''|\")?([^\";]+)", disposition, re.IGNORECASE)
    if match:
        candidate = unquote(match.group(1)).strip().strip("'")
    else:
        candidate = Path(urlparse(url).path).name or fallback
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(candidate).name).strip("._")
    if not safe:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(fallback).name).strip("._") or "datasheet"
    if not safe.lower().endswith(".pdf"):
        safe = f"{safe}.pdf"
    return safe[:180]


def _extract_pdf_links(page: str, base_url: str, part_key: str, domains: set[str] | list[str]) -> list[str]:
    candidates = []
    for _attrs, href, inner in _anchor_parts(page):
        url = urljoin(base_url, html_lib.unescape(href))
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not _is_official_host(_host(url), domains):
            continue
        path = parsed.path.lower()
        title = html_lib.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
        is_pdf_path = path.endswith(".pdf") or "pdf" in path or "datasheet" in path
        if not is_pdf_path:
            continue
        if part_key not in _part_key(url) and part_key not in _part_key(title):
            continue
        score = 0 if path.endswith(".pdf") else 10
        if "datasheet" in path:
            score += 5
        candidates.append((score, url))
    return [url for _score, url in sorted(candidates, key=lambda item: (item[0], item[1]))]


def _fetch_pdf_from_candidate(
    candidate: DatasheetCandidate,
    part_number: str,
    domains: set[str] | list[str],
    client: httpx.Client | Any,
) -> FetchedPdf:
    part_key = _part_key(part_number)
    fallback = candidate.filename or f"{part_number}.pdf"
    resource = _fetch_resource(client, candidate.url, domains)
    if _looks_like_pdf(resource.data):
        return FetchedPdf(
            data=resource.data,
            filename=_filename_from_headers(resource.headers, resource.final_url, fallback),
            source_url=resource.final_url,
        )
    if not _looks_like_html(resource.data):
        raise DatasheetServiceError("The official source did not provide a verified PDF.")

    for link in _extract_pdf_links(resource.text, resource.final_url, part_key, domains):
        pdf_resource = _fetch_resource(client, link, domains)
        if _looks_like_pdf(pdf_resource.data):
            return FetchedPdf(
                data=pdf_resource.data,
                filename=_filename_from_headers(pdf_resource.headers, pdf_resource.final_url, fallback),
                source_url=pdf_resource.final_url,
            )
    raise DatasheetServiceError("The official source did not expose a verified PDF download link.")


def _find_existing_download(db: Session, source_url: str) -> DatasheetDownload | None:
    key = _source_key(source_url)
    return (
        db.query(DatasheetDownload)
        .filter(
            DatasheetDownload.source_key == key,
            DatasheetDownload.download_status.in_(["downloaded", "duplicate"]),
        )
        .order_by(DatasheetDownload.id.desc())
        .first()
    )


def _create_attempt(
    db: Session,
    manufacturer: str,
    part_number: str,
    source_url: str,
    filename: str,
) -> DatasheetDownload:
    attempt = DatasheetDownload(
        manufacturer=manufacturer.strip(),
        part_number=part_number.strip(),
        source_url=source_url,
        source_key=_source_key(source_url),
        filename=filename,
        download_status="downloading",
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt


def _result_from_record(record: DatasheetDownload, message: str, is_duplicate: bool) -> DatasheetDownloadResult:
    return DatasheetDownloadResult(
        download_id=record.id,
        document_id=record.document_id,
        source_url=record.source_url,
        filename=record.filename,
        download_status="duplicate" if is_duplicate else record.download_status,
        sha256=record.sha256 or "",
        is_duplicate=is_duplicate,
        message=message,
    )


def download_official_datasheet(
    db: Session,
    candidates: list[DatasheetCandidate | dict[str, Any]],
    manufacturer: str,
    part_number: str,
    client: httpx.Client | Any | None = None,
) -> DatasheetDownloadResult:
    domains = official_domains_for(manufacturer)
    if not domains:
        raise DatasheetServiceError("No official datasheet source is configured for this manufacturer.")

    client = client or httpx.Client()
    last_error = "No official datasheet candidate could be downloaded."
    normalized_candidates = [coerce_candidate(candidate) for candidate in candidates]
    for candidate in normalized_candidates:
        existing = _find_existing_download(db, candidate.url)
        if existing and existing.document_id and db.get(Document, existing.document_id):
            return _result_from_record(existing, "Official datasheet was already downloaded.", True)

        attempt = _create_attempt(
            db,
            manufacturer,
            part_number,
            candidate.url,
            candidate.filename or f"{part_number}.pdf",
        )
        try:
            fetched = _fetch_pdf_from_candidate(candidate, part_number, domains, client)
            ingested = ingest_pdf_bytes(fetched.data, fetched.filename, db)
            if fetched.source_url != attempt.source_url:
                attempt.source_url = fetched.source_url
                attempt.source_key = _source_key(fetched.source_url)
            attempt.filename = fetched.filename
            attempt.download_status = "duplicate" if ingested.is_duplicate else "downloaded"
            attempt.sha256 = ingested.document.sha256
            attempt.document_id = ingested.document.id
            attempt.error_message = None
            db.commit()
            db.refresh(attempt)
            message = (
                "Official datasheet matched an existing document."
                if ingested.is_duplicate
                else "Official datasheet downloaded and verified."
            )
            return _result_from_record(attempt, message, ingested.is_duplicate)
        except (DatasheetServiceError, DocumentIngestError) as exc:
            last_error = str(exc)
            attempt.download_status = "failed"
            attempt.error_message = last_error
            db.commit()
            logger.warning("Official datasheet attempt failed for %s: %s", candidate.url, last_error)

    raise DatasheetServiceError(last_error)


def download_verified_datasheet(
    db: Session,
    url: str,
    manufacturer: str,
    part_number: str,
    client: httpx.Client | Any | None = None,
) -> DatasheetDownloadResult:
    return download_official_datasheet(
        db,
        [candidate_from_url(url)],
        manufacturer,
        part_number,
        client,
    )


def download_to_dict(record: DatasheetDownload) -> dict[str, Any]:
    return {
        "id": record.id,
        "manufacturer": record.manufacturer,
        "part_number": record.part_number,
        "source_url": record.source_url,
        "filename": record.filename,
        "download_status": record.download_status,
        "sha256": record.sha256,
        "document_id": record.document_id,
        "error_message": record.error_message,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def list_downloads(db: Session) -> list[DatasheetDownload]:
    return db.query(DatasheetDownload).order_by(DatasheetDownload.created_at.desc()).all()
