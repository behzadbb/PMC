"""
Import filtered PMC JSON from .json.tar.gz files into SQL Server:
- Books table: one row per article (Article object map). Column names loaded from DB.
- Segments table: one row per full-text section (Article.Full_Text_Sections).

Schema (from SQL Server):
  Books: BookId (IDENTITY PK), Category, Keyword, Title, Authors, Year, Doi, Issn,
         Issue, Journal, PmId, PmcId, Summary, Article, ... (NOT NULL: Category, Keyword, Article)
  Segments: SegmentId (IDENTITY PK), Title, Text, BookId (FK to Books.BookId), ...

On Linux, install ODBC driver before running (e.g. Ubuntu/Debian):
  sudo apt-get install unixodbc unixodbc-dev
  # Then install Microsoft ODBC Driver 17: https://docs.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server
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

# Connection string and fast_executemany for much faster batch inserts
try:
    sql_server_connection = sqlalchemy.create_engine(
        f"mssql+pyodbc://{sql_server_username}:{sql_server_password}@"
        f"{sql_server_server}:{sql_server_port}/{sql_server_database}"
        "?driver=ODBC+Driver+17+for+SQL+Server",
        connect_args={"fast_executemany": True},
    )
except ImportError as e:
    if "libodbc" in str(e) or "pyodbc" in str(e):
        raise SystemExit(
            "ODBC driver not found. On Linux install unixODBC and Microsoft ODBC Driver 17, e.g.\n"
            "  Ubuntu/Debian: sudo apt-get install unixodbc unixodbc-dev\n"
            "  Then: https://docs.microsoft.com/en-us/sql/connect/odbc/linux-mac/install-microsoft-odbc-driver-sql-server-linux"
        ) from e
    raise


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


# Batch size for bulk insert (fewer round-trips = faster)
BATCH_SIZE = 500

# Column order for Books batch INSERT (must match VALUES placeholders)
_BOOKS_COLS = [
    "Category", "Keyword", "Title", "Authors", "Year", "Doi", "Issn", "Issue",
    "Journal", "PmId", "PmcId", "Summary", "Article", "IsTest", "AddedDateTime",
]

# Single-row insert (fallback or small remainder)
INSERT_BOOKS_ONE = text("""
    INSERT INTO dbo.Books (
        Category, Keyword, Title, Authors, Year, Doi, Issn, Issue, Journal,
        PmId, PmcId, Summary, Article, IsTest, AddedDateTime
    ) VALUES (
        :Category, :Keyword, :Title, :Authors, :Year, :Doi, :Issn, :Issue, :Journal,
        :PmId, :PmcId, :Summary, :Article, :IsTest, :AddedDateTime
    );
    SELECT SCOPE_IDENTITY() AS BookId;
""")

INSERT_SEGMENTS_ONE = text("""
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


def _books_row_to_flat(row: dict) -> list:
    """Convert a Books row dict to a flat list in _BOOKS_COLS order (for batch INSERT)."""
    return [row[k] for k in _BOOKS_COLS]


def _insert_article_one(conn, article: Article, cursor) -> None:
    """Insert one article (Books + Segments). Used for fallback or remainder."""
    row = _article_to_books_row(article)
    if cursor is not None:
        # Raw pyodbc: use ? placeholders
        cursor.execute(
            "INSERT INTO dbo.Books (Category, Keyword, Title, Authors, Year, Doi, Issn, Issue, Journal, PmId, PmcId, Summary, Article, IsTest, AddedDateTime) "
            "OUTPUT INSERTED.BookId VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            _books_row_to_flat(row),
        )
        book_id = cursor.fetchone()[0]
    else:
        result = conn.execute(INSERT_BOOKS_ONE, row)
        book_id = result.scalar()
    if book_id is None:
        return
    book_id = int(book_id)
    full_text = _merge_full_text_sections(article.Full_Text_Sections or {})
    if cursor is not None:
        cursor.execute(
            "INSERT INTO dbo.Segments (BookId, Title, Text) VALUES (?,?,?)",
            (book_id, "Full text", full_text),
        )
    else:
        conn.execute(INSERT_SEGMENTS_ONE, {"BookId": book_id, "Title": "Full text", "Text": full_text})


def _insert_articles_batch(conn, articles: list[Article], cursor) -> None:
    """Insert a batch of articles: one bulk Books INSERT with OUTPUT, then bulk Segments."""
    if not articles:
        return
    batch_dt = datetime.now()
    book_rows = [_article_to_books_row(a) for a in articles]
    full_texts = [_merge_full_text_sections(a.Full_Text_Sections or {}) for a in articles]
    # Use same AddedDateTime for whole batch
    for row in book_rows:
        row["AddedDateTime"] = batch_dt
    n = len(book_rows)
    placeholders = ",".join([" (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)" for _ in range(n)])
    sql = (
        "INSERT INTO dbo.Books (Category, Keyword, Title, Authors, Year, Doi, Issn, Issue, Journal, PmId, PmcId, Summary, Article, IsTest, AddedDateTime) "
        f"OUTPUT INSERTED.BookId VALUES {placeholders}"
    )
    flat = []
    for row in book_rows:
        flat.extend(_books_row_to_flat(row))
    cursor.execute(sql, flat)
    book_ids = [int(r[0]) for r in cursor.fetchall()]
    segment_rows = [(bid, "Full text", txt) for bid, txt in zip(book_ids, full_texts)]
    cursor.executemany(
        "INSERT INTO dbo.Segments (BookId, Title, Text) VALUES (?,?,?)",
        segment_rows,
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

    print(f"Loaded {len(articles)} articles. Inserting into Books and Segments (batch size={BATCH_SIZE})...")
    with sql_server_connection.begin() as conn:
        raw_cursor = conn.connection.cursor()
        for i in tqdm(range(0, len(articles), BATCH_SIZE), desc="Inserting", unit="batch"):
            chunk = articles[i : i + BATCH_SIZE]
            try:
                _insert_articles_batch(conn, chunk, raw_cursor)
            except Exception as e:
                print(f"Batch at {i} failed ({e}), inserting one-by-one...")
                for article in chunk:
                    try:
                        _insert_article_one(conn, article, raw_cursor)
                    except Exception as e2:
                        print(f"  Skip article (PMCID={getattr(article, 'PMCID', None)}): {e2}")
    print("Done.")


if __name__ == "__main__":
    main()
