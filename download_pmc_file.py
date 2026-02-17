import re
from pathlib import Path

import requests
from tqdm import tqdm

download_directory_path = Path("/media/breg/adata_512/pmc_2026/")
download_directory_path.mkdir(parents=True, exist_ok=True)

fpt_openaccess_comm_xml_url = "https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_bulk/oa_comm/xml/"
fpt_openaccess_noncomm_xml_url = "https://ftp.ncbi.nlm.nih.gov/pub/pmc/oa_bulk/oa_noncomm/xml/"

# Match links like oa_*_xml.PMC*.baseline.*.tar.gz
pattern = re.compile(r"oa_.*_xml\.PMC.*\.baseline\..*\.tar\.gz$")


def get_tar_gz_links(url: str) -> list[str]:
    """Fetch FTP listing page and return all href links matching the tar.gz pattern."""
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch {url}: {e}") from e

    # FTP directory listings use <a href="filename">; extract href values
    link_pattern = re.compile(r'href=["\']([^"\']+)["\']')
    hrefs = link_pattern.findall(resp.text)
    links = []
    for href in hrefs:
        # Resolve relative links (e.g. "oa_comm_xml.PMC123.baseline.2024.1.tar.gz")
        name = href.strip()
        if pattern.search(name):
            full_url = url.rstrip("/") + "/" + name.lstrip("/")
            links.append(full_url)
    return links


def download_file(url: str, path: Path) -> None:
    """Download url to path with streaming and progress bar."""
    try:
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        with open(path, "wb") as f:
            with tqdm(total=total, unit="B", unit_scale=True, desc=path.name, leave=False) as pbar:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))
    except requests.RequestException as e:
        raise RuntimeError(f"Download failed for {url}: {e}") from e


try:
    _links_comm = get_tar_gz_links(fpt_openaccess_comm_xml_url)
except Exception as e:
    print(f"Error getting comm links: {e}")
    _links_comm = []

try:
    _links_noncomm = get_tar_gz_links(fpt_openaccess_noncomm_xml_url)
except Exception as e:
    print(f"Error getting noncomm links: {e}")
    _links_noncomm = []

links = []
links.extend(_links_comm)
links.extend(_links_noncomm)

print(f"Extract {len(links)} links from PMC FTP Website.")

for link in tqdm(links, desc="Download tar gz files"):
    try:
        file_name = link.split("/")[-1]
        download_path = download_directory_path / file_name
        if download_path.exists():
            print(f"File {download_path} already exists, skipping download")
            continue
        download_file(link, download_path)
    except Exception as e:
        print(f"Error processing {link}: {e}")
