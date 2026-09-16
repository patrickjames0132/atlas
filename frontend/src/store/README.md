# `src/store`

The store separates an exploration, its threads, and the workspace currently
on screen. A thread owns one graph (or no graph for General) and one transcript.
Opening another graph changes the active thread; it never replaces the graph
beneath an unrelated conversation. This deliberately reverses v7.10.0: the
continuity that release protected now belongs to the parent exploration.

## Ownership and navigation

`explorations.ts` owns the parent records, thread order and names, summaries,
and parked workspace states. General is created with each exploration and keeps
its name. A graph thread's identity is provider + resolved seed id, so returning
to the same paper reuses its thread, while identical ids from different providers
cannot collide. The seed title supplies the initial thread name; users can rename it.

`workspace.ts` holds the active graph, discoveries, selections, layout and view
filters. `threadActivated` parks the outgoing state and restores the incoming
state in one action, also handled by `transcript.ts` and `highlight.ts`.
Two scope fields for `scope/resolve.ts`'s priority list: `visibleNodeIds` is
the papers **passing the view filters** (published by `GraphExplorer` from
its eligible set, never the drawn one), the default; `selectedNodeIds` is
the selection, which outranks the filters and is saved with the thread —
written by the reader's hand and by a message that chose its own scope
(`useConversation.send` makes that scope the selection, permanently; there
is no separate per-turn scope state). `selectScope` resolves the two rungs
for the panel's readouts. The v7.23.0 `revealedNodeIds` is gone: a scoped
paper the filters hide is drawn by the canvas *because* it is selected,
derived rather than stored.
`loadGraph` resolves aliases before creating a thread. Refresh and display
changes stay with the current thread. A response from a superseded graph load
cannot navigate back over a newer user choice.

Only serializable data belongs here. The force simulation still owns its mutable
node positions, velocities and links. A canvas remount restores its graph and
filter state, but recalculates physics; coordinates are not saved.

## Conversations and streaming

`transcript.ts` keys conversations by thread id. Every stream captures that id
before starting and dispatches to it explicitly. A background answer continues
writing to its own conversation. Its discoveries wait in `pendingDiscoveries`
until the thread is displayed; they also participate in saves while it is away.
Deleting an exploration drops every owned conversation, so late events have
nowhere to land.

A turn begins with `unfinished: true`; only a successful terminal response
clears that flag. Partial answers remain readable but do not become model history.
Lectures live in `ChatMsg.beats`, not in a separate lecture slot. `teacher/history.ts`
converts completed prose and beats into model history and strips figure markers.
The same conversion is used for normal sends, retries and borrowed discussion.

## Persistence and migration

`threadPersistence.ts` writes a versioned exploration container containing thread
records. Each thread reuses `SessionData`: its chat, graph reference, discoveries,
layout, filters and selected ids. Parked simulation state is omitted. The graph
is rebuilt from its reference on a cold reopen, while agent discoveries are
stored because no provider rebuild could reproduce them. A failed rebuild must
not erase the only saved reference.

A legacy save becomes one exploration. Assistant graph stamps determine the
thread by seed + provider (falling back to the save's provider); the preceding
user turn travels with its answer. Unstamped turns stay with the save's own seed,
or General when it had none. Legacy standalone lectures and citation-field
aliases are retained. Migration happens in memory on load; opening a saved
exploration does not itself rewrite its blob.

`shell/useExplorations.ts` owns the autosave and navigation orchestration.
`shell/saveQueue.ts` orders whole-exploration writes and retains an unacknowledged
snapshot in a local browser outbox before awaiting the server. The outbox is
cleared only when that exact snapshot is acknowledged, and is replayed on the
next launch. SQLite remains the durable store.

## Other shared state and selectors

`library.ts` loads uploaded sources once and refreshes after source operations.
`highlight.ts` contains serializable paper ids and clears on navigation.
`selectScope` replaced `selectGroundingNodes`/`selectLectureNodes` in v7.24.0
(they intersected the selection with the visible set and kept hidden
discoveries for the researcher only); the one rule now lives in
`scope/resolve.ts`, and filters decide only the default scope. Paper
citations highlight their node on the canvas.

## Verification

`test/store/threads.test.ts` covers graph identity, General, selection restoration,
background token ownership, migration and serialization. Transcript tests cover
the keyed stream reducers. Shell tests cover write ordering, teardown recovery,
read-only legacy opening, deletion and preserving names. Build with `npm run build`
and run the offline suite with `npm test`.
