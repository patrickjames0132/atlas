"""External-service clients: every module that talks to a remote API.

* ``semantic_scholar`` — the S2 Academic Graph + Recommendations client (the
  paper-data backbone).
* ``arxiv_client``     — arXiv seed search (find the paper to map).
* ``fulltext``         — full paper text from ar5iv for the Q&A agent.
* ``figures``          — paper figures + captions from ar5iv.
* ``huggingface``      — code & artifact links (GitHub repo, models/datasets/
  Spaces) from Hugging Face Papers.
* ``taxonomy``         — the arXiv category taxonomy (dormant; kept for future
  category-scoped features).

Modules here own their own HTTP plumbing (stdlib ``urllib`` / the ``arxiv``
package), rate-limit etiquette, and caching keys; the ``services`` package
composes them into domain logic.
"""
