/**
 * The ForceGraph2D wrapper: all canvas painting for the explorer — node
 * fills by relation, the dim/highlight/pin/selection rings, dashed
 * "discovered" markers, node labels, edge colors/arrows, and pointer areas.
 *
 * Purely presentational: the simulation's node/link objects, the fgRef, and
 * every piece of interaction state live in GraphExplorer and arrive as props.
 * The one rule this component must respect is object identity — `data` is
 * the live view whose nodes RFG mutates (x/y/fx/fy), so nothing here may
 * copy or recreate them.
 */

import ForceGraph2DImport from 'react-force-graph-2d'
import type { GraphNode } from '../../api'
import { latexToUnicode } from '../../notation/latexToUnicode'
import { nodeRadius, primaryRel } from '../model'
import type { VLink, VNode } from '../model'
import { DIM_EDGE, DIM_NODE, EDGE_COLOR, REL_COLOR, SELECTION_RING } from '../theme'

// The lib's generic prop typings fight our accessor signatures; render via an
// untyped alias so our canvas/link callbacks stay readable.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const ForceGraph2D = ForceGraph2DImport as any

/** Props for {@link GraphCanvas}. */
export interface GraphCanvasProps {
  /** The ForceGraph2D instance ref, owned by GraphExplorer (reheat/zoom/forces). */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  fgRef: { current: any }
  /** Canvas dimensions (tracked by GraphExplorer's ResizeObserver). */
  width: number
  height: number
  /** The filtered live view — node objects the sim mutates; do not copy. */
  data: { nodes: VNode[]; links: VLink[] }
  /** Nodes in focus (hover neighborhood or teacher highlights); null = no dimming. */
  focusSet: Set<string> | null
  /** User-pinned node ids (drawn with a pale ring). */
  pinned: Set<string>
  /** The selected node id (bright ring + always-on label). */
  selectedId: string | null
  /** Hand-picked nodes scoping the teacher (cyan ring; others dim). */
  selectedIds: Set<string>
  /** Nodes the teacher is currently talking about (gold glow + ring). */
  highlightIds: Set<string>
  /** Select / re-seed handler (single vs. quick double click); the DOM event
   *  carries the shift modifier used for add/remove selection. */
  onNodeClick: (node: VNode, event?: MouseEvent) => void
  /** Hover handler — receives the node id, or null when leaving. */
  onNodeHover: (id: string | null) => void
  /** Drag-release handler (pins the node where it was dropped). */
  onNodeDragEnd: (node: VNode) => void
  /** Sim-settled handler (timeline y-freeze + one-shot zoomToFit). */
  onEngineStop: () => void
  /** Pre-frame painter (the timeline year axis). */
  onRenderFramePre: (ctx: CanvasRenderingContext2D, globalScale: number) => void
}

/**
 * Render the force-directed graph canvas.
 *
 * @returns The configured ForceGraph2D element.
 */
