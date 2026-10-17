"""Map every ABO image file to its listing's product_type.

Usage: python scripts/image_categories.py
Joins data/images/metadata/images.csv.gz (file path -> image_id) with
data/listings/metadata/listings_*.json.gz (image_id -> product_type) and writes
data/image_categories.csv with columns: file, image_id, product_type, is_main.
An image shared by several listings takes the product_type of the first listing
that uses it as its main image, else the first listing that uses it at all.
"""
import csv
import gzip
import json
from pathlib import Path

LISTINGS = Path("data/listings/metadata")
IMAGES_CSV = Path("data/images/metadata/images.csv.gz")
OUT = Path("data/image_categories.csv")


def main():
    main_type, other_type = {}, {}
    for f in sorted(LISTINGS.glob("listings_*.json.gz")):
        with gzip.open(f, "rt") as fh:
            for line in fh:
                item = json.loads(line)
                ptype = (item.get("product_type") or [{}])[0].get("value")
                if not ptype:
                    continue
                if "main_image_id" in item:
                    main_type.setdefault(item["main_image_id"], ptype)
                for iid in item.get("other_image_id", []):
                    other_type.setdefault(iid, ptype)

    n = missing = 0
    with gzip.open(IMAGES_CSV, "rt") as fh, open(OUT, "w", newline="") as out:
        w = csv.writer(out)
        w.writerow(["file", "image_id", "product_type", "is_main"])
        for row in csv.DictReader(fh):
            iid = row["image_id"]
            ptype = main_type.get(iid) or other_type.get(iid)
            missing += ptype is None
            w.writerow([Path(row["path"]).name, iid, ptype or "", int(iid in main_type)])
            n += 1
    print(f"{n} images, {missing} without a product_type -> {OUT}")


if __name__ == "__main__":
    main()
