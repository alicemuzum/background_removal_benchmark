# Issues and fixes

Significant problems found while building the benchmark, how each was found, and how it was
fixed. Source material for the README.

---

## 1. Half the white-background images are phone cases

**Symptom.** A plain random sample of 200 white-background images had 115 phone cases.

**How found.** After mapping every image to its listing's `product_type`. Before that, an
estimate from looking at a contact sheet said "about a quarter", which badly undercounted.

**Cause.** `CELLULAR_PHONE_CASE` is 51.5% of the 205,805 white-background ABO images. The next
largest categories are GROCERY (4.9%) and SHOES (4.4%).

**Fix.** Downloaded the ABO listings metadata, joined image ids to `product_type`
(`scripts/image_categories.py`), and capped each category at 5 images (`--cap` in
`scripts/make_bench_set.py`). The set now covers about 100 product types.

---

## 2. Marketing text and diagrams in product images

**Symptom.** Some listing images have captions, dimension labels and arrows, logos, or are
nothing but text (ingredient lists). The white-background matte treats this text as foreground,
so it isn't a fair ground truth.

**Fix, in three layers** (all in `scripts/make_bench_set.py`):
1. `keep_main_parts`: drop disconnected blobs smaller than 10% of the largest part, and skip the
   image if more than 15% of the foreground would be dropped. This removes small captions and
   stray marks.
2. Outline-ratio check in `looks_sane`: text blocks are mostly outline. Real products have
   about 5% of their foreground pixels on an edge, thin products (scissors, necklaces) up to
   about 37%, and a text page about 67%, so mattes above 50% are rejected. This caught a
   text-only image whose lines were large blobs that layer 1 couldn't catch.
3. `has_text_overlay`: easyocr's text detector (detection only, no reading). An image is skipped
   if more than 0.5% of it is text lying *off* the product. Text printed on the product (labels)
   is allowed. Near-square boxes are ignored, because at 256 px the detector sometimes boxes
   whole hooks or earrings.

**Verified.** All 18 images rejected by layer 3 were inspected and all had real off-product text.

**Remaining.** Very small text (e.g. "32mm x 18pcs" at 256 px) isn't detected even at higher
magnification. Those cases were caught in the manual review (issue 3).

---

## 3. Wrong mattes on white and clear products

**Symptom.** For white or transparent products (white bottles, boxes, furniture, glass light
fittings, clear containers), parts of the product are as white as the background and come out
as background in the matte.

**How found.** Every one of the 200 bench mattes was reviewed by eye, composited on magenta so
missing or extra regions stand out.

**Fix.** 31 images were excluded via `scripts/bench_exclude.txt` (each with a short reason):
21 white/clear products and 10 text or diagram images the detector missed. Excluded slots refill
in the same seeded order, and every replacement was reviewed too (two more rounds, until the
replacements were clean).

**Remaining / TODO.** White and clear products are among the hardest real-world cases, and the
benchmark now under-represents them. Plan: bring them back as a separate "hard" subset with
hand-corrected mattes (see `TODO.md`).

---

## 4. White fringe around products in composites

**Symptom.** Composited products had a ring of white pixels between them and the new
background, on almost every image.

**Cause, found in stages.**
1. *First attempt: colour recovery only.* Edge pixels are part product, part white, so
   `decontaminate` (`scripts/make_composites.py`) recovers the true colour as
   F = (C − (1−α)·255) / α. That's correct only if α is correct, and the fringe stayed.
2. *Second attempt: soft inner edge.* Pixels within 2 px inside the outline got
   α = distance-from-white / 60. Applying this *before* the selection checks pushed border
   pixels under the 0.5 cutoff, which let 11 bad images (products touching the frame, white
   products) into the set. It was moved to run after selection, but the fringe remained.
3. *Measured.* The recovered edge colour averaged about 220 out of 255 (near white) for nearly
   all products, including dark ones. The real bug was the original edge ramp,
   α = distance-from-white / 15, which assumes any pixel within 15 levels of white is fully
   product. A pixel at 245 next to a dark glove is really about 5% glove but got α ≈ 0.67.

