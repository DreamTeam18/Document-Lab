# Frontend adaptation and validation

## What the sample actually does

Inspected `DESIGN.md`, `src/config/site.ts`, landing components, OGL Galaxy shaders,
FlickeringGrid, MagicBento, render-activity observers, chat store/reducer/adapter,
composer, sidebar, and Streamdown rendering. Read the installed Next.js route
handler and rewrite documentation before implementing the integration.

- OGL renders a procedural, multi-layer star field with time uniforms and pointer
  interaction. Hero dynamically imports it, disposes GPU resources on unmount,
  and unmounts it when offscreen, document-hidden, or reduced-motion is requested.
  The shader has an unavailable-WebGL fallback; we retain a CSS background.
- Canvas grid creates the masked silhouette. Replaced the deer with a document
  mask and connected the grid to the same visibility/reduced-motion observer.
- Motion drives rotating headline and transition states. Our interactive examples
  are original RAG scenarios with selectable tabs, pause/play, and stage controls.
  Timers pause offscreen, on hidden tabs, and for reduced motion. Static answers
  remain visible with reduced motion. Examples are explicitly fictional illustrations.
- MagicBento supplies spotlight/particle interactions and responsive feature cards.
  Feature copy now describes implemented RAG capabilities rather than code agents.
- Semantic tokens, Radix overlays, collapsible sidebar, system/light/dark themes,
  Streamdown Markdown with raw HTML disabled, copy buttons, scroll-to-bottom, and
  tool progress are retained from the sample instead of imitated with static HTML.

## Backend integration

`/api/rag/[...path]` allows only the RAG endpoints and streams requests/responses
through to `RAG_BACKEND_URL` (default `http://127.0.0.1:8001`). Provider keys never
enter Next.js client code. The adapter sends the latest question, selected UUIDs,
and backend conversation UUID, not the whole browser transcript. SSE session,
progress, result, and error events map onto the sample's reducer. Citations and
warnings are stored and rendered separately from answer Markdown. An incomplete
stream fails visibly. No fake tokens or reasoning are generated.

Documents load from PostgreSQL. File uploads use the existing extraction/indexing
API with an upload deadline; completed uploads refresh the library and select the
new source in a fresh chat. Source selection locks once a conversation starts.
Backend validation remains authoritative. Nonfunctional model/mode choices and
mock conversations were removed from the active interface.

Recent-chat navigation stores a local display copy in this browser, including
server UUIDs, sources, citations and stopped/error states. The backend still saves
completed exchanges in PostgreSQL. This is not cross-device history sync. Closing
a browser stream stops displaying its answer; backend cancellation is not guaranteed.

## Run

From `web`: `npm ci`, `npm run build`, then `npm start` (127.0.0.1:3001).
Run FastAPI separately on 127.0.0.1:8001 with the existing Python environment.
`npm run dev` provides a development server on the same frontend port.
Backend `/` and `/chat` redirect to the new frontend, configurable through
`WEB_FRONTEND_URL`. Old UI remains at `/legacy` and `/legacy/chat` for comparison.
No Docker, Redis, gateway service, or new paid API was introduced. The Next.js
route handler is a same-origin transport inside the frontend, not a separate gateway.

## Scope

Native local deployment is verified. Hosted deployment and large-document proxy
timeouts need separate verification. Scanned PDFs still require OCR. MIT attribution
is in `LICENSE`; unrelated sample photographs are not shipped.

## Verification completed

- Optimized `npm run build` and TypeScript checks pass; `npm start` serves the
  production bundle on localhost:3001.
- Six adapter/reducer tests pass: fragmented UTF-8/CRLF SSE, bounded query payload,
  backend session propagation, citations, HTTP/SSE errors and incomplete responses.
- Existing Python suite: 63 pass, one optional database integration test skipped.
  Existing JavaScript stream parser tests: two pass.
- Eleven browser check groups pass on the production build, covering WebGL/canvas,
  interactive examples, document loading, file chooser, Markdown/citations,
  follow-up UUIDs, restored browser history, themes, mobile sidebar, no horizontal
  overflow at 390/768/1440px, reduced motion and no runtime errors.
- Live browser check: uploaded a small TXT using real OpenRouter embeddings,
  asked a question through the real backend, rendered the answer with citations,
  and verified two persisted messages in PostgreSQL. Test fixtures were removed.
- Production proxy rejects unlisted endpoints and preserves upload-validation
  errors. Its long-upload HTTP dispatcher uses the same Undici implementation as
  its fetch function, avoiding the incompatible built-in fetch/Agent combination
  found during verification. A full 30-minute upload was not exercised.

Repeat browser checks from the repository root:

```sh
uv run --with playwright python -m scripts.check_web_frontend
# Explicitly uses provider credits; removes its own document and conversation:
uv run --with playwright python -m scripts.check_web_live --allow-live
```

The browser scripts currently use the installed macOS Google Chrome executable.
Screenshots and machine-readable browser results are in ignored `.local/` files.
These checks validate the local integration; they do not establish hosted capacity,
cross-device conversation synchronization, or security for a public multi-user app.
