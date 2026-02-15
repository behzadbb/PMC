"""
Run archive-to-JSON conversion for FTP PMC XML packages.

This script delegates heavy lifting to `Services.Ftp_XML.Ftp_XML`, which
parses each XML entry in a ``tar.gz`` archive and incrementally writes JSON.
It serves as a practical entry point for batch conversion runs.
"""

import os
from pathlib import Path

from Services.Ftp_XML import Ftp_XML


def main():
    """
    Execute a single tar.gz to JSON conversion workflow.

    Steps:
    1. Instantiate the FTP XML service.
    2. Process archive contents with streaming conversion.
    3. Print completion metrics.
    """
    directory = Path("g:/PMC/Dataset/2026/tar_gz/")
    tar_gz_file_paths = [str(directory / f) for f in os.listdir(directory) if f.endswith('.tar.gz')]
    
    print("=" * 60)
    print(f"Found {len(tar_gz_file_paths)} tar.gz files to process")
    print(f"Files: {tar_gz_file_paths}")
    
    print("=" * 60)
    print("PMC Tar.gz to JSON Converter")
    print("=" * 60)
    print()
    
    for tar_gz_file_path in tar_gz_file_paths:
        print("=" * 60)
        print(f"Processing {tar_gz_file_path}...")
        print("=" * 60)
        # Create Ftp_XML instance
        ftp_xml = Ftp_XML()
        
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
