"""Sample client for downloading PMC BioC JSON and restructuring content.

This script calls the NCBI BioC REST endpoint, normalizes the response into a
compact article structure, and writes one JSON file per PMC ID under
``pmc_articles/``.

It is intended as an integration smoke test for:
- External API connectivity and response shape.
- Basic section/title extraction logic from BioC passages.
- Local serialization of transformed article data.
"""

import requests
import json
import time
from pathlib import Path

# -----------------------------
# Configuration
# -----------------------------
pmc_ids = [
    4049904, 11089781, 1351071, 1627071,
    5767866, 6128885, 10031415,
    9368379, 6109114, 12062735
]

BASE_URL = "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json"
OUTPUT_DIR = Path("pmc_articles")
OUTPUT_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "PMC-FullText-Downloader/1.0 (your_email@example.com)"
}

# -----------------------------
# Fetch BioC JSON
# -----------------------------
def fetch_bioc_json(pmc_id: str):
    """Fetch BioC JSON payload for a single PMC identifier.

    Args:
        pmc_id: Identifier in ``PMC<digits>`` format.

    Returns:
        Parsed JSON object on success, otherwise ``None``.
    """
    url = f"{BASE_URL}/{pmc_id}/unicode"
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)

        if response.status_code == 200:
            try:
                data = response.json()
                return data
            except json.JSONDecodeError:
                print(f"[ERROR] {pmc_id} -> Invalid JSON response")
                print(f"[ERROR] Response preview: {response.text[:200]}")
                return None
        else:
            print(f"[ERROR] {pmc_id} -> Status {response.status_code}")
            print(f"[ERROR] Response: {response.text[:200]}")
            return None
    except Exception as e:
        print(f"[ERROR] {pmc_id} -> Exception: {str(e)}")
        return None


# -----------------------------
# Parse BioC to structured article
# -----------------------------
def parse_bioc_structure(bioc_json):
    """Transform raw BioC JSON into a simplified article dictionary.

    The parser is defensive against multiple response shapes (list vs dict) and
    builds an output document with:
    - ``pmc_id``
    - ``title``
    - ordered ``sections`` containing section title and concatenated text.

    Args:
        bioc_json: Raw decoded JSON response from the BioC endpoint.

    Returns:
        A normalized article dictionary suitable for file export.
    """
    # Handle different response structures
    if isinstance(bioc_json, list):
        if len(bioc_json) > 0:
            bioc_json = bioc_json[0]
        else:
            return {"pmc_id": "", "title": "", "sections": []}
    
    if not isinstance(bioc_json, dict) or "documents" not in bioc_json:
        print(f"[WARNING] Unexpected structure. Type: {type(bioc_json)}")
        if isinstance(bioc_json, dict):
            print(f"[WARNING] Keys: {list(bioc_json.keys())}")
        return {"pmc_id": "", "title": "", "sections": []}
    
    if len(bioc_json["documents"]) == 0:
        return {"pmc_id": "", "title": "", "sections": []}
    
    document = bioc_json["documents"][0]

    article = {
        "pmc_id": document.get("id"),
        "title": "",
        "sections": []
    }

    current_section = None

    for passage in document.get("passages", []):
        infons = passage.get("infons", {})
        text = passage.get("text", "").strip()
        
        if not text:
            continue

        # Detect title from section_type or type
        section_type = infons.get("section_type", "")
        passage_type = infons.get("type", "")
        
        if section_type == "TITLE" or passage_type == "title":
            article["title"] = text
            continue

        # Detect section headings
        if section_type and section_type not in ["TITLE", "ABSTRACT"]:
            if current_section:
                article["sections"].append(current_section)

            current_section = {
                "section_title": text if len(text) < 100 else text[:100] + "...",
                "text": ""
            }
        elif section_type == "ABSTRACT":
            if not current_section:
                current_section = {
                    "section_title": "Abstract",
                    "text": ""
                }
            current_section["text"] += text + "\n"
        else:
            # Regular paragraph text
            if current_section:
                current_section["text"] += text + "\n"
            else:
                # If no section yet, create a default one
                current_section = {
                    "section_title": "Introduction",
                    "text": text + "\n"
                }

    if current_section:
        article["sections"].append(current_section)

    return article


# -----------------------------
# Main Download Loop
# -----------------------------
def main():
    """Download, parse, and persist BioC JSON for configured PMC IDs.

    The loop applies a short sleep between requests to respect NCBI rate-limit
    expectations.
    """
    for pmc_id in pmc_ids:
        pmc_str = f"PMC{pmc_id}"
        print(f"Downloading {pmc_str}...")

        bioc = fetch_bioc_json(pmc_str)
        if not bioc:
            continue

        structured_article = parse_bioc_structure(bioc)

        output_file = OUTPUT_DIR / f"{pmc_str}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(structured_article, f, indent=2, ensure_ascii=False)

        print(f"[SAVED] {output_file}")

        # Respect NCBI rate limit
        time.sleep(0.4)


if __name__ == "__main__":
    main()
