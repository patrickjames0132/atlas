"""The agentic Q&A loop (teacher/agentic.py), driven by the scripted client.

Every test scripts the model's turns with REAL SDK event objects (see
conftest), so the loop's event handling runs exactly as in production —
no network, no API key.
"""

from __future__ import annotations

from conftest import text_turn, tool_turn

from arxiv_digest import config
from arxiv_digest.teacher.agentic import answer_agentic

SEED = {"id": "p1", "title": "Attention Is All You Need", "year": 2017,
        "abstract": "We propose the Transformer.", "tldr": "Attention replaces recurrence."}
BERT = {"id": "p2", "title": "BERT", "year": 2018,
        "abstract": "Bidirectional encoder representations.", "tldr": "Pretrain then fine-tune."}
NODES = [SEED, BERT]


def collect(events):
    """Split the (kind, data) stream into kinds + route-style token assembly."""
    events = list(events)  # materialize — answer_agentic yields a generator
    kinds = [k for k, _ in events]
    parts: list[str] = []
    for k, d in events:
        if k == "token":
            parts.append(d)
        elif k == "discard":
            parts.clear()
    cited = next((d for k, d in events if k == "cited"), None)
    return kinds, "".join(parts).strip(), cited


def test_plain_answer_with_sentinel(fake_claude):
    """A one-turn answer streams prose, hides <<CITED>>, and maps indices to ids."""
    client = fake_claude([text_turn("Attention won. <<CITED>> [1, 2]")])
    kinds, text, cited = collect(answer_agentic("why?", SEED, NODES))
    assert text == "Attention won."
    assert cited == ["p1", "p2"]
    assert "discard" not in kinds
    # The model was offered the tool set on a fresh (in-wallclock) turn.
    assert client.calls[0]["tools"], "tools should be offered"


def test_split_sentinel_never_leaks(fake_claude):
    """A sentinel split across stream chunks stays hidden from the prose."""
    from anthropic.types import TextBlock
    from conftest import final_message, text_delta

    full = "RNNs lost. <<CITED>> [2]"
    events = [text_delta("RNNs lost. <<CIT"), text_delta("ED>> [2]")]
    fake_claude([(events, final_message([TextBlock(type="text", text=full)], "end_turn"))])
    _, text, cited = collect(answer_agentic("q", SEED, NODES))
    assert text == "RNNs lost."
    assert "<<" not in text
    assert cited == ["p2"]


def test_tool_turn_discards_preamble_then_answers(fake_claude):
    """Preamble streamed before a tool call is disavowed; the real answer follows."""
    fake_claude([
        tool_turn("read_paper", {"index": 2, "detail": "summary"},
                  preamble="Let me look at BERT..."),
        text_turn("BERT builds on it. <<CITED>> [2]"),
    ])
    events = list(answer_agentic("how does BERT relate?", SEED, NODES))
    kinds, text, cited = collect(events)
    assert "discard" in kinds
    assert text == "BERT builds on it."
    # read_paper marks the paper read AND the sentinel names it — deduped.
    assert cited == ["p2"]
    # The read emitted a live trace event before the answer streamed.
    traces = [d for k, d in events if k == "trace"]
    assert traces and traces[0]["action"] == "read" and traces[0]["ok"] is True


def test_unknown_tool_is_answered_not_raised(fake_claude):
    """An unrecognized tool name feeds an error string back; the loop continues."""
    client = fake_claude([
        tool_turn("frobnicate", {"x": 1}),
        text_turn("Answer anyway. <<CITED>> []"),
    ])
    _, text, _ = collect(answer_agentic("q", SEED, NODES))
    assert text == "Answer anyway."
    # The tool_result carried the unknown-tool message back to the model.
    followup_messages = client.calls[1]["messages"]
    results = followup_messages[-1]["content"]
    assert "Unknown tool" in results[0]["content"]


