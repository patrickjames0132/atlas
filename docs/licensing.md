# Licensing — why Atlas is MIT, and when that must change

The decision, the reasoning behind it, and the one trigger that forces a
revisit. Written 2026-07-20 when the project first got a `LICENSE`, ahead of
sharing the code more widely and publishing to PyPI.

> **Not legal advice.** This captures the engineering reasoning so it isn't
> re-derived every time the question comes up. For anything with real money at
> stake, a short consult with an IP attorney is worth it.

## The decision

**Atlas is licensed under the [MIT License](../LICENSE).** Anyone may fork it,
modify it, and even sell their own service built on it. The only obligations on
them are trivial: keep the copyright notice, and accept that the software comes
with no warranty.

That last point is the one that protects **us**: MIT's disclaimer ("THE SOFTWARE
IS PROVIDED 'AS IS'… IN NO EVENT SHALL THE AUTHORS… BE LIABLE…") means someone
who uses Atlas, has it break, and tries to sue over the damage will lose. Every
mainstream open-source license disclaims this equally; it is not a weak point of
MIT.

## Copyright vs. patent — the distinction that drove the choice

These protect different things, and conflating them causes most licensing
confusion:

- **Copyright** protects the **expression** — the actual code as written. It is
  automatic and free the moment the code exists, and it stops someone from
  **copying the code**. It does *not* stop someone re-implementing the same idea
  in their own, different code. We hold Atlas's copyright automatically.
- **A patent** protects an **invention / method** — a novel, non-obvious *way of
  doing something*, independent of the specific code. It must be applied for,
  examined, and granted (slow and expensive), and it stops others from using the
  method **even if they wrote entirely different code**. We hold **no patents**
  and have filed for none.

So copyright guards our *code*; a patent would guard a *technique*.

## Why MIT and not Apache-2.0 (yet)

Apache-2.0 is the same kind of permissive, fork-and-sell, liability-disclaiming
license as MIT, with one addition: **patent clauses**.

- **Contributor patent grant** — anyone who contributes code automatically
  licenses any patent *they* own that covers *their* contribution, so a
  contributor can't hand over code and later sue over a patent on it.
- **Patent retaliation** — anyone who *uses* the software and then sues claiming
  it infringes *their* patent instantly loses their license to it.

Neither clause requires *us* to own a patent — they defuse patents that
**other people** (contributors, users) might hold. But their value only appears
once there are **outside contributors or a base of users**. Today Atlas is
solo-authored with none, so Apache's patent machinery would sit idle, and MIT's
smaller, ubiquitous, ~20-line text wins on simplicity.

Importantly, for the specific fear of *a third party patenting the idea and
sending a cease-and-desist* — **neither license is the defense.** A troll who
never touched our code isn't bound by our license at all. The real protection is
**public, timestamped release** (this repo, and PyPI): it establishes dated
**prior art**, which makes it very hard for anyone to later patent the same idea
and enforce it against us. Publishing *is* the shield; the license is not.

## ⚠️ The trigger: relicense to Apache-2.0 BEFORE accepting outside contributions

**The moment Atlas opens to third-party contributions — a pull request from
anyone but the author, a collaborator with commit access, a public
`CONTRIBUTING` guide, or a CLA — relicense MIT → Apache-2.0 *first*, before the
first outside contribution lands.**

Why the ordering matters: once other people's copyright and potential patent
rights are mixed into the codebase, cleanly changing the license gets much
harder (every contributor may need to agree). Doing the switch while the author
is still the sole rights-holder is a one-person decision. That is exactly the
window Apache's contributor-patent-grant and retaliation clauses were built for,
so the switch and the first contributor should happen in that order.

Mechanically the switch means: swap `LICENSE` for the Apache-2.0 text, add a
`NOTICE` file, and re-stamp the per-file headers (they name "MIT License"). It is
mostly a find-and-replace, but it must precede the contributions, not follow
them.

## Per-file headers

Every source file (backend and frontend) carries the license in its top
docstring / file comment, in three parts:

1. **Top line** — `Copyright (c) 2026 Charles Patrick James
   <charles.patrick.james@gmail.com>. MIT License — see LICENSE.`
2. **`Description:`** — the file's own documentation (what it always said).
3. **`Authors:`** — name and email.

The `LICENSE` file at the repo root is the authoritative text; the per-file
lines make each file self-describing about its terms.
