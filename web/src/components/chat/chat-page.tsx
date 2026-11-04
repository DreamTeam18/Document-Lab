"use client";

import { MessageSquareOffIcon } from "lucide-react";
import { nanoid } from "nanoid";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { PromptInputProvider } from "@/components/ai-elements/prompt-input";
import { ConversationEmptyState } from "@/components/ai-elements/conversation";
import { Button } from "@/components/ui/button";
import { site } from "@/config/site";
import { useChatStore } from "@/core/chat/store";
import { cn } from "@/lib/utils";

import { Composer } from "./composer";
import { FlipDisplay } from "./flip-display";
import { MessageList } from "./message-list";
import { TodoList } from "./todo-list";
import { Welcome } from "./welcome";
import { WorkspaceSidebarTrigger } from "./workspace-sidebar-trigger";

const NEW_THREAD_ID = "new";

export function ChatPage() {
  // Not useParams: it ignores the history.replaceState call in handleSubmit.
  const routeThreadId = usePathname().split("/").pop() ?? NEW_THREAD_ID;
  const {
    ready,
    webAvailable,
    threads,
    selectedIds,
    settings,
    setSettings,
    isStreaming,
    send,
    stop,
  } = useChatStore();

  const isNewThread = routeThreadId === NEW_THREAD_ID;
  const thread = threads.find((item) => item.id === routeThreadId);
  const isWelcomeMode = isNewThread || !thread?.messages.length;
  const streaming = isStreaming(routeThreadId);
  const title = thread?.title;

  useEffect(() => {
    document.title = `${title ?? "New chat"} - ${site.name}`;
  }, [title]);

  const handleSubmit = (text: string, files: File[]) => {
    const threadId = isNewThread ? nanoid() : routeThreadId;
    send({ threadId, text, files });
    if (isNewThread) {
      // Keeps this page mounted so the composer can animate down from welcome.
      history.replaceState(null, "", `/workspace/chats/${threadId}`);
    }
  };

  if (ready && !isNewThread && !thread) {
    return (
      <div className="flex size-full flex-col">
        <ChatHeader isWelcomeMode={false} />
        <ConversationEmptyState>
          <MessageSquareOffIcon className="text-muted-foreground size-8" />
          <p className="text-sm font-medium">Chat not found</p>
          <p className="text-muted-foreground text-sm">
            Chats are saved in this browser. Start a new one to continue.
          </p>
          <Button asChild className="mt-2" size="sm" variant="outline">
            <Link href={`/workspace/chats/${NEW_THREAD_ID}`}>New chat</Link>
          </Button>
        </ConversationEmptyState>
      </div>
    );
  }

  return (
    <PromptInputProvider>
      <div className="relative flex size-full min-h-0 flex-col justify-between">
        <ChatHeader
          isWelcomeMode={isWelcomeMode}
          threadId={routeThreadId}
          title={title}
        />
        <section className="flex min-h-0 max-w-full grow flex-col" aria-label="Conversation">
          <div className="flex min-h-0 flex-1 justify-center">
            {!isWelcomeMode && thread && (
              <MessageList
                className="size-full pt-10"
                messages={thread.messages}
              />
            )}
          </div>
          <div
            className={cn(
              "right-0 bottom-0 left-0 z-30 flex justify-center px-3 sm:px-4",
              isWelcomeMode ? "absolute" : "relative shrink-0 pb-4",
            )}
          >
            <div
              className={cn(
                "relative w-full",
                isWelcomeMode &&
                  "-translate-y-[calc(50vh-48px)] sm:-translate-y-[calc(50vh-96px)]",
                isWelcomeMode
                  ? "max-w-(--container-width-sm)"
                  : "max-w-(--container-width-md)",
              )}
            >
              {thread && thread.todos.length > 0 && !isWelcomeMode && (
                <TodoList className="bg-background/5" todos={thread.todos} />
              )}
              <Composer
                className={cn(
                  "bg-background/5 w-full",
                  isWelcomeMode && "-translate-y-2 sm:-translate-y-4",
                )}
                disabled={
                  !ready || !(thread?.documentIds?.length || selectedIds.length)
                }
                isStreaming={streaming}
                isWelcomeMode={isWelcomeMode}
                settings={settings}
                webAvailable={webAvailable}
                extraHeader={isWelcomeMode && <Welcome mode={settings.mode} />}
                onSettingsChange={setSettings}
                onStop={() => stop(routeThreadId)}
                onSubmit={handleSubmit}
              />
            </div>
          </div>
        </section>
      </div>
    </PromptInputProvider>
  );
}

function ChatHeader({
  isWelcomeMode,
  threadId,
  title,
}: {
  isWelcomeMode: boolean;
  threadId?: string;
  title?: string;
}) {
  return (
    <header
      className={cn(
        "absolute top-0 right-0 left-0 flex h-12 shrink-0 items-center gap-2 px-2 sm:px-4",
        isWelcomeMode
          ? "bg-background/0 z-40 backdrop-blur-none"
          : "bg-background/80 z-30 shadow-xs backdrop-blur",
      )}
    >
      <WorkspaceSidebarTrigger className="md:hidden" />
      <div className="flex min-w-0 flex-1 items-center gap-2 text-sm font-medium">
        {title && threadId && (
          <FlipDisplay
            uniqueKey={threadId}
            className="min-w-0 [&>div]:truncate"
          >
            {title}
          </FlipDisplay>
        )}
      </div>
    </header>
  );
}
