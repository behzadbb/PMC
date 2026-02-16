from pathlib import Path

from tqdm import tqdm

directory_path = Path("D:/PMC/Dataset/2026")

pmc_ids_not_found_path = directory_path / "pmc_ids_not_found.txt"
pmc_ids_path = directory_path / "pmc_id_parts"

# Load txt file: each line -> one ID (as string)
with open(pmc_ids_not_found_path, "r", encoding="utf-8") as f:
    pmc_ids = [line.strip() for line in f if line.strip()]

# Split into chunks of 5000 and save each to a new txt file
pmc_ids_path.mkdir(parents=True, exist_ok=True)
chunk_size = 5000

chunk_range = range(0, len(pmc_ids), chunk_size)
for i in tqdm(chunk_range, desc="Saving parts", unit="file"):
    chunk = pmc_ids[i : i + chunk_size]
    part_num = (i // chunk_size) + 1
    out_path = pmc_ids_path / f"pmc_ids_part_{part_num:04d}.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(chunk))

print(f"Loaded {len(pmc_ids)} IDs from {pmc_ids_not_found_path}")
print(f"Saved {((len(pmc_ids) - 1) // chunk_size) + 1} files to {pmc_ids_path}")
