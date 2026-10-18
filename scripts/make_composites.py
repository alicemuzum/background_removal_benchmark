"""Paste each bench product onto a random DTD texture, keeping its matte as ground truth.

Usage: python scripts/make_composites.py [--bench data/bench] [--textures data/dtd/images]
                                         [--out data/composites] [-k 1] [--seed 42]
Writes <out>/images/<id>_<j>.jpg, <out>/alpha/<id>_<j>.png (same matte as the bench
image) and <out>/manifest.csv. Textures are drawn without replacement.
"""
import argparse
import csv
import random
import shutil
from pathlib import Path

import cv2
import numpy as np

MIN_ALPHA = 0.05  # below this, edge colour can't be recovered reliably


def decontaminate(bgr, alpha):
    """Recover foreground colour from pixels blended with the white background.

    Observed C = a*F + (1-a)*255, so F = (C - (1-a)*255) / a.
    """
    a = alpha[..., None]
    fg = (bgr.astype(np.float32) - (1 - a) * 255.0) / np.maximum(a, MIN_ALPHA)
    return np.clip(fg, 0, 255)


def random_crop(tex, h, w, rng):
    th, tw = tex.shape[:2]
    if th < h or tw < w:
        s = max(h / th, w / tw)
        tex = cv2.resize(tex, (int(np.ceil(tw * s)), int(np.ceil(th * s))), interpolation=cv2.INTER_AREA)
        th, tw = tex.shape[:2]
    y, x = rng.randint(0, th - h), rng.randint(0, tw - w)
    return tex[y:y + h, x:x + w]


def composite(bgr, alpha, bg):
    a = alpha[..., None]
    out = decontaminate(bgr, alpha) * a + bg.astype(np.float32) * (1 - a)
    return np.round(out).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench", default="data/bench")
    ap.add_argument("--textures", default="data/dtd/images")
    ap.add_argument("--out", default="data/composites")
    ap.add_argument("-k", type=int, default=1, help="backgrounds per product")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    bench = Path(args.bench)
    with open(bench / "manifest.csv", newline="") as f:
        items = list(csv.DictReader(f))
    textures = sorted(Path(args.textures).glob("*/*.jpg"))
    rng = random.Random(args.seed)
    picks = rng.sample(textures, len(items) * args.k)

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "images").mkdir(parents=True)
    (out / "alpha").mkdir()
    with open(out / "manifest.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "bench_id", "product_type", "texture", "texture_class", "height", "width"])
        for n, it in enumerate(items):
            img = cv2.imread(next(str(p) for p in (bench / "images").glob(f"{it['id']}.*")), cv2.IMREAD_COLOR)
            alpha_u8 = cv2.imread(str(bench / "alpha" / f"{it['id']}.png"), cv2.IMREAD_GRAYSCALE)
            alpha = alpha_u8.astype(np.float32) / 255.0
            h, wd = img.shape[:2]
            for j in range(args.k):
                tex_path = picks[n * args.k + j]
                bg = random_crop(cv2.imread(str(tex_path), cv2.IMREAD_COLOR), h, wd, rng)
                cid = f"{it['id']}_{j}"
                cv2.imwrite(str(out / "images" / f"{cid}.jpg"), composite(img, alpha, bg), [cv2.IMWRITE_JPEG_QUALITY, 95])
                cv2.imwrite(str(out / "alpha" / f"{cid}.png"), alpha_u8)
                w.writerow([cid, it["id"], it["product_type"], str(tex_path), tex_path.parent.name, h, wd])
    print(f"{len(items) * args.k} composites -> {out}")


if __name__ == "__main__":
    main()
