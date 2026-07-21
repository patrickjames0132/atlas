"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The per-request build shape — how much of a seed's neighborhood to ship.

Every other knob in the app is a ``config.json`` setting, read once and shared
by every request. This one deliberately isn't: it belongs to **the user**, not
to the deployment, and it changes between one build and the next as they explore
(the v6.0.0 purge deleted the old file toggles for exactly this reason — they
were deployment settings pretending to be user ones). So the shape arrives as
request parameters, is carried by the browser, and never touches the file.

The headline field is :attr:`BuildShape.adaptive`:

* **ON** (the default, and every build before this module existed) — the app
  sizes itself. The STOP/SKIP rules in ``budget`` measure the landmark band from
  the pool's own year distribution, and the fitted tau rule in ``bands`` places
  the Latest cluster's start per seed. The band-shape fields below are ignored.
* **OFF** — the user sizes it. The build ships **all** landmark citers, with the
  ``UNBOUNDED_LANDMARK_CAP`` payload guard as the only ceiling, and the Latest
  bands take their shape from :attr:`cluster_start`, :attr:`number_of_bands`,
  and :attr:`nodes_per_band` instead of from the tau rule. Trimming what's
  *displayed* then moves to the frontend's per-chip count sliders.

**The two modes reuse the traversals' existing degradation paths rather than
adding branches to them.** All three citation traversals (live S2, the S2
corpus, OpenAlex) already take the budget and band-start rules as *injected
callables*, and already fall back to the flat payload guard when a rule declines
by returning None. Non-adaptive mode is therefore just a different pair of
rules: a budget rule that always declines, and a band-start rule that always
answers the user's fixed year. No traversal needed an ``if adaptive`` branch —
:meth:`BuildShape.landmark_budget` and :meth:`BuildShape.band_start` hand each
one the rules that produce the behavior.

**The cache key.** Graph snapshots are cached under ``(provider, seed)``, which
knows nothing about shape — so a non-adaptive build would otherwise be served
the adaptive snapshot it was meant to replace. :meth:`BuildShape.cache_suffix`
closes that: it is **empty for an adaptive build**, so the default path keeps
today's exact key and every already-cached snapshot stays valid, and it is a
stable signature of the four fields otherwise, so each distinct non-adaptive
shape caches beside the adaptive one instead of clobbering it.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from ...integrations.caps import LATEST_NODES_PER_BAND, LATEST_NUMBER_OF_BANDS
from . import bands, budget

#: The landmark-band rule the traversals inject — given the ranked citers'
#: years, how many to ship (None = no opinion, take the payload guard). Same
#: contract as ``semantic_scholar.traversal.LandmarkBudgetFn``, restated here so
#: this module needn't import a provider just to name a type.
LandmarkBudgetFn = Callable[[Sequence[int | None]], int | None]

#: The Latest band-start rule the traversals inject — given the shipped
#: landmarks' years and the landmark cutoff, the first year to band (None = keep
#: the fixed span). Same contract as the providers' ``BandStartFn``.
BandStartFn = Callable[[list[int], int], int | None]

#: The truncated-pool landmark rule — given the ranked citers' years, which
#: indices to keep (None = no opinion). Same contract as the live S2
#: traversal's ``LandmarkSelectFn``.
LandmarkSelectFn = Callable[[Sequence[int | None]], list[int] | None]


def _decline_budget(citer_years: Sequence[int | None]) -> int | None:
    """The non-adaptive landmark rule: never compute a count.

    Returning None is the traversals' established "no opinion" answer, and every
    one of them responds by shipping the ranked pool trimmed to the
    ``UNBOUNDED_LANDMARK_CAP`` payload guard — which *is* non-adaptive mode's
    "ship all nodes, the guard as the only ceiling". The years are accepted and
    ignored so this matches the injected rule's signature exactly.

    Args:
        citer_years: The ranked citers' publication years — unused.

    Returns:
        None, always.
    """
    return None


@dataclass(frozen=True)
class BuildShape:
    """How one graph build should size its relations.

    Frozen because a build must not be able to edit the shape it was handed —
    the same instance is read by the traversal, the cache key, and the log line.

    Attributes:
        adaptive: When True (the default), the app sizes the landmark band and
            places the Latest cluster start itself, and the three fields below
            are ignored. When False, the build ships all landmarks up to the
            payload guard and takes its band shape from those fields.
        cluster_start: The first year the Latest bands cover, when non-adaptive.
            None keeps the fixed ``number_of_bands`` span below the landmark
            cutoff — the same fallback an unplaceable tau rule takes.
        number_of_bands: How many one-year Latest bands to cover below the
            landmark cutoff, when ``cluster_start`` doesn't name a start.
        nodes_per_band: The top-N most-cited citers each one-year band keeps.
    """

    adaptive: bool = True
    cluster_start: int | None = None
    number_of_bands: int = LATEST_NUMBER_OF_BANDS
    nodes_per_band: int = LATEST_NODES_PER_BAND

    def landmark_budget(self) -> LandmarkBudgetFn:
        """The landmark-band rule to inject into a traversal.

        Returns:
            The STOP rule (``budget.computed_cite_limit``) when adaptive, so the
            band's length is computed from the pool's years; the always-decline
            rule otherwise, which lands the traversal on its flat payload-guard
            fallback.
        """
        return budget.computed_cite_limit if self.adaptive else _decline_budget

    def landmark_select(self) -> LandmarkSelectFn | None:
        """The truncated-pool landmark rule to inject into the live S2 traversal.

        The live fallback bands a *truncated* pool with the SKIP selector rather
        than prefixing it. Non-adaptive mode wants no rule at all — the
        traversal's own "no selector" path ships the ranked prefix trimmed to the
        payload guard, which is the same all-nodes answer the other two pools
        reach by declining a budget.

        Returns:
            The SKIP selector (``budget.select_landmarks``) when adaptive, else
            None.
        """
        return budget.select_landmarks if self.adaptive else None

    def band_start(self) -> BandStartFn | None:
        """The Latest band-start rule to inject into a traversal.

        Returns:
            The fitted tau rule (``bands.earliest_band_year``) when adaptive.
            When not, a rule answering :attr:`cluster_start` for every seed — or
            None when the user named no start, which leaves the traversal on its
            fixed ``number_of_bands`` span.
        """
        if self.adaptive:
            return bands.earliest_band_year
        if self.cluster_start is None:
            return None
        fixed_start = self.cluster_start

        def fixed_band_start(landmark_years: list[int], landmark_max_year: int) -> int | None:
            """Answer the user's chosen cluster start, whatever the seed looks like.

            Args:
                landmark_years: The shipped landmarks' years — unused.
                landmark_max_year: The last landmark-era year — unused.

            Returns:
                The user's fixed start year.
            """
            return fixed_start

        return fixed_band_start

    def cache_suffix(self) -> str:
        """The part of the graph cache key that distinguishes this shape.

        Empty for an adaptive build — the default path keeps the pre-shape key
        exactly, so snapshots cached before this module existed still hit. A
        non-adaptive build gets a stable signature of its fields, so each shape
        caches alongside the adaptive snapshot rather than overwriting it.

        Returns:
            "" when adaptive, else a ``":shape:…"`` fragment.
        """
        if self.adaptive:
            return ""
        start = "auto" if self.cluster_start is None else str(self.cluster_start)
        return f":shape:{start}-{self.number_of_bands}-{self.nodes_per_band}"
