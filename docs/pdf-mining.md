# PDF mining — why the PDF is the cache, and everything else is derived

*(Written 2026-07-18, alongside v5.27.0's open-access PDF mining. This is the
design rationale behind `services/pdf`'s storage choices — the questions
Patrick asked before approving, answered for the next reader. The package's
mechanics live in `src/atlas/services/pdf/README.md`; the knobs in
`docs/configuration.md` § `pdf`.)*

## The shape of the problem

For papers ar5iv can't serve (journal papers, failed LaTeX conversions), Atlas
downloads the paper's open-access PDF and mines it with pymupdf. Three
artifacts come out of one file:

1. **Full text** — for the researcher's `read_paper(detail="full")`.
2. **The figure manifest** — one entry per figure/table/algorithm, each just
   four fields: `kind`, 1-based `page`, `caption`, and the `region` rectangle
   in page points. A few KB per paper.
3. **Figure images** — PNGs served by `/api/pdf_figure/<token>/<n>`.

The design question: which of these do we store, and where?

## The answer: store the source, derive the rest

**A rendered PNG is not a thing that exists inside the PDF waiting to be
pulled out — it is computed from the PDF.** The manifest stores only
coordinates ("page 5, rectangle [100, 100, 300, 250]"); producing pixels means
opening the PDF, loading the page, and rasterizing that rectangle. The PDF is
the render's *input*. Render-on-request therefore only works while the file
still exists.

That asymmetry drives everything:

- **The PDF (the source)** lives as a real file in `data/oa_pdfs/`, named by a
  hash of its URL — the one store with a hard LRU cap
  (`config.pdf.cache_files`, pruned by mtime after every download, plus the
  `max_bytes` per-file cap). It is the only artifact we cannot cheaply
  recompute (recomputing it = re-downloading it).
- **Text and manifest (small derivatives)** memoize in the SQLite cache
  (`pdftext:` / `pdffloats:` keys). A few KB per paper — the shape that table
  (JSON text values) was built for.
- **Images (the big derivative) are never stored at all.** A render takes
  milliseconds from the local file, and every response carries
  `Cache-Control: max-age=86400`, so the browser holds the pixels for a day.
  Server-side, pixels are the biggest artifact (0.5–3 MB per paper — hundreds
  of times the text + manifest combined) and the cheapest to recompute: the
  worst combination for caching.

### Why not cache the PNGs in SQLite alongside text + manifest?

Three reasons, in descending weight:

1. The cache table stores **JSON text** — binary PNGs would need base64
   (+33 %) or a new blob table.
2. `digest.db` has **no eviction** — TTLs are checked at read time; rows are
   never deleted. The PDF directory is the store with an actual LRU cap.
   Caching PNGs in SQLite would move the *largest* artifacts out of the capped
   store into the uncapped one — the DB would only ever grow.
3. It buys almost nothing: the one helped scenario is "LRU evicted the PDF
   *and* the browser cache expired *and* someone re-opens the figures" — which
   self-heals with a single re-download (the `pdfurl:` registry keeps the
   token → URL mapping so the figure route can re-fetch on its own).

### Why not delete the PDF after mining ("pre-render-and-delete")?

A coherent alternative if we didn't want third-party PDFs on disk: at mining
time, render **every** manifest entry to an image file cache, extract the
text, delete the PDF. It was considered and rejected:

- Rendering must be **eager** — once the PDF is gone there is nothing left to
  render from, so you pay for every figure whether or not anyone ever views
  it (and the PNGs total roughly what the PDF weighed anyway).
- Any later render change re-downloads everything (see dpi below).
- The month-TTL re-mine (see below) also becomes a re-download.

## Why the derived caches have a TTL at all

A paper is immutable — but the cached value is not the paper, it's **the
output of our extraction code run on the paper**, and two things about that do
change:

1. **The extraction heuristics.** The caption-anchoring rules get tuned (the
   text-only-float miss is a known gap). With a month TTL, improved mining
   reaches previously-viewed papers automatically. The permanent-cache
   alternative is a version lever — like the TL;DR cache's `tldr:v1:` key,
   bumped to invalidate — which works but requires remembering to bump it on
   every heuristic tweak. TTL is the self-healing, zero-discipline version;
   its cost is one re-download + re-mine per paper per month, only for papers
   actually still being opened.
2. **The URL's contents, occasionally.** Publishers swap files under stable
   URLs — corrected proofs, updated arXiv versions, retraction watermarks —
   and OA copies move or disappear. Rare, but a permanent cache would hold
   the stale answer forever.

Immutable paper, mutable lens: the TTL refreshes the lens.

## dpi, and why keeping the PDF future-proofs the images

Dots per inch — how finely a page region is rasterized. PDF coordinates are
points (72/inch), so a 3-inch-wide figure region at `render_dpi: 150` becomes
a 450-pixel-wide PNG; at 300, 900 pixels. Most paper figures are **vector**
graphics (matplotlib, TikZ) — drawing instructions, effectively infinite
resolution. While the PDF is on disk, "make every figure 2× sharper for the
lightbox" is a one-line config change; had we stored only 150-dpi PNGs and
deleted the sources, it would be a re-download of every paper.

## Summary

The PDF is the only *source*; text, manifest, and pixels are all cheap
*derivatives*. So: source in the LRU-capped file store, small derivatives
memoized in SQLite with a freshness TTL, pixels recomputed on demand — because
they are simultaneously the biggest artifact and the cheapest to recompute.
