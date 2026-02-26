import json
import os
import tarfile
from pathlib import Path

import requests
from tqdm import tqdm

from DTO.Article import Article






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


def api_call(json_gz_file_path: Path | str) -> requests.Response:
    """POST a .json.tar.gz file to the Articles bulk API. Key 'File' must match C# model."""
    url = "https://demoapi.bregulator.com/api/Articles/bulk"
    path = Path(json_gz_file_path)
    # Use path.name so the server sees a filename, not a full path
    with open(path, "rb") as f:
        files = {"File": (path.name, f)}
        response = requests.post(url, files=files, timeout=120)
    print("Status Code:", response.status_code)
    print("Response:", response.text)
    response.raise_for_status()
    return response

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

    for json_file_path in tqdm(json_gz_filtered_files, desc="Uploading"):
        try:
            print(f"Start Uploading {json_file_path}...")
            response = api_call(json_file_path)
            print(f"Uploaded {json_file_path}")
            print("Status Code:", response.status_code)
            print("Response:", response.text)
        except Exception as e:
            print(f"Error uploading {json_file_path}: {e}")
            print("Response:", response.text)

    print("Done.")


if __name__ == "__main__":
    main()
