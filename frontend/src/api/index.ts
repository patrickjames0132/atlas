// Typed client for the arXiv Atlas backend API.
//
// Split by concern into sibling modules; this barrel re-exports them so callers
// keep importing everything from `./api`:
//   search   — arXiv + local seed search
//   graph    — the paper neighborhood graph, detail hydration, figures
//   teacher  — streaming lecture, Q&A, and offline library chat
//   sources  — the user's local semantic library (bring-your-own sources)
//   sessions — saved workspaces (graph + transcript)
//   sse      — the shared text/event-stream reader (internal)

export * from './search'
export * from './graph'
export * from './teacher'
export * from './sources'
export * from './sessions'
