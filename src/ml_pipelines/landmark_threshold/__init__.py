"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The landmark-threshold pipeline: fit the citation predicate that splits Landmarks from Latest.

Fits the three offline constants behind the one-line rule that replaces the whole
STOP/SKIP/prefix/band machinery (see ``docs/citation-threshold.md``)::

    is_landmark(citer) = citer.cited_by >= max(FLOOR, T[now - citer.year] * S(seed.cited_by))

A predicate reads *one* citer, never the pool, so it is order- and
pool-independent — which is the entire justification for the rip-out. ``T[]`` (the
age curve), ``S()`` (the seed scale), and ``FLOOR`` are fitted here and shipped as
an artifact the app loads; the predicate itself runs online.

**Two curves, calibrated per provider** — S2 and OpenAlex report different citation
counts for the same paper, so a curve fit on one miscalibrates the other. The S2
curve (``collect_s2`` / ``train_s2``) is fit from the offline corpus — thousands of
seeds, local, free; the OpenAlex curve joins later from a throttled live run. Each
pins ``S(median seed) = 1`` on its own scale.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""
