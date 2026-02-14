"""
PMC FTP CSV filelist handler.

Fetches and parses CSV filelists from PubMed Central FTP (OA bulk). Supports listing,
downloading, and extracting article identifiers (e.g. AccessionID) for downstream processing.
"""

import csv
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


# Regex for OA baseline filelist CSV filenames in FTP directory listings.
DEFAULT_CSV_PATTERN = re.compile(
    r"oa_.*_xml\.PMC.*\.baseline\..*\.filelist\.csv",
    re.IGNORECASE,
)

# Default OA bulk XML directory URLs (HTTPS listing).
URL_OA_COMM_XML = "https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_bulk/oa_comm/xml/"
URL_OA_NONCOMM_XML = "https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_bulk/oa_noncomm/xml/"


class Ftp_CSV:
    """
    Lists and downloads PMC OA filelist CSVs from FTP; parses CSVs to yield PMC IDs.
    Intended only for CSV filelists that enumerate article filenames (e.g. AccessionID).
    """

    def __init__(
        self,
        url_comm: Optional[str] = None,
        url_noncomm: Optional[str] = None,
        csv_pattern: Optional[re.Pattern] = None,
        session: Optional[requests.Session] = None,
    ):
        self.url_comm = url_comm or URL_OA_COMM_XML
        self.url_noncomm = url_noncomm or URL_OA_NONCOMM_XML
        self.csv_pattern = csv_pattern or DEFAULT_CSV_PATTERN
        self.session = session or requests.Session()
        self.session.headers.setdefault(
            "User-Agent",
            "PMC-CSV-Downloader/1.0 (Python; research use)",
        )

    def _get_csv_links_from_listing(self, base_url: str) -> list[str]:
        """Extract filelist CSV links from an FTP directory HTML listing matching the pattern."""
        try:
            resp = self.session.get(base_url, timeout=60)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise RuntimeError(f"Failed to fetch listing from {base_url}: {e}") from e

        soup = BeautifulSoup(resp.text, "html.parser")
        links: list[str] = []
        for a in soup.find_all("a", href=True):
            href = (a["href"] or "").strip()
            if href and not href.startswith("../") and self.csv_pattern.search(href):
                full_url = urljoin(base_url, href)
                links.append(full_url)
        return links

    def _download_file(self, file_url: str, save_dir: Path) -> Path:
        """Download a single file from URL into save_dir; return path to saved file."""
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        filename = file_url.rstrip("/").split("/")[-1]
        save_path = save_dir / filename

        try:
            resp = self.session.get(file_url, timeout=120, stream=True)
            resp.raise_for_status()
            with open(save_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
        except requests.RequestException as e:
            raise RuntimeError(f"Download failed for {file_url}: {e}") from e
        return save_path

    def download_file_list(self, path: str) -> tuple[list[str], list[str]]:
        """
        Discover filelist CSVs from OA comm/noncomm directories, download all into path.

        Args:
            path: Local directory to save CSV files.

        Returns:
            (commercial CSV URLs, non-commercial CSV URLs).
        """
        save_dir = Path(path)
        list_comm = self._get_csv_links_from_listing(self.url_comm)
        list_noncomm = self._get_csv_links_from_listing(self.url_noncomm)

        for file_url in list_comm:
            self._download_file(file_url, save_dir)
        for file_url in list_noncomm:
            self._download_file(file_url, save_dir)

        return (list_comm, list_noncomm)

    def get_csv_file_list(self, path: str) -> list[str]:
        """
        Return absolute paths of all *.csv files in the given directory (single level).

        Args:
            path: Directory to scan.

        Returns:
            List of absolute path strings.
        """
        folder = Path(path)
        if not folder.is_dir():
            return []
        return [str(p.resolve()) for p in folder.glob("*.csv")]

    def _parse_pmc_id(self, value: str) -> Optional[int]:
        """Parse a string (e.g. 'PMC123' or '123') to integer PMC ID, or None."""
        if value is None or not str(value).strip():
            return None
        s = str(value).strip()
        match = re.search(r"PMC?\s*(\d+)", s, re.IGNORECASE)
        if match:
            return int(match.group(1))
        if s.isdigit():
            return int(s)
        return None

    def get_id_list_from_csv_file(self, csv_file_path: str) -> list[int]:
        """
        Read CSV and return PMC IDs from the identifier column (AccessionID or fallbacks).

        Tries AccessionID, then Article Citation, File, PMCID. Accepts values like PMC123 or 123.
        Deduplicates and preserves order of first occurrence.

        Args:
            csv_file_path: Path to the CSV file.

        Returns:
            List of integer PMC IDs.
        """
        path = Path(csv_file_path)
        if not path.is_file():
            return []

        seen: set[int] = set()
        result: list[int] = []
        id_columns = ("AccessionID", "Article Citation", "File", "PMCID", "pmcid")

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            try:
                reader = csv.DictReader(f)
                if not reader.fieldnames:
                    return []
                id_col = next(
                    (n for n in id_columns if n in (reader.fieldnames or [])),
                    (reader.fieldnames or [None])[0],
                )
                if id_col is None:
                    return []

                for row in reader:
                    raw = row.get(id_col, "")
                    pid = self._parse_pmc_id(raw)
                    if pid is not None and pid not in seen:
                        seen.add(pid)
                        result.append(pid)
            except (csv.Error, UnicodeDecodeError):
                return []

        return result

    def get_pmc_ids(self, directory_path: str) -> list[int]:
        """
        Aggregate PMC IDs from every CSV in the given directory.

        Args:
            directory_path: Directory containing CSV filelists.

        Returns:
            List of PMC IDs (may contain duplicates if an ID appears in multiple files).
        """
        pmc_ids: list[int] = []
        for file_path in self.get_csv_file_list(directory_path):
            ids = self.get_id_list_from_csv_file(file_path)
            pmc_ids.extend(ids)
        return pmc_ids