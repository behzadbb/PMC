"""
Test script for PMC scraper
Can be used to test with saved HTML files or live URLs
"""

import json
import sys
from pmc_scraper import PMCScraper

def test_live_url(url):
    """Test scraping from a live URL."""
    print(f"Testing live URL: {url}")
    scraper = PMCScraper()
    result = scraper.scrape_article(url)
    
    print("\n" + "="*50)
    print("Results:")
    print("="*50)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # Save to file
    output_file = 'test_output.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {output_file}")
    
    return result

def test_from_file(file_path, url=None):
    """Test scraping from a saved HTML file."""
    print(f"Testing from file: {file_path}")
    scraper = PMCScraper()
    result = scraper.scrape_from_file(file_path, url)
    
    print("\n" + "="*50)
    print("Results:")
    print("="*50)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # Save to file
    output_file = 'test_output.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to: {output_file}")
    
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
