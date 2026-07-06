"""External-service clients: every module that talks to a remote API.

* ``semantic_scholar`` — the S2 Academic Graph + Recommendations client (the
  paper-data backbone). Also holds S2's fields-of-study vocabulary (``vocab``).
* ``arxiv``            — arXiv-derived content: arXiv-id detection (``ID_RE``),
  a paper's figures + full body text from ar5iv (arXiv's LaTeX→HTML renderer),
  and the arXiv category taxonomy (``vocab`` + bundled ``taxonomy.json``).
  (Was ``ar5iv``; renamed as the single home for arXiv code.)
* ``huggingface``      — code & artifact links (GitHub repo, models/datasets/
  Spaces) from Hugging Face Papers.

Clients here own their own transport (stdlib ``urllib`` or ``huggingface_hub``),
rate-limit etiquette, and caching keys; the ``services`` package composes them
into domain logic. Each provider also owns its own controlled *vocabulary*
(``arxiv.vocab`` = category codes, ``semantic_scholar.vocab`` = fields of study)
— static/inline data, no remote call — rather than a shared taxonomy package.
"""
