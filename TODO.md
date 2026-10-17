# TODO

- **White / clear products in the bench set.** `alpha_from_white_bg` can't separate
  white or transparent product parts from the white background, so 21 such images
  were dropped via `scripts/bench_exclude.txt` (see the "White / clear" section).
  These are among the hardest real-world cases, so the benchmark currently
  under-represents them. Plan: bring them back as a separate "hard" subset with
  hand-corrected mattes, and report scores with and without it.
