# `integrations`

External-service clients — every module that talks to a remote API. Modules
here own their own HTTP plumbing, rate-limit etiquette, and caching keys;
the `services` package (Phase 3) composes them into domain logic.

Since v5.0.0 a graph is built from **one** of two interchangeable providers,
chosen per graph in the header's "Data source" dropdown:

- **`semantic_scholar/`** — the S2 Academic Graph + Recommendations client; as a
  graph provider it supplies the seed, references, and citer relations. Its live
  citer path has a ~10k-offset landmark recency bias, now fixed by its
  **`corpus/`** sub-package (the offline bulk-Datasets **citations corpus** →
  local Parquet, queried via DuckDB and preferred over the live path when a
  release is ingested; the AWS Athena-over-S3 endgame's local prototype). Also
  holds S2's fields-of-study vocabulary (`vocab`) and the recommendations client
  the researcher's `expand_node` still uses. Its own package; see its own README.
- **`openalex/`** — the OpenAlex client: seed resolution, references, citations,
  and the Latest-Publications banding. As a graph provider it supplies the whole
  graph via server-sorted `cites:`/`cited_by:` queries (true top-cited landmarks,
  no offset ceiling). Its own package; see its own README. Why *both* S2 and
  OpenAlex, what "citation completeness" means, and how they compare (with
  measured numbers) lives in
  [`docs/citation-coverage.md`](../../../docs/citation-coverage.md).
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

One deliberately provider-neutral module sits beside the packages:
**`caps.py`**, home of `UNBOUNDED_LANDMARK_CAP` (500) — the shared **payload
guard** every citation traversal trims to (never fitted, never config; it
exists so a mega seed can't page its entire citer list into one graph
payload). It lives here rather than inside either provider because S2 (live
and corpus) and OpenAlex must agree on the same guard while staying
independent of each other.
