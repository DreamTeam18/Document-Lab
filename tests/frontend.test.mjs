import test from "node:test";
import assert from "node:assert/strict";
import { readEvents } from "../frontend/stream.js";

test("SSE preserves events and Unicode split across arbitrary network chunks", async () => {
  const text = ': keepalive\r\n\r\nevent: progress\r\ndata: {"step":"retrieve"}\r\n\r\nevent: result\ndata: {"answer":"café ✓"}\n\n';
  const bytes = new TextEncoder().encode(text);
  const stream = new ReadableStream({ start(controller) {
    for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
    controller.close();
  }});
  const events = [];
  await readEvents(stream, (name, data) => events.push([name, data]));
  assert.deepEqual(events, [["progress", { step: "retrieve" }], ["result", { answer: "café ✓" }]]);
});

test("SSE handles multiple events in one chunk and final unterminated frame", async () => {
  const stream = new ReadableStream({ start(controller) {
    controller.enqueue(new TextEncoder().encode('event: session\ndata: {"thread_id":"abc"}\n\nevent: error\ndata: {"message":"missing key"}'));
    controller.close();
  }});
  const events = [];
  await readEvents(stream, (name, data) => events.push([name, data]));
  assert.equal(events.length, 2);
  assert.deepEqual(events[1], ["error", { message: "missing key" }]);
});
