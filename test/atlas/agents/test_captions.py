"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
split_label: the float designation split off the front of a caption.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import pytest

from atlas.agents import captions


@pytest.mark.parametrize(
    ("caption", "label", "rest"),
    [
        ("Figure 12.4: The forward view. More.", "Figure 12.4", "The forward view. More."),
        ("Figure 3: The model.", "Figure 3", "The model."),
        ("Fig. 7: Ablations.", "Figure 7", "Ablations."),
        ("Table 2: Results on WMT.", "Table 2", "Results on WMT."),
        ("Algorithm 1 PPO, Actor-Critic Style", "Algorithm 1", "PPO, Actor-Critic Style"),
        ("Figure A.2: Appendix diagram.", "Figure A.2", "Appendix diagram."),
        ("Figure 12.9: Sarsa(λ)'s backup diagram.", "Figure 12.9", "Sarsa(λ)'s backup diagram."),
        # Chapter-hyphenated numbering — the Feynman Lectures' whole scheme.
        # Matching only dots truncated these to "Figure 3" and left the rest
        # opening with a stray "-2.", so the chip named the wrong figure.
        ("Figure 3-2. Two-slit interference.", "Figure 3-2", "Two-slit interference."),
        ("Fig. 1-4 The apparatus.", "Figure 1-4", "The apparatus."),
        ("Figure 3\u20132. En-dash typesetting.", "Figure 3\u20132", "En-dash typesetting."),
        ("Table 10-1: Measured values.", "Table 10-1", "Measured values."),
    ],
)
def test_split_label_variants(caption, label, rest):
    assert captions.split_label(caption) == (label, rest)


def test_no_designation_passes_through():
    assert captions.split_label("A photograph of the apparatus.") == (
        None,
        "A photograph of the apparatus.",
    )
    assert captions.split_label("") == (None, "")
    # An in-caption cross-reference mid-sentence isn't a designation.
    assert captions.split_label("As shown before, Figure 2 helps.")[0] is None


def test_a_spaced_dash_stays_in_the_caption():
    """A separator only joins the number when digits follow immediately — a
    spaced dash is punctuation the caption owns, not part of the label."""
    assert captions.split_label("Figure 3 - A single slit.") == ("Figure 3", "- A single slit.")
