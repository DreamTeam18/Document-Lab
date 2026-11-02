"use client";

import { nanoid } from "nanoid";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { toast } from "sonner";

import { site } from "@/config/site";

import { chatAdapter } from "./adapter";

import {
  applyChatEvent,
  finishAssistantMessage,
  updateAssistantMessage,
} from "./reducer";
import type { ChatMessage, ChatSettings, ChatThread } from "./types";

const THREADS_KEY = "document-lab.threads";
const SETTINGS_KEY = "document-lab.settings";

const DEFAULT_SETTINGS: ChatSettings = {
  mode: "pro",
  model: site.chat.models[0]!.name,
};

type SendInput = {
  threadId: string;
  text: string;
  files: File[];
};

type ChatStore = {
  /** False until browser storage has been read, on the client only. */
  ready: boolean;
  documents: { id: string; title: string; edition: string }[];
  selectedIds: string[];
  setSelectedIds: (ids: string[]) => void;
  refreshDocuments: () => Promise<void>;
  documentsError: string;
  threads: ChatThread[];
  settings: ChatSettings;
  setSettings: (settings: ChatSettings) => void;
  isStreaming: (threadId: string) => boolean;
  send: (input: SendInput) => void;
  stop: (threadId: string) => void;
};

const ChatStoreContext = createContext<ChatStore | null>(null);

export function useChatStore() {
  const store = useContext(ChatStoreContext);
  if (!store) {
    throw new Error("useChatStore must be used within ChatStoreProvider");
  }
  return store;
}

function readJson<T>(key: string): T | undefined {
  try {
    const value = localStorage.getItem(key);
    return value ? (JSON.parse(value) as T) : undefined;
  } catch {
    return undefined;
  }
}

function writeJson(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage may be full or blocked; the session still works in memory.
  }
}

function titleFromPrompt(text: string) {
  return text.length > 60 ? `${text.slice(0, 60).trimEnd()}…` : text;
}

/** A reload cannot resume a stream, so a saved running turn reads as stopped. */
function settleInterruptedTurn(thread: ChatThread): ChatThread {
  return {
    ...thread,
    messages: thread.messages.map((message) =>
      message.role === "assistant" && message.status === "streaming"
        ? finishAssistantMessage(message, "stopped", 0)
        : message,
    ),
  };
}

