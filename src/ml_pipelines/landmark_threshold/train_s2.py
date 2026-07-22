"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Fit the S2 landmark-threshold curve and write the served artifact.

The fit stage of the landmark-threshold pipeline's **S2 curve**. Reads the
committed ``corpus_s2.csv.gz`` (sampled seeds + their citer citation-count
distributions) and fits the three constants of the predicate::

    is_landmark(citer) = citer.cited_by >= max(FLOOR, T(now - citer.year) * S(seed))

with

    T(age)  = a * (age + 1) ** p          # the age curve, monotone in age
    S(seed) = (seed.cited_by / MEDIAN) ** beta   # the seed scale, S(median) = 1

Four parameters — ``a, p, beta, FLOOR`` — fit jointly so each seed's **landmark
count** lands in the 20–40 target band (``docs/citation-threshold.md``). The
objective is a per-seed band penalty, not a regression: it is zero inside the band
and grows outside, so the fit optimizes the *composition* of the split rather than
any single label. It is minimized by a vectorized coarse-to-fine search (a coarse
grid then coordinate descent) rather than a gradient method, because a count-based
band penalty is non-smooth and the parameter space is only four-dimensional — no
scipy needed.

**Report, don't just fit.** A single-parameter ``S()`` holding *every* seed inside a
2× band across three orders of magnitude of seed size is the design's stated
fitting risk, so this prints the **achieved landmark-count distribution** (the
fraction in band, the spread by seed-size decade, and the four worked examples),
not only the parameters. If the band proves infeasible, that shows up here, at fit
time.

Run from the repo root:

    uv run python -m ml_pipelines.landmark_threshold.train_s2              # fit from committed corpus
    uv run python -m ml_pipelines.landmark_threshold.train_s2 --refresh     # re-collect the corpus first

