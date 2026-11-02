"use client";

import { useCallback, useRef } from "react";
import { toast } from "sonner";

import {
  PromptInput,
  PromptInputFooter,
  type PromptInputMessage,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
} from "@/components/ai-elements/prompt-input";
import { site } from "@/config/site";
import type { ChatSettings } from "@/core/chat/types";
import { cn } from "@/lib/utils";

import { SuggestionList } from "./suggestion-list";

export function Composer({
  className,
  isWelcomeMode,
  isStreaming,
  disabled,
  settings,
  extraHeader,
  onSettingsChange,
  onSubmit,
  onStop,
}: {
  className?: string;
  isWelcomeMode: boolean;
  isStreaming: boolean;
  disabled?: boolean;
  settings: ChatSettings;
  extraHeader?: React.ReactNode;
  onSettingsChange: (settings: ChatSettings) => void;
  onSubmit: (text: string, files: File[]) => void;
  onStop: () => void;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  // Prompts carry placeholders like [topic]: select one so typing replaces it.
  const selectPlaceholder = useCallback((prompt: string) => {
    requestAnimationFrame(() => {
      const textarea = rootRef.current?.querySelector("textarea");
      if (!textarea) return;
      textarea.focus();
      const start = prompt.indexOf("[");
      const end = prompt.indexOf("]");
      if (start >= 0 && end > start) {
        textarea.setSelectionRange(start, end + 1);
      }
    });
  }, []);

  const handleSubmit = (message: PromptInputMessage) => {
    const text = message.text.trim();
    if (disabled || isStreaming || !text) {
      // Throwing keeps the draft; PromptInput clears it on a clean return.
      throw new Error("Nothing to send");
    }
    const files = message.files.flatMap((file) =>
      file.file ? [file.file] : [],
    );
    onSubmit(text, files);
  };

  return (
    <div
      ref={rootRef}
      onPasteCapture={(event) => {
        if (event.clipboardData.files.length) {
          event.preventDefault();
          event.stopPropagation();
          toast.info(
            "Use Upload document in the sidebar to index files before chatting.",
          );
        }
      }}
      onDragOverCapture={(event) => {
        if (event.dataTransfer.types.includes("Files")) event.preventDefault();
      }}
      onDropCapture={(event) => {
        if (event.dataTransfer.files.length) {
          event.preventDefault();
          event.stopPropagation();
          toast.info(
            "Use Upload document in the sidebar to index files before chatting.",
          );
        }
      }}
      className={cn(
        "relative flex min-w-0 flex-col",
        isWelcomeMode ? "gap-4" : "gap-2",
      )}
    >
      <PromptInput
        className={cn(
          "bg-background/85 relative z-10 rounded-2xl backdrop-blur-sm transition-all duration-300 ease-out *:data-[slot='input-group']:rounded-2xl",
          className,
        )}
        onError={(error) => toast.error(error.message)}
        onSubmit={handleSubmit}
      >
        {extraHeader && (
          <div className="absolute top-0 right-0 left-0 z-10">
            <div className="absolute right-0 bottom-0 left-0 flex items-center justify-center">
              {extraHeader}
            </div>
          </div>
        )}
        <div className="min-h-16 w-full min-w-0 px-3 py-3">
          <PromptInputTextarea
            aria-label="Message"
            maxLength={4000}
            autoFocus={isWelcomeMode}
            className="min-h-6! w-full min-w-0 p-0! leading-6!"
            disabled={disabled}
            placeholder={site.chat.placeholder}
          />
        </div>
        <PromptInputFooter className="flex flex-wrap gap-2 sm:flex-nowrap">
          <PromptInputTools className="min-w-0 flex-1 flex-wrap">
            <span className="text-muted-foreground px-2 text-xs">
              Document search · selected sources
            </span>
          </PromptInputTools>
          <PromptInputTools className="min-w-0 justify-end">
            <PromptInputSubmit
              aria-label={isStreaming ? "Stop" : "Send"}
              className="rounded-full"
              disabled={disabled}
              variant="outline"
              status={isStreaming ? "streaming" : "ready"}
              onClick={(event) => {
                if (isStreaming) {
                  event.preventDefault();
                  onStop();
                }
              }}
            />
          </PromptInputTools>
        </PromptInputFooter>
      </PromptInput>
      {!isWelcomeMode && (
        <div className="bg-background absolute right-0 -bottom-[17px] left-0 z-0 h-4"></div>
      )}

      {isWelcomeMode && (
        <div className="flex items-center justify-center pt-2">
          <SuggestionList onSelectPlaceholder={selectPlaceholder} />
        </div>
      )}

      <p
        className={cn(
          "text-muted-foreground/67 z-10 px-4 text-center text-xs leading-4",
          !isWelcomeMode && "absolute top-full right-0 left-0",
        )}
      >
        {site.chat.disclaimer}
      </p>
    </div>
  );
}
