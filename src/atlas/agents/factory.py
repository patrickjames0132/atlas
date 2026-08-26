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

**This module is the whole vendor seam.** Every agent gets its model from
``build_model``, so teaching Atlas a new vendor is a case arm here plus a
config block — no agent package changes. Vendors are per *agent*, not global:
``config.llm.agents`` carries one model string each, so a perfectly sensible
setup runs the lecturer on a free local model and leaves the web scout on a
vendor that can actually search the web (see ``supports_web_search``).

Authors:
Charles Patrick James <charles.patrick.james@gmail.com>
"""

from __future__ import annotations

from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelSettings
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider

from ..config import AgentConfig, config

#: Vendors whose models can search the web *provider-side* — the search runs on
#: their infrastructure and never reaches this process. Ollama is the pointed
#: omission: a local server has no such facility, and there is no honest way to
#: fake one, so agents on a local model do without rather than pretend.
WEB_SEARCH_VENDORS = frozenset({"anthropic", "openai", "google"})


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


def supports_web_search(agent_id: str) -> bool:
    """Whether this agent's vendor can run a provider-side web search.

    Asked by the web scout at construction time, because the capability has
    to be attached (or not) when its ``Agent`` is built. Attaching one to a
    vendor that can't honour it produces an agent prompted to search with no
    way to, which is the failure mode worth designing out.

    Args:
        agent_id: The agent's ``config.llm.agents`` entry id.

    Returns:
        True when the agent's vendor offers provider-side search.

    Raises:
        LookupError: When no entry has that id.
    """
    return agent_entry(agent_id).provider in WEB_SEARCH_VENDORS


def build_model(agent_id: str) -> Model:
    """Build the model an agent's entry names, with explicit credentials.

    Args:
        agent_id: The agent's ``config.llm.agents`` entry id.

    Returns:
        A ready PydanticAI ``Model`` carrying a provider built from this
        app's config — never from the environment.

    Raises:
        LookupError: When no entry has that id.
        ValueError: When the entry names a vendor whose config block is
            blank. Deliberately a *request-time* failure and not a load-time
            one: the app must start and serve the (keyless) graph explorer
            with no LLM configured at all, so an unconfigured teacher has to
            surface as an honest message rather than a refusal to boot.
        NotImplementedError: When the entry names a vendor this factory
            doesn't construct. Config validation guarantees the vendor is a
            known field, so this fires only when a vendor is added to config
            without a case arm here — loudly, rather than mysteriously.
    """
    entry = agent_entry(agent_id)
    provider_name, model_name = entry.model.split(":", 1)
    vendors = config.llm.providers
    vendor = getattr(vendors, provider_name, None)
    if vendor is None:
        raise NotImplementedError(
            f"agent {agent_id!r} wants provider {provider_name!r}, which the "
            "factory doesn't construct yet"
        )
    if not vendor.configured:
        raise ValueError(
            f"agent {agent_id!r} runs on {provider_name!r}, but that vendor is blank "
            f"in config.json. Fill it in, or point the agent at one of "
            f"{vendors.configured_vendors() or ['(none configured)']}."
        )

    match provider_name:
        case "anthropic":
            return AnthropicModel(
                model_name,
                provider=AnthropicProvider(api_key=vendors.anthropic.api_key),
                # Without eager input streaming, Anthropic buffers a tool call's
                # argument JSON server-side and delivers it in one burst — and every
                # structured output here IS a tool call, so lecture beats and answer
                # prose would only "stream" all at once at the end (observed live,
                # frame-timestamped). Eager streaming is what makes them stream.
                settings=AnthropicModelSettings(anthropic_eager_input_streaming=True),
            )
        case "openai":
            # One adapter, many endpoints: a blank base_url is OpenAI proper,
            # and any other value points the same client at an OpenAI-compatible
            # server (Groq, OpenRouter, Together, LM Studio, ...). `or None`
            # matters — the provider treats None as "use the default host",
            # while "" would be sent as a literal empty URL.
            return OpenAIChatModel(
                model_name,
                provider=OpenAIProvider(
                    api_key=vendors.openai.api_key or None,
                    base_url=vendors.openai.base_url or None,
                ),
            )
        case "google":
            return GoogleModel(
                model_name, provider=GoogleProvider(api_key=vendors.google.api_key)
            )
        case "ollama":
            # No api_key: a local server authenticates nobody. The base_url
            # must already carry the '/v1' suffix (config says so) because
            # Ollama's OpenAI-compatible surface lives there, not at the root.
            return OllamaModel(
                model_name, provider=OllamaProvider(base_url=vendors.ollama.base_url)
            )
        case _:  # pragma: no cover — unreachable while every vendor has an arm
            raise NotImplementedError(
                f"agent {agent_id!r} wants provider {provider_name!r}, which the "
                "factory doesn't construct yet"
            )
