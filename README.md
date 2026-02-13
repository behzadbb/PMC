# PMC Scraper

A Python project for downloading, parsing, and transforming PubMed Central (PMC) articles from multiple data sources.

The repository supports both single-article retrieval and large archive processing, with a unified output model based on the `Article` DTO.

## Overview

The project can ingest article data from:

- PMC article HTML pages
- NCBI E-utilities XML API
- FTP `tar.gz` archives containing XML files
- BioC JSON API (for structure-focused testing)

Parsed outputs can be serialized to JSON for downstream processing.

## Key Features

- Extract core metadata: `PMCID`, `PMID`, `DOI`, title, authors, journal, year, volume, issue
- Extract content data: abstract, keywords, and full-text sections
- Map all parsed fields to a single Pydantic contract: `DTO/Article.py`
- Process large FTP archives incrementally to reduce memory usage
- Use fallback retrieval paths for access-restricted cases (`403`/`401`)

## Project Structure

```text
pmc_scraper/
├─ DTO/
│  └─ Article.py               # Canonical Article data contract (Pydantic)
├─ Services/
│  ├─ Api_XML.py               # NCBI XML API ingestion -> Article
│  └─ Ftp_XML.py               # FTP tar.gz XML processing -> Article/JSON
├─ pmc_scraper.py              # Main scraper (HTML + XML + fallback strategies)
├─ fetch_bioc_json.py          # BioC JSON API → structured export
├─ fetch_api_xml.py            # NCBI XML API → Article DTO
├─ convert_tar_to_json.py      # tar.gz archive → JSON
├─ load_pmc_ids.py             # Load PMC article IDs (config)
└─ test_scraper.py             # Additional test script(s)
```

## Requirements

- Python 3.10+
- Internet access to NCBI/PMC services
- Dependencies listed in `requirements.txt`

Install dependencies:

```bash
pip install -r requirements.txt
```

## Quick Start

### 1) Run the main scraper

```bash
python pmc_scraper.py
```

This runs a batch workflow over predefined PMC IDs and stores output JSON files in `articles/`.

### 2) BioC JSON API flow

```bash
python fetch_bioc_json.py
```

Output files are written to `pmc_articles/`.

### 3) XML API to DTO flow

```bash
python fetch_api_xml.py
```

Fetches one article from XML API, converts to `Article`, writes JSON.

### 4) Convert FTP `tar.gz` to JSON

Update the archive path in `convert_tar_to_json.py`, then run:

```bash
python convert_tar_to_json.py
```

## Programmatic Usage

### Main `PMCScraper` flow

```python
from pmc_scraper import PMCScraper

scraper = PMCScraper()
result = scraper.scrape_article("https://pmc.ncbi.nlm.nih.gov/articles/PMC4049904/")

if isinstance(result, dict) and "error" in result:
    print("failed:", result["error"])
else:
    print(result.Title, result.PMCID)
```

### XML API service

```python
from Services.Api_XML import Api_XML

service = Api_XML()
article = service.get_article_from_xml(6109114)
print(article.Title, article.source)  # source = 2
```

### FTP archive service

```python
from Services.Ftp_XML import Ftp_XML

ftp_service = Ftp_XML()
count = ftp_service.convert_tar_gz_to_json("path/to/archive.tar.gz")
print("converted:", count)
```

## Data Flow

1. **Ingestion**: Retrieve data from HTML, API, or FTP sources
2. **Parsing**: Extract fields with `BeautifulSoup` or `lxml`
3. **Transformation**: Map extracted data to `Article`
4. **Serialization**: Persist records to JSON

## Output Model

The canonical output model is defined in `DTO/Article.py` and includes:

- Identifiers: `PMCID`, `PMID`, `DOI`
- Bibliographic metadata: `Title`, `Year`, `Journal`, `Volume`, `Issue`
- Content fields: `Abstract`, `Keywords`, `Full_Text_Sections`
- Review/status fields: `s1_*`, `s2_*`, `s3_*`
- Source/error fields: `source`, `error_message`

## Operational Notes

- Request pacing is applied to reduce rate-limit risk.
- If HTML scraping fails, fallback paths (XML/API/FTP/OAI/Selenium) are attempted.
- Large FTP archives are processed via generators to keep memory stable.
- If Selenium is unavailable, browser-dependent fallbacks are skipped automatically.

## Known Limitations

- Changes in PMC HTML/XML structure may affect extraction quality.
- Some articles do not contain all metadata fields; `None` values are expected.
- For very large workloads, staged processing and resource monitoring are recommended.

## Compliance

This project is intended for research and analysis use cases. Follow NCBI/PMC terms, request-rate constraints, and data access policies.
