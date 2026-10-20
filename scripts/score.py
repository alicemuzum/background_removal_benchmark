"""Score saved model predictions against the reference mattes.

Usage: python scripts/score.py [--sets bench composites]
Reads data/preds/<set>/<model>/ (from scripts/run_models.py) and data/<set>/alpha/.
Writes data/results/per_image.csv and data/results/summary.csv, and prints the summary.

Metrics, per image, then averaged:
  mae       mean |pred - gt| over the whole image (lower is better)
  iou       IoU of the masks at alpha >= 0.5 (higher is better)
  edge_mae  mean |pred - gt| within EDGE_PX of the reference outline: how well the
            edge itself is cut, which whole-image MAE dilutes (lower is better)
  seconds   inference time per image on CPU, model load excluded
95% intervals are bootstrap intervals of the mean over images.
"""
import argparse
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

EDGE_PX = 4
N_BOOT = 2000


def score_one(pred, gt):
    p, g = pred >= 0.5, gt >= 0.5
    union = (p | g).sum()
    hard = g.astype(np.uint8)
    k = np.ones((2 * EDGE_PX + 1, 2 * EDGE_PX + 1), np.uint8)
    edge = cv2.dilate(hard, k).astype(bool) & ~cv2.erode(hard, k).astype(bool)
    err = np.abs(pred - gt)
    return dict(mae=err.mean(), iou=(p & g).sum() / union if union else 1.0, edge_mae=err[edge].mean())


def boot_ci(x, rng):
    x = np.asarray(x, float)
    means = x[rng.integers(0, len(x), (N_BOOT, len(x)))].mean(axis=1)
    return np.percentile(means, [2.5, 97.5])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", nargs="+", default=["bench", "composites"])
    args = ap.parse_args()

    rows = []
    for set_name in args.sets:
        manifest = pd.read_csv(Path("data", set_name, "manifest.csv"), dtype={"id": str, "bench_id": str})
        for model_dir in sorted(Path("data/preds", set_name).iterdir()):
            if not model_dir.is_dir():
                continue
            times = pd.read_csv(model_dir / "times.csv", dtype={"id": str}).set_index("id").seconds
            for r in manifest.itertuples():
                pred_path = model_dir / f"{r.id}.png"
                if not pred_path.exists():
                    continue
                pred = cv2.imread(str(pred_path), cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255.0
                gt = cv2.imread(str(Path("data", set_name, "alpha", f"{r.id}.png")), cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255.0
                rows.append(dict(set=set_name, model=model_dir.name, id=r.id, product_type=r.product_type,
                                 **score_one(pred, gt), seconds=times.get(r.id, np.nan)))

    per_image = pd.DataFrame(rows)
    out = Path("data/results")
    out.mkdir(parents=True, exist_ok=True)
    per_image.to_csv(out / "per_image.csv", index=False)

    rng = np.random.default_rng(0)
    summary = []
    for (set_name, model), g in per_image.groupby(["set", "model"], sort=False):
        s = dict(set=set_name, model=model, n=len(g))
        for m in ["mae", "iou", "edge_mae"]:
            lo, hi = boot_ci(g[m], rng)
            s[m], s[f"{m}_lo"], s[f"{m}_hi"] = g[m].mean(), lo, hi
        s["seconds"] = g.seconds.mean()
        summary.append(s)
    summary = pd.DataFrame(summary).sort_values(["set", "mae"])
    summary.to_csv(out / "summary.csv", index=False)

    for set_name, g in summary.groupby("set", sort=False):
        print(f"\n== {set_name}")
        for s in g.itertuples():
            print(f"  {s.model:24s} n={s.n:3d}  MAE {s.mae:.4f} [{s.mae_lo:.4f}-{s.mae_hi:.4f}]  "
                  f"IoU {s.iou:.3f} [{s.iou_lo:.3f}-{s.iou_hi:.3f}]  "
                  f"edge MAE {s.edge_mae:.3f} [{s.edge_mae_lo:.3f}-{s.edge_mae_hi:.3f}]  {s.seconds:.2f}s/img")


if __name__ == "__main__":
    main()
