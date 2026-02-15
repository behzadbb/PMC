"""
Test script for PMC scraper
Can be used to test with saved HTML files or live URLs
"""

import json
import sys
from pmc_scraper import PMCScraper

def _to_serializable(obj):
    """Convert Article or dict to a JSON-serializable dict (safe for file and console)."""
    if hasattr(obj, 'model_dump'):
        return obj.model_dump(mode='json')
    if hasattr(obj, 'dict'):
        try:
            return obj.dict(exclude_none=False)
        except Exception:
            pass
    return obj

def test_live_url(url):
    """Test scraping from a live URL."""
    print(f"Testing live URL: {url}")
    scraper = PMCScraper()
    result = scraper.scrape_article(url)
    
    data = _to_serializable(result) if not isinstance(result, dict) else result
    if isinstance(data, dict) and 'error' in data:
        print("Error:", data.get("error", data))
        return result

    print("\n" + "="*50)
    print("Results (key fields):")
    print("="*50)
    for key in ('Title', 'title', 'Journal', 'journal', 'ISSN', 'issn', 'PMCID', 'pmcid', 'source'):
        if isinstance(data, dict) and key in data and data[key] is not None:
            print(f"  {key}: {data[key]}")
    print("\nFull JSON saved to test_output.json")

    output_file = 'test_output.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    print(f"Results saved to: {output_file}")
    return result

def test_from_file(file_path, url=None):
    """Test scraping from a saved HTML file."""
    print(f"Testing from file: {file_path}")
    scraper = PMCScraper()
    result = scraper.scrape_from_file(file_path, url)
    
    data = _to_serializable(result) if not isinstance(result, dict) else result
    print("\n" + "="*50)
    print("Results (key fields):")
    print("="*50)
    for key in ('Title', 'title', 'Journal', 'journal', 'ISSN', 'issn', 'PMCID', 'pmcid', 'source'):
        if isinstance(data, dict) and key in data and data[key] is not None:
            print(f"  {key}: {data[key]}")
    print("\nFull JSON saved to test_output.json")

    output_file = 'test_output.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    print(f"Results saved to: {output_file}")
    return result

if __name__ == '__main__':
    if len(sys.argv) > 1:
        if sys.argv[1].startswith('http'):
            # URL provided
            test_live_url(sys.argv[1])
        else:
            # File path provided
            url = sys.argv[2] if len(sys.argv) > 2 else None
            test_from_file(sys.argv[1], url)
    else:
        # Default test
        print("Usage:")
        print("  python test_scraper.py <URL>")
        print("  python test_scraper.py <file_path> [URL]")
        print("\nRunning default test...")
        test_url = "https://pmc.ncbi.nlm.nih.gov/articles/PMC4049904/"
        test_live_url(test_url)
