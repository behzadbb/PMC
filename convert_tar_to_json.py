"""
Run archive-to-JSON conversion for FTP PMC XML packages.

This script delegates heavy lifting to `Services.Ftp_XML.Ftp_XML`, which
parses each XML entry in a ``tar.gz`` archive and incrementally writes JSON.
It serves as a practical entry point for batch conversion runs.
"""

import os
from pathlib import Path

from Services.Ftp_XML import Ftp_XML
from tqdm import tqdm

import pandas as pd




def main():
    """
    Execute a single tar.gz to JSON conversion workflow.

    Steps:
    1. Instantiate the FTP XML service.
    2. Process archive contents with streaming conversion.
    3. Print completion metrics.
    """
    directory = Path("/media/breg/adata_512/pmc_2026/")
    #directory = Path("g:/PMC/Dataset/2026/tar_gz/")
    tar_gz_file_paths = [str(directory / f) for f in os.listdir(directory) if f.endswith('.tar.gz')]
    
    
    # Load exclusion keywords from CSV file
    exclusion_keywords_ids_path = directory / "exclusion_keywords.csv"
    
    save_directory = Path("/Home/pmc_2026/json_gz/")
    if not save_directory.exists():
        save_directory.mkdir(parents=True, exist_ok=True)
    
    keywords = []
    if exclusion_keywords_ids_path.exists():
        try:
            keywords_df = pd.read_csv(exclusion_keywords_ids_path, encoding="utf-8")
            if "Keyword" in keywords_df.columns:
                keywords = keywords_df["Keyword"].dropna().astype(str).str.strip().tolist()
                print(f"[INFO] Loaded {len(keywords)} exclusion keywords from CSV")
            else:
                print(f"[WARNING] Column 'Keyword' not found in {exclusion_keywords_ids_path}")
        except Exception as e:
            print(f"[WARNING] Failed to load exclusion keywords from CSV: {e}")
            print(f"[INFO] Continuing without exclusion keywords")
    else:
        print(f"[INFO] Exclusion keywords file not found: {exclusion_keywords_ids_path}")
        print(f"[INFO] Continuing without exclusion keywords")
    
    print("=" * 60)
    print(f"Found {len(tar_gz_file_paths)} tar.gz files to process")
    print(f"Files: {tar_gz_file_paths}")
    
    print("=" * 60)
    print("PMC Tar.gz to JSON Converter")
    print("=" * 60)
    print()
    
    for tar_gz_file_path in tqdm(tar_gz_file_paths, desc="Processing tar.gz files", unit="file"):
        print("=" * 60)
        print(f"Processing {tar_gz_file_path}...")
        print("=" * 60)
        # Create Ftp_XML instance
        ftp_xml = Ftp_XML(save_directory=save_directory, exclusion_keywords=keywords if keywords else None)
        
        try:
            # Convert tar.gz to JSON (memory-efficient incremental processing)
            article_count = ftp_xml.convert_tar_gz_to_json(tar_gz_file_path)
            
            print(f"\n{'=' * 60}")
            print(f"Conversion completed!")
            print(f"Total articles: {article_count}")
            print(f"{'=' * 60}")
        finally:
            # Dispose object (explicit cleanup for best practices)
            del ftp_xml


if __name__ == "__main__":
    main()