export function ChatStoreProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [documents, setDocuments] = useState<
    { id: string; title: string; edition: string }[]
  >([]);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [documentsError, setDocumentsError] = useState("");
  const refreshDocuments = useCallback(async () => {
    try {
      const r = await fetch("/api/rag/documents", {
        signal: AbortSignal.timeout(20000),
      });
      if (!r.ok)
        throw new Error("Cannot load documents. Check the backend connection.");
      setDocuments(await r.json());
      setDocumentsError("");
    } catch (e) {
      setDocumentsError(
        e instanceof Error ? e.message : "Unable to load documents.",
      );
    }
  }, []);
  useEffect(() => {
    void refreshDocuments();
  }, [refreshDocuments]);
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [streamingIds, setStreamingIds] = useState<ReadonlySet<string>>(
    new Set(),
  );
  const controllers = useRef(new Map<string, AbortController>());
  const threadsRef = useRef(threads);
  threadsRef.current = threads;

  useEffect(() => {
    const saved = readJson<ChatThread[]>(THREADS_KEY) ?? [];
    const restored = saved.map(settleInterruptedTurn);
    setThreads(restored);
    const savedSettings = readJson<Partial<ChatSettings>>(SETTINGS_KEY);
    setSettings((current) => ({ ...current, ...savedSettings }));
    setReady(true);
  }, []);

  // Saved between turns rather than on every streamed token.
  useEffect(() => {
    if (ready && streamingIds.size === 0) {
      writeJson(THREADS_KEY, threads);
    }
  }, [ready, streamingIds, threads]);

  useEffect(() => {
    if (ready) writeJson(SETTINGS_KEY, settings);
  }, [ready, settings]);

  const updateThread = useCallback(
    (threadId: string, update: (thread: ChatThread) => ChatThread) => {
      setThreads((current) =>
        current.map((thread) =>
          thread.id === threadId ? update(thread) : thread,
        ),
      );
    },
    [],
  );

  const stop = useCallback((threadId: string) => {
    controllers.current.get(threadId)?.abort();
  }, []);

  const send = useCallback(
    ({ threadId, text, files }: SendInput) => {
      if (controllers.current.has(threadId)) return;

      const userMessage: ChatMessage = {
        id: nanoid(),
        role: "user",
        text,
        files: files.map((file) => file.name),
      };
      const assistantId = nanoid();
      const existing = threadsRef.current.find(
        (thread) => thread.id === threadId,
      );
      const documentIds = existing?.documentIds ?? selectedIds;
      if (!documentIds.length) {
        toast.error("Select a document in the sidebar before sending.");
        throw new Error("Select a document first.");
      }
      if (text.length > 4000) {
        toast.error("Questions can contain up to 4,000 characters.");
        throw new Error("Question too long");
      }
      const messages = [...(existing?.messages ?? []), userMessage];

      setThreads((current) => {
        const next: ChatThread = {
          id: threadId,
          documentIds,
          serverThreadId: existing?.serverThreadId,
          title: existing?.title ?? titleFromPrompt(text),
          todos: [],
          updatedAt: Date.now(),
          messages: [
            ...messages,
            {
              id: assistantId,
              role: "assistant",
              reasoning: "",
              steps: [],
              text: "",
              status: "streaming",
            },
          ],
        };
        return [next, ...current.filter((thread) => thread.id !== threadId)];
      });

      const controller = new AbortController();
      controllers.current.set(threadId, controller);
      setStreamingIds((current) => new Set(current).add(threadId));
      const startedAt = Date.now();

      const finish = (status: "complete" | "stopped" | "error") => {
        const durationSeconds = Math.round((Date.now() - startedAt) / 1000);
        updateThread(threadId, (thread) =>
          updateAssistantMessage(thread, assistantId, (message) =>
            finishAssistantMessage(message, status, durationSeconds),
          ),
        );
        controllers.current.delete(threadId);
        setStreamingIds((current) => {
          const next = new Set(current);
          next.delete(threadId);
          return next;
        });
      };

      void (async () => {
        try {
          const events = chatAdapter.stream(
            {
              threadId,
              messages,
              files,
              settings,
              documentIds,
              serverThreadId: existing?.serverThreadId,
            },
            controller.signal,
          );
          for await (const event of events) {
            updateThread(threadId, (thread) =>
              applyChatEvent(thread, assistantId, event),
            );
          }
          finish("complete");
        } catch (error) {
          if (controller.signal.aborted) {
            finish("stopped");
            return;
          }
          const detail =
            error instanceof Error
              ? error.message
              : "The response failed. Try again.";
          toast.error(detail);
          updateThread(threadId, (thread) =>
            updateAssistantMessage(thread, assistantId, (message) => ({
              ...message,
              error: detail,
            })),
          );
          finish("error");
        }
      })();
    },
    [settings, updateThread, selectedIds],
  );

  const isStreaming = useCallback(
    (threadId: string) => streamingIds.has(threadId),
    [streamingIds],
  );

  const value = useMemo(
    () => ({
      ready,
      documents,
      selectedIds,
      setSelectedIds,
      refreshDocuments,
      documentsError,
      threads,
      settings,
      setSettings,
      isStreaming,
      send,
      stop,
    }),
    [
      ready,
      threads,
      settings,
      isStreaming,
      send,
      stop,
      documents,
      selectedIds,
      refreshDocuments,
      documentsError,
    ],
  );

  return (
    <ChatStoreContext.Provider value={value}>
      {children}
    </ChatStoreContext.Provider>
  );
}
