import type { ChatAdapter } from "./types";
export async function* parseSSE(
  body: ReadableStream<Uint8Array>,
): AsyncGenerator<{ event: string; data: any }> {
  const reader = body.getReader(),
    decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += done
        ? decoder.decode()
        : decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, "\n");
      let index;
      while ((index = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, index);
        buffer = buffer.slice(index + 2);
        const lines = frame.split("\n");
        const raw = lines
          .filter((l) => l.startsWith("data:"))
          .map((l) => l.slice(5).trimStart())
          .join("\n");
        if (raw)
          yield {
            event:
              lines
                .find((l) => l.startsWith("event:"))
                ?.slice(6)
                .trim() || "message",
            data: JSON.parse(raw),
          };
      }
      if (done) break;
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
export const chatAdapter: ChatAdapter = {
  async *stream(request, signal) {
    const last = request.messages.at(-1);
    if (!last || last.role !== "user") throw new Error("Enter a question.");
    const response = await fetch("/api/rag/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_query: last.text,
        document_ids: request.documentIds,
        thread_id: request.serverThreadId || null,
      }),
      signal: AbortSignal.any([signal, AbortSignal.timeout(250000)]),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : `Request failed (${response.status}).`,
      );
    }
    if (!response.body) throw new Error("Streaming is unavailable.");
    let complete = false;
    let streamed = false;
    const labels: Record<string, string> = {
      triage: "Request routed",
      conversational: "Response prepared",
      plan: "Search planned",
      hyde: "Retrieval hints prepared",
      retrieve: "Evidence retrieved",
      assess: "Evidence checked",
      refine: "Search refined",
      answer: "Answer prepared",
    };
    for await (const { event, data } of parseSSE(response.body)) {
      if (event === "session")
        yield { type: "session", serverThreadId: data.thread_id };
      if (event === "progress")
        yield {
          type: "step",
          step: {
            id: data.step,
            kind: "search",
            label: labels[data.step] || data.step,
            status: "complete",
          },
        };
      if (event === "token" && typeof data.delta === "string") {
        streamed = true;
        yield { type: "text", delta: data.delta };
      }
      if (event === "error") throw new Error(data.message || "Query failed.");
      if (event === "result") {
        complete = true;
        // Final validated text is authoritative: replace drafts, never append twice.
        if (streamed) yield { type: "text-replace", text: data.answer };
        else yield { type: "text", delta: data.answer };
        yield {
          type: "sources",
          citations: data.citations || [],
          warnings: data.warnings || [],
        };
      }
    }
    if (!complete)
      throw new Error(
        "The connection ended before an answer arrived. Try again.",
      );
  },
};