export default function GraphCanvas({
  fgRef,
  width,
  height,
  data,
  focusSet,
  pinned,
  selectedId,
  selectedIds,
  highlightIds,
  onNodeClick,
  onNodeHover,
  onNodeDragEnd,
  onEngineStop,
  onRenderFramePre,
}: GraphCanvasProps) {
  return (
    <ForceGraph2D
      ref={fgRef}
      width={width}
      height={height}
      graphData={data}
      backgroundColor="#0f1115"
      nodeLabel={(node: GraphNode) =>
        `${latexToUnicode(node.title)}${node.year ? ` (${node.year})` : ''}`
      }
      nodeRelSize={1}
      onNodeClick={onNodeClick}
      onNodeHover={(node: VNode | null) => onNodeHover(node ? node.id : null)}
      onNodeDragEnd={onNodeDragEnd}
      onEngineStop={onEngineStop}
      onRenderFramePre={onRenderFramePre}
      cooldownTicks={120}
      linkColor={(link: VLink) =>
        focusSet && !focusSet.has(link._s) && !focusSet.has(link._t)
          ? DIM_EDGE
          : EDGE_COLOR[link.type]
      }
      linkWidth={(link: { influential?: boolean | null }) => (link.influential ? 1.6 : 0.6)}
      linkDirectionalArrowLength={(link: VLink) => (link.type === 'similar' ? 0 : 2.4)}
      linkDirectionalArrowRelPos={1}
      nodeCanvasObject={(
        node: VNode & { x: number; y: number },
        ctx: CanvasRenderingContext2D,
        globalScale: number,
      ) => {
        const radius = nodeRadius(node)
        // A hand-picked selection dims everything outside it (like focus), on
        // top of any hover/highlight dimming, so the scoped cluster stands out.
        const hasSelection = selectedIds.size > 0
        const dim =
          (focusSet ? !focusSet.has(node.id) : false) || (hasSelection && !selectedIds.has(node.id))
        const isPicked = selectedIds.has(node.id)
        const isPinned = pinned.has(node.id)
        const isSel = selectedId === node.id
        const isLit = highlightIds.has(node.id)

        // Glow behind papers the teacher is highlighting.
        if (isLit && !dim) {
          ctx.beginPath()
          ctx.arc(node.x, node.y, radius + 5, 0, 2 * Math.PI)
          ctx.fillStyle = 'rgba(255,209,102,0.22)'
          ctx.fill()
        }
        ctx.beginPath()
        ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI)
        ctx.fillStyle = dim ? DIM_NODE : REL_COLOR[primaryRel(node)]
        ctx.fill()
        if (node.discovered && !dim) {
          // Dashed ring marks a paper the AI teacher pulled in mid-chat. Its
          // own path, just outside the fill: stroking the fill's arc buried
          // half the line under the disc, which is why the old 1.2-width ring
          // was so easy to miss.
          ctx.beginPath()
          ctx.arc(node.x, node.y, radius + 1.5, 0, 2 * Math.PI)
          ctx.lineWidth = 2 / globalScale
          ctx.strokeStyle = 'rgba(242,244,248,0.9)'
          ctx.setLineDash([3 / globalScale, 2 / globalScale])
          ctx.stroke()
          ctx.setLineDash([])
          // Restore the fill's arc as the current path — the lit/pinned/
          // selected rings below stroke it.
          ctx.beginPath()
          ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI)
        }
        if (isLit && !dim) {
          ctx.lineWidth = 2 / globalScale
          ctx.strokeStyle = '#ffd166'
          ctx.stroke()
        }
        if (isPinned && !dim) {
          ctx.lineWidth = 1.5 / globalScale
          ctx.strokeStyle = 'rgba(242,244,248,0.55)'
          ctx.stroke()
        }
        if (isPicked && !dim) {
          // Cyan ring marks a node hand-picked into the teacher's scope. Drawn
          // just outside the fill so it coexists with a pin/select/lit ring.
          ctx.beginPath()
          ctx.arc(node.x, node.y, radius + 2.5, 0, 2 * Math.PI)
          ctx.lineWidth = 2 / globalScale
          ctx.strokeStyle = SELECTION_RING
          ctx.stroke()
        }
        if (isSel) {
          ctx.lineWidth = 2 / globalScale
          ctx.strokeStyle = '#f2f4f8'
          ctx.stroke()
        }
        if (!dim && (node.is_seed || isSel || isLit || isPicked || globalScale > 1.6)) {
          const fontSize = Math.max(11 / globalScale, 2)
          ctx.font = `${fontSize}px -apple-system, sans-serif`
          ctx.textAlign = 'center'
          ctx.textBaseline = 'top'
          ctx.fillStyle = 'rgba(231,236,245,0.9)'
          const title = latexToUnicode(node.title)
          ctx.fillText(
            title.length > 42 ? title.slice(0, 40) + '…' : title,
            node.x,
            node.y + radius + 1,
          )
        }
      }}
      nodePointerAreaPaint={(
        node: VNode & { x: number; y: number },
        color: string,
        ctx: CanvasRenderingContext2D,
      ) => {
        ctx.fillStyle = color
        ctx.beginPath()
        ctx.arc(node.x, node.y, nodeRadius(node) + 2, 0, 2 * Math.PI)
        ctx.fill()
      }}
    />
  )
}
