# BUGS.md — notable bugs, found & fixed

A running log of bugs worth remembering — the ones with a non-obvious root
cause, a surprising reproduction, or a lesson that outlives the fix. It is
**not** an issue tracker for open work (that's [OnePager.md](OnePager.md)'s
roadmap and the `todos.md` inbox); every entry here is already **fixed and
shipped**. The point is institutional memory: when a symptom recurs or someone
touches the same code, the story is one grep away instead of buried in a diff.

Keep it newest-first. One entry per bug, with:

- **Symptom** — what was visibly wrong (a screenshot-level description).
- **Root cause** — the actual mechanism, not the surface.
- **Fix** — what changed, and where.
- **Lesson / guard** — what keeps it from coming back (a test, an invariant).

Small, obvious bugs don't need an entry — the commit message is enough. This
file is for the ones you'd want to re-read a year later.

---

## Tripled MathML soup in ar5iv figure captions

*Found & fixed v3.2.0 (2026-07-08), while shipping "Proper subscripts & math
notation".*

- **Symptom.** Figure captions in the detail panel and in the teacher's
  answers rendered as garbled, tripled math — e.g. the Double Q-Learning paper
  (arXiv 1509.06461) showed
  `…the action values are Q(s,a)=V*(s)+eaQsasubscriptVssubscriptitalic-ϵaQ(s,a)=V_{*}(s)+\epsilon_{a} and the errors…`.
  The new frontend KaTeX renderer couldn't help — the caption *string itself*
  was already corrupt, and the LaTeX in it wasn't even `$`-delimited.
- **Root cause.** ar5iv renders each formula as a `<math>` element whose
  children are **three redundant text renderings** of the same formula:
  presentation MathML (`<mi>`, `<msub>`…), a content-MathML / semantic
  annotation (the source of the literal words `subscript`, `superscript`,
  `italic-ϵ`), and a LaTeX annotation. `_FigureParser` in
  `src/atlas/integrations/arxiv/figures.py` stripped tags and accumulated **all
  of it**, concatenating the three into soup. The clean LaTeX was sitting
  unused in each element's `alttext` attribute the whole time.
- **Fix.** `_FigureParser` now tracks `<math>` nesting: on entering the
  outermost `<math>` inside a caption it emits the element's `alttext` wrapped
  in `$…$`, and suppresses the subtree's own text nodes. Captions come out as
  clean, KaTeX-ready `$V_{*}(s)+\epsilon_{a}$`. Covers every figure surface at
  once (detail panel, teacher `FigCard`, lightbox) because they all fetch
  through `get_figures`.
- **Lesson / guard.** When scraping rendered LaTeX (ar5iv/MathJax/KaTeX
  output), prefer the source-carrying attribute (`alttext`, `data-tex`,
  `<annotation encoding="application/x-tex">`) over the visual subtree — the
  subtree is *display* markup, often duplicated for accessibility, and
  text-stripping it is lossy. Two regression tests pin this
  (`test_get_figures_math_becomes_delimited_latex_not_tripled_mathml`,
  `…math_without_alttext_is_dropped_not_garbled`). Note the 30-day figure cache:
  a parser fix doesn't reach already-cached captions until they re-fetch —
  clear `figures:*` from the `cache` table to re-test immediately.
