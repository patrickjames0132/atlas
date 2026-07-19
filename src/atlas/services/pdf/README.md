# services/pdf — open-access PDF mining

Full text and figures for papers **ar5iv can't serve**: journal papers that
were never on arXiv, and the occasional arXiv paper whose LaTeX ar5iv failed
to render. When a provider knows an open-access PDF for the paper (S2's
`openAccessPdf`, an OpenAlex location's `pdf_url`) — or the paper is on arXiv,
whose `arxiv.org/pdf/<id>` is always open — this package downloads the file
once and mines it with pymupdf.

```
resolve.py — where the paper's OA PDF lives (arXiv → primed URL → provider), cached
fetch.py   — the download + on-disk cache (data_dir/oa_pdfs, LRU-pruned)
text.py    — readable body text from the file (the ar5iv fulltext's PDF twin)
floats.py  — caption-anchored float mining: figures, tables, algorithms
mine.py    — the cached high-level API the app calls; token → URL registry
errors.py  — PdfError, the package's one exception
```

## Who uses it

* **`routes/graph.py`** — `/api/paper/<ref>/figures` falls back
  ar5iv → the mined **figure manifest**; `/api/pdf_figure/<token>/<n>` serves
  a manifest entry as a rendered PNG; paper hydration `prime()`s the resolver.
* **`agents/researcher/tools.py`** — `read_paper(detail="full")` falls back
  ar5iv → `get_pdf_text`, and `show_figure` draws from the same figure
  manifest the full read printed.

**The figure manifest** is what mining a PDF produces and caches
(`pdffloats:<token>`): one entry per float, each just four fields — `kind`
(`figure`/`table`/`algorithm`), 1-based `page` number, `caption`, and the
`region` rectangle (`[x0, y0, x1, y1]` in page points). No pixels are stored:
images are rendered from `page`+`region` on demand.

> **Storage rationale in depth:** [docs/pdf-mining.md](../../../../docs/pdf-mining.md)
> — why the PDF is the cache and text/manifest/pixels are derivatives, why the
> derived caches carry a TTL over an immutable paper, and what dpi has to do
> with keeping the source.

## The geometry, precisely

How `floats.py` turns a page of ink into figure regions — with the
terminology the code (and the tuning constants) use.

First, the two nouns that name the pipeline's input and output. A **float**
is typography's term for a figure, table, or algorithm block — content that
"floats" free of the text flow to wherever the layout fits it, carrying a
caption. It's what this module hunts, hence the filename. The **figure
manifest** is what the hunt produces and caches: the list of found floats,
one entry each (`kind`, `page`, `caption`, `region`). Floats are the things;
the manifest is the record of them.

All coordinates are in **points** (pt): PDF's native unit, 1/72 inch, origin
at the page's top-left.

**The raw material.** pymupdf exposes three kinds of ink on a page:

- **Text blocks** (`page.get_text("blocks")`) — paragraphs/lines of text,
  each with a bounding rectangle. Captions are found here.
- **Embedded images** (`page.get_images` + `get_image_rects`) — raster
  pictures (photos, plot PNGs) placed on the page, each with the rectangle
  it's drawn into.
- **Drawings** (`page.get_drawings`) — vector strokes: every line, curve,
  and filled shape as its own tiny rectangle. A matplotlib plot is hundreds
  of these; so is a hand-drawn diagram. pymupdf's `page.cluster_drawings()`
  groups strokes that touch or nearly touch (~3 pt) into **drawing
  clusters** — one rectangle per connected clump of ink. Crucially, a
  *sparse* diagram (arrows and circles with whitespace between them — a
  backup diagram) comes back as MANY small clusters, not one big one.

**Special drawings.** A **hairline rule** is a drawing whose rectangle is
almost flat (height ≤ 3 pt) and wide (≥ 100 pt) — the horizontal lines that
bound tables and algorithm boxes. (pymupdf quirk: such a rectangle is
*empty* — zero area — and `Rect.__or__` silently ignores empty operands, so
rule spans are assembled from raw min/max coordinates, never `|`.)

**Step 1 — find captions.** Every text block matching `CAPTION_RE`
(`Figure N:` / `Fig. N.` / `Table N:` / `Algorithm N`) is a **caption
block**. The trailing `[:.]` is load-bearing for Figure/Table: an in-prose
cross-reference ("Figure 2 provides…") starts with the same words but has no
separator. Algorithm captions carry no separator; their filter is the rule
anchor below.

**Step 2 — collect content candidates.** The page's **candidate rectangles**
are every embedded-image placement at least `_MIN_TILE` (30 pt) on a side,
plus every drawing cluster with area ≥ `_MIN_CLUSTER_AREA` (100 pt²). This
floor is a **dust filter** and nothing more — it drops stray specks (a
6×6 pt fleck is not evidence of anything) while *keeping* the small pieces
sparse diagrams are made of. It was originally 4000 pt², which silently
discarded every piece of Sutton & Barto's backup diagrams (each arrow
column is a few hundred pt²); the lesson — filter dust at the input,
judge *size* only on the finished answer — is written up in `docs/bugs.md`.

