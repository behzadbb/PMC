from pathlib import Path

directory_path = Path("D:/PMC/Dataset/2026")

pmc_ids_sitemap_path = directory_path / "clean_pmc_articles.txt"  # 11.5 Million PMC IDs
pmc_ids_csv_path = directory_path / "pmc_ids_csv.txt"  # 7125757 PMC IDs
pmc_ids_not_found_path = directory_path / "pmc_ids_not_found.txt"  # ?? PMC IDs

# Load sitemap IDs
with open(pmc_ids_sitemap_path, "r", encoding="utf-8") as f:
    pmc_ids_sitemap = [line.strip() for line in f if line.strip()]

# Load CSV IDs
with open(pmc_ids_csv_path, "r", encoding="utf-8") as f:
    pmc_ids_csv = [line.strip() for line in f if line.strip()]

# Print top 10 from each file
print("Top 10 from pmc_ids_sitemap (clean_pmc_articles.txt):")
for i, pid in enumerate(pmc_ids_sitemap[:10], 1):
    print(f"  {i}. {pid}")

print("\nTop 10 from pmc_ids_csv (pmc_ids_csv.txt):")
for i, pid in enumerate(pmc_ids_csv[:10], 1):
    print(f"  {i}. {pid}")

# IDs that are in sitemap but NOT in csv
set_sitemap = set(pmc_ids_sitemap)
set_csv = set(pmc_ids_csv)
pmc_ids_not_found = set_sitemap - set_csv

# Save to txt file
with open(pmc_ids_not_found_path, "w", encoding="utf-8") as f:
    f.write("\n".join(sorted(pmc_ids_not_found)))

print(f"\nTotal IDs in sitemap: {len(pmc_ids_sitemap)}")
print(f"Total IDs in csv: {len(pmc_ids_csv)}")
print(f"IDs not found (in sitemap but not in csv): {len(pmc_ids_not_found)}")
print(f"Saved to: {pmc_ids_not_found_path}")
