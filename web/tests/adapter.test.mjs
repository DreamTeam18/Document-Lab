import test from "node:test";
import assert from "node:assert/strict";
import { chatAdapter, parseSSE } from "../src/core/chat/adapter.ts";
import { applyChatEvent } from "../src/core/chat/reducer.ts";
const body = (text) =>
  new ReadableStream({
    start(c) {
      for (const byte of new TextEncoder().encode(text))
        c.enqueue(new Uint8Array([byte]));
      c.close();
    },
  });
const request = {
  threadId: "browser-id",
  serverThreadId: "server-id",
  documentIds: ["document-id"],
  messages: [
    { role: "user", text: "Old question" },
    { role: "assistant", text: "Old answer" },
    { role: "user", text: "What color?" },
  ],
  files: [],
  settings: { mode: "pro", model: "default" },
};
const frame = (event, data) =>
  `event: ${event}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`;
test("SSE handles byte-split UTF8 and CRLF", async () => {
  const events = [];
  for await (const e of parseSSE(body(frame("result", { answer: "Blue 💙" }))))
    events.push(e);
  assert.equal(events[0].data.answer, "Blue 💙");
});
test("adapter sends only latest question and backend session, maps progress/citations", async () => {
  const old = globalThis.fetch;
  let payload;
  globalThis.fetch = async (url, options) => {
    payload = JSON.parse(options.body);
    return new Response(
      body(
        frame("session", { thread_id: "server-id" }) +
          frame("progress", { step: "retrieve" }) +
          frame("result", {
            answer: "Blue [1]",
            citations: [{ citation: 1, page: 2 }],
            warnings: ["Keyword fallback"],
          }),
      ),
    );
  };
  try {
    const events = [];
    for await (const e of chatAdapter.stream(
      request,
      new AbortController().signal,
    ))
      events.push(e);
    assert.deepEqual(payload, {
      user_query: "What color?",
      document_ids: ["document-id"],
      thread_id: "server-id",
    });
    assert.equal(events[0].type, "session");
    assert.equal(events[1].step.label, "Evidence retrieved");
    assert.equal(events[3].citations[0].page, 2);
    assert.equal(events[3].warnings[0], "Keyword fallback");
  } finally {
    globalThis.fetch = old;
  }
});
for (const [name, response, message] of [
  [
    "HTTP failure",
    () =>
      new Response(JSON.stringify({ detail: "Wrong document selection" }), {
        status: 409,
      }),
    /Wrong document selection/,
  ],
  [
    "stream error",
    () =>
      new Response(body(frame("error", { message: "Provider unavailable" }))),
    /Provider unavailable/,
  ],
  [
    "incomplete stream",
    () => new Response(body(frame("session", { thread_id: "id" }))),
    /connection ended/,
  ],
])
  test(name, async () => {
    const old = globalThis.fetch;
    globalThis.fetch = async () => response();
    try {
      await assert.rejects(async () => {
        for await (const e of chatAdapter.stream(
          request,
          new AbortController().signal,
        )) {
        }
      }, message);
    } finally {
      globalThis.fetch = old;
    }
  });
test("reducer preserves backend session, citations and source selection", () => {
  let t = {
    id: "local",
    documentIds: ["doc"],
    messages: [
      {
        id: "assistant",
        role: "assistant",
        text: "",
        steps: [],
        reasoning: "",
        status: "streaming",
      },
    ],
  };
  t = applyChatEvent(t, "assistant", {
    type: "session",
    serverThreadId: "backend",
  });
  t = applyChatEvent(t, "assistant", {
    type: "sources",
    citations: [{ citation: 1, page: 1 }],
    warnings: [],
  });
  assert.equal(t.serverThreadId, "backend");
  assert.deepEqual(t.documentIds, ["doc"]);
  assert.equal(t.messages[0].citations[0].page, 1);
});
