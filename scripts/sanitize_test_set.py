import csv
import os

def sanitize():
    train_paths = set()
    val_paths = set()
    
    with open("data/manifests/noise_train.csv") as f:
        reader = csv.DictReader(f)
        for row in reader: train_paths.add(row["path"])
        
    with open("data/manifests/noise_val.csv") as f:
        reader = csv.DictReader(f)
        for row in reader: val_paths.add(row["path"])
        
    safe_rows = []
    removed = 0
    with open("data/manifests/noise_test.csv") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        for row in reader:
            if row["path"] not in train_paths and row["path"] not in val_paths:
                safe_rows.append(row)
            else:
                removed += 1
                
    with open("data/manifests/noise_test.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(safe_rows)
        
    print(f"Sanitized! Test set now has {len(safe_rows)} clips. Removed {removed} overlapping clips.")

if __name__ == "__main__":
    sanitize()
