"""Generate short AI summaries of paper abstracts.

Two backends (set via SUMMARY_BACKEND in .env):

  * "claude_cli" — shell out to the `claude` CLI in headless mode (`claude -p`).
    Runs under your Claude Pro/Max subscription, so there's no API billing.
    Local-only and subject to your subscription's usage limits.

  * "api" — call the Anthropic API directly (pay-as-you-go; needs ANTHROPIC_API_KEY).
    Faster and deployable anywhere, but billed per token (Haiku 4.5 is cheap).

Either way, summaries are cached in the database by arXiv id, so each paper is
only ever summarized once.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from . import config


SYSTEM_PROMPT = (
    "You are a research assistant who writes crisp, plain-English summaries of "
    "computer-science and machine-learning papers for a busy researcher. "
    "Given a paper's title and abstract, write a single short paragraph that "
    "explains what the paper does and why it matters. Avoid hype and jargon; "
    "do not restate the title. Write for a smart non-specialist. "
    "Output only the summary text — no preamble, no markdown headers."
)


def _user_content(title: str, abstract: str) -> str:
    return (
        f"Title: {title}\n\n"
        f"Abstract: {abstract or '(no abstract available)'}\n\n"
        f"Summarize in roughly {config.SUMMARY_MAX_WORDS} words or fewer."
    )


# --- Backend: Anthropic API --------------------------------------------------
def _build_api_client():
    import anthropic

    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError(
            "SUMMARY_BACKEND=api but ANTHROPIC_API_KEY is not set. Add it to .env "
            "(https://console.anthropic.com), or use SUMMARY_BACKEND=claude_cli."
        )
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def _summarize_api(client, title: str, abstract: str) -> str:
    response = client.messages.create(
        model=config.ANTHROPIC_MODEL,
        max_tokens=400,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _user_content(title, abstract)}],
    )
    return "".join(b.text for b in response.content if b.type == "text").strip()


# --- Backend: claude CLI (subscription) --------------------------------------
def _summarize_cli(title: str, abstract: str) -> str:
    cmd = [
        config.CLAUDE_CLI_PATH,
        "-p",
        _user_content(title, abstract),
        "--system-prompt",
        SYSTEM_PROMPT,
        "--output-format",
        "text",
    ]
    if config.CLAUDE_CLI_MODEL:
        cmd += ["--model", config.CLAUDE_CLI_MODEL]

    # Strip API auth from the environment so the CLI uses your claude.ai
    # subscription login (otherwise ANTHROPIC_API_KEY takes precedence and bills
    # the API — exactly what this backend is meant to avoid).
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=config.CLAUDE_CLI_TIMEOUT,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"claude CLI failed (exit {result.returncode}): "
            f"{(result.stderr or result.stdout).strip()[:300]}"
        )
    return result.stdout.strip()


# --- Dispatch ----------------------------------------------------------------
def _ensure_backend(backend: str, ctx: dict) -> None:
    """Validate/prepare a backend, caching the API client in `ctx` if needed."""
    if backend == "api":
        if ctx.get("api_client") is None:
            ctx["api_client"] = _build_api_client()
    elif backend == "claude_cli":
        if not shutil.which(config.CLAUDE_CLI_PATH):
            raise RuntimeError(
                f"claude CLI '{config.CLAUDE_CLI_PATH}' not found on PATH. "
                "Install Claude Code / sign in, or set CLAUDE_CLI_PATH."
            )
    else:
        raise RuntimeError(f"Unknown summary backend {backend!r}. Use 'api' or 'claude_cli'.")


def _summarize_one(backend: str, title: str, abstract: str, ctx: dict) -> str:
    if backend == "api":
        return _summarize_api(ctx["api_client"], title, abstract)
    return _summarize_cli(title, abstract)


def summarize_pending(papers: list[dict]) -> int:
    """Summarize every paper in `papers` (each a DB row dict). Returns count done.

    Tries the primary backend (config.SUMMARY_BACKEND) first. If it fails — e.g.
    API credits run out — it switches to the fallback backend
    (config.SUMMARY_FALLBACK_BACKEND) for the rest of the run. Each summary is
    persisted immediately, so nothing is lost or re-billed on interruption.
    """
    from . import store

    if not papers:
        return 0

    primary = config.SUMMARY_BACKEND
    fallback = config.SUMMARY_FALLBACK_BACKEND or None
    if fallback == primary:
        fallback = None

    ctx: dict = {}
    active = primary
    try:
        _ensure_backend(active, ctx)
    except Exception as exc:
        if fallback:
            print(f"  ! Primary backend '{active}' unavailable ({exc}); using '{fallback}'")
            active = fallback
            _ensure_backend(active, ctx)
        else:
            raise

    done = 0
    for paper in papers:
        summary = ""
        try:
            summary = _summarize_one(active, paper["title"], paper.get("abstract", ""), ctx)
        except Exception as exc:
            print(f"  ! [{active}] failed for {paper['arxiv_id']}: {exc}")
            if fallback and active != fallback:
                print(f"    -> switching to '{fallback}' for the remaining papers")
                try:
                    _ensure_backend(fallback, ctx)
                    active = fallback
                    summary = _summarize_one(active, paper["title"], paper.get("abstract", ""), ctx)
                except Exception as exc2:
                    print(f"  ! [{fallback}] also failed for {paper['arxiv_id']}: {exc2}")

        if not summary:
            continue
        store.set_summary(paper["arxiv_id"], summary)
        done += 1
        print(f"  + [{active}] {paper['arxiv_id']}: {paper['title'][:55]}")
    return done
