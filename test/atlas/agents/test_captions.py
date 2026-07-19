"""split_label: the float designation split off the front of a caption."""

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