def test_step_budget_forces_toolfree_answer(fake_claude, monkeypatch):
    """When AGENT_MAX_STEPS runs out mid-investigation, a tool-free turn answers."""
    monkeypatch.setattr(config, "AGENT_MAX_STEPS", 1)
    client = fake_claude([
        tool_turn("read_paper", {"index": 1, "detail": "summary"}),
        text_turn("Forced summary. <<CITED>> [1]"),
    ])
    kinds, text, cited = collect(answer_agentic("q", SEED, NODES))
    assert text == "Forced summary."
    assert cited == ["p1"]
    # The forced call carries no tools kwarg and an explicit "answer now" nudge.
    assert "tools" not in client.calls[1]
    assert client.calls[1]["messages"][-1]["content"] == "Answer now with what you've gathered."


def test_wallclock_expiry_strips_tools(fake_claude, monkeypatch):
    """Past AGENT_WALLCLOCK, turns run without tools (the model must answer)."""
    monkeypatch.setattr(config, "AGENT_WALLCLOCK", 0)  # expired immediately
    client = fake_claude([text_turn("Quick answer. <<CITED>> []")])
    _, text, _ = collect(answer_agentic("q", SEED, NODES))
    assert text == "Quick answer."
    assert client.calls[0]["tools"] == []


def test_history_threads_into_messages(fake_claude):
    """Prior turns precede the question; malformed turns are skipped."""
    client = fake_claude([text_turn("Follow-up answer. <<CITED>> []")])
    history = [
        {"role": "user", "content": "earlier question"},
        {"role": "assistant", "content": "earlier answer"},
        {"role": "system", "content": "not a turn"},          # bad role
        {"role": "user", "content": ["not", "a", "string"]},  # bad content
    ]
    collect(answer_agentic("and now?", SEED, NODES, history=history))
    msgs = client.calls[0]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[0]["content"] == "earlier question"
    assert "and now?" in msgs[-1]["content"]


def test_show_figure_slot_flows_to_figure_event_and_marker_streams(fake_claude, monkeypatch):
    """Inline-figure protocol: the figure event carries its slot, and the
    <<FIG n>> marker the model places in prose streams through verbatim (the
    frontend splits on it to interleave the image)."""
    from arxiv_digest.teacher import tools

    monkeypatch.setattr(tools.figures_mod, "get_figures", lambda arxiv_id: {
        "available": True,
        "figures": [{"image": "https://ar5iv.labs.arxiv.org/x.png", "caption": "Arch"}],
    })
    nodes = [dict(SEED, arxiv_id="1706.03762"), BERT]
    fake_claude([
        tool_turn("show_figure", {"index": 1, "figure": 1}),
        text_turn("See the architecture:\n<<FIG 1>>\nas shown. <<CITED>> [1]"),
    ])
    events = list(answer_agentic("show me", SEED, nodes))
    (figure,) = [d for k, d in events if k == "figure"]
    assert figure["slot"] == 1 and figure["image"].startswith("/api/figure_proxy")
    _, text, cited = collect(events)
    assert "<<FIG 1>>" in text          # marker reaches the frontend intact
    assert "<<CITED" not in text        # the citation sentinel still hidden
    assert cited == ["p1"]


def test_empty_source_scope_disables_source_tool(fake_claude, stub_embeddings):
    """source_ids=[] ("no sources selected") must not offer search_sources."""
    from arxiv_digest.library import sources

    sources.add_source("Book", "pdf", "b.pdf", [(1, "some text about optimizers")])
    client = fake_claude([text_turn("ok <<CITED>> []")])
    collect(answer_agentic("q", SEED, NODES, source_ids=[]))
    names = [t["name"] for t in client.calls[0]["tools"]]
    assert "search_sources" not in names


def test_library_presence_offers_source_tool(fake_claude, stub_embeddings):
    """With a library and no scope, search_sources is offered and listed."""
    from arxiv_digest.library import sources

    sources.add_source("Book", "pdf", "b.pdf", [(1, "some text about optimizers")])
    client = fake_claude([text_turn("ok <<CITED>> []")])
    collect(answer_agentic("q", SEED, NODES))
    names = [t["name"] for t in client.calls[0]["tools"]]
    assert "search_sources" in names
    # The library listing rode into the grounding context.
    assert "Your library" in client.calls[0]["messages"][-1]["content"]
