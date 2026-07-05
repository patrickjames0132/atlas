"""External-service clients: every module that talks to a remote API.

* ``semantic_scholar`` — the S2 Academic Graph + Recommendations client (the
  paper-data backbone).
* ``arxiv_client``     — arXiv seed search (find the paper to map).
* ``ar5iv``            — a paper's figures + full body text from ar5iv
  (arXiv's LaTeX→HTML renderer).
* ``huggingface``      — code & artifact links (GitHub repo, models/datasets/
  Spaces) from Hugging Face Papers.
* ``taxonomy``         — the arXiv category taxonomy (arXiv-specific paper
  enrichment; bundled JSON, no network).

Clients here own their own transport (stdlib ``urllib``, the ``arxiv`` package,
or ``huggingface_hub``), rate-limit etiquette, and caching keys; the
``services`` package composes them into domain logic. (``taxonomy`` is the odd
one out — static bundled data, no remote call.)
"""