**Fix.** `refine_edge_alpha` in `scripts/make_bench_set.py` estimates edge alpha against the
*local product colour*: α = (W−C)·(W−F) / |W−F|², with F averaged from nearby clearly coloured
product pixels. It's the standard formula when the background colour is known. It applies only
along the outer silhouette (holes filled), and only where F is at least 40 levels from white.
Tiny pale blobs left floating (JPEG noise) are dropped.

**Attempts discarded along the way.**
- Re-running blob removal after the edge change made whole thin parts look like detached blobs
  and deleted them (the side strips on a phone case).
- Applying the edge band to every boundary, interior ones included, punched holes around the
  letters on a white label. A few near-white specks in the label connected to the outside
  through a thin channel, which made the label look like an outline.

**Verified.** Recovered edge colours now track the product (mean 93 vs 125 for the product just
inside the edge, instead of 220). No deep-interior pixel changed in any of the 200 mattes. The
bench selection is unchanged. 48 composites on the darkest backgrounds were inspected and show
no fringe.

**Remaining.** Edges of near-white products keep the old matte, because they can't be separated
from a white background.

---

## 5. Shadows and floor reflections counted as product

**Symptom.** Some source photos have a soft grey shadow or reflection under the product (shoes,
a game controller, wipes, boxes, jewellery). It's grey rather than white, so the matte treats it
as product and it appears as a pale patch in composites. Background-removal models normally drop
shadows, so the ground truth was wrong for these images.

**Attempts discarded along the way.**
- *Pale pixels connected to the background → background.* Colour alone can't separate a shadow
  from a light product surface. It would have removed lamp shades, white pillows, silver metal and
  labels, and 47 of the 200 products would have lost more than 15% of their area.
- *Growing the background only through smooth pixels* (shadows fade out, product edges are
  sharp). It found the real shadows, but light products still leaked: at 256 px with JPEG
  softening, their edges against white aren't sharp enough to stop the growth.
- *Region tests on brightness profile and contact with coloured product.* These didn't separate
  shadows from pale products. The shadow of a black shoe and a white plastic knife had nearly the
  same numbers.
- *Reopening white pockets after a shadow is removed* (e.g. the gap between a controller's grips,
  closed off by the shadow). It erased white product faces and part of a white label, which also
  connect to the outside once the shadow is gone.

**Fix.** `remove_shadows` in `scripts/make_bench_set.py`. Candidates are pale (within 60 of
white), grey (channel spread < 30) and smooth (gradient < 6/px) pixels that the outside background
can reach without crossing an edge. A connected candidate region is removed only if it is also:
- small next to the product (< 15% of its area),
- thin (at most 25 px from the outside),
- under the product: at least 60% of its pixels have clearly coloured product within 25 px
  directly above.
Like the edge refinement, it runs only on the saved matte, after selection. Polished silver looks
just like a shadow under these tests, so three ids where it would take real product (a ring band,
an earring bezel, part of a faucet handle) are listed in `scripts/shadow_skip.txt`.

**Verified.** 27 of the 200 mattes changed, and no image lost more than 10% of its product. Every
removed region was inspected on the source image and all are shadows or reflections under the
product. Composites before and after were compared side by side. The bench selection is
unchanged.

**Remaining.** Large or unusual shadows fail the size, thickness or position tests and stay in the
matte. A white pocket of background closed off by a shadow (the gap between a controller's grips)
also stays, because reopening those erased product (see above).

---

## 6. Background seen through holes in the product counts as product (open)

**Symptom.** White background visible *through* a product (inside a ring, through a bag's handle
loop) is kept as foreground, so it shows up white in composites.

**Cause.** `alpha_from_white_bg` treats white regions not connected to the image border as part
of the product. That's deliberate: it keeps white labels and white printed areas solid. But a
hole through the product is also white and also not connected to the border.

**Status.** Open. Found while checking the shadow fix. Telling a hole from a white label needs
more than colour (both are pure white and fully enclosed). Options: a per-image list of hole ids
fixed by hand, or a rule based on shape, such as holes being bounded on all sides by the same
part.
