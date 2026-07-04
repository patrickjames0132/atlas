"""The bring-your-own-sources subsystem (Phase 3d): the user's persistent,
semantically-searchable library of their own material.

* ``sources``    — ingestion (PDF / URL → chunks → vectors in sqlite-vec) and
  semantic search over the library.
* ``embeddings`` — the local sentence-transformers model behind it (lazy,
  degrades gracefully when unavailable).
"""
