"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The cross-provider sizing constants every citation traversal shares.

None of these is a config knob, on purpose (the per-relation count caps and
band-shape fields were deleted as knobs nobody turned — the app sizes its
relations itself), and none is fitted like ``budget.PER_YEAR_CAP`` — they
are **named guards and defaults**. They live here — beside, not inside, the
provider packages — because Semantic Scholar (live and corpus) and OpenAlex
must agree on them while staying independent of each other.

* ``UNBOUNDED_LANDMARK_CAP`` — the **payload guard**: the hard upper bound
  on how many citers one relation ships in a single graph payload, so a mega
  seed ("Attention Is All You Need" has ~150k citers; Hawking's 1974 letter
  ~5.7k) can't page its entire citer list into one response. The sizing
  rules in ``services/graph/budget.py`` treat it as their ceiling, and every
  traversal's flat fallback (no sizing rule injected, or a rule that
  declines) trims to it.
* ``LATEST_NUMBER_OF_BANDS`` — the Latest bands' **fallback span**: how many
  one-year bands below the landmark cutoff the relation covers when the
  fitted tau rule (``services/graph/bands.py``) can't place a per-seed start
  (model unloadable, or too few dated landmarks).
* ``LATEST_NODES_PER_BAND`` — the top-N most-cited citers each one-year
  Latest band keeps (≤200, OpenAlex's page cap) — the Latest analog of the
  landmarks' fitted ``PER_YEAR_CAP``, except this one was eyeballed, not
  fitted. Per-year banding gives even coverage; a single recency query
  sorted by citations would let its oldest year dominate.

Since v6.2.0 the last two are **defaults, not fixed values**: the settings
modal's non-adaptive mode hands this pair to the user, who sends them per
request (see ``services/graph/shape.py``). Each traversal resolves them at
*call time* rather than in a signature default, so these constants stay the
live source of truth for every build that doesn't override them.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

UNBOUNDED_LANDMARK_CAP = 500

LATEST_NUMBER_OF_BANDS = 5

LATEST_NODES_PER_BAND = 50
