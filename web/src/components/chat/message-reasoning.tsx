"use client";

import { ChevronRightIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import {
  Reasoning,
  ReasoningContent,
  ReasoningTrigger,
} from "@/components/ai-elements/reasoning";
import { Shimmer } from "@/components/ai-elements/shimmer";

export function MessageReasoning({
  children,
  isLoading,
  durationSeconds,
}: {
  children: string;
  isLoading: boolean;
  durationSeconds?: number;
}) {
  const [open, setOpen] = useState(isLoading);
  const hasStreamed = useRef(isLoading);

  useEffect(() => {
    if (isLoading) {
      hasStreamed.current = true;
      setOpen(true);
      return;
    }
    if (!hasStreamed.current) return;

    // Close only after a live stream, never after mounting historical content.
    const timer = setTimeout(() => setOpen(false), 1000);
    return () => clearTimeout(timer);
  }, [isLoading]);

  return (
    <Reasoning
      className="border-border/60 mb-3 border-b pb-3"
      isStreaming={isLoading}
      defaultOpen={false}
      open={open}
      onOpenChange={setOpen}
    >
      <ReasoningTrigger className="group/reasoning w-fit cursor-pointer gap-1.5 rounded-sm focus-visible:outline-2 focus-visible:outline-offset-4">
        {isLoading ? (
          <Shimmer duration={1}>Reasoning</Shimmer>
        ) : (
          <span>
            {durationSeconds ? `Worked for ${durationSeconds}s` : "Reasoning"}
          </span>
        )}
        <ChevronRightIcon className="size-4 transition-transform group-data-[state=open]/reasoning:rotate-90" />
      </ReasoningTrigger>
      <ReasoningContent>{children}</ReasoningContent>
    </Reasoning>
  );
}
