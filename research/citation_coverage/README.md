# `citation_coverage` — Semantic Scholar vs OpenAlex citation coverage (write-up)

The exploratory notebook behind [`docs/citation-coverage.md`](../../docs/citation-coverage.md)
and the recurring **"could we drop Semantic Scholar (S2) and make OpenAlex (OA)
the single source of truth?"** question.

Unlike its siblings (`cite_budget`, `latest_gap`), this study has **no
productionized pipeline** — it's pure decision-support. The graph still uses
both sources (`services/graph/build.py`); the notebook is the evidence for *why*,
and the settled conclusions live in `docs/citation-coverage.md`.

## The question

The hybrid graph pulls references + similar from S2 and citations from OA (see
`docs/citation-coverage.md` for the division of labor). Going **OA-only** would
kill the cross-source dedup glue and the S2 rate-limit pain — but at what cost to
citation quality? Does OA cover citations as well as S2, and does it matter which
field the paper is in?

## What `analyze.ipynb` shows

1. **Citation-count coverage (ML vs physics).** S2 `citationCount` vs OA
   `cited_by_count` over 18 ML + 5 physics seeds. OA undercounts **ML** ~3–4×
   (median OA/S2 ≈ 0.28 on the exact same OA record) but is **fine-to-better for
   physics** (≥ 0.73, often > 1). It's not a missing physics corpus — ML is a
   preprint-native citation graph OA under-extracts.
2. **Resolution & the preprint→published gap.** The app's arXiv-DOI resolution
   lands on the low-cited **preprint** record (ResNet 4.7k vs a 223k published
   record); OA carries **no preprint→VoR link** and `type:article` isn't a
   reliable fix, so an OA-only build would still need a canonical-picking
   heuristic.
3. **Top-cited citer overlap.** Since the build keeps only the top-`cite_limit`
   citers by impact, the sharper test is whether OA surfaces the *same
   landmarks*. On fully-pullable RL papers the top-15 overlap is just 3/15, 3/15,
   6/15 — OA's top citers skew to applied/journal papers, missing the
   arXiv-native methodological landmarks. An extraction gap a dedup heuristic
   can't close.

## Data & caveats

Everything runs against the **live** S2 + OA APIs through the app's throttled,
keyed clients (`config.json` credentials). No stored corpus — hence no data file
here. The result tables in the notebook are **recorded from a 2026-07-12 run**;
code cells ship without pre-computed outputs because re-execution hammers S2's
~1 req/s limit (it 429s on deep citation paging). Counts drift; the *patterns*
are the point. S2 is treated as the *reference*, not absolute ground truth; the
coverage seeds are famous papers (fame bias); the overlap test is RL-only (only
small citer-count papers are fully pullable from S2).

## Re-running

```bash
uv run --group research jupyter nbconvert --execute --to notebook \
    --inplace research/citation_coverage/analyze.ipynb
```

Expect it to be slow and possibly throttled — the notebook hits the live APIs and
paginates S2 citations. The narrative conclusions (and the hybrid's division of
labor) are documented in [`docs/citation-coverage.md`](../../docs/citation-coverage.md).
