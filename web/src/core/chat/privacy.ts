import type { ChatThread, Citation } from "./types";

export const WEB_NOT_RETAINED = "From the web: web response and source links not retained. Search again to verify.";
export function stripUrls(text: string) {
  return text.replace(/(?:https?:\/\/|www\.)[^\s<>\]"']+/gi, "[link not retained]");
}
export function safeWebUrl(value: string): boolean {
  try {
    const u = new URL(value);
    return ["https:", "http:"].includes(u.protocol) && !u.username && !u.password
      && !/[\s\\]/.test(value);
  } catch { return false; }
}
function documentCitations(citations: Citation[] = []): Citation[] {
  return citations.filter(c => c.source_type !== "web").map(c =>
    Object.fromEntries(Object.entries(c).filter(([k]) => !["url", "text", "excerpt"].includes(k))
      .map(([k, v]) => [k, typeof v === "string" ? stripUrls(v) : v])) as Citation);
}
/** Build a separate persistence object; never mutate the current live response. */
export function persistedThread(thread: ChatThread): ChatThread {
  return {
    ...thread,
    title: stripUrls(thread.title),
    messages: thread.messages.map(message => {
      if (message.role === "user") return { ...message, text: stripUrls(message.text) };
      const { persistedAnswer, persistedCitations, ...rest } = message;
      if (message.webRequested) return {
        ...rest,
        text: stripUrls(persistedAnswer ?? WEB_NOT_RETAINED),
        citations: documentCitations(persistedCitations),
        reasoning: "", warnings: [], error: message.error ? "Web response was interrupted." : undefined,
        steps: message.steps.map(s => ({ ...s, label: stripUrls(s.label), results: undefined })),
      };
      return { ...rest, text: stripUrls(message.text), citations: documentCitations(message.citations) };
    }),
  };
}
