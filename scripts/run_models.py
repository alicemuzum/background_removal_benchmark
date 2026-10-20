"""Run each background-removal model on a benchmark set and save its predicted alpha.

Usage: python scripts/run_models.py [--sets bench composites] [--models u2net ...] [--force]
Writes data/preds/<set>/<model>/<id>.png (8-bit alpha, same size as the input) and
data/preds/<set>/<model>/times.csv (seconds per image, model load excluded).
Images that already have a prediction are skipped unless --force.
"""
import argparse
import csv
import time
from pathlib import Path

import numpy as np
from PIL import Image

REMBG_MODELS = ["u2net", "isnet-general-use", "birefnet-general"]
ALL_MODELS = REMBG_MODELS + ["transparent-background"]


def load_model(name):
    """Return a function PIL RGB image -> float alpha array in [0, 1]."""
    if name in REMBG_MODELS:
        import onnxruntime as ort
        from rembg import new_session, remove
        # Without the memory arena birefnet-general peaks at ~8 GB instead of ~12.7 GB,
        # at the same speed; with it, the process was OOM-killed on a 15 GB machine.
        opts = ort.SessionOptions()
        opts.enable_cpu_mem_arena = False
        session = new_session(name, sess_opts=opts)
        return lambda im: np.asarray(remove(im, session=session, only_mask=True), np.float32) / 255.0
    if name == "transparent-background":
        from transparent_background import Remover
        remover = Remover(mode="base", device="cpu")
        return lambda im: np.asarray(remover.process(im, type="rgba"), np.float32)[..., 3] / 255.0
    raise ValueError(f"unknown model {name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", nargs="+", default=["bench", "composites"])
    ap.add_argument("--models", nargs="+", default=ALL_MODELS, choices=ALL_MODELS)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    for model in args.models:
        predict = None
        for set_name in args.sets:
            images = sorted(Path("data", set_name, "images").iterdir())
            out = Path("data/preds", set_name, model)
            out.mkdir(parents=True, exist_ok=True)
            todo = [p for p in images if args.force or not (out / f"{p.stem}.png").exists()]
            if not todo:
                print(f"{model} / {set_name}: all {len(images)} done")
                continue
            if predict is None:
                predict = load_model(model)
                predict(Image.open(todo[0]).convert("RGB"))  # warm-up, not timed
            times_path = out / "times.csv"
            new_file = not times_path.exists() or args.force
            with open(times_path, "w" if new_file else "a", newline="") as f:
                w = csv.writer(f)
                if new_file:
                    w.writerow(["id", "seconds"])
                for n, p in enumerate(todo, 1):
                    im = Image.open(p).convert("RGB")
                    t0 = time.perf_counter()
                    alpha = predict(im)
                    dt = time.perf_counter() - t0
                    Image.fromarray(np.round(np.clip(alpha, 0, 1) * 255).astype(np.uint8)).save(out / f"{p.stem}.png")
                    w.writerow([p.stem, f"{dt:.4f}"])
                    if n % 50 == 0:
                        print(f"{model} / {set_name}: {n}/{len(todo)}", flush=True)
            print(f"{model} / {set_name}: done ({len(todo)} images)", flush=True)


if __name__ == "__main__":
    main()