**Step 3 — seed a region from the caption.** For a figure caption, look
ABOVE it (fall back to below): every candidate whose bottom edge is within
`_GAP` (60 pt) of the caption's top edge and which overlaps the caption
horizontally becomes a **seed**. The union of the seeds is the initial
**region** — one rectangle that will grow.

**Step 4 — grow by axis-aware chaining.** Repeatedly, any remaining
candidate for which `_chain_near(region, rect)` holds is unioned in, until
nothing more joins. `_chain_near` is deliberately looser than "touches":
a piece joins when it **overlaps the region in one axis** and sits within
`_CHAIN_GAP` (60 pt) of it **in the other**. Contact-only chaining (the
first implementation, an 8 pt pad) handled subfigure tiles that touch, but
couldn't walk a sparse diagram whose pieces sit 40–60 pt apart and relate
*diagonally* — from one seeded arrow column it never reached the rest.
Axis-aware chaining climbs column to column: each newly joined piece
extends the region, which brings the next piece within reach.

**Step 5 — judge the answer.** The grown region must have area ≥
`_MIN_REGION_AREA` (4000 pt²) — the **region floor**. This is where junk
actually dies: a lone underline or footnote rule near a caption may seed a
region, but it can't *grow* one of figure size, so it's rejected. The two
floors work as a pair: the dust filter keeps the inputs honest, the region
floor keeps the answers honest, and everything in between is allowed to be
small.

Tables and algorithms take different step-3/4 routes (in `_table_region` /
`_algorithm_region`): tables try pymupdf's `find_tables` bounding box, then
a **rule span** — consecutive hairline rules of the same width walking away
from the caption, the anatomy of a booktabs table — then a drawing-skeleton
cluster widened to the caption's x-span; algorithms take the region between
the full-width rule directly above their caption and the last same-width
rule below it. Both include their caption in the rendered clip (it's part
of the float's visual identity); figures don't (theirs is displayed as the
card text instead).

**Known misses**, all shapes with no geometry to anchor: floats made purely
of text (no image, drawing, or rule — pseudo-code "figures" in very old
PDFs), and truly uncaptioned inline graphics. Edge text labels of a figure
(axis names hanging outside the drawn ink) can also clip, since text blocks
never join the union.

## Design decisions worth knowing

* **Caption-first mining.** A PDF has no semantic markup, so floats are
  found from their captions and the caption anchors the content region —
  the full pipeline, with its terminology, is the "The geometry, precisely"
  section above. The caption doubles as the junk filter: uncaptioned
  drawing clusters (decorations, stray rules) are never shown. Mining caps
  are the caller's: paper-sized for OA papers (`config.pdf.research_papers`),
  book-sized for uploaded library PDFs (`config.pdf.library_documents`) — one
  sub-object per corpus, because paper-tuned limits were silent data loss
  on textbooks.
* **Renders, not embedded images.** A manifest entry is served by rendering
  its page region to PNG at `config.pdf.render_dpi` — vector figures
  (matplotlib, TikZ) have no embedded image to extract, and a render treats
  raster and vector floats identically.
* **Tokens, not URLs, in the browser.** Image URLs are
  `/api/pdf_figure/<token>/<n>` where the token is a hash of the PDF URL,
  resolvable only through the server-side `pdfurl:` registry written when a
  PDF is mined. The browser never supplies a URL, so the route can't be used
  as an open proxy (the same SSRF posture as the ar5iv figure proxy).
* **Everything is cached, misses included.** The file on disk
  (`oa_pdfs/`, LRU beyond `config.pdf.cache_files`), the mined text/floats
  and the resolver's answers in the SQLite cache for a month (published PDFs
  are immutable) — including "no PDF"/"nothing mined", so a barren paper
  isn't re-mined on every panel open. Transient provider failures are the
  one thing **not** cached.
* **pymupdf trap, learned the hard way:** a hairline rule is an *empty* rect
  (zero height) and `Rect.__or__` silently ignores empty operands — rule
  spans are built from raw min/max coordinates, never `|`.

## How it's verified

Offline, like the whole suite: `test/atlas/services/pdf/` builds synthetic
PDFs with pymupdf in-test (drawn figures, ruled algorithm boxes, booktabs
tables, prose decoys) and runs the real geometry pipeline over them; the
fetcher's network is a monkeypatched `urlopen`. The extraction heuristics
were tuned against three real PDFs (JMLR's LDA paper — vector-only figures;
Attention Is All You Need — raster figures + booktabs tables; PPO — algorithm
floats and rules-and-ticks appendix tables): 33 of 35 real floats mined with
correct captions, the two misses both text-only floats.
