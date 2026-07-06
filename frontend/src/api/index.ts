// Typed client for the Atlas backend API.
//
// Split by concern into sibling modules; this barrel re-exports them so callers
// keep importing everything from `./api`:
//   search   — live (S2) + local seed search, and the field-picker vocabulary
//   graph    — the paper neighborhood graph, detail hydration, figures
//   agents   — streaming lecture, Q&A, and offline library chat (SSE)
//   sources  — the user's local semantic library (bring-your-own sources)
//   sessions — saved workspaces (graph + transcript)
//   sse      — the shared text/event-stream reader (internal)

export * from './search'
export * from './graph'
export * from './agents'
export * from './sources'
export * from './sessions'
