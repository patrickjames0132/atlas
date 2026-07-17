"""Fit the adaptive latest-band boundary and write the served artifact.

The training stage: read the labelled corpus (``corpus.csv`` — each seed's
shipped-landmark year distribution), then **fit the tail-edge rule's parameters**
the app applies at serve time — the density threshold ``tau`` (where in the
landmark distribution the cluster's recent edge sits) — and pin the ``max_span``
cost cap. The chosen pair is serialized to a joblib bundle at ``model.joblib``
beside this trainer (in ``src/ml_pipelines/latest_gap/``) plus a human-readable
``model.metadata.json`` sidecar. The app loads that bundle via
``atlas.services.graph.bands.load_model``.

Unlike the ``cite_budget`` sibling, the boundary is **not** a regression on seed
features — a feature regression was tried and fails (negative CV R², see
``research/latest_gap``): the boundary is a property of each seed's landmark
*distribution*, so what we fit is the tail-edge rule's parameter, not
coefficients over age/citations. It is also **not** a quantile: a quantile is
mass-based and a seed's large old bulk drags it years before the cluster's
visible edge, so the rule is the density tail-onset detector
(:func:`atlas.services.graph.bands.tail_edge`), imported from the app so training
and serving share one contract. Run from the repo root:

    uv run python -m ml_pipelines.latest_gap.train              # fit from committed corpus.csv
    uv run python -m ml_pipelines.latest_gap.train --refresh     # re-pull the corpus first
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import logging
from pathlib import Path

import joblib

from atlas.services.graph.bands import RULE_NAME, tail_edge

from . import collect as collect_module

log = logging.getLogger("train")

#: The artifact lives beside its trainer, in this model's own package.
MODEL_DIR = Path(__file__).resolve().parent
MODEL_PATH = MODEL_DIR / "model.joblib"
METADATA_PATH = MODEL_PATH.with_suffix(".metadata.json")  # human-readable sidecar

# The current year and the last landmark-era year, matching the app's traversal
# (``_LATEST_YEARS`` = 2). Bands run from the boundary up to CURRENT_YEAR.
CURRENT_YEAR = datetime.date.today().year
LANDMARK_MAX_YEAR = CURRENT_YEAR - 2

# ``max_span`` is a **cost** choice, not a data optimum: it caps how far back an
# old seed's bands may reach (max bands = max_span + 2, the extra two being the
# latest-only years always banded up to today). 7 keeps the corpus's gap closure
# while bounding worst-case queries at 9 — the balance point Patrick picked.
MAX_SPAN = 7

# The density-threshold grid the fit searches (fraction of a seed's peak-year
# landmark count). ``tau`` barely moves gap closure — the ``max_span`` cap
# dominates — so it is fit on **misdate-robustness** instead: a higher threshold
# needs more same-year citers to shift the boundary, so a couple of OpenAlex
# misdated years (the arc's recurring hazard) can't drag it. The fit takes the
# smallest tau whose boundary survives a two-citer future-misdate perturbation on
# nearly every seed (cheapest bands among the robust thresholds).
TAU_GRID = [0.10, 0.15, 0.20, 0.25, 0.30]

# A tau is "robust" when a two-citer same-year misdate moves the boundary on at
# most this fraction of corpus seeds.
ROBUST_TOLERANCE = 0.05

# The misdate perturbation: two citers stamped this many years past a seed's
# newest landmark (an OpenAlex future-misdate, e.g. the 2025-stamped "Attention"
# record), used to score a threshold's robustness.
MISDATE_OFFSET = 2


def load_corpus(path: Path = collect_module.CORPUS_PATH) -> list[dict]:
    """Read the corpus CSV into rows with parsed year lists.

    Args:
        path: The corpus CSV (defaults to the committed ``corpus.csv``).

    Returns:
        One dict per seed with ``years`` (the landmark-year list) parsed.

    Raises:
        FileNotFoundError: When the corpus hasn't been collected yet.
    """
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["years"] = [int(year) for year in row["citer_years"].split()]
    return rows


def _band_start(years: list[int], tau: float, max_span: int) -> int:
    """The band start the served rule would pick for one seed (edge, then cap)."""
    return max(tail_edge(years, tau), LANDMARK_MAX_YEAR - max_span + 1)


def _visible_gap(years: list[int], band_start: int) -> int:
    """Longest run of empty years between the landmark cluster and the band region.

    A year renders a node when it holds a landmark OR falls in the band range
    ``[band_start, CURRENT_YEAR]``; a "gap" is a maximal run of empty years — the
    dead stretch a user sees on the timeline.

    Args:
        years: The seed's landmark publication years.
        band_start: The first band year under evaluation.

    Returns:
        The longest empty run, in years.
    """
    populated = set(years) | set(range(band_start, CURRENT_YEAR + 1))
    lowest = min(populated)
    longest = current = 0
    for year in range(lowest, CURRENT_YEAR + 1):
        current = 0 if year in populated else current + 1
        longest = max(longest, current)
    return longest


def _score(rows: list[dict], tau: float, max_span: int) -> tuple[int, float]:
    """Total gap-years remaining and mean band-query count for one ``tau``.

    Args:
        rows: Corpus rows from :func:`load_corpus`.
        tau: The candidate density threshold.
        max_span: The span cap.

    Returns:
        ``(gap_years, mean_bands)`` over the corpus.
    """
    gap_years = 0
    total_bands = 0
    for row in rows:
        band_start = _band_start(row["years"], tau, max_span)
        gap_years += _visible_gap(row["years"], band_start)
        total_bands += CURRENT_YEAR - band_start + 1
    return gap_years, total_bands / len(rows)


def _misdate_movement(rows: list[dict], tau: float) -> float:
    """Fraction of seeds whose density edge shifts under a two-citer future misdate.

    Stamps :data:`MISDATE_OFFSET` years past each seed's newest landmark with two
    extra citers (an OpenAlex future-misdate) and checks whether the tail edge
    moves. A robust ``tau`` leaves nearly every seed's boundary unchanged.

    Args:
        rows: Corpus rows from :func:`load_corpus`.
        tau: The candidate density threshold.

    Returns:
        The fraction of corpus seeds whose edge moved.
    """
    moved = 0
    for row in rows:
        years = row["years"]
        outlier = max(years) + MISDATE_OFFSET
        if tail_edge(years, tau) != tail_edge(years + [outlier, outlier], tau):
            moved += 1
    return moved / len(rows)


def fit(rows: list[dict], max_span: int = MAX_SPAN) -> dict:
    """Fit ``tau`` on the corpus and assemble the bundle.

    ``tau`` is the **smallest threshold robust to misdating** — the cheapest (in
    band queries) density threshold whose boundary survives a two-citer future
    misdate on at least ``1 - ROBUST_TOLERANCE`` of the corpus. Gap closure is
    flat across ``tau`` (the ``max_span`` cap dominates), so robustness is the
    fit criterion, not gap-years. ``max_span`` is the fixed cost cap, not fit.

    Args:
        rows: Corpus rows from :func:`load_corpus`.
        max_span: The span cap to bake into the artifact.

    Returns:
        The serializable bundle — the fitted ``tau`` and chosen ``max_span`` plus
        the rule contract and training metadata — ready for :func:`save`.
    """
    robust = [tau for tau in TAU_GRID if _misdate_movement(rows, tau) <= ROBUST_TOLERANCE]
    best_tau = min(robust) if robust else max(TAU_GRID)  # cheapest robust, else the safest
    gap_years, mean_bands = _score(rows, best_tau, max_span)
    return {
        "rule": RULE_NAME,
        "tau": best_tau,
        "max_span": max_span,
        "gap_years_remaining": gap_years,
        "misdate_movement": round(_misdate_movement(rows, best_tau), 3),
        "mean_bands": round(mean_bands, 2),
        "max_bands": max_span + 2,  # + the two latest-only years banded up to today
        "n_seeds": len(rows),
        "trained_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }


def save(bundle: dict) -> None:
    """Serialize the bundle to ``model.joblib`` and write ``model.metadata.json``.

    The joblib file is what the app loads; the JSON is a human-readable sidecar
    (the fitted params + provenance) that never gets loaded — it's for eyeballing
    and for the git diff to show when a retrain moved the numbers.

    Args:
        bundle: The training bundle from :func:`fit`.
    """
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_PATH)
    with METADATA_PATH.open("w") as handle:
        json.dump(bundle, handle, indent=2)
        handle.write("\n")
    log.info("Saved model -> %s", MODEL_PATH)
    log.info("  tau=%.2f max_span=%d  misdate_movement=%.3f mean_bands=%.2f  n_seeds=%d",
             bundle["tau"], bundle["max_span"], bundle["misdate_movement"],
             bundle["mean_bands"], bundle["n_seeds"])


def main() -> None:
    """CLI: fit from the committed corpus, or ``--refresh`` to re-pull it first."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Train the adaptive latest-band model.")
    parser.add_argument("--refresh", action="store_true",
                        help="Re-pull the OpenAlex corpus before fitting (writes corpus.csv).")
    args = parser.parse_args()

    if args.refresh:
        log.info("Refreshing corpus from OpenAlex…")
        collect_module.write_corpus(collect_module.collect())
    save(fit(load_corpus()))


if __name__ == "__main__":
    main()
