# OpenAlex quirks and the two arXiv touchpoints

Why the OpenAlex provider leans on arXiv in two specific places, what each one
does (and doesn't) cost, and a glossary for the terms that keep coming up (DOI,
arXiv-DOI). Read this before touching `integrations/openalex/nodes.py`'s date
handling or `integrations/openalex/traversal.py`'s `resolve_seed_work`. For the
deeper S2-vs-OpenAlex citation comparison see
[`citation-coverage.md`](citation-coverage.md).

## Glossary (the terms that keep slipping)

### DOI

A **DOI** (Digital Object Identifier) is a **permanent, unique id for a document**
— a paper, dataset, etc. It looks like `10.<registrant>/<suffix>`, e.g.
`10.1038/nature14539` (a Nature paper) or `10.1145/3065386` (an ACM one). The
`10.` prefix marks it as a DOI; the registrant is the publisher/agency, the
suffix is their internal id. Unlike a URL, a DOI is meant to never change and to
always resolve (via `https://doi.org/<doi>`) to the current location of the
thing. **Most academic databases key papers by DOI**, so it's the closest thing
to a universal paper id — which is exactly why OpenAlex nodes prefer a `DOI:` id
(see the OpenAlex package README).

### arXiv-DOI (the arXiv-minted DOI)

Since 2022, **arXiv auto-mints a DOI for every preprint**, of the form
`10.48550/arXiv.<arxiv_id>` — e.g. "Attention Is All You Need" (arXiv id
`1706.03762`) gets `10.48550/arXiv.1706.03762`. `10.48550` is arXiv's registrant.

The catch: that DOI points at the **arXiv preprint record specifically** — which
is a *different* record (and a different DOI) from the paper's **published
version of record** (its journal/conference DOI). So one intellectual work often
has **two DOIs**: the arXiv-DOI (preprint) and the publisher DOI (published). This
one-work-two-records split is the root of most of the OpenAlex quirks below.

## Why OpenAlex is quirky for arXiv/ML papers

OpenAlex assembles "one work" from many noisy metadata sources (arXiv, Crossref,
the publisher, re-crawled mirrors). Its merging/canonicalization is imperfect,
and that single underlying reality — **one intellectual work represented as
several records** — shows up as three *different* symptoms:

1. **Citation undercount.** OpenAlex under-extracts arXiv-preprint → preprint
   citations (the dense ML citation web), so an ML paper's `cited_by_count` reads
   far below reality (AIAYN ~6.5k in OpenAlex vs ~100k+ elsewhere). This is an
   *extraction* problem — see `citation-coverage.md`.
2. **arXiv-id identifiability gap.** OpenAlex has **no clean arXiv-id field** — the
   id only appears inside a work's `locations[].landing_page_url`. A record that
   is the *published-only* version carries no arXiv location, so we can't recover
   an arXiv id from it (which is why some OpenAlex papers show no "arXiv tags").
3. **Misdating.** OpenAlex sometimes stamps the canonical work with a **wrong
   `publication_year`** — AIAYN's OpenAlex record says **2025**, not 2017 —
   almost certainly a late re-crawl / re-published record's date leaking into the
   merged work. This is a *metadata-provenance* error, **not** a preprint-vs-
   published *selection* we make.

The two arXiv touchpoints below are targeted mitigations for #2/#3.

## Touchpoint 1 — deriving the date from the arXiv id (no network)

**Where:** `integrations/openalex/nodes.py` — `_arxiv_date()`, used by `node()`.

A **new-format arXiv id encodes its own submission date**: `YYMM.NNNNN`, so
`1706`.03762 → `17` = 2017, `06` = June. `_arxiv_date` just **parses those
digits** — there is **no arXiv request**, it's a pure string operation on the id
we already hold. When OpenAlex's `publication_year` *disagrees* with the arXiv
id's year, we trust the arXiv id (the true appearance date) and override
year/month/pub_date; when they agree we keep OpenAlex's fuller date (it has the
day). Old-format ids (`hep-th/9901001`) aren't parsed — they keep OpenAlex's date.

- **Only works for arXiv papers** — by nature: the id has to encode the date. A
  pure-journal paper with no arXiv id can't be corrected this way. That's fine —
  the misdating is concentrated in **arXiv-native ML papers**; journal-native
  papers have reliable OpenAlex dates.
- **Free** — no network, no rate-limit cost, runs on every OpenAlex node.

## Touchpoint 2 — arXiv title lookup for seed resolution (a real arXiv call)

**Where:** `integrations/arxiv/categories.py` — `get_title()`, called by
`integrations/openalex/traversal.py`'s `resolve_seed_work`.

`resolve_seed_work` turns a bare arXiv id into an OpenAlex work cheapest-first,
via the **arXiv-DOI** (`doi:10.48550/arXiv.<id>`). But that DOI **404s in
OpenAlex** for a paper whose canonical OpenAlex record is the *published* version
(not aliased to the arXiv-DOI) — AIAYN is the poster child, and it used to fail
outright ("No paper found on OpenAlex"). The fallback: fetch the paper's **title
from arXiv's export API** (`arxiv.get_title` — one HTTP call, sharing
`categories.py`'s existing fetch), then title-search OpenAlex, which lands the
canonical record.

- **This one does hit arXiv** — but only on the **rare resolve-miss path** (the
  arXiv-DOI didn't resolve), only to get a title, and the resulting graph
  snapshot is cached whole afterward. `integrations/openalex` already depends on
  `integrations/arxiv` (for `extract_id`), so it's not new coupling.
- Contrast with touchpoint 1: **the date fix makes no request; the resolution
  fallback does.** When someone asks "are we hitting arXiv?", touchpoint 2 is the
  one that does, and only on a miss.

## In one line

The arXiv id is authoritative for two things OpenAlex gets wrong for arXiv
papers — **its date** (parsed straight from the id, free) and, when OpenAlex
can't find the paper at all, **its title** (one arXiv call on the miss path, to
let OpenAlex resolve it by title).
