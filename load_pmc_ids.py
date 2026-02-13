"""Load PMC article IDs from a text file (one ID per line)."""

import re
from pathlib import Path
from typing import List


def load_pmc_ids(file_path: str) -> List[int]:
    """
    Read PMC IDs from a text file.
    Accepts lines like: 4049904, PMC4049904, or PMC4049904\\n
    Returns list of numeric IDs.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ids: List[int] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.search(r"(?:PMC)?\s*(\d+)", line, re.I)
        if match:
            ids.append(int(match.group(1)))

    return ids


def main():
    txt_path = Path(__file__).parent / "clean_pmc_articles.txt"
    pmc_ids = load_pmc_ids(str(txt_path))
    print(f"Loaded {len(pmc_ids)} PMC IDs")
    print("First 10:", pmc_ids[:10])


if __name__ == "__main__":
    main()
