"use client";

import Link from "next/link";

import { WorkspaceSidebarTrigger } from "@/components/chat/workspace-sidebar-trigger";
import { useChatStore } from "@/core/chat/store";

export default function ChatsPage() {
  const { threads } = useChatStore();

  return (
    <div className="flex size-full flex-col">
      <header className="flex h-12 shrink-0 items-center gap-2 px-2 text-sm font-medium sm:px-4">
        <WorkspaceSidebarTrigger className="md:hidden" />
        Chats
      </header>
      <main className="mx-auto w-full max-w-(--container-width-md) flex-1 overflow-y-auto px-4 py-4">
        <ul className="flex flex-col gap-2">
          {threads.map((thread) => (
            <li key={thread.id}>
              <Link
                className="hover:bg-accent block rounded-lg border px-4 py-3 text-sm transition-colors"
                href={`/workspace/chats/${thread.id}`}
              >
                <span className="block truncate font-medium">
                  {thread.title}
                </span>
                <span className="text-muted-foreground text-xs">
                  {thread.messages.length} messages
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </main>
    </div>
  );
}
