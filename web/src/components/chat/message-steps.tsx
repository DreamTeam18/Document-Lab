import {
  FileTextIcon,
  GlobeIcon,
  LoaderCircleIcon,
  SearchIcon,
  SquareTerminalIcon,
  type LucideIcon,
} from "lucide-react";

import {
  ChainOfThought,
  ChainOfThoughtContent,
  ChainOfThoughtSearchResult,
  ChainOfThoughtSearchResults,
  ChainOfThoughtStep,
} from "@/components/ai-elements/chain-of-thought";
import type { ChatStep, ChatStepKind } from "@/core/chat/types";

const STEP_ICONS: Record<ChatStepKind, LucideIcon> = {
  search: SearchIcon,
  fetch: GlobeIcon,
  bash: SquareTerminalIcon,
  write: FileTextIcon,
};

export function MessageSteps({ steps }: { steps: ChatStep[] }) {
  return (
    <ChainOfThought
      className="w-full gap-2 rounded-lg border p-0.5"
      open={true}
    >
      <ChainOfThoughtContent className="px-4 py-2">
        {steps.map((step) => {
          const active = step.status === "active";
          return (
            <ChainOfThoughtStep
              key={step.id}
              icon={
                active ? (
                  <LoaderCircleIcon className="size-4 animate-spin" />
                ) : (
                  STEP_ICONS[step.kind]
                )
              }
              label={step.label}
              status={active ? "active" : "complete"}
            >
              {step.results && (
                <ChainOfThoughtSearchResults>
                  {step.results.map((result) => (
                    <ChainOfThoughtSearchResult key={result}>
                      {result}
                    </ChainOfThoughtSearchResult>
                  ))}
                </ChainOfThoughtSearchResults>
              )}
            </ChainOfThoughtStep>
          );
        })}
      </ChainOfThoughtContent>
    </ChainOfThought>
  );
}
