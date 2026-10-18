import csv
import os
import hashlib
from collections import defaultdict

def file_hash(path, chunk=65536):
    """SHA-256 of first chunk of audio file — fast, catches duplicate crops of same source."""
    h = hashlib.sha256()
    try:
        with open(path, 'rb') as f:
            h.update(f.read(chunk))
        return h.hexdigest()
    except Exception:
        return None

def sanitize():
    train_paths = set()
    val_paths   = set()
    train_hashes = set()
    val_hashes   = set()

    for manifest, path_set, hash_set in [
        ("data/manifests/noise_train.csv", train_paths, train_hashes),
        ("data/manifests/noise_val.csv",   val_paths,   val_hashes),
    ]:
        with open(manifest) as f:
            for row in csv.DictReader(f):
                path_set.add(row["path"])
                h = file_hash(row["path"])
                if h: hash_set.add(h)

    all_train_paths   = train_paths   | val_paths
    all_train_hashes  = train_hashes  | val_hashes

    safe_rows = []
    removed_path  = 0
    removed_hash  = 0
    cat_counts = defaultdict(int)

    with open("data/manifests/noise_test.csv") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        for row in reader:
            p = row["path"]
            if p in all_train_paths:
                removed_path += 1
                continue
            h = file_hash(p)
            if h and h in all_train_hashes:
                removed_hash += 1
                continue
            safe_rows.append(row)
            cat_counts[row.get("category", "unknown")] += 1

    with open("data/manifests/noise_test.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(safe_rows)

    print(f"Sanitized! {len(safe_rows)} clips remain.")
    print(f"  Removed by exact path: {removed_path}")
    print(f"  Removed by content hash: {removed_hash}")
    print("  Breakdown by category:")
    for cat, count in sorted(cat_counts.items()):
        print(f"    {cat}: {count}")

if __name__ == "__main__":
    sanitize()
