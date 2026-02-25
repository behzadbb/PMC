"""
Import filtered PMC JSON from .json.tar.gz files into SQL Server:
- Books table: one row per article (Article object map). Column names loaded from DB.
- Segments table: one row per full-text section (Article.Full_Text_Sections).

Schema (from SQL Server):
  Books: BookId (IDENTITY PK), Category, Keyword, Title, Authors, Year, Doi, Issn,
         Issue, Journal, PmId, PmcId, Summary, Article, ... (NOT NULL: Category, Keyword, Article)
  Segments: SegmentId (IDENTITY PK), Title, Text, BookId (FK to Books.BookId), ...
"""

import json
import os
import tarfile
from datetime import datetime
from pathlib import Path

import sqlalchemy
from sqlalchemy import text
from tqdm import tqdm

from DTO.Article import Article


sql_server_username = "sa"
sql_server_password = "12345678"
sql_server_server = "56.54.50.20"
sql_server_port = 13790
sql_server_database = "pharma"

# Connection string: use port in server string if required, e.g. server,port
sql_server_connection = sqlalchemy.create_engine(
    f"mssql+pyodbc://{sql_server_username}:{sql_server_password}@"
    f"{sql_server_server}:{sql_server_port}/{sql_server_database}"
    "?driver=ODBC+Driver+17+for+SQL+Server"
)


def _article_to_books_row(article: Article) -> dict:
    """Map Article fields to Books table columns (dbo.Books schema from SQL Server)."""
    return {
        "Category": "PMC",
        "Keyword": (article.Keywords or "")[: 4000] if article.Keywords else "",
        "Title": article.Title,
        "Authors": article.Authors,
        "Year": str(article.Year) if article.Year is not None else None,
        "Doi": article.DOI,
        "Issn": article.ISSN,
        "Issue": str(article.Issue) if article.Issue is not None else None,
        "Journal": (article.Journal or "")[:500] if article.Journal else None,
        "PmId": article.PMID,
        "PmcId": article.PMCID,
        "Summary": article.Abstract,  # Summary = Abstract
        "Article": 1,  # always 1: all imported rows are articles
        "IsTest": 0,
        "AddedDateTime": datetime.now(),
    }


def load_articles_from_tar_gz(json_file_path: Path) -> list[Article]:
    """Extract JSON array from .json.tar.gz and return list of Article instances."""
    articles: list[Article] = []
    with tarfile.open(json_file_path, "r:gz") as tar:
        member = next((m for m in tar.getmembers() if m.name.endswith(".json")), None)
        if member is None:
            return articles
        with tar.extractfile(member) as f:
            data = json.load(f)
        if not isinstance(data, list):
            data = [data]
        for record in data:
            try:
                articles.append(Article.model_validate(record))
            except Exception:
                pass
    return articles


# SQL: insert into Books (dbo.Books) and get BookId; then insert Segments (dbo.Segments).
# Column names from SQL Server: Books.Category, Keyword, Title, Authors, Year, Doi, Issn, Issue, Journal, PmId, PmcId, Summary, Article.
INSERT_BOOKS = text("""
    INSERT INTO dbo.Books (
        Category, Keyword, Title, Authors, Year, Doi, Issn, Issue, Journal,
        PmId, PmcId, Summary, Article, IsTest, AddedDateTime
    ) VALUES (
        :Category, :Keyword, :Title, :Authors, :Year, :Doi, :Issn, :Issue, :Journal,
        :PmId, :PmcId, :Summary, :Article, :IsTest, :AddedDateTime
    );
    SELECT SCOPE_IDENTITY() AS BookId;
""")

# Segments: one row per article with merged full-text (section_title:\ntext\n\n...).
INSERT_SEGMENTS = text("""
    INSERT INTO dbo.Segments (BookId, Title, Text)
    VALUES (:BookId, :Title, :Text);
""")


def _merge_full_text_sections(sections: dict[str, str]) -> str:
    """Merge all sections into one full-text: 'section_title 1:\ntext 1\n\nsection_title 2:\ntext 2\n\n...'."""
    if not sections:
        return ""
    parts = []
    for section_title, content in sections.items():
        title = section_title or ""
        text = content or ""
        parts.append(f"{title}:\n{text}")
    return "\n\n".join(parts)


def insert_article(conn, article: Article) -> None:
    """Insert one article into Books and one merged full-text row into Segments."""
    row = _article_to_books_row(article)
    result = conn.execute(INSERT_BOOKS, row)
    book_id = result.scalar()
    if book_id is None:
        return
    book_id = int(book_id)

    full_text = _merge_full_text_sections(article.Full_Text_Sections or {})
    conn.execute(
        INSERT_SEGMENTS,
        {
            "BookId": book_id,
            "Title": "Full text",
            "Text": full_text,
        },
    )


def main() -> None:
    if os.name == "posix":
        base_path = Path("/home/breg/pmc_2026")
        save_filtered_directory_path = base_path / "filtered_json_gz"
    elif os.name == "nt":
        base_path = Path("D:/PMC/Dataset/2026")
        save_filtered_directory_path = base_path / "filtered_json_gz"
    else:
        base_path = Path("/home/breg/pmc_2026")
        save_filtered_directory_path = base_path / "filtered_json_gz"

    print(f"Using {base_path} as base path")
    json_gz_filtered_files = list(save_filtered_directory_path.glob("**/*.json.tar.gz"))
    print(f"Found {len(json_gz_filtered_files)} .json.tar.gz files to process")

    articles: list[Article] = []
    for json_file_path in tqdm(json_gz_filtered_files, desc="Loading JSON"):
        articles.extend(load_articles_from_tar_gz(json_file_path))

    print(f"Loaded {len(articles)} articles. Inserting into Books and Segments...")
    with sql_server_connection.begin() as conn:
        for article in tqdm(articles, desc="Inserting"):
            try:
                insert_article(conn, article)
            except Exception as e:
                print(f"Skip article (PMCID={getattr(article, 'PMCID', None)}): {e}")
    print("Done.")


if __name__ == "__main__":
    main()
