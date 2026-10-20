# Background-removal benchmark

Ever wondered which background-removal model actually works best? This repo tests four popular
open-source ones on 200 product photos and compares how well (and how fast) they cut the product out.

The four models:

- **u2net**, **isnet-general-use** and **birefnet-general**, all run through [rembg](https://github.com/danielgatis/rembg)
- **transparent-background** ([link](https://github.com/plemeri/transparent-background)), in its `base` mode

## The idea

To score a background-removal model you need the "right answer" for every image: a mask (called an
*alpha matte*) that says exactly which pixels are product and which are background. Drawing those by
hand is slow, so here's the trick:

1. Take product photos shot on a **plain white background**, from the
   [Amazon Berkeley Objects (ABO)](https://amazon-berkeley-objects.s3.amazonaws.com/index.html) dataset.
   On white, it's easy to work out the mask automatically: whatever isn't white is product.
2. White backgrounds are a bit too easy, though. So each product is also **pasted onto a random
   texture** (wood, fabric, marble, etc.) from the
   [Describable Textures Dataset (DTD)](https://www.robots.ox.ac.uk/~vgg/data/dtd/). We know
   exactly where we pasted it, so the right answer is still known.

That gives two test sets of 200 images each:

- **bench**: the original white-background photos
- **composites**: the same products on busy textures

## Results

Everything ran on a laptop CPU (Intel i5-11400H, no GPU). The numbers in brackets are 95% confidence
intervals. If two models' ranges overlap a lot, treat them as roughly tied.

**On white backgrounds**

| Model | MAE ↓ | IoU ↑ | Edge MAE ↓ | Seconds per image |
|---|---|---|---|---|
| transparent-background | **0.026** [0.020–0.033] | **0.944** [0.930–0.957] | 0.090 [0.079–0.101] | 8.5 |
| birefnet-general | 0.027 [0.020–0.034] | 0.938 [0.922–0.953] | **0.080** [0.070–0.091] | 15.3 |
| u2net | 0.044 [0.033–0.056] | 0.905 [0.884–0.925] | 0.110 [0.097–0.123] | **0.44** |
| isnet-general-use | 0.055 [0.042–0.069] | 0.894 [0.870–0.918] | 0.120 [0.106–0.134] | 1.1 |

**On textured backgrounds**

| Model | MAE ↓ | IoU ↑ | Edge MAE ↓ | Seconds per image |
|---|---|---|---|---|
| birefnet-general | **0.017** [0.013–0.023] | **0.961** [0.947–0.972] | **0.065** [0.059–0.073] | 16.3 |
| transparent-background | 0.027 [0.020–0.036] | 0.940 [0.923–0.955] | 0.096 [0.086–0.106] | 9.0 |
| u2net | 0.057 [0.044–0.071] | 0.858 [0.826–0.887] | 0.138 [0.123–0.154] | **0.38** |
| isnet-general-use | 0.075 [0.059–0.093] | 0.833 [0.797–0.868] | 0.156 [0.139–0.173] | 1.05 |

### What do these numbers mean?

- **MAE** (lower is better): on average, how far off the model's mask is from the right answer, pixel
  by pixel. 0 would be perfect.
- **IoU** (higher is better): how much the model's cut-out overlaps the real product. 1.0 means a
  perfect match.
- **Edge MAE** (lower is better): the same as MAE, but only looking at a thin strip around the
  product's outline. Getting the inside of a product right is easy; the edges are where models
  usually mess up, so this one's worth watching.
- **Seconds per image**: how long one image takes, not counting loading the model.

One small caveat: on the white set, some timing data got lost when earlier runs were interrupted.
transparent-background's white-set time is based on 41 images and isnet's on 195. The textured-set
timings are complete for every model and tell the same story.

### So which one should I use?

- **Best quality: birefnet-general.** It's the clear winner on textured backgrounds and has the
  cleanest edges everywhere. The catch: it's slow (about 16 s per image on CPU) and needs about 8 GB of RAM.
- **Good balance: transparent-background.** It basically ties BiRefNet on white backgrounds, is
  still very good on textures, and is about twice as fast.
- **Need speed: u2net.** About 40× faster than BiRefNet. It's fine on white backgrounds but gets
  noticeably worse on busy ones.
- **Skip isnet-general-use.** It came last on accuracy in both tests, behind the older u2net.

Fun fact: BiRefNet actually did *better* on the textured backgrounds than on the white ones, while
u2net and isnet both got worse.

## Things that went wrong (and how they got fixed)

The "just use white backgrounds" trick sounded easy, but the automatic masks had a bunch of problems
that needed fixing before the scores could be trusted. If you want all the gory details, including
the fixes that *didn't* work, check out [`ISSUES.md`](ISSUES.md). The short version:

- **Too many phone cases.** About half of all white-background ABO photos are phone cases! A random
  pick of 200 had 115 of them. Fix: look up each image's product category and allow at most 5 per
  category. The final set covers 102 different kinds of products.
- **Text in the photos.** Some product photos have captions, size arrows or logos, which would count
  as "product". Fix: a text detector (easyocr) plus a few simple checks that skip those images.
- **White or see-through products.** A white bottle on a white background is invisible to the
  "whatever isn't white is product" rule. Fix: every mask was checked by eye, and the 31 bad ones were
  swapped out.
- **A white outline around pasted products.** The edges of the masks were a bit too generous, so a
  thin white ring came along when products were pasted onto textures. Fix: work out the edges more
  carefully, using the product's own colour near the edge.
- **Shadows.** Soft grey shadows under products counted as part of the product. Fix: detect small,
  thin, grey patches right underneath the product and remove them.
- **Holes.** The gap between a table's legs or the inside of a ring was filled in as product. Fix:
  open up those holes, with a hand-checked list for the tricky images.
- **BiRefNet ran out of memory.** Fix: one setting in ONNX Runtime (turning off its memory arena)
  brought it down from 12.7 GB to 8.3 GB.

## Limitations

This is a small benchmark, so take it with a pinch of salt:

- **White and see-through products are mostly missing.** They're some of the hardest cases in real
  life, but their masks couldn't be made automatically, so they were left out.
- **The masks aren't perfect.** Some big or unusual shadows and some tiny holes slipped through.
- **Pasted products don't look like real photos.** There's no matching lighting or shadow, so the
  textured set tests "can you find the product on a busy background", not "real-world scenes".
- **The images are small** (256 px), smaller than what most of these models were designed for.
- **One laptop, no GPU.** The speeds are only useful for comparing the models with each other.

## Run it yourself

You'll need [uv](https://docs.astral.sh/uv/) and about 16 GB of RAM.

**1. Set up Python**

```bash
uv venv
uv pip install "rembg[cpu]" transparent-background opencv-python numpy pillow scipy pandas matplotlib easyocr
```

**2. Download the data** and put it in a `data/` folder (git ignores it, so it won't get committed):

- ABO small images, unpacked to `data/images/` (you should end up with `data/images/small/` and
  `data/images/metadata/images.csv.gz`)
- ABO listings metadata, unpacked to `data/listings/metadata/`
- DTD textures, unpacked to `data/dtd/` (images in `data/dtd/images/<texture type>/`)

**3. Run the scripts in order**, from the repo's main folder:

```bash
.venv/bin/python scripts/filter_white_bg.py    # find the white-background photos
.venv/bin/python scripts/image_categories.py   # look up each photo's product category
.venv/bin/python scripts/make_bench_set.py     # pick 200 photos and build their masks
.venv/bin/python scripts/make_composites.py    # paste them onto textures
.venv/bin/python scripts/run_models.py         # run all 4 models (about 3 hours on a CPU!)
.venv/bin/python scripts/score.py              # compare and print the results
```

A few tips:

- The models download themselves the first time you run them.
- If `run_models.py` gets interrupted, just run it again. It picks up where it left off.
- If you rebuild the composites, delete `data/preds/composites/` first so old predictions don't stick around.
- Results end up in `data/results/`: `summary.csv` has the tables above, and `per_image.csv` has
  the score for every single image.

## Credits

- **Amazon Berkeley Objects**: Collins et al., *ABO: Dataset and Benchmarks for Real-World 3D Object
  Understanding*, CVPR 2022 (CC BY 4.0).
- **Describable Textures Dataset**: Cimpoi et al., *Describing Textures in the Wild*, CVPR 2014.
- **Models**: U²-Net (Qin et al.), IS-Net/DIS (Qin et al.), BiRefNet (Zheng et al.), InSPyReNet (Kim et al.).
