import { ChevronUpIcon, ListTodoIcon } from "lucide-react";
import { useState } from "react";

import {
  QueueItem,
  QueueItemContent,
  QueueItemIndicator,
  QueueList,
} from "@/components/ai-elements/queue";
import type { ChatTodo } from "@/core/chat/types";
import { cn } from "@/lib/utils";

export function TodoList({
  className,
  todos,
}: {
  className?: string;
  todos: ChatTodo[];
}) {
  const [collapsed, setCollapsed] = useState(true);

  return (
    <div
      className={cn(
        "flex h-fit w-full origin-bottom translate-y-4 flex-col overflow-hidden rounded-t-xl border border-b-0 backdrop-blur-sm transition-all duration-200 ease-out",
        className,
      )}
    >
      <button
        type="button"
        aria-expanded={!collapsed}
        className="bg-accent flex min-h-8 shrink-0 cursor-pointer items-center justify-between px-4 text-sm transition-all duration-300 ease-out"
        onClick={() => setCollapsed((current) => !current)}
      >
        <span className="text-muted-foreground flex items-center justify-center gap-2">
          <ListTodoIcon className="size-4" />
          To-dos
        </span>
        <ChevronUpIcon
          className={cn(
            "text-muted-foreground size-4 transition-transform duration-300 ease-out",
            collapsed ? "" : "rotate-180",
          )}
        />
      </button>
      <div
        className={cn(
          "bg-accent flex grow px-2 transition-all duration-300 ease-out",
          collapsed ? "h-0 pb-3" : "h-28 pb-4",
        )}
      >
        <QueueList className="bg-background mt-0 w-full rounded-t-xl">
          {todos.map((todo) => (
            <QueueItem key={todo.content}>
              <div className="flex items-center gap-2">
                <QueueItemIndicator
                  className={
                    todo.status === "in_progress" ? "bg-primary/70" : ""
                  }
                  completed={todo.status === "completed"}
                />
                <QueueItemContent
                  className={
                    todo.status === "in_progress" ? "text-primary/70" : ""
                  }
                  completed={todo.status === "completed"}
                >
                  {todo.content}
                </QueueItemContent>
              </div>
            </QueueItem>
          ))}
        </QueueList>
      </div>
    </div>
  );
}
