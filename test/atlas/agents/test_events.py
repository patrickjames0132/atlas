"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
The typed event stream: model shapes, the two discriminated unions, and
that discoveries stay in lockstep with the graph's own node/edge models.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from atlas.agents import events

EVENT = TypeAdapter(events.Event)
TRACE = TypeAdapter(events.Trace)


def make_node_payload(**overrides) -> dict:
    """A valid DiscoveredNode payload (all graph-Node fields present)."""
    payload = {
        "id": "s2-abc",
        "arxiv_id": "2301.00001",
        "title": "Attention Is All You Need",
        "abstract": "We propose the Transformer.",
        "tldr": "Attention replaces recurrence.",
        "year": 2017,
        "month": 6,
        "pub_date": "2017-06-12",
        "citation_count": 100000,
        "authors": "Vaswani et al.",
        "url": "https://example.org/paper",
        "rels": ["reference"],
        "is_seed": False,
    }
    payload.update(overrides)
    return payload


def test_beat_round_trips_through_dump_and_validate():
    beat = events.Beat(heading="The roots", text="It began...", node_ids=["a", "b"])
    assert events.Beat.model_validate(beat.model_dump()) == beat
    assert beat.type == "beat"


def test_event_union_discriminates_by_type():
    event = EVENT.validate_python({"type": "token", "text": "hello"})
    assert isinstance(event, events.Token)
    event = EVENT.validate_python({"type": "cited", "node_ids": ["x"]})
    assert isinstance(event, events.Cited)
    event = EVENT.validate_python({"type": "done"})
    assert isinstance(event, events.Done)
    event = EVENT.validate_python({"type": "error", "message": "boom"})
    assert isinstance(event, events.Error)


def test_trace_union_discriminates_by_action():
    trace = TRACE.validate_python(
        {"action": "expand", "ok": True, "index": 3, "title": "T", "relation": "citations"}
    )
    assert isinstance(trace, events.ExpandTrace)
    assert trace.found is None  # optional: absent on failure traces
    trace = TRACE.validate_python({"action": "retrieval", "found": 2, "sources": ["Deep Learning"]})
    assert isinstance(trace, events.RetrievalTrace)


def test_traces_nest_inside_the_event_union():
    event = EVENT.validate_python(
        {
            "type": "trace",
            "action": "read",
            "ok": True,
            "index": 1,
            "title": "T",
            "detail": "full",
        }
    )
    assert isinstance(event, events.ReadTrace)


def test_unknown_type_and_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        EVENT.validate_python({"type": "narration", "text": "hi"})
    with pytest.raises(ValidationError):
        events.Token(text="hi", surprise=True)


def test_discovered_node_extends_the_graph_node():
    node = events.DiscoveredNode.model_validate(make_node_payload(idx=12))
    assert node.discovered is True
    assert node.idx == 12
    # idx defaults to None — old saved sessions carry un-numbered discoveries.
    unnumbered = events.DiscoveredNode.model_validate(make_node_payload())
    assert unnumbered.idx is None
    # extra="forbid" is inherited: a drifted field fails loudly.
    with pytest.raises(ValidationError):
        events.DiscoveredNode.model_validate(make_node_payload(surprise=True))


def test_discovery_reuses_graph_edges():
    discovery = events.Discovery.model_validate(
        {
            "type": "discovery",
            "nodes": [make_node_payload()],
            "edges": [
                {"source": "a", "target": "b", "type": "reference", "influential": True}
            ],
        }
    )
    assert discovery.edges[0].influential is True
    # Search discoveries carry no edges — an empty list is a valid discovery.
    assert events.Discovery(nodes=[], edges=[]).edges == []


def test_figure_event_shape():
    figure = events.Figure(
        image="/api/figure_proxy?src=x",
        caption="The architecture.",
        title="Attention Is All You Need",
        index=1,
        figure=2,
        slot=1,
    )
    assert EVENT.validate_python(figure.model_dump()) == figure
