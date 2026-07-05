# `integrations`

External-service clients — every module that talks to a remote API. Modules
here own their own HTTP plumbing, rate-limit etiquette, and caching keys;
the `services` package (Phase 3) composes them into domain logic.

- **`semantic_scholar/`** — the S2 Academic Graph + Recommendations client
  (the paper-data backbone). Its own package; see its own README.
- **`arxiv_client/`** — seed search against arXiv itself (finds the starting
  paper; `semantic_scholar` builds the graph around it once picked). Its
  own package; see its own README.
- **`ar5iv/`** — everything from ar5iv (arXiv's LaTeX→HTML renderer): a
  paper's figures/captions and its full body text. Its own package (merges
  the original app's separate `figures.py` and `fulltext.py`); see its own
  README.
- **`huggingface/`** — code & artifact links (GitHub repo, models/datasets/
  Spaces) from Hugging Face Papers. Its own package; see its own README.
- **`taxonomy/`** — the arXiv category taxonomy (arXiv-specific paper
  enrichment; bundled JSON, no network). Its own package; see its own README.
