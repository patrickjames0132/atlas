/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * The lecture beats: click one to light its papers on the graph, click the
 * active one again to clear. A beat may carry a real paper figure — rendered
 * inline, click to enlarge.
 *
 * **A beat is only a control while its papers are loaded.** A lecture lives in
 * the transcript, the transcript outlives the graph it was told over, and so a
 * beat is routinely read with none of its papers on screen. Clicking one then
 * lights nothing, which is the same dead pointer the inline `[n]` chips grey
 * out for and the same rule the answer bubble follows (`Teacher.tsx`, the
 * `clickable` gate): at least one of the beat's papers has to be there.
 * Partial overlap still counts — lighting the ones that *are* present is
 * useful.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

import type { AnswerFigure, Beat, SourceRef } from '../../api'
import MathText from '../../notation/MathText'
import FigCard from '../figures/FigCard'
import AnswerMarkdown from './AnswerMarkdown'

/**
 * Adapt a beat's figure to the shape FigCard/Lightbox render.
 *
 * @param figure The beat's attached figure.
 * @returns The same figure as an `AnswerFigure`.
 */
const asAnswerFigure = (figure: NonNullable<Beat['figure']>): AnswerFigure => ({
  image: figure.image,
  caption: figure.caption,
  title: figure.title ?? null,
  figure: figure.number,
})

/**
 * Render the lecture's beats.
 *
 * @returns The beat cards, papers lighting up on click.
 */
export default function BeatList({
  beats,
  activeBeat,
  sourceRefs,
  onBeatClick,
  onRefClick,
  onEnlarge,
}: {
  beats: Beat[]
  activeBeat: number | null
  /** The lecture's `[Sn]` index → source map, shared by every beat (they all
   *  cite the same retrieved library). */
  sourceRefs?: Record<string, SourceRef>
  onBeatClick: (index: number, beat: Beat) => void
  /** Spotlight one paper from a clicked inline `[n]` marker in a beat. */
  onRefClick?: (nodeId: string) => void
  /** Paper ids still on the graph; a beat (and a `[n]`) outside it greys out.
   *  Undefined means "don't check" — every beat stays a control, which is the
   *  right way round for a caller that forgets to pass the set. */
  onEnlarge: (figure: AnswerFigure) => void
}) {
  if (beats.length === 0) return null
  return (
    <ol className="beats">
      {beats.map((beat, index) => {
        // Note this also covers a beat with **no** papers at all: there is
        // nothing for it to light, so it stops pretending to be a button.
        const lightable = beat.node_ids.length > 0
        return (
          <li
            key={index}
            className={`beat ${activeBeat === index ? 'active' : ''}${lightable ? '' : ' stale'}`}
            onClick={lightable ? () => onBeatClick(index, beat) : undefined}
            title={
              lightable ? undefined : 'None of this beat’s papers are on the graph currently open'
            }
          >
            {beat.heading && (
              <div className="beat-heading">
                <MathText>{beat.heading}</MathText>
              </div>
            )}
            <AnswerMarkdown
              text={beat.text}
              graphRefs={beat.graph_refs}
              sourceRefs={sourceRefs}
              onRefClick={onRefClick}
            />
            {beat.figure && (
              // Enlarging the figure must not toggle the beat's highlight.
              <div onClick={(event) => event.stopPropagation()}>
                <FigCard figure={asAnswerFigure(beat.figure)} onEnlarge={onEnlarge} />
              </div>
            )}
            {beat.node_ids.length > 0 && (
              // The ✦ is the affordance, not the count — it marks "click to
              // light these". A stale beat keeps the count (it really is about
              // two papers) and drops the mark, the same way a stale `[n]` keeps
              // its number and loses its chip.
              <div className="beat-nodes">
                {beat.node_ids.length} paper{beat.node_ids.length > 1 ? 's' : ''}
                {lightable ? ' ✦' : ''}
              </div>
            )}
          </li>
        )
      })}
    </ol>
  )
}