Writes ``model_s2.joblib`` (the bundle the app's predicate loads) and a
human-readable ``model_s2.metadata.json`` sidecar beside this trainer.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np

from . import collect_s2

log = logging.getLogger("train")

#: The artifact lives beside its trainer, in this model's own package.
MODEL_DIR = Path(__file__).resolve().parent
MODEL_PATH = MODEL_DIR / "model_s2.joblib"
METADATA_PATH = MODEL_DIR / "model_s2.metadata.json"

#: The target landmark-count band (Patrick, 2026-07-20). A composition target, not
#: a volume one — the sliders govern how much is *drawn*; this governs the *split*.
TARGET_LOW = 20
TARGET_HIGH = 40

#: Citer ages are clipped into ``[0, AGE_MAX]``: the curve keeps rising with age,
#: but a citer more than three decades old has had long enough to accrue citations
#: that the bar needn't climb further, and clipping keeps a handful of ancient
#: citers from dominating ``p``.
AGE_MAX = 30

#: The floor can't drop below the collector's prune floor, or landmark counts read
#: off the (pruned) committed corpus would understate the truth. Constraining it
#: here makes the pruning exactly lossless. See ``collect_s2.PRUNE_FLOOR``.
FLOOR_MIN = collect_s2.PRUNE_FLOOR


@dataclass(frozen=True)
class Seed:
    """One sampled seed with its landmark-eligible citer distribution.

    Attributes:
        corpus_id: The seed's S2 ``corpusid``.
        label: A human label (for the worked examples).
        is_worked_example: Whether this is a carried worked example.
        year: The seed's publication year.
        cited_by: The seed's own citation count (drives ``S()``).
        total_citers: All the seed's citers (the un-pruned denominator).
        citer_ages: Each landmark-eligible citer bin's clipped age.
        citer_cited_by: Each bin's citer citation count.
        citer_counts: How many citers fall in each bin.
    """

    corpus_id: int
    label: str
    is_worked_example: bool
    year: int
    cited_by: int
    total_citers: int
    citer_ages: np.ndarray
    citer_cited_by: np.ndarray
    citer_counts: np.ndarray

    @property
    def max_possible_landmarks(self) -> int:
        """The most landmarks this seed could yield — all its eligible citers.

        A seed with fewer eligible citers than the target's lower edge can never
        reach the band; the fit must not be penalized for that scarcity (see
        :func:`band_penalty`).

        Returns:
            The seed's total landmark-eligible citer count.
        """
        return int(self.citer_counts.sum())


def load_seeds(path: Path = collect_s2.CORPUS_PATH, *, as_of_year: int) -> list[Seed]:
    """Read ``corpus_s2.csv.gz`` and group its citer rows into per-seed records.

    Args:
        path: The committed corpus CSV (long format, one row per citer bin;
            gzipped when it ends ``.gz``).
        as_of_year: The reference year ages are measured from (the corpus release
            year at fit time).

    Returns:
        One :class:`Seed` per distinct ``corpus_id`` in the file.

    Raises:
        FileNotFoundError: When the corpus hasn't been collected yet.
    """
    grouped: dict[int, dict] = {}
    with collect_s2.open_corpus(path, "r") as handle:
        for row in csv.DictReader(handle):
            corpus_id = int(row["corpus_id"])
            record = grouped.setdefault(corpus_id, {
                "label": row["label"],
                "is_worked_example": row["is_worked_example"] == "1",
                "year": int(row["seed_year"]),
                "cited_by": int(row["seed_cited_by"]),
                "total_citers": int(row["total_citers"]),
                "ages": [], "cited": [], "counts": [],
            })
            age = min(max(as_of_year - int(row["citer_year"]), 0), AGE_MAX)
            record["ages"].append(age)
            record["cited"].append(int(row["citer_cited_by"]))
            record["counts"].append(int(row["n"]))
    seeds = []
    for corpus_id, record in grouped.items():
        seeds.append(Seed(
            corpus_id=corpus_id,
            label=record["label"],
            is_worked_example=record["is_worked_example"],
            year=record["year"],
            cited_by=record["cited_by"],
            total_citers=record["total_citers"],
            citer_ages=np.array(record["ages"], dtype=np.float64),
            citer_cited_by=np.array(record["cited"], dtype=np.float64),
            citer_counts=np.array(record["counts"], dtype=np.float64),
        ))
    return seeds


@dataclass(frozen=True)
class FitInputs:
    """The corpus flattened into flat arrays for a vectorized objective.

    Every landmark-eligible citer bin across all seeds becomes one entry, tagged
    with its seed's index, so a candidate rule's per-seed landmark counts are one
    masked ``bincount`` over the whole corpus — no Python loop over seeds.

    Attributes:
        ages: Each bin's clipped citer age.
        cited_by: Each bin's citer citation count.
        counts: How many citers each bin holds.
        seed_index: Which seed (row in the per-seed arrays) each bin belongs to.
        seed_ratio: Per seed, ``seed.cited_by / MEDIAN`` — the base of ``S()``.
        max_possible: Per seed, its most-possible landmark count.
        median_seed: The pinning constant ``MEDIAN`` (``S(median) = 1``).
    """

    ages: np.ndarray
    cited_by: np.ndarray
    counts: np.ndarray
    seed_index: np.ndarray
    seed_ratio: np.ndarray
    max_possible: np.ndarray
    median_seed: float

    @property
    def n_seeds(self) -> int:
        """How many seeds the fit spans."""
        return int(self.seed_ratio.shape[0])


def build_inputs(seeds: list[Seed]) -> FitInputs:
    """Flatten seeds into the vectorized-objective arrays, pinning ``S(median) = 1``.

    Args:
        seeds: The per-seed records from :func:`load_seeds`.

    Returns:
        The flattened :class:`FitInputs`.
    """
    median_seed = float(np.median([seed.cited_by for seed in seeds]))
    seed_ratio = np.array([seed.cited_by / median_seed for seed in seeds])
    max_possible = np.array([seed.max_possible_landmarks for seed in seeds], dtype=np.float64)
    ages, cited_by, counts, seed_index = [], [], [], []
    for index, seed in enumerate(seeds):
        ages.append(seed.citer_ages)
        cited_by.append(seed.citer_cited_by)
        counts.append(seed.citer_counts)
        seed_index.append(np.full(seed.citer_ages.shape, index, dtype=np.int64))
    return FitInputs(
        ages=np.concatenate(ages),
        cited_by=np.concatenate(cited_by),
        counts=np.concatenate(counts),
        seed_index=np.concatenate(seed_index),
        seed_ratio=seed_ratio,
        max_possible=max_possible,
        median_seed=median_seed,
    )


def landmark_counts(inputs: FitInputs, scale: float, exponent: float,
                    beta: float, floor: float) -> np.ndarray:
    """Per-seed landmark counts under one candidate ``(a, p, beta, FLOOR)``.

    The vectorized predicate: each citer bin clears the bar when its citation
    count meets ``max(FLOOR, a·(age+1)^p · ratio^beta)``; its ``count`` then adds
    to its seed's tally.

    Args:
        inputs: The flattened corpus (see :func:`build_inputs`).
        scale: ``a`` — the age curve's value at age 0.
        exponent: ``p`` — the age curve's growth exponent.
        beta: The seed-scale exponent.
        floor: The absolute floor ``FLOOR``.

    Returns:
        A length-``n_seeds`` array of landmark counts, seed order preserved.
    """
    seed_scale = inputs.seed_ratio[inputs.seed_index] ** beta
    bar = np.maximum(floor, scale * (inputs.ages + 1.0) ** exponent * seed_scale)
    admitted = inputs.cited_by >= bar
    weighted = inputs.counts * admitted
    return np.bincount(inputs.seed_index, weights=weighted, minlength=inputs.n_seeds)


def band_penalty(counts: np.ndarray, max_possible: np.ndarray) -> float:
    """The fit objective: how far the seeds' landmark counts sit outside 20–40.

    Zero for a seed inside the band. Above the band always costs (a flood of
    landmarks is the rule's fault); below the band costs **only when the seed even
    has** :data:`TARGET_LOW` eligible citers — a niche seed with 12 citers total
    can't be blamed for shipping 12. Distances are measured in log space so a
    blockbuster's overflow doesn't swamp everything else.

    Args:
        counts: Per-seed landmark counts.
        max_possible: Per-seed most-possible landmark counts.

    Returns:
        The summed penalty (lower is better).
    """
    # Clamp to >=1 inside the log (only a count of 0 is affected, and only its
    # shortfall term), so the band edges are exact: a count of 40 costs nothing.
    log_counts = np.log(np.maximum(counts, 1.0))
    over = np.maximum(log_counts - np.log(TARGET_HIGH), 0.0)
    under_gap = np.maximum(np.log(TARGET_LOW) - log_counts, 0.0)
    can_reach = max_possible >= TARGET_LOW
    under = under_gap * can_reach
    return float(np.sum(over ** 2 + under ** 2))


#: The coarse search grid per parameter — spans plausible ranges for each of the
#: four constants. Kept modest (≈17k combinations) because coordinate descent
#: refines from the best grid point afterwards, so the grid only has to land in
#: the right basin, not pinpoint the optimum.
_SCALE_GRID = np.geomspace(1.0, 60.0, 12)
_EXPONENT_GRID = np.linspace(0.0, 3.0, 12)
_BETA_GRID = np.linspace(0.0, 1.2, 12)
_FLOOR_GRID = np.geomspace(FLOOR_MIN, 60.0, 10)


def _coarse_search(inputs: FitInputs) -> tuple[float, float, float, float]:
    """Grid-search the four parameters for the lowest band penalty.

    Loop-ordered so each expensive term is computed as far out as it can be. The
    predicate ``cited_by >= max(FLOOR, a·(age+1)^p · ratio^beta)`` splits exactly
    into two independent comparisons — ``cited_by >= FLOOR`` and
    ``cited_by >= a·(age+1)^p·ratio^beta`` — so the floor masks are built once for
    the whole search, the two ``pow`` calls (the costly part, over ~1.5M bins) are
    hoisted to the ``p`` and ``beta`` loops, and only a compare-and-``bincount``
    runs innermost. Same grid, same answer, ~6× less work.

    Args:
        inputs: The flattened corpus.

    Returns:
        The best ``(a, p, beta, FLOOR)`` on the coarse grid.
    """
    best_params = (float(_SCALE_GRID[0]), 1.0, 0.5, float(FLOOR_MIN))
    best_loss = np.inf
    # Independent of every fitted parameter but the floor itself.
    floor_masks = [(float(floor), inputs.cited_by >= floor) for floor in _FLOOR_GRID]

    for exponent in _EXPONENT_GRID:
        age_term = (inputs.ages + 1.0) ** exponent
        for beta in _BETA_GRID:
            base = age_term * (inputs.seed_ratio ** beta)[inputs.seed_index]
            for scale in _SCALE_GRID:
                above_curve = inputs.cited_by >= scale * base
                for floor, floor_mask in floor_masks:
                    weighted = inputs.counts * (above_curve & floor_mask)
                    counts = np.bincount(inputs.seed_index, weights=weighted,
                                         minlength=inputs.n_seeds)
                    loss = band_penalty(counts, inputs.max_possible)
                    if loss < best_loss:
                        best_loss = loss
                        best_params = (float(scale), float(exponent), float(beta), floor)
    return best_params


def _refine(inputs: FitInputs, params: tuple[float, float, float, float],
            *, rounds: int = 6) -> tuple[float, float, float, float]:
    """Coordinate-descent refinement around a coarse solution.

    Each round shrinks a per-parameter step and line-searches one parameter at a
    time; a non-smooth count objective makes this steadier than a gradient step.

    Args:
        inputs: The flattened corpus.
        params: The coarse ``(a, p, beta, FLOOR)`` to refine.
        rounds: How many shrink-and-sweep rounds to run.

    Returns:
        The refined ``(a, p, beta, FLOOR)``.
    """
    scale, exponent, beta, floor = params
    current = [scale, exponent, beta, floor]
    steps = [scale * 0.5, 0.5, 0.2, floor * 0.5]
    lower = [1e-3, 0.0, 0.0, float(FLOOR_MIN)]

    def loss_at(values: list[float]) -> float:
        return band_penalty(landmark_counts(inputs, *values), inputs.max_possible)

    best_loss = loss_at(current)
    for _round in range(rounds):
        for axis in range(4):
            for direction in (-1.0, 1.0):
                trial = list(current)
                trial[axis] = max(lower[axis], current[axis] + direction * steps[axis])
                trial_loss = loss_at(trial)
                if trial_loss < best_loss:
                    best_loss = trial_loss
                    current = trial
        steps = [step * 0.5 for step in steps]
    return (current[0], current[1], current[2], current[3])


def fit(inputs: FitInputs) -> tuple[float, float, float, float]:
    """Fit ``(a, p, beta, FLOOR)`` by coarse grid then coordinate descent.

    Args:
        inputs: The flattened corpus.

    Returns:
        The fitted ``(a, p, beta, FLOOR)``.
    """
    coarse = _coarse_search(inputs)
    return _refine(inputs, coarse)


def achieved_spread(inputs: FitInputs, seeds: list[Seed],
                    params: tuple[float, float, float, float]) -> dict:
    """Summarize the fitted rule's landmark-count distribution — the deliverable.

    Args:
        inputs: The flattened corpus.
        seeds: The per-seed records (for worked-example labels and seed sizes).
        params: The fitted ``(a, p, beta, FLOOR)``.

    Returns:
        A JSON-serializable report: the in-band fraction, the count distribution,
        the spread by seed-size decade, and the worked-example counts.
    """
    counts = landmark_counts(inputs, *params)
    reachable = inputs.max_possible >= TARGET_LOW
    in_band = (counts >= TARGET_LOW) & (counts <= TARGET_HIGH)
    # For seeds that can't reach the band, "in band or capped at their ceiling"
    # is the fair success test.
    fair_success = in_band | (~reachable & (counts <= TARGET_HIGH))

    decades = np.floor(np.log10(np.maximum(inputs.seed_ratio * inputs.median_seed, 1.0)))
    by_decade = {}
    for decade in np.unique(decades):
        mask = decades == decade
        low = int(10 ** decade)
        by_decade[f"cites~1e{int(decade)}"] = {
            "n_seeds": int(mask.sum()),
            "median_landmarks": float(np.median(counts[mask])),
            "in_band_frac": round(float(in_band[mask].mean()), 3),
            "example_low_cites": low,
        }

    worked = {}
    for index, seed in enumerate(seeds):
        if seed.is_worked_example:
            worked[seed.label] = {
                "seed_year": seed.year,
                "seed_cited_by": seed.cited_by,
                "landmarks": int(round(float(counts[index]))),
                "max_possible": seed.max_possible_landmarks,
            }

    return {
        "n_seeds": inputs.n_seeds,
        "target_band": [TARGET_LOW, TARGET_HIGH],
        "in_band_frac": round(float(in_band.mean()), 3),
        "fair_success_frac": round(float(fair_success.mean()), 3),
        "reachable_frac": round(float(reachable.mean()), 3),
        "count_percentiles": {
            str(percentile): round(float(np.percentile(counts, percentile)), 1)
            for percentile in (5, 25, 50, 75, 95)
        },
        "by_seed_size": by_decade,
        "worked_examples": worked,
    }


def build_bundle(inputs: FitInputs, params: tuple[float, float, float, float],
                 seeds: list[Seed], *, as_of_year: int) -> dict:
    """Assemble the serializable artifact bundle from a fitted solution.

    Args:
        inputs: The flattened corpus.
        params: The fitted ``(a, p, beta, FLOOR)``.
        seeds: The per-seed records (for the spread report).
        as_of_year: The reference year ages were measured from.

    Returns:
        The bundle dict — the predicate's constants plus provenance and the
        achieved-spread report — ready for :func:`save`.
    """
    scale, exponent, beta, floor = params
    return {
        "provider": "s2",
        "form": "cited_by >= max(floor, a*(age+1)^p * (seed_cited_by/median_seed)^beta)",
        "a": round(scale, 4),
        "p": round(exponent, 4),
        "beta": round(beta, 4),
        "floor": round(max(floor, float(FLOOR_MIN)), 4),
        "median_seed": round(inputs.median_seed, 2),
        "age_max": AGE_MAX,
        "as_of_year": as_of_year,
        "target_band": [TARGET_LOW, TARGET_HIGH],
        "n_seeds": inputs.n_seeds,
        "achieved_spread": achieved_spread(inputs, seeds, params),
        "trained_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "numpy_version": np.__version__,
    }


def save(bundle: dict) -> None:
    """Serialize the bundle to ``model_s2.joblib`` and write the JSON sidecar.

    The joblib file is what the app's predicate will load; the JSON is a
    human-readable sidecar (never loaded) for eyeballing and for the git diff to
    show what a re-fit moved.

    Args:
        bundle: The bundle from :func:`build_bundle`.
    """
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_PATH)
    with METADATA_PATH.open("w") as handle:
        json.dump(bundle, handle, indent=2)
        handle.write("\n")
    log.info("Saved S2 threshold curve -> %s", MODEL_PATH)
    spread = bundle["achieved_spread"]
    log.info("  a=%.4g  p=%.4g  beta=%.4g  floor=%.4g  median_seed=%.1f",
             bundle["a"], bundle["p"], bundle["beta"], bundle["floor"], bundle["median_seed"])
    log.info("  n_seeds=%d  in-band %.1f%%  fair-success %.1f%%  (%d–%d target)",
             bundle["n_seeds"], 100 * spread["in_band_frac"],
             100 * spread["fair_success_frac"], TARGET_LOW, TARGET_HIGH)
    log.info("  landmark-count percentiles %s", spread["count_percentiles"])
    for label, stats in spread["worked_examples"].items():
        log.info("  %-26s %d landmarks (of %d possible, seed %d cites)",
                 label, stats["landmarks"], stats["max_possible"], stats["seed_cited_by"])


def main() -> None:
    """CLI: fit from the committed corpus, or ``--refresh`` to re-collect first."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Fit the S2 landmark-threshold curve.")
    parser.add_argument("--refresh", action="store_true",
                        help="Re-collect the corpus from the local S2 corpus before fitting.")
    parser.add_argument("--as-of-year", type=int, default=datetime.date.today().year,
                        help="Reference year ages are measured from (defaults to this year; "
                             "collection and fit run the same year, so the default is right).")
    args = parser.parse_args()

    if args.refresh:
        log.info("Refreshing corpus from the local S2 corpus…")
        collect_s2.write_corpus(collect_s2.collect())

    seeds = load_seeds(as_of_year=args.as_of_year)
    log.info("Loaded %d seeds from %s", len(seeds), collect_s2.CORPUS_PATH.name)
    inputs = build_inputs(seeds)
    params = fit(inputs)
    save(build_bundle(inputs, params, seeds, as_of_year=args.as_of_year))


if __name__ == "__main__":
    main()
