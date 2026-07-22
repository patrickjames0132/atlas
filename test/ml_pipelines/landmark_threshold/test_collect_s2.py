"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The S2 threshold collector (src/ml_pipelines/landmark_threshold): offline checks.

Fully offline — the corpus queries run against the synthetic ingested release
(``conftest.synthetic_corpus``), and the pure ``seed_rows`` prune/denominator
logic is driven directly. No network at all (this collector never had any — it's
corpus-only).

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from ml_pipelines.landmark_threshold import collect_s2, train_s2


class TestCorpusReader:
    """The study's corpus queries: the citer distribution, sampling, resolution."""

    def test_citer_distribution_collapses_overlapping_batches(self, synthetic_corpus):
        # 6 distinct citers arrive as 9 edge rows across two shards; counting rows
        # (not papers) would inflate every bin's count. Each (year, cited_by) pair
        # is distinct here, so 6 bins of count 1 — undated citer 5 included (the
        # collector, not the reader, drops it).
        distribution = collect_s2.CorpusReader().citer_distribution(1)
        assert len(distribution) == 6
        assert all(count == 1 for _year, _cited_by, count in distribution)
        assert sorted(cited_by for _year, cited_by, _count in distribution) == [0, 1, 250, 300, 400, 500]

    def test_resolves_worked_example_by_arxiv_and_by_doi(self, synthetic_corpus):
        reader = collect_s2.CorpusReader()
        by_arxiv = reader.resolve_worked_example({"arxiv_id": "1312.5602"})
        assert by_arxiv == {"corpus_id": 1, "seed_year": 2013, "seed_cited_by": 900}
        # DOIs match case-folded, and the DOI-only seed has no arXiv id.
        by_doi = reader.resolve_worked_example({"doi": "10.5555/JOURNAL-ONLY"})
        assert by_doi == {"corpus_id": 10, "seed_year": 2015, "seed_cited_by": 40}
        assert reader.resolve_worked_example({"arxiv_id": "0000.0000"}) is None

    def test_sampling_is_banded_and_repeatable(self, synthetic_corpus):
        reader = collect_s2.CorpusReader()
        first = reader.sample_stratum((2013, 2021), (100, 2_000), 5, sample_seed=7)
        second = reader.sample_stratum((2013, 2021), (100, 2_000), 5, sample_seed=7)
        ids = sorted(seed["corpus_id"] for seed in first)
        # Seed 1 (2013, 900) and citer papers 2 (2019, 500) / 3 (2020, 400) /
        # 4 (2021, 400? no — 2021 excluded)… the band admits ids 1, 2, 3.
        assert 1 in ids
        assert all(100 <= seed["seed_cited_by"] < 2_000 for seed in first)
        assert all(2013 <= seed["seed_year"] < 2021 for seed in first)
        # Same seed -> identical draw (reproducible committed corpus).
        assert [seed["corpus_id"] for seed in first] == [seed["corpus_id"] for seed in second]


class TestSeedRows:
    """The prune + denominator logic that shapes the committed rows."""

    def test_prunes_undated_and_low_cited_but_keeps_totals(self):
        seed = {"corpus_id": 1, "label": "S", "seed_year": 2013, "seed_cited_by": 900}
        # 500/400/300 survive; the undated 250 and the sub-floor 1/0 are dropped.
        distribution = [
            (2019, 500, 1), (2020, 400, 1), (2021, 300, 1),
            (None, 250, 1), (2023, 1, 1), (2024, 0, 1),
        ]
        rows = collect_s2.seed_rows(seed, distribution, is_worked_example=1)
        assert len(rows) == 3
        assert sorted(row["citer_cited_by"] for row in rows) == [300, 400, 500]
        # Totals count everything (all six), dated counts the five with a year.
        assert rows[0]["total_citers"] == 6
        assert rows[0]["dated_citers"] == 5
        assert rows[0]["is_worked_example"] == 1

    def test_seed_with_no_eligible_citer_yields_no_rows(self):
        seed = {"corpus_id": 2, "label": "S", "seed_year": 2020, "seed_cited_by": 100}
        distribution = [(2021, 1, 3), (None, 5, 2)]  # all pruned (sub-floor or undated)
        assert collect_s2.seed_rows(seed, distribution, is_worked_example=0) == []


class TestFieldContract:
    """The committed schema and the prune floor the fit relies on."""

    def test_prune_floor_is_at_least_two(self):
        # The fit constrains FLOOR >= PRUNE_FLOOR so the (pruned) corpus never
        # understates a landmark count — keep the floor meaningful.
        assert collect_s2.PRUNE_FLOOR >= 2

    def test_fields_cover_every_written_key(self):
        seed = {"corpus_id": 1, "label": "S", "seed_year": 2013, "seed_cited_by": 900}
        rows = collect_s2.seed_rows(seed, [(2019, 500, 1)], is_worked_example=0)
        assert set(rows[0]) == set(collect_s2.FIELDS)


class TestCorpusRoundTrip:
    """Writing the corpus and reading it back — gzip, and the encoding that bit us.

    A whole hour-long collection was once lost at the final write step, because
    the run accumulates in memory and writes once at the end: a seed title held a
    Unicode hyphen and Windows' default cp1252 encoder raised. Nothing exercised
    ``write_corpus``, so the gate was green. These do.
    """

    def _seed_row(self, label):
        seed = {"corpus_id": 1, "label": label, "seed_year": 2013, "seed_cited_by": 900}
        return collect_s2.seed_rows(seed, [(2019, 500, 2)], is_worked_example=1)

    def test_writes_non_cp1252_titles(self, tmp_path):
        # U+2010 HYPHEN — the exact character that sank the run.
        rows = self._seed_row("Hawking‐Radiation — éü中文")
        path = tmp_path / "corpus_s2.csv"
        collect_s2.write_corpus(rows, path)
        assert "‐" in path.read_text(encoding="utf-8")

    def test_gzip_round_trips_through_the_trainer(self, tmp_path):
        rows = self._seed_row("Attention‐Is All You Need")
        path = tmp_path / "corpus_s2.csv.gz"
        collect_s2.write_corpus(rows, path)
        # Really gzip (not plain text that merely ends in .gz).
        assert path.read_bytes()[:2] == b"\x1f\x8b"
        seeds = train_s2.load_seeds(path, as_of_year=2026)
        assert len(seeds) == 1
        assert seeds[0].label == "Attention‐Is All You Need"
        assert seeds[0].cited_by == 900
        assert seeds[0].max_possible_landmarks == 2
        assert list(seeds[0].citer_cited_by) == [500.0]

    def test_plain_and_gzip_load_identically(self, tmp_path):
        rows = self._seed_row("plain vs gzip")
        plain, zipped = tmp_path / "corpus.csv", tmp_path / "corpus.csv.gz"
        collect_s2.write_corpus(rows, plain)
        collect_s2.write_corpus(rows, zipped)
        from_plain = train_s2.load_seeds(plain, as_of_year=2026)[0]
        from_gzip = train_s2.load_seeds(zipped, as_of_year=2026)[0]
        assert from_plain.corpus_id == from_gzip.corpus_id
        assert list(from_plain.citer_ages) == list(from_gzip.citer_ages)
        assert list(from_plain.citer_counts) == list(from_gzip.citer_counts)
