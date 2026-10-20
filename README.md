# Background-removal benchmark

A small, reproducible benchmark of four open background-removal models on product photos:

- `u2net`, `isnet-general-use` and `birefnet-general`, run through [rembg](https://github.com/danielgatis/rembg)
- [`transparent-background`](https://github.com/plemeri/transparent-background) (InSPyReNet, `base` mode)

The images come from the [Amazon Berkeley Objects (ABO)](https://amazon-berkeley-objects.s3.amazonaws.com/index.html)
small image set. Products photographed on a plain white background give a reference alpha matte
almost for free. The same products are then pasted onto textures from the
[Describable Textures Dataset (DTD)](https://www.robots.ox.ac.uk/~vgg/data/dtd/), so the models are
also scored on busy, non-white backgrounds while the ground truth stays known exactly.

## Results

200 products from 102 product types, each scored on its original white background (**bench**) and
on a random DTD texture (**composites**). All models ran on CPU (Intel i5-11400H, 6 cores / 12 threads).
Brackets are bootstrap 95% intervals of the mean over images.

**White background (bench)**

| Model | MAE ↓ | IoU ↑ | Edge MAE ↓ | Seconds / image |
|---|---|---|---|---|
| transparent-background | **0.026** [0.020–0.033] | **0.944** [0.930–0.957] | 0.090 [0.079–0.101] | 8.5 |
| birefnet-general | 0.027 [0.020–0.034] | 0.938 [0.922–0.953] | **0.080** [0.070–0.091] | 15.3 |
| u2net | 0.044 [0.033–0.056] | 0.905 [0.884–0.925] | 0.110 [0.097–0.123] | **0.44** |
| isnet-general-use | 0.055 [0.042–0.069] | 0.894 [0.870–0.918] | 0.120 [0.106–0.134] | 1.1 |

**Textured background (composites)**

| Model | MAE ↓ | IoU ↑ | Edge MAE ↓ | Seconds / image |
|---|---|---|---|---|
| birefnet-general | **0.017** [0.013–0.023] | **0.961** [0.947–0.972] | **0.065** [0.059–0.073] | 16.3 |
| transparent-background | 0.027 [0.020–0.036] | 0.940 [0.923–0.955] | 0.096 [0.086–0.106] | 9.0 |
| u2net | 0.057 [0.044–0.071] | 0.858 [0.826–0.887] | 0.138 [0.123–0.154] | **0.38** |
| isnet-general-use | 0.075 [0.059–0.093] | 0.833 [0.797–0.868] | 0.156 [0.139–0.173] | 1.05 |

Metrics, per image and then averaged:

- **MAE**: mean absolute difference between predicted and reference alpha over the whole image.
- **IoU**: intersection over union of the masks thresholded at alpha 0.5.
- **Edge MAE**: MAE only within 4 px of the reference outline. Whole-image MAE is dominated by easy
  interior and background pixels; this isolates how well the edge itself is cut.
- **Seconds / image**: inference time after a warm-up call, model load excluded. On the bench set,
  some timings were lost to interrupted runs, so transparent-background's figure is from 41 images
  and isnet's from 195. The composite timings cover all 200 for every model and agree.

### What the numbers say

- **BiRefNet is the most accurate on textured backgrounds** and has the best edges on both sets. It
  beats transparent-background on 155 of the 200 composites (by MAE), and only 6 composites fall
  below IoU 0.8, against 13 for transparent-background and 44–48 for u2net and isnet. It's also the
  slowest model, at about 16 s per image and about 8 GB of RAM on CPU.
- **transparent-background ties BiRefNet on white backgrounds** (the intervals overlap; BiRefNet
  wins 112 of 200 images) at about half the time.
- **u2net and isnet lose ground on textures.** IoU drops from about 0.90 to 0.83–0.86. BiRefNet
  doesn't get worse, and transparent-background barely changes.
- **isnet-general-use ranks last on accuracy in both settings**, behind the older and faster u2net.
- **u2net is the fast option**, about 40× faster than BiRefNet, if 0.86–0.90 IoU is acceptable.

Per-image scores are written to `data/results/per_image.csv`, the table above to
`data/results/summary.csv`.

## How the benchmark is built

1. **Find white-background images.** All 398,212 ABO small images were scanned. An image qualifies
   if a 3% border around it is uniformly near-white (mean ≥ 238, standard deviation ≤ 12). 205,805 qualify.
2. **Map images to product types.** The ABO listings metadata gives each image a `product_type`.
3. **Draw 200 images** with a fixed seed, at most 5 per product type, and derive a matte from the
   white background (pixels connected to the border and close to white are background). Images are
   skipped if the matte looks implausible (foreground too small or large, touching the frame, too
   fragmented) or if they carry marketing text. The saved matte is then cleaned up: shadows and see-through
   holes are removed and edge alpha is re-estimated (see below).
4. **Composite** each product onto a random DTD texture (46 of DTD's 47 texture classes appear),
   recovering edge colours so no white halo is carried over. The matte is unchanged, so it's still the
   exact ground truth.
5. **Run each model** on both sets and **score** against the mattes.

## Problems found and how they were fixed

Getting trustworthy ground truth took most of the work. The short version is below; the full
account, including the approaches that didn't work, is in [`ISSUES.md`](ISSUES.md).

**Half of the white-background images are phone cases.** `CELLULAR_PHONE_CASE` is 51.5% of them
(the next category is 4.9%), and a plain random sample of 200 had 115. The listings metadata was
joined in to get product types, and each type is capped at 5 images. The set now spans 102 types.

**Marketing text and diagrams.** Captions, dimension arrows, logos and whole text pages would count as
"product" in the matte. Three filters handle them: small detached blobs are dropped, mattes that are
mostly outline (text) are rejected, and images with more than 0.5% of their area covered by text
*off* the product are skipped, using easyocr's detector. Text printed on the product itself is kept.

**White and clear products.** Where a product is as white as the background, the matte can't tell
them apart. Every matte was reviewed by eye on a magenta background; 31 were excluded (21 white or
clear products, 10 text images the detector missed) and listed in `scripts/bench_exclude.txt` so
rebuilds are reproducible.

**A white halo around every composite.** The original edge rule treated any pixel within 15 levels of
white as fully product, so a pale edge pixel next to a dark glove that is really 5% glove got about
67% alpha. Two earlier fixes (colour recovery alone, a softer inner edge) didn't remove it. The final fix
estimates edge alpha against the *local product colour*: α = (W−C)·(W−F)/|W−F|², with F taken from
nearby solid product pixels, which is the standard formula when the background colour is known.
Recovered edge colours went from about 220 (near white) to tracking the product.

**Shadows and floor reflections.** Soft grey shadows under shoes, boxes and jewellery were counted as
product, though models are expected to drop them. Pale, grey, smooth regions reachable from the
background are removed only if they are small, thin, and sit directly under solid product. Simpler
rules ate light-coloured products. 27 mattes changed, each checked on the source image; 3
polished-silver items are exempt.

**Background seen through the product.** Gaps between table legs, inside rings or through handles
were filled in as product. The scoring run exposed this: u2net was penalised for cutting around
side-table legs correctly. Enclosed white regions are now opened when they look like plain
background, with per-image overrides from a review of all 63 affected images (`scripts/holes.txt`).
35 mattes changed.

All matte clean-ups run *after* selection, so they never change which 200 images are in the set.

**BiRefNet ran out of memory** (12.7 GB on a 15 GB machine). Turning off ONNX Runtime's CPU memory
arena brings it to 8.3 GB with no loss of speed.

## Limitations

- **White and clear products are under-represented.** They are among the hardest real cases but were
  excluded because their mattes can't be derived automatically. A hand-corrected "hard" subset is
  planned (`TODO.md`).
- **Some ground-truth errors remain.** Large or unusual shadows fail the shadow tests and stay in the
  matte. Small see-through gaps in images outside the 63 reviewed ones may still be filled in.
  Edges of near-white products keep a hard-edged matte.
- **Composites are not real photos.** A product pasted onto a texture has no matching lighting,
  shadow or perspective, so the composite set tests separation from busy backgrounds rather than
  realistic scenes.
- **Small images.** ABO "small" images are at most 256 px on the long side, which is below the
  resolution most of these models are tuned for.
- **One CPU, no GPU.** Speeds are only comparable with each other.

## Reproducing

Requires [uv](https://docs.astral.sh/uv/). About 16 GB of RAM is enough if BiRefNet runs on its own.

```bash
uv venv
uv pip install "rembg[cpu]" transparent-background opencv-python numpy pillow scipy pandas matplotlib easyocr
```

Data (all under `data/`, which is gitignored):

- ABO small images, unpacked to `data/images/` (`data/images/small/`, `data/images/metadata/images.csv.gz`)
- ABO listings metadata, unpacked to `data/listings/metadata/listings_*.json.gz`
- DTD, unpacked to `data/dtd/` (`data/dtd/images/<class>/*.jpg`)

Then, from the repo root:

```bash
.venv/bin/python scripts/filter_white_bg.py      # -> data/sources/, data/white_bg_scan.csv
.venv/bin/python scripts/image_categories.py     # -> data/image_categories.csv
.venv/bin/python scripts/make_bench_set.py       # -> data/bench/
.venv/bin/python scripts/make_composites.py      # -> data/composites/
.venv/bin/python scripts/run_models.py           # -> data/preds/  (about 3 h on CPU, mostly BiRefNet)
.venv/bin/python scripts/score.py                # -> data/results/
```

Model weights download on first use (rembg to `~/.rembg/models/`, easyocr to `~/.EasyOCR/model/`).
`run_models.py` skips images that already have a prediction, so an interrupted run can be resumed.
If the composites are rebuilt, delete `data/preds/composites/` first.

## Credits

- Amazon Berkeley Objects: Collins et al., *ABO: Dataset and Benchmarks for Real-World 3D Object
  Understanding*, CVPR 2022. Licensed CC BY 4.0.
- Describable Textures Dataset: Cimpoi et al., *Describing Textures in the Wild*, CVPR 2014.
- Models: U²-Net (Qin et al.), IS-Net/DIS (Qin et al.), BiRefNet (Zheng et al.), InSPyReNet (Kim et al.).
