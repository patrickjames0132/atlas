# `integrations`

External-service clients — every module that talks to a remote API. Modules
here own their own HTTP plumbing, rate-limit etiquette, and caching keys;
the `services` package (Phase 3) composes them into domain logic.

- **`semantic_scholar/`** — the S2 Academic Graph + Recommendations client
  (the paper-data backbone); also holds S2's fields-of-study vocabulary
  (`vocab`). Its own package; see its own README.
- **`arxiv/`** — arXiv-derived content: arXiv-id detection (`ID_RE`), a paper's
  figures/captions and full body text from ar5iv (arXiv's LaTeX→HTML renderer),
  and the arXiv category taxonomy (`vocab` + bundled `taxonomy.json`). Its own
  package (was `ar5iv`, renamed as the single home for arXiv code); see its own
  README.
- **`huggingface/`** — code & artifact links (GitHub repo, models/datasets/
  Spaces) from Hugging Face Papers. Its own package; see its own README.

Each provider owns its own controlled **vocabulary** — `arxiv.vocab` (category
codes) and `semantic_scholar.vocab` (fields of study) — rather than a shared
`taxonomy` package. Static/inline data, no remote call.
