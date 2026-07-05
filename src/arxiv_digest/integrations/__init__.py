"""External-service clients: every module that talks to a remote API.

* ``semantic_scholar`` — the S2 Academic Graph + Recommendations client (the
  paper-data backbone).
* ``arxiv``            — arXiv-derived content: arXiv-id detection (``ID_RE``)
  plus a paper's figures + full body text from ar5iv (arXiv's LaTeX→HTML
  renderer). (Was ``ar5iv``; renamed as the single home for arXiv code.)
* ``huggingface``      — code & artifact links (GitHub repo, models/datasets/
  Spaces) from Hugging Face Papers.
* ``taxonomy``         — the app's controlled subject vocabularies:
  ``taxonomy.arxiv`` (arXiv category codes) and ``taxonomy.s2`` (S2 fields of
  study). Static/inline data, no network.

Clients here own their own transport (stdlib ``urllib``, the ``arxiv`` package,
or ``huggingface_hub``), rate-limit etiquette, and caching keys; the
``services`` package composes them into domain logic. (``taxonomy`` is the odd
one out — static bundled data, no remote call.)
"""
