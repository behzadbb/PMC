"""Test the Ftp_CSV class."""

from pathlib import Path

from Services.Ftp_CSV import Ftp_CSV

# Use a local directory under the project so the test works on any machine
DATA_DIR = Path(__file__).resolve().parent / "data" / "csv"

ftp_csv = Ftp_CSV()

# print("=" * 60)
# print("Start downloading csv files from ftp")
# ftp_csv.download_file_list(str(DATA_DIR))
# print("Successfully downloaded csv files from ftp")

print("=" * 60)
print("Start getting pmc ids from csv files")
pmc_ids = ftp_csv.get_pmc_ids(str(DATA_DIR))
print("Successfully got pmc ids from csv files")
print("=" * 60)
print(f"Total PMC IDs: {len(pmc_ids)}")
print("Top 10 PMC IDs:", pmc_ids[:10])
