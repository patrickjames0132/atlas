"""Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.

Description:
Turns ``config.llm`` entries into live PydanticAI model objects.

Each sub-agent's ``main.py`` calls ``build_model(<its id>)`` to get the model
its ``config.llm.agents`` entry names, and passes it to its ``pydantic_ai.
Agent``. This is the one place credentials meet PydanticAI.

Why not PydanticAI's own ``"anthropic:claude-..."`` string shorthand? Passed
straight to an ``Agent``, that shorthand pulls the API key from environment
variables — and this app's config rule is *no env vars*: every credential
lives in config.json, explicitly. So the provider is constructed by hand with
the key from ``config.llm.providers``, and the ``"provider:model"`` string is
only ever *parsed*, never handed to PydanticAI whole.

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings
from pydantic_ai.providers.anthropic import AnthropicProvider

from ..config import AgentConfig, config


def agent_entry(agent_id: str) -> AgentConfig:
    """Look up an agent's ``config.llm.agents`` entry by id.

    Args:
        agent_id: The entry's unique ``id`` (each sub-agent package names its
            own in its ``config.py``).

    Returns:
        The matching ``AgentConfig``.

    Raises:
        LookupError: When no entry has that id — the fix is adding one to
            config.json (see config.example.json for the shape).
    """
    for entry in config.llm.agents:
        if entry.id == agent_id:
            return entry
    configured = [entry.id for entry in config.llm.agents]
    raise LookupError(
        f"no agent {agent_id!r} in config.llm.agents (configured: {configured}) — "
        "add an entry to config.json"
    )


def build_model(agent_id: str) -> AnthropicModel:
    """Build the model an agent's entry names, with explicit credentials.

    Args:
        agent_id: The agent's ``config.llm.agents`` entry id.

    Returns:
        A ready ``AnthropicModel`` carrying an ``AnthropicProvider`` built
        from the config key.

    Raises:
        LookupError: When no entry has that id.
        NotImplementedError: When the entry names a vendor this factory
            doesn't construct yet. Config validation already guarantees the
            vendor is configured under ``llm.providers``, so today (Anthropic
            only) this can't trigger — it exists so adding a vendor to config
            without wiring it here fails loudly, not mysteriously.
    """
    entry = agent_entry(agent_id)
    provider_name, model_name = entry.model.split(":", 1)
    if provider_name != "anthropic":
        raise NotImplementedError(
            f"agent {agent_id!r} wants provider {provider_name!r}, which the "
            "factory doesn't construct yet"
        )
    provider = AnthropicProvider(api_key=config.llm.providers.anthropic.api_key)
    return AnthropicModel(
        model_name,
        provider=provider,
        # Without eager input streaming, Anthropic buffers a tool call's
        # argument JSON server-side and delivers it in one burst — and every
        # structured output here IS a tool call, so lecture beats and answer
        # prose would only "stream" all at once at the end (observed live,
        # frame-timestamped). Eager streaming is what makes them stream.
        settings=AnthropicModelSettings(anthropic_eager_input_streaming=True),
    )
