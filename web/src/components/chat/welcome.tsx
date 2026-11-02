"use client";

import { useEffect, useMemo } from "react";

import { AuroraText } from "@/components/ui/aurora-text";
import { site } from "@/config/site";
import type { ChatMode } from "@/core/chat/types";
import { cn } from "@/lib/utils";

let waved = false;

export function Welcome({
  className,
  mode,
}: {
  className?: string;
  mode?: ChatMode;
}) {
  const isUltra = useMemo(() => mode === "ultra", [mode]);
  const colors = useMemo(() => {
    if (isUltra) {
      return ["#efefbb", "#e9c665", "#e3a812"];
    }
    return ["var(--color-foreground)"];
  }, [isUltra]);
  useEffect(() => {
    waved = true;
  }, []);
  return (
    <div
      className={cn(
        "mx-auto flex w-full max-w-full flex-col items-center justify-center gap-2 px-4 py-4 text-center sm:px-8",
        className,
      )}
    >
      <div className="max-w-full text-2xl font-bold">
        <div className="flex max-w-full flex-wrap items-center justify-center gap-2">
          <div className={cn("inline-block", !waved ? "animate-wave" : "")}>
            {isUltra ? "🚀" : "👋"}
          </div>
          <AuroraText colors={colors}>{site.chat.greeting}</AuroraText>
        </div>
      </div>
      <div className="text-muted-foreground max-w-full text-sm">
        <p className="max-w-full text-wrap break-words whitespace-pre-line">
          {site.chat.description}
        </p>
      </div>
    </div>
  );
}
