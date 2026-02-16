import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from DTO.Article import Article
from pmc_scraper import PMCScraper

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Optional: also write to a log file for monitoring
_log_path = Path(__file__).parent / "download_pmc.log"
_file_handler = logging.FileHandler(_log_path, encoding="utf-8")
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
logger.addHandler(_file_handler)

scraper = PMCScraper()
directory_path = Path("D:/PMC/Dataset/2026")

pmc_ids_not_found_path = directory_path / "pmc_ids_not_found.txt"
pmc_ids_path = directory_path / "pmc_id_parts"
pmc_articles_path = directory_path / "pmc_articles_not_found_files"
exclusion_keywords_ids_path = directory_path / "PMC safe-exclusion keywords.csv"

logger.info("Starting download_pmc: loading keywords and paths")
try:
    try:
        keywords_df = pd.read_csv(exclusion_keywords_ids_path, encoding="utf-8")
    except UnicodeDecodeError:
        keywords_df = pd.read_csv(exclusion_keywords_ids_path, encoding="latin-1")
    Keywords = keywords_df["Keyword"].dropna().astype(str).str.strip().tolist()
    logger.info("Loaded %d exclusion keywords from %s", len(Keywords), exclusion_keywords_ids_path)
except Exception as e:
    logger.exception("Error loading keywords")
    raise

try:
    pmc_articles_path.mkdir(parents=True, exist_ok=True)
    logger.debug("Output directory ready: %s", pmc_articles_path)
except Exception as e:
    logger.exception("Error creating directory")
    raise

try:
    file_path_list = sorted(pmc_ids_path.glob("*.txt"))
    if not file_path_list:
        raise FileNotFoundError(f"No .txt files found in {pmc_ids_path}")
    logger.info("Found %d PMC ID files in %s", len(file_path_list), pmc_ids_path)
except Exception as e:
    logger.exception("Error listing PMC ID files")
    raise

start_download_index = 0
end_download_index = 1

articles = []
logger.info("Processing batch index range [%s, %s)", start_download_index, end_download_index)

for i in range(start_download_index, end_download_index):
    pmc_file_path = file_path_list[i]
    logger.info("Processing file %s (batch index %s)", pmc_file_path.name, i)
    try:
        with open(pmc_file_path, "r", encoding="utf-8") as f:
            pmc_ids = [line.strip() for line in f if line.strip()]
        logger.debug("Read %d IDs from %s", len(pmc_ids), pmc_file_path.name)
    except Exception as e:
        logger.error("Error reading %s: %s", pmc_file_path, e)
        continue

    pmc_ids = pmc_ids[:100]
    for pmc_id in tqdm(pmc_ids):
        try:
            url = f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{pmc_id}/"
            print(f"Scraping URL: {url}")
            article = scraper.scrape_article(url)
            if not isinstance(article, Article):
                logger.warning("Skipped pmc_id %s (scraper returned no article)", pmc_id)
            elif (article.Title is not None and
                  article.Abstract is not None and
                  not any(keyword in article.Abstract for keyword in Keywords)):
                articles.append(article)
                logger.debug("Added article pmc_id=%s", pmc_id)
            else:
                logger.warning("Skipped pmc_id %s (missing title/abstract or keyword match)", pmc_id)
        except Exception as e:
            logger.error("Error scraping pmc_id %s: %s", pmc_id, e, exc_info=True)

    json_path = pmc_articles_path / f"pmc_articles_{i}.json"
    def to_dict(a):
        if isinstance(a, dict):
            return a
        if hasattr(a, "model_dump"):
            return a.model_dump(mode="json")
        return a.dict(exclude_none=False)

    def json_default(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump([to_dict(a) for a in articles], f, indent=2, ensure_ascii=False, default=json_default)
        logger.info("Saved batch %s: %d articles to %s", i, len(articles), json_path.name)
    except Exception as e:
        logger.exception("Error saving %s", json_path)
    articles.clear()

logger.info("Download run finished")