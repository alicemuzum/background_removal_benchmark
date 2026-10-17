"""Copy ABO images whose border is uniformly near-white into data/sources/.

Usage: python scripts/filter_white_bg.py [--src data/images/small] [--dst data/sources]
Also writes data/white_bg_scan.csv with the border stats for every image,
so thresholds can be re-tuned without re-reading the images.
"""
import argparse
import csv
import os
import shutil
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np

MARGIN, MIN_MEAN, MAX_STD = 0.03, 238, 12


def border_stats(bgr, margin=MARGIN):
    """Mean and std of the gray level in a thin strip around the image edge."""
    h, w = bgr.shape[:2]
    m = max(2, int(min(h, w) * margin))
    border = np.concatenate([
        bgr[:m, :].reshape(-1, 3),   # top
        bgr[-m:, :].reshape(-1, 3),  # bottom
        bgr[:, :m].reshape(-1, 3),   # left
        bgr[:, -m:].reshape(-1, 3),  # right
    ])
    gray = border.mean(axis=1)
    return float(gray.mean()), float(gray.std())


def has_white_bg(bgr, margin=MARGIN, min_mean=MIN_MEAN, max_std=MAX_STD):
    """Is the border of this image uniformly near-white?"""
    mean, std = border_stats(bgr, margin)
    return mean > min_mean and std < max_std


def scan(path):
    bgr = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if bgr is None:
        return str(path), None, None
    return str(path), *border_stats(bgr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/images/small")
    ap.add_argument("--dst", default="data/sources")
    ap.add_argument("--report", default="data/white_bg_scan.csv")
    args = ap.parse_args()

    paths = sorted(p for p in Path(args.src).rglob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    dst = Path(args.dst)
    dst.mkdir(parents=True, exist_ok=True)

    kept = unreadable = 0
    with ProcessPoolExecutor() as pool, open(args.report, "w", newline="") as f:
        out = csv.writer(f)
        out.writerow(["path", "border_mean", "border_std", "white_bg"])
        for i, (path, mean, std) in enumerate(pool.map(scan, paths, chunksize=256), 1):
            if mean is None:
                unreadable += 1
                out.writerow([path, "", "", ""])
                continue
            white = mean > MIN_MEAN and std < MAX_STD
            out.writerow([path, f"{mean:.2f}", f"{std:.2f}", int(white)])
            if white:
                shutil.copy2(path, dst / os.path.basename(path))
                kept += 1
            if i % 20000 == 0:
                print(f"{i}/{len(paths)} scanned, {kept} kept", flush=True)

    print(f"done: {kept}/{len(paths)} white-background images -> {dst} ({unreadable} unreadable)")


if __name__ == "__main__":
    main()
