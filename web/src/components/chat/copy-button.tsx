"use client";

import { CheckIcon, CopyIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { writeTextToClipboard } from "@/core/clipboard";

import { Tooltip } from "./tooltip";

export function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => () => clearTimeout(timer.current), []);

  return (
    <Tooltip content="Copy to clipboard">
      <Button
        aria-label="Copy to clipboard"
        size="icon-sm"
        type="button"
        variant="ghost"
        onClick={async () => {
          if (!(await writeTextToClipboard(text))) return;
          setCopied(true);
          clearTimeout(timer.current);
          timer.current = setTimeout(() => setCopied(false), 2000);
        }}
      >
        {copied ? (
          <CheckIcon className="size-4" />
        ) : (
          <CopyIcon className="size-4" />
        )}
      </Button>
    </Tooltip>
  );
}
