import { expect, it } from "vitest";
import { persistedThread, WEB_NOT_RETAINED, safeWebUrl } from "@/core/chat/privacy";
import type { ChatThread } from "@/core/chat/types";

const url = "https://example.org/private-sentinel";
function thread(): ChatThread {
  return { id: "t", title: "Question", documentIds: ["d"], todos: [], updatedAt: 1, messages: [{
    id: "a", role: "assistant", status: "complete", text: "External excerpt " + url,
    reasoning: url, warnings: [url], steps: [], webRequested: true,
    citations: [{ source_type: "web", citation: 2, title: "Source", url, retrieved_at: "today" }],
    persistedAnswer: "Document answer [1]. " + WEB_NOT_RETAINED,
    persistedCitations: [{ citation: 1, document_id: "d", document_title: "Manual", edition: "v1", number: "1", kind: "section" }],
  }] };
}
it("retains safe document answer but no web URL or excerpt in stored thread", () => {
  const t = thread(), snapshot = structuredClone(t), stored = persistedThread(t);
  expect(JSON.stringify(stored)).not.toContain(url);
  expect(JSON.stringify(stored)).not.toContain("External excerpt");
  expect(stored.messages[0].text).toContain("Document answer");
  expect(t).toEqual(snapshot);
});
it.each(["streaming", "error", "stopped"] as const)("does not persist %s web drafts", status => {
  const t = thread(), m = t.messages[0];
  if (m.role === "assistant") { m.status = status; delete m.persistedAnswer; }
  expect(persistedThread(t).messages[0].text).toBe(WEB_NOT_RETAINED);
});
it("strips URLs accidentally placed in the persistence payload", () => {
  const t = thread(), m = t.messages[0];
  if (m.role === "assistant") m.persistedAnswer = url;
  expect(JSON.stringify(persistedThread(t))).not.toContain(url);
});
it.each(["javascript:alert(1)", "file:///etc/passwd", "https://u:p@example.org", "not a URL"])("rejects unsafe link %s", url => {
  expect(safeWebUrl(url)).toBe(false);
});
it("permits public HTTPS links", () => expect(safeWebUrl(url)).toBe(true));
