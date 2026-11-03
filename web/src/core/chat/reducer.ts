import type { AssistantMessage, ChatEvent, ChatThread } from "./types";

/** Applies one event to the thread's trailing assistant message. */
export function applyChatEvent(
  thread: ChatThread,
  messageId: string,
  event: ChatEvent,
): ChatThread {
  if (event.type === "session")
    return { ...thread, serverThreadId: event.serverThreadId };
  if (event.type === "title") {
    return { ...thread, title: event.title };
  }
  if (event.type === "todos") {
    return { ...thread, todos: event.todos };
  }
  return updateAssistantMessage(thread, messageId, (message) => {
    switch (event.type) {
      case "sources":
        return {
          ...message,
          citations: event.citations,
          warnings: event.warnings,
        };
      case "reasoning":
        return { ...message, reasoning: message.reasoning + event.delta };
      case "text-replace":
        return { ...message, text: event.text };
      case "text":
        return { ...message, text: message.text + event.delta };
      case "step": {
        const exists = message.steps.some((step) => step.id === event.step.id);
        return {
          ...message,
          steps: exists
            ? message.steps.map((step) =>
                step.id === event.step.id ? event.step : step,
              )
            : [...message.steps, event.step],
        };
      }
    }
  });
}

export function updateAssistantMessage(
  thread: ChatThread,
  messageId: string,
  update: (message: AssistantMessage) => AssistantMessage,
): ChatThread {
  return {
    ...thread,
    messages: thread.messages.map((message) =>
      message.id === messageId && message.role === "assistant"
        ? update(message)
        : message,
    ),
  };
}

/** Ends a turn, settling anything a stopped stream left marked as running. */
export function finishAssistantMessage(
  message: AssistantMessage,
  status: AssistantMessage["status"],
  durationSeconds: number,
): AssistantMessage {
  return {
    ...message,
    status,
    durationSeconds,
    steps: message.steps.map((step) =>
      step.status === "active"
        ? { ...step, status: status === "error" ? "failed" : status === "stopped" ? "stopped" : "complete" }
        : step,
    ),
  };
}
