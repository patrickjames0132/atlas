# `src/shell`

The left rail names explorations and nests their threads. `SideBar.tsx` owns the
parent navigation; `SessionRow.tsx` supplies the shared rows and menus; `ThreadList.tsx` shows General and graph
threads beneath the active exploration. A row selects that discussion and its
graph together. The ellipsis opens Rename/Delete, with inline editing after Rename; General
keeps its name. Running conversations show a working indicator even off-screen.

`useSessions.ts` remains the thin server-list CRUD client. `useExplorations.ts`
coordinates that list with the live Redux exploration records. Returning to a
live exploration uses memory, not an older server response. A first server load
passes through the lazy migration in `store/threadPersistence.ts`.

## Saving without losing background work

Each save takes one immutable state snapshot before any await. It includes all
threads of the exploration, not whichever chat happens to be visible when the
network request finishes. The short debounce coalesces streamed changes; a
settled background conversation participates in the same snapshot. Naming runs
independently, so a slow model never delays storing the reader's words. Only the
first substantive request names an exploration, and manual names persist.

`saveQueue.ts` serializes writes per exploration. It records the latest body in a
local outbox synchronously, which covers page closure while an earlier network
request is in flight. An acknowledgement removes only its own exact body, never a
newer pending one. On launch pending bodies are replayed; opening a row waits for
its pending recovery. Deletion stops queued writes, waits for any request already
sent, then removes the row, so autosave cannot resurrect it.

A newly read legacy record establishes an in-memory baseline. It is not written
merely because its graph was rebuilt. New turns, thread navigation, renames and
other saved edits cause subsequent saves in the new format.

## Summaries

A thread is settled when its Redux `running` list is empty. Its completed history
(including lecture prose) feeds `/api/sessions/summary` when it has moved beyond
`summarizedThrough`. The response is accepted only for the transcript length it
read. One attempt per observed length prevents provider failure from creating an
unbounded retry loop. Summaries are persisted with the thread and rolled up into
the exploration's saved summary. They are background context, never substitutes
for the actual transcript.

## Verification

`test/shell/useExplorations.test.ts` exercises the real hook with isolated Redux
stores and stubbed APIs. It covers empty sessions, debounced streams, stable row
identity, one-time naming, delayed naming, background writes, legacy reads and
deletions. `saveQueue.test.ts` covers ordered writes and browser-close recovery.

Explorations and threads share `SessionRow`: identical typography, spacing,
hover controls, Rename/Delete menu and inline name editing (Enter or blur saves;
Escape cancels). General is permanent and has no rename/delete menu. Deleting
an active graph thread returns to General and discards its transcript.

Each exploration has a caret. Only the active, expanded exploration renders
its thread list; a fresh unsaved exploration never appends an orphan General
beneath another session. `SideBar.test.tsx` verifies collapse, new-exploration
navigation, rename and active-thread deletion.
