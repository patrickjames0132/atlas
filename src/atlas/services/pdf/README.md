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

## Design decisions worth knowing

* **Caption-first mining.** A PDF has no semantic markup, so floats are
  found from their captions (`Figure N:` / `Table N:` / `Algorithm N`) and
  the caption anchors the content region — figures above the caption
  (subfigures union in by adjacency chaining), tables below-or-above via
  `find_tables` → same-width **rule spans** (booktabs) → widened drawing
  skeletons, algorithms between the full-width rules that visually box them.
  The caption doubles as the junk filter: uncaptioned drawing clusters
  (decorations, stray rules) are never shown. The known miss: floats made
  purely of text (no image, drawing, or rule anywhere — seen in very old
  PDFs), which nothing anchors geometrically.
* **The `[:.]` in the caption regex is load-bearing** — in-prose references
  ("Figure 2 provides…") start exactly like captions ("Figure 2: …");
  algorithm captions have no colon but must sit directly under their float's
  top rule, which filters prose mentions the same way.
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
