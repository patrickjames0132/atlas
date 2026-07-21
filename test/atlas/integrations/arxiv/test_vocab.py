"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
arxiv.vocab: the bundled arXiv category taxonomy — per-paper tag labelling
(``name_for``).

Loads the real taxonomy.json (static bundled data — no network, no fixture).

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from atlas.integrations.arxiv import vocab


def test_name_for_known_and_unknown_codes():
    assert vocab.name_for("cs.LG") == "Machine Learning"
    assert vocab.name_for("not.a.real.code") is None
