import io
import json
import os
import re
import tarfile
from pathlib import Path

import pandas as pd

from DTO.Article import Article


def _column_candidates(field_name: str) -> list[str]:
    """Return possible DataFrame column names for an Article field (name + alias)."""
    f = Article.model_fields[field_name]
    candidates = [field_name]
    if getattr(f, "alias", None):
        candidates.append(f.alias)
    return candidates


def _resolve_column(
    df: pd.DataFrame, field_name: str, fallbacks: list[str] | None = None
) -> str | None:
    """Pick first column present in df from DTO field candidates, then optional fallbacks."""
    dto_candidates = _column_candidates(field_name)
    candidates = dto_candidates + (fallbacks or [])
    for c in candidates:
        if c in df.columns:
            return c
    return None if field_name == "PMCID" else (dto_candidates[0] if dto_candidates else None)


def load_json_tar_gz(file_path: Path) -> pd.DataFrame:
    """Load a .json.tar.gz archive (single JSON array inside) into a DataFrame."""
    with tarfile.open(file_path, "r:gz") as tar:
        member = next((m for m in tar.getmembers() if m.name.endswith(".json")), None)
        if member is None:
            return pd.DataFrame()
        f = tar.extractfile(member)
        data = json.load(f)
    return pd.DataFrame(data)


def _text_words(text: str) -> list[str]:
    """Tokenize text into words (word-boundary, lowercase)."""
    if not text or not isinstance(text, str):
        return []
    return re.findall(r"\b\w+\b", text.lower())


def _keyword_matches_text(keyword: str, text_words: list[str]) -> bool:
    """
    True if keyword appears in text as whole word(s).
    Single word: "rat" matches only the word "rat", not "rat" inside "carbohydrates".
    Multi-word: "animal study" matches contiguous phrase "animal" then "study".
    """
    kw_clean = keyword.strip().lower()
    if not kw_clean:
        return False
    kw_tokens = re.split(r"\s+", kw_clean)
    if len(kw_tokens) == 1:
        return kw_tokens[0] in text_words
    # Phrase: find contiguous sequence
    n = len(kw_tokens)
    for i in range(len(text_words) - n + 1):
        if text_words[i : i + n] == kw_tokens:
            return True
    return False


def get_matching_keywords_with_category(
    text: str, keyword_to_category: dict[str, str]
) -> list[tuple[str, str]]:
    """
    Return (keyword, category) for keywords that appear in text as whole word(s).
    Single-word keywords match only as full words; multi-word keywords match as phrases.
    """
    if pd.isna(text) or not isinstance(text, str):
        return []
    text_words = _text_words(text)
    return [
        (kw, cat)
        for kw, cat in keyword_to_category.items()
        if _keyword_matches_text(kw, text_words)
    ]


