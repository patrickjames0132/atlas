"""The shared payload ceiling every citation traversal trims to.

``UNBOUNDED_LANDMARK_CAP`` is a **payload guard**, and is named as one on
purpose: unlike ``budget.PER_YEAR_CAP`` it was never fitted to data, and it
is deliberately not a config knob (the per-relation count caps were deleted
as knobs nobody turned — the app sizes its relations itself). It is the hard
upper bound on how many citers one relation ships in a single graph payload,
so a mega seed ("Attention Is All You Need" has ~150k citers; Hawking's 1974
letter ~5.7k) can't page its entire citer list into one response. The sizing
rules in ``services/graph/budget.py`` treat it as their ceiling, and every
traversal's flat fallback (no sizing rule injected, or a rule that declines)
trims to it. It lives here — beside, not inside, the provider packages —
because Semantic Scholar (live and corpus) and OpenAlex must agree on the
same guard while staying independent of each other.
"""

UNBOUNDED_LANDMARK_CAP = 500
