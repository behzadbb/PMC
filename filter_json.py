import io
import json
import os
import tarfile
from pathlib import Path

import pandas as pd


def load_json_tar_gz(file_path: Path) -> pd.DataFrame:
    """Load a .json.tar.gz archive (single JSON array inside) into a DataFrame."""
    with tarfile.open(file_path, "r:gz") as tar:
        member = next((m for m in tar.getmembers() if m.name.endswith(".json")), None)
        if member is None:
            return pd.DataFrame()
        f = tar.extractfile(member)
        data = json.load(f)
    return pd.DataFrame(data)


def text_contains_any_keyword(text: str, keywords: list[str]) -> bool:
    """Return True if text (lowercased) contains any of the keywords."""
    if pd.isna(text) or not isinstance(text, str):
        return False
    lower = text.lower()
    return any(kw in lower for kw in keywords)


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
    exclusion_keywords = (
        exclusion_keywords_df["Keyword"]
        .dropna()
        .astype(str)
        .str.lower()
        .str.strip()
        .tolist()
    )
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

        # Filter out rows where Abstract or Title contains any exclusion keyword
        abstract_col = "Abstract" if "Abstract" in df.columns else "abstract"
        title_col = "Title" if "Title" in df.columns else "title"
        mask_abstract = df[abstract_col].apply(lambda t: text_contains_any_keyword(t, exclusion_keywords))
        mask_title = df[title_col].apply(lambda t: text_contains_any_keyword(t, exclusion_keywords))
        df_filtered = df[~(mask_abstract | mask_title)]

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

    print("Done.")


if __name__ == "__main__":
    main()
