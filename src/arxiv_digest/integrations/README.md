# `integrations`

External-service clients — every module that talks to a remote API. Modules
here own their own HTTP plumbing, rate-limit etiquette, and caching keys;
the `services` package (Phase 3) composes them into domain logic.

- **`semantic_scholar/`** — the S2 Academic Graph + Recommendations client
  (the paper-data backbone). Its own package; see its own README.
- **`arxiv/`** — arXiv-derived content: arXiv-id detection (`ID_RE`) plus a
  paper's figures/captions and full body text from ar5iv (arXiv's LaTeX→HTML
  renderer). Its own package (was `ar5iv`, renamed as the single home for arXiv
  code); see its own README.
- **`huggingface/`** — code & artifact links (GitHub repo, models/datasets/
  Spaces) from Hugging Face Papers. Its own package; see its own README.
- **`taxonomy/`** — the app's controlled subject vocabularies: `taxonomy.arxiv`
  (arXiv category codes) and `taxonomy.s2` (S2 fields of study). Static/inline
  data, no network. Its own package; see its own README.