def main():
    if os.name == "posix":
        base_path = Path("/home/breg/pmc_2026")
        directory_path = base_path / "json_gz"
        save_filtered_directory_path = base_path / "filtered_json_gz"
        csv_exclusion_keywords_path = base_path / "PMC safe-exclusion keywords.csv"
        print("Using Linux paths under /home/breg/pmc_2026/")
    elif os.name == "nt":
        base_path = Path("D:/PMC/Dataset/2026")
        directory_path = base_path / "json_gz"
        save_filtered_directory_path = base_path / "filtered_json_gz"
        csv_exclusion_keywords_path = base_path / "PMC safe-exclusion keywords.csv"
        print("Using Windows paths under D:/PMC/Dataset/2026/")
    else:
        base_path = Path("/home/breg/pmc_2026")
        directory_path = base_path / "json_gz"
        save_filtered_directory_path = base_path / "filtered_json_gz"
        csv_exclusion_keywords_path = base_path / "PMC safe-exclusion keywords.csv"
        print("Unknown OS, using Linux-style paths under /home/breg/pmc_2026/")

    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            exclusion_keywords_df = pd.read_csv(csv_exclusion_keywords_path, encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise SystemExit(f"Cannot read CSV with utf-8, cp1252, or latin-1: {csv_exclusion_keywords_path}")
    # Build keyword -> category dict for fast lookup (Category, Keyword columns)
    keyword_to_category: dict[str, str] = {}
    for _, row in exclusion_keywords_df.iterrows():
        kw = str(row["Keyword"]).strip().lower() if pd.notna(row.get("Keyword")) else ""
        cat = row.get("Category", "")
        if kw:
            keyword_to_category[kw] = str(cat).strip() if pd.notna(cat) else ""
    json_gz_file_paths = sorted(directory_path.glob("**/*.json.tar.gz"))
    print(f"Found {len(json_gz_file_paths)} .json.tar.gz files to process.")

    for json_gz_file_path in json_gz_file_paths:
        # Same relative path under destination: json_gz/.../file.json.tar.gz -> filtered_json_gz/.../file.json.tar.gz
        rel_path = json_gz_file_path.relative_to(directory_path)
        filtered_file_path = save_filtered_directory_path / rel_path
        filtered_file_path.parent.mkdir(parents=True, exist_ok=True)

        df = load_json_tar_gz(json_gz_file_path)
        if df.empty:
            print(f"[SKIP] No data in {json_gz_file_path}")
            continue

        # Resolve column names from DTO.Article (field name + alias), with fallbacks for legacy JSON
        abstract_col = _resolve_column(df, "Abstract") or "Abstract"
        title_col = _resolve_column(df, "Title") or "Title"
        pmc_id_col = _resolve_column(df, "PMCID", fallbacks=["PMC_Id", "pmc_id"])

        # For each row, get (keyword, category) matches in abstract or title
        # Aggregate by (PMC_ID, Title): one record per article with comma-separated Keywords and Categories
        exclusion_by_article: dict[tuple, tuple[set[str], set[str]]] = {}  # (pmc_id, title) -> (keywords, categories)
        mask_excluded = pd.Series(False, index=df.index)
        for idx, row in df.iterrows():
            matches = get_matching_keywords_with_category(
                row.get(abstract_col), keyword_to_category
            ) + get_matching_keywords_with_category(row.get(title_col), keyword_to_category)
            seen = set()
            unique_matches = []
            for kw, cat in matches:
                if (kw, cat) not in seen:
                    seen.add((kw, cat))
                    unique_matches.append((kw, cat))
            if unique_matches:
                mask_excluded.loc[idx] = True
                pmc_id = row[pmc_id_col] if pmc_id_col else idx
                title_val = row.get(title_col, "")
                key = (pmc_id, title_val)
                if key not in exclusion_by_article:
                    exclusion_by_article[key] = (set(), set())
                kw_set, cat_set = exclusion_by_article[key]
                for kw, cat in unique_matches:
                    kw_set.add(kw)
                    cat_set.add(cat)
        df_filtered = df[~mask_excluded]

        # One row per unique PMC_ID: PMC_ID, Title, Keywords, Categories (comma-separated)
        exclusion_records = [
            {
                "PMC_ID": pmc_id,
                "Title": title,
                "Keywords": ",".join(sorted(kw_set)),
                "Categories": ",".join(sorted(cat_set)),
            }
            for (pmc_id, title), (kw_set, cat_set) in exclusion_by_article.items()
        ]

        print(f"{json_gz_file_path.name}: {len(df)} -> {len(df_filtered)} articles")

        # Save filtered articles to .json.tar.gz (same format as source)
        records = df_filtered.to_dict(orient="records")
        json_bytes = json.dumps(records, ensure_ascii=False, default=str).encode("utf-8")
        inner_name = filtered_file_path.name.replace(".tar.gz", "") if filtered_file_path.name.endswith(".tar.gz") else filtered_file_path.stem + ".json"
        info = tarfile.TarInfo(name=inner_name)
        info.size = len(json_bytes)
        with tarfile.open(filtered_file_path, "w:gz") as tar:
            tar.addfile(info, io.BytesIO(json_bytes))
        print(f"  -> {filtered_file_path}")

        # Save exclusions CSV: one row per PMC_ID, columns PMC_ID, Title, Keywords, Categories (comma-separated)
        if exclusion_records:
            csv_name = filtered_file_path.name.replace(".json.tar.gz", "_exclusions.csv")
            csv_path = filtered_file_path.parent / csv_name
            pd.DataFrame(exclusion_records).to_csv(
                csv_path, index=False, encoding="utf-8-sig"
            )
            print(f"  -> {csv_path} ({len(exclusion_records)} unique PMC_IDs)")

    print("Done.")


def _test_word_boundary_matching() -> None:
    """Assert whole-word and phrase matching: no substring matches."""
    keyword_to_category = {
        "rat": "Animal",
        "ner": "Ner",
        "animal study": "Animal Studies",
    }
    # Should NOT match (substring)
    assert get_matching_keywords_with_category("carbohydrates", keyword_to_category) == []
    assert get_matching_keywords_with_category("energy", keyword_to_category) == []
    # Should match (whole word)
    assert get_matching_keywords_with_category("rat", keyword_to_category) == [("rat", "Animal")]
    assert get_matching_keywords_with_category("ner", keyword_to_category) == [("ner", "Ner")]
    # Phrase
    assert get_matching_keywords_with_category("animal study", keyword_to_category) == [
        ("animal study", "Animal Studies")
    ]
    # Mixed: "rat" in sentence as word, not in "carbohydrates"
    matches = get_matching_keywords_with_category("We used rat and carbohydrates.", keyword_to_category)
    assert ("rat", "Animal") in matches
    assert ("animal study", "Animal Studies") not in matches
    print("Word-boundary matching tests passed.")


if __name__ == "__main__":
    _test_word_boundary_matching()
    main()
