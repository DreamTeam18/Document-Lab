"use client";

import { PaperclipIcon } from "lucide-react";
import { memo, useMemo } from "react";

import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  Message,
  MessageContent,
  MessageToolbar,
} from "@/components/ai-elements/message";
import {
  ClipboardSafeStreamdown,
  type ClipboardSafeStreamdownProps,
} from "@/components/ai-elements/streamdown";
import {
  rehypeStreamingListItems,
  streamdownPluginsWithoutRawHtml,
  streamdownSmoothStreamingAnimation,
} from "@/core/streamdown/plugins";
import { preprocessStreamdownMarkdown } from "@/core/streamdown/preprocess";
import type {
  AssistantMessage,
  ChatMessage,
  UserMessage,
} from "@/core/chat/types";
import { cn } from "@/lib/utils";

import { CopyButton } from "./copy-button";
import { MessageReasoning } from "./message-reasoning";
import { MessageSteps } from "./message-steps";
import { StreamingIndicator } from "./streaming-indicator";

const TOOLBAR_VISIBILITY =
  "z-20 opacity-0 transition-opacity delay-200 duration-300 group-hover/conversation-message:opacity-100 focus-within:opacity-100";

function Markdown({
  content,
  isLoading,
}: {
  content: string;
  isLoading: boolean;
}) {
  const rehypePlugins = useMemo(
    () =>
      [
        ...(streamdownPluginsWithoutRawHtml.rehypePlugins ?? []),
        ...(isLoading ? [rehypeStreamingListItems] : []),
      ] as ClipboardSafeStreamdownProps["rehypePlugins"],
    [isLoading],
  );
  const normalized = useMemo(
    () => preprocessStreamdownMarkdown(content),
    [content],
  );
  return (
    <ClipboardSafeStreamdown
      {...streamdownPluginsWithoutRawHtml}
      className="my-3"
      rehypePlugins={rehypePlugins}
      parseIncompleteMarkdown={isLoading}
      animated={streamdownSmoothStreamingAnimation}
      isAnimating={isLoading}
    >
      {normalized}
    </ClipboardSafeStreamdown>
  );
}

const UserRow = memo(function UserRow({ message }: { message: UserMessage }) {
  return (
    <Message className="group/conversation-message relative w-full" from="user">
      {message.files.length > 0 && (
        <div className="ml-auto flex flex-wrap justify-end gap-2">
          {message.files.map((file) => (
            <span
              key={file}
              className="bg-muted text-muted-foreground flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs font-medium"
            >
              <PaperclipIcon className="size-3" />
              <span className="max-w-40 truncate">{file}</span>
            </span>
          ))}
        </div>
      )}
      <MessageContent className="w-fit whitespace-pre-wrap">
        {message.text}
      </MessageContent>
      <MessageToolbar
        className={cn(
          "absolute right-0 -bottom-9 left-0 justify-end",
          TOOLBAR_VISIBILITY,
        )}
      >
        <div className="pointer-events-auto flex gap-1">
          <CopyButton text={message.text} />
        </div>
      </MessageToolbar>
    </Message>
  );
});

function statusNote(status: AssistantMessage["status"]) {
  if (status === "stopped") return "Stopped";
  if (status === "error") return "The response failed";
  return null;
}

function AssistantRow({ message }: { message: AssistantMessage }) {
  const isLoading = message.status === "streaming";
  const isEmpty =
    !message.reasoning && !message.text && message.steps.length === 0;
  const note = statusNote(message.status);

  return (
    <Message
      className="group/conversation-message relative w-full pb-8"
      from="assistant"
    >
      {message.steps.length > 0 && <MessageSteps steps={message.steps} />}
      <MessageContent className="w-full">
        {message.reasoning && (
          <MessageReasoning
            isLoading={isLoading && !message.text}
            durationSeconds={message.durationSeconds}
          >
            {message.reasoning}
          </MessageReasoning>
        )}
        {isEmpty && isLoading && <StreamingIndicator className="my-4" />}
        {message.text && (
          <Markdown content={message.text} isLoading={isLoading} />
        )}
        {message.citations && message.citations.length > 0 && (
          <div className="mt-5 flex flex-wrap gap-2" aria-label="Sources">
            {message.citations.map((c) => (
              <details
                key={c.citation}
                className="bg-secondary/50 max-w-full rounded-lg border px-3 py-2 text-xs"
              >
                <summary className="cursor-pointer break-words">
                  [{c.citation}] {c.document_title}
                  {c.page ? ` · Page ${c.page}` : ""}
                </summary>
                <p className="mt-2">
                  {c.edition} · {c.kind} {c.number}
                </p>
              </details>
            ))}
          </div>
        )}
        {message.warnings?.map((w) => (
          <p key={w} className="text-muted-foreground mt-2 text-sm">
            {w}
          </p>
        ))}
        {note && (
          <p role="status" className="text-destructive text-sm">
            {message.error || note}
          </p>
        )}
      </MessageContent>
      {!isLoading && message.text && (
        <MessageToolbar
          className={cn("absolute right-0 bottom-0 left-0", TOOLBAR_VISIBILITY)}
        >
          <div className="pointer-events-auto flex gap-1">
            <CopyButton text={message.text} />
          </div>
        </MessageToolbar>
      )}
    </Message>
  );
}

export function MessageList({
  className,
  messages,
}: {
  className?: string;
  messages: ChatMessage[];
}) {
  return (
    <Conversation className={className}>
      <ConversationContent className="mx-auto w-full max-w-(--container-width-md) gap-8 pt-8">
        {messages.map((message) =>
          message.role === "user" ? (
            <UserRow key={message.id} message={message} />
          ) : (
            <AssistantRow key={message.id} message={message} />
          ),
        )}
      </ConversationContent>
      <ConversationScrollButton />
    </Conversation>
  );
}
