/**
 * Copyright (c) 2026 Charles Patrick James <charles.patrick.james@gmail.com>. MIT License — see LICENSE.
 *
 * Description:
 * Shared Server-Sent-Events reader for the streaming teacher endpoints.
 *
 * The lecture / ask / ask_sources endpoints are POSTs that answer with
 * `text/event-stream`, so the browser's native EventSource (GET-only) can't
 * consume them — this hand-rolled reader decodes the frames instead.
 *
 * Authors:
 * Charles Patrick James <charles.patrick.james@gmail.com>
 */

/**
 * Read a `text/event-stream` POST response, dispatching each frame to
 * `onEvent` as `(eventName, parsedData)`.
 *
 * Frames are separated by a blank line; each frame carries `event:` and
 * `data:` lines per the SSE wire format. `data` payloads are JSON-parsed
 * before dispatch, and malformed frames are silently skipped so one bad
 * frame never kills the stream.
 *
 * @param res     A fetch Response whose body is an SSE stream.
 * @param onEvent Called once per frame with the event name (default
 *                `"message"`) and the parsed JSON payload.
 * @throws When the response is not ok or has no body — the error message is
 *         taken from the JSON `error` field when the server provided one.
 */
export async function readSSE(
  res: Response,
  onEvent: (event: string, data: unknown) => void,
): Promise<void> {
  if (!res.ok || !res.body) {
    const data = await res.json().catch(() => ({}))
    throw new Error((data as { error?: string }).error || `Request failed (${res.status})`)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let sep: number
    // Frames are separated by a blank line.
    while ((sep = buf.indexOf('\n\n')) !== -1) {
      const frame = buf.slice(0, sep)
      buf = buf.slice(sep + 2)
      let event = 'message'
      let data = ''
      for (const line of frame.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      if (!data) continue
      try {
        onEvent(event, JSON.parse(data))
      } catch {
        /* ignore malformed frame */
      }
    }
  }
}
