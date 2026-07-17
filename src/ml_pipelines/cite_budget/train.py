"""Fit the adaptive landmark-budget model and write the served artifact.

The training stage: read the labelled corpus (``corpus.csv``), build the feature
matrix through the app's own :func:`atlas.services.graph.budget.compute_features`
(so training and serving share one feature contract), fit a scikit-learn
``LinearRegression``, score it with 5-fold cross-validation, and serialize a
joblib bundle to ``model.joblib`` beside this trainer (in
``src/ml_pipelines/cite_budget/``) plus a human-readable ``model.metadata.json``.
The app loads that bundle via ``atlas.services.graph.budget.load_model``.

This reproduces the research notebook's fit as a repeatable job (the notebook in
``research/cite_budget`` stays the exploratory write-up). Run from the repo root:

    uv run python -m ml_pipelines.cite_budget.train              # fit from committed corpus.csv
    uv run python -m ml_pipelines.cite_budget.train --refresh     # re-pull the corpus first

The chosen model form (plain-age linear over sqrt-age) and the density label are
justified in the notebook and this package's README; here we just fit and ship.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import logging
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import KFold, cross_val_score

from atlas.services.graph.budget import FEATURE_NAMES, compute_features

from . import collect as collect_module
from .features import PER_YEAR_CAP

log = logging.getLogger("train")

#: The artifact lives beside its trainer, in this model's own package.
MODEL_DIR = Path(__file__).resolve().parent
MODEL_PATH = MODEL_DIR / "model.joblib"
METADATA_PATH = MODEL_PATH.with_suffix(".metadata.json")  # human-readable sidecar

# 5-fold CV, shuffled with a fixed seed so the reported score is reproducible.
_CV = KFold(n_splits=5, shuffle=True, random_state=0)


def load_corpus(path: Path = collect_module.CORPUS_PATH) -> list[dict]:
    """Read the corpus CSV into typed rows.

    Args:
        path: The corpus CSV (defaults to the committed ``corpus.csv``).

    Returns:
        One dict per seed with ``year``, ``cited_by_count``, and ``citers_before_overflow``
        coerced to ``int``.

    Raises:
        FileNotFoundError: When the corpus hasn't been collected yet.
    """
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        for key in ("year", "cited_by_count", "citers_before_overflow"):
            row[key] = int(row[key])
    return rows


def build_matrix(rows: list[dict], as_of_year: int) -> tuple[np.ndarray, np.ndarray]:
    """Turn corpus rows into the ``(features, labels)`` arrays for fitting.

    Features come from the app's :func:`compute_features` — the same call the
    graph build uses at serving time — so the fitted matrix can't drift from
    what the model will later be asked to predict on.

    Args:
        rows: Corpus rows from :func:`load_corpus`.
        as_of_year: Reference year for age (the training run's year).

    Returns:
        ``(features, labels)`` — features shaped ``(n_seeds, len(FEATURE_NAMES))``,
        labels the ``citers_before_overflow`` density budgets.
    """
    features = np.array([
        compute_features(row["year"], row["cited_by_count"], as_of_year=as_of_year)
        for row in rows
    ])
    labels = np.array([row["citers_before_overflow"] for row in rows])
    return features, labels


def train(rows: list[dict], as_of_year: int) -> dict:
    """Fit the model on ``rows`` and assemble the serializable bundle.

    Args:
        rows: Corpus rows from :func:`load_corpus`.
        as_of_year: Reference year for age (the training run's year).

    Returns:
        The bundle dict — the fitted estimator plus the feature contract, the
        clamp floor, and training metadata — ready for :func:`save`.
    """
    features, labels = build_matrix(rows, as_of_year)
    model = LinearRegression().fit(features, labels)
    cv_r2 = float(cross_val_score(model, features, labels, cv=_CV, scoring="r2").mean())
    return {
        "model": model,
        "feature_names": FEATURE_NAMES,
        # Never ship fewer landmarks than the smallest budget the label ever
        # justified — the serving clamp's floor.
        "floor": int(labels.min()),
        "cv_r2": cv_r2,
        "n_seeds": len(rows),
        "per_year_cap": PER_YEAR_CAP,
        "as_of_year": as_of_year,
        "trained_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "sklearn_version": sklearn.__version__,
    }


def save(bundle: dict) -> None:
    """Serialize the bundle to ``cite_budget.joblib`` and write ``metadata.json``.

    The joblib file is what the app loads; the JSON is a human-readable sidecar
    (coefficients + provenance) that never gets loaded — it's for eyeballing and
    for the git diff to show when a retrain moved the numbers.

    Args:
        bundle: The training bundle from :func:`train`.
    """
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, MODEL_PATH)
    model = bundle["model"]
    metadata = {key: value for key, value in bundle.items() if key != "model"}
    metadata["coefficients"] = dict(zip(bundle["feature_names"], (round(coef, 4) for coef in model.coef_)))
    metadata["intercept"] = round(float(model.intercept_), 4)
    with METADATA_PATH.open("w") as handle:
        json.dump(metadata, handle, indent=2)
        handle.write("\n")
    log.info("Saved model -> %s", MODEL_PATH)
    log.info("  coefficients %s  intercept %.4f", metadata["coefficients"], metadata["intercept"])
    log.info("  floor %d  CV R2 %.3f  n_seeds %d", bundle["floor"], bundle["cv_r2"], bundle["n_seeds"])


def main() -> None:
    """CLI: fit from the committed corpus, or ``--refresh`` to re-pull it first."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Train the adaptive cite-budget model.")
    parser.add_argument("--refresh", action="store_true",
                        help="Re-pull the OpenAlex corpus before fitting (writes corpus.csv).")
    args = parser.parse_args()

    if args.refresh:
        log.info("Refreshing corpus from OpenAlex…")
        rows = collect_module.collect()
        collect_module.write_corpus(rows)
    rows = load_corpus()
    save(train(rows, as_of_year=datetime.date.today().year))


if __name__ == "__main__":
    main()
