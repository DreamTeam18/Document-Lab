"use client";

import { PlusIcon, SparklesIcon } from "lucide-react";

import { usePromptInputController } from "@/components/ai-elements/prompt-input";
import { Suggestion, Suggestions } from "@/components/ai-elements/suggestion";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { site } from "@/config/site";

export function SuggestionList({
  onSelectPlaceholder,
}: {
  onSelectPlaceholder: (prompt: string) => void;
}) {
  const { textInput } = usePromptInputController();
  const choose = (prompt: string) => {
    textInput.setInput(prompt);
    onSelectPlaceholder(prompt);
  };

  return (
    <Suggestions className="min-h-16 w-full max-w-full justify-center px-4 sm:w-fit sm:px-0">
      <button
        className="text-muted-foreground hover:bg-accent inline-flex h-8 cursor-pointer items-center gap-2 rounded-full border px-4 text-xs font-normal"
        onClick={() => choose(site.chat.surpriseMe.prompt)}
      >
        <SparklesIcon className="size-4" /> {site.chat.surpriseMe.label}
      </button>
      {site.chat.suggestions.map((suggestion) => (
        <Suggestion
          key={suggestion.label}
          icon={suggestion.icon}
          suggestion={suggestion.label}
          onClick={() => choose(suggestion.prompt)}
        />
      ))}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Suggestion icon={PlusIcon} suggestion={site.chat.createLabel} />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start">
          <DropdownMenuGroup>
            {site.chat.createSuggestions.map((suggestion) => (
              <DropdownMenuItem
                key={suggestion.label}
                onClick={() => choose(suggestion.prompt)}
              >
                <suggestion.icon className="size-4" />
                {suggestion.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuGroup>
        </DropdownMenuContent>
      </DropdownMenu>
    </Suggestions>
  );
}
