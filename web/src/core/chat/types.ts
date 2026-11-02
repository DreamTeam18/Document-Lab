export type Citation = {
  citation: number;
  document_id: string;
  document_title: string;
  edition: string;
  number: string;
  kind: string;
  page?: number;
};
export type ChatMode = "flash" | "thinking" | "pro" | "ultra";

export type ChatStepKind = "search" | "fetch" | "bash" | "write";

export type ChatStep = {
  id: string;
  kind: ChatStepKind;
  label: string;
  status: "active" | "complete";
  /** Rendered as small badges under the step, e.g. searched domains. */
  results?: string[];
};

export type ChatTodo = {
  content: string;
  status: "pending" | "in_progress" | "completed";
};

export type UserMessage = {
  id: string;
  role: "user";
  text: string;
  /** Filenames only: file contents are for your adapter, not local storage. */
  files: string[];
};

export type AssistantMessage = {
  id: string;
  role: "assistant";
  reasoning: string;
  citations?: Citation[];
  warnings?: string[];
  error?: string;
  steps: ChatStep[];
  text: string;
  status: "streaming" | "complete" | "stopped" | "error";
  durationSeconds?: number;
};

export type ChatMessage = UserMessage | AssistantMessage;

export type ChatThread = {
  serverThreadId?: string;
  documentIds?: string[];
  id: string;
  title: string;
  messages: ChatMessage[];
  todos: ChatTodo[];
  updatedAt: number;
};

export type ChatSettings = {
  mode: ChatMode;
  model: string;
};

/** One increment of an assistant turn. A backend maps its stream onto these. */
export type ChatEvent =
  | { type: "session"; serverThreadId: string }
  | { type: "sources"; citations: Citation[]; warnings: string[] }
  | { type: "title"; title: string }
  | { type: "reasoning"; delta: string }
  /** Inserts the step, or replaces the existing step with the same id. */
  | { type: "step"; step: ChatStep }
  | { type: "todos"; todos: ChatTodo[] }
  | { type: "text"; delta: string }
  | { type: "text-replace"; text: string };

export type ChatRequest = {
  documentIds: string[];
  serverThreadId?: string;
  threadId: string;
  /** The full conversation, ending with the new user message. */
  messages: ChatMessage[];
  /** The browser files attached to the new user message. */
  files: File[];
  settings: ChatSettings;
};

/**
 * The only seam between the UI and a backend. Implement `stream` against your
 * API and export it from `adapter.ts`. Throw to fail the turn, and stop when
 * `signal` aborts.
 */
export type ChatAdapter = {
  stream: (
    request: ChatRequest,
    signal: AbortSignal,
  ) => AsyncIterable<ChatEvent>;
};
