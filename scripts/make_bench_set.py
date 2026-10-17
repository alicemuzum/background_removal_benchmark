"""Pick a reproducible set of white-background images and derive a reference alpha for each.

Usage: python scripts/make_bench_set.py [--src data/sources] [--out data/bench] [-n 200] [--seed 42] [--cap 5]
At most --cap images are kept per product_type (from data/image_categories.csv,
built by scripts/image_categories.py). Ids listed in scripts/bench_exclude.txt
(mattes found wrong on review) are skipped. Images with text overlays (marketing copy,
dimension labels) are skipped using easyocr's text detector. Writes <out>/images/<id>.jpg, <out>/alpha/<id>.png (8-bit matte) and <out>/manifest.csv.
"""
import argparse
import csv
from collections import Counter
import random
import shutil
from pathlib import Path

import cv2
import numpy as np

from filter_white_bg import has_white_bg

WHITE_TOL = 15  # a pixel is "white" if its darkest channel is within this of 255


def alpha_from_white_bg(bgr, tol=WHITE_TOL):
    """Alpha in [0, 1]: background = near-white pixels connected to the image border.

    White regions enclosed by the product (labels, highlights) stay foreground.
    Background pixels touching the foreground get a soft value from their distance
    to white, so anti-aliased edges are kept as partial alpha.
    """
    d = 255.0 - bgr.min(axis=2).astype(np.float32)        # 0 = pure white
    white = (d < tol).astype(np.uint8)
    _, labels = cv2.connectedComponents(white, connectivity=4)
    edge_labels = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    bg = np.isin(labels, edge_labels[edge_labels > 0])

    alpha = (~bg).astype(np.float32)
    band = bg & cv2.dilate((~bg).astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    alpha[band] = d[band] / tol
    return alpha


def keep_main_parts(alpha, rel_min=0.10, max_dropped=0.15):
    """Remove small disconnected blobs (text, dimension arrows, stray marks).
    Returns (cleaned alpha, ok) - ok is False if too much was removed."""
    mask = (alpha > 0.5).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if n <= 1:
        return alpha, False                       # nothing found at all

    areas = stats[1:, cv2.CC_STAT_AREA]           # label 0 is the background
    biggest = areas.max()
    keep = [i + 1 for i, a in enumerate(areas) if a >= rel_min * biggest]

    kept = np.isin(labels, keep).astype(np.uint8)
    # Grow by 1px so the soft edge band (alpha < 0.5) around kept parts survives.
    cleaned = alpha * cv2.dilate(kept, np.ones((3, 3), np.uint8))
    dropped = 1.0 - kept.sum() / mask.sum()
    return cleaned, dropped <= max_dropped


def looks_sane(alpha, min_fg=0.05, max_fg=0.85, max_border=0.01, min_main=0.8, max_edge=0.5):
    """Reject mattes that are near-empty, near-full, touch the border, fragmented, or text-like."""
    fg = alpha > 0.5
    frac = fg.mean()
    if not (min_fg < frac < max_fg):
        return False
    border = np.concatenate([fg[0], fg[-1], fg[:, 0], fg[:, -1]])
    if border.mean() > max_border:
        return False
    # The largest few components should hold almost all of the foreground (no speckle).
    n, _, stats, _ = cv2.connectedComponentsWithStats(fg.astype(np.uint8), connectivity=8)
    areas = np.sort(stats[1:, cv2.CC_STAT_AREA])[::-1]
    if areas[:5].sum() < min_main * fg.sum():
        return False
    # Text blocks are mostly outline: a high share of foreground pixels sit on an edge.
    # Real products sit around 0.05; thin ones (scissors, jewellery) reach ~0.37.
    fg8 = fg.astype(np.uint8)
    edge = fg8 - cv2.erode(fg8, np.ones((3, 3), np.uint8))
    return edge.sum() / fg8.sum() <= max_edge


_reader = None


def text_boxes(bgr, min_aspect=1.5):
    """Mask of detected text lines. Near-square boxes are dropped: at 256px the
    detector often fires on whole small objects (hooks, earrings)."""
    global _reader
    if _reader is None:
        import easyocr
        _reader = easyocr.Reader(["en"], gpu=False, recognizer=False, verbose=False)
    h, w = bgr.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    for x0, x1, y0, y1 in _reader.detect(bgr, mag_ratio=2.0)[0][0]:
        x0, y0, x1, y1 = max(0, int(x0)), max(0, int(y0)), min(w, int(x1)), min(h, int(y1))
        if x1 > x0 and y1 > y0 and (x1 - x0) >= min_aspect * (y1 - y0):
            mask[y0:y1, x0:x1] = 1
    return mask.astype(bool)


def has_text_overlay(bgr, alpha, max_overlay=0.005, text_part=0.5):
    """Is there text that isn't printed on the product?

    Matte parts mostly covered by text boxes are treated as text, not product.
    Overlay = text boxes outside the remaining product parts (holes filled, grown
    a few px). Printed labels on the product don't count.
    """
    text = text_boxes(bgr)
    if not text.any():
        return False
    fg = (alpha > 0.5).astype(np.uint8)
    n, labels = cv2.connectedComponents(fg, connectivity=8)
    product = np.zeros_like(fg)
    for i in range(1, n):
        part = labels == i
        if text[part].mean() <= text_part:
            product[part] = 1
    # Fill holes (so text on a label inside a ring/frame counts as on-product), then grow.
    cnts, _ = cv2.findContours(product, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(product, cnts, -1, 1, -1)
    product = cv2.dilate(product, np.ones((7, 7), np.uint8)).astype(bool)
    return (text & ~product).mean() > max_overlay


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="data/sources")
    ap.add_argument("--out", default="data/bench")
    ap.add_argument("-n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--cap", type=int, default=5, help="max images per product_type")
    ap.add_argument("--categories", default="data/image_categories.csv")
    ap.add_argument("--exclude", default="scripts/bench_exclude.txt", help="ids with known-bad mattes")
    args = ap.parse_args()

    with open(args.exclude) as f:
        exclude = {line.split("#")[0].strip() for line in f} - {""}

    with open(args.categories, newline="") as f:
        category = {r["file"]: r["product_type"] or "UNKNOWN" for r in csv.DictReader(f)}

    paths = sorted(p for p in Path(args.src).iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    random.Random(args.seed).shuffle(paths)

    kept, checked, per_cat, text_rejects = [], 0, Counter(), []
    for p in paths:
        if p.stem in exclude:
            continue
        cat = category.get(p.name, "UNKNOWN")
        if per_cat[cat] >= args.cap:
            continue
        checked += 1
        img = cv2.imread(str(p), cv2.IMREAD_COLOR)
        if img is None or not has_white_bg(img):
            continue
        alpha, ok = keep_main_parts(alpha_from_white_bg(img))
        if not ok or not looks_sane(alpha):
            continue
        if has_text_overlay(img, alpha):
            text_rejects.append(p)
            continue
        per_cat[cat] += 1
        kept.append((p, cat, img, alpha))
        if len(kept) >= args.n:
            break
    print(f"checked {checked}, kept {len(kept)} across {len(per_cat)} product types (cap {args.cap}), "
          f"{len(text_rejects)} skipped for text overlays")

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "images").mkdir(parents=True)
    (out / "alpha").mkdir()
    with open(out / "manifest.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "product_type", "source", "height", "width", "fg_frac"])
        for p, cat, img, alpha in kept:
            shutil.copy2(p, out / "images" / f"{p.stem}{p.suffix}")
            cv2.imwrite(str(out / "alpha" / f"{p.stem}.png"), np.round(alpha * 255).astype(np.uint8))
            w.writerow([p.stem, cat, str(p), *img.shape[:2], f"{(alpha > 0.5).mean():.3f}"])
    with open(out / "text_rejects.txt", "w") as f:
        f.writelines(f"{p}\n" for p in text_rejects)


if __name__ == "__main__":
    main()
