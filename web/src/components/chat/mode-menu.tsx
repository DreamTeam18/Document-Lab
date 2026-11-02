import {
  CheckIcon,
  GraduationCapIcon,
  LightbulbIcon,
  type LucideIcon,
  RocketIcon,
  ZapIcon,
} from "lucide-react";

import {
  PromptInputActionMenu,
  PromptInputActionMenuContent,
  PromptInputActionMenuItem,
  PromptInputActionMenuTrigger,
} from "@/components/ai-elements/prompt-input";
import {
  DropdownMenuGroup,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu";
import type { ChatMode } from "@/core/chat/types";
import { cn } from "@/lib/utils";

const MODES: {
  value: ChatMode;
  label: string;
  description: string;
  icon: LucideIcon;
}[] = [
  {
    value: "flash",
    label: "Flash",
    description: "Fast and efficient, but may not be accurate",
    icon: ZapIcon,
  },
  {
    value: "thinking",
    label: "Reasoning",
    description: "Reasoning before action, balance between time and accuracy",
    icon: LightbulbIcon,
  },
  {
    value: "pro",
    label: "Pro",
    description:
      "Reasoning, planning and executing, get more accurate results, may take more time",
    icon: GraduationCapIcon,
  },
  {
    value: "ultra",
    label: "Ultra",
    description:
      "Pro mode with subagents to divide work; best for complex multi-step tasks",
    icon: RocketIcon,
  },
];

export function ModeMenu({
  mode,
  disabled,
  onChange,
}: {
  mode: ChatMode;
  disabled?: boolean;
  onChange: (mode: ChatMode) => void;
}) {
  const current = MODES.find((item) => item.value === mode) ?? MODES[0]!;
  const isUltra = mode === "ultra";

  return (
    <PromptInputActionMenu>
      <PromptInputActionMenuTrigger
        aria-label={`Mode: ${current.label}`}
        className="max-w-28 gap-1! px-2! sm:max-w-none"
        disabled={disabled}
      >
        <current.icon
          className={cn("size-3", isUltra && "text-[#dabb5e]")}
        />
        <div
          className={cn(
            "truncate text-xs font-normal",
            isUltra && "golden-text",
          )}
        >
          {current.label}
        </div>
      </PromptInputActionMenuTrigger>
      <PromptInputActionMenuContent className="w-80">
        <DropdownMenuGroup>
          <DropdownMenuLabel className="text-muted-foreground text-xs">
            Mode
          </DropdownMenuLabel>
          {MODES.map((item) => {
            const selected = item.value === mode;
            return (
              <PromptInputActionMenuItem
                key={item.value}
                className={cn(
                  selected
                    ? "text-accent-foreground"
                    : "text-muted-foreground/65",
                )}
                onSelect={() => onChange(item.value)}
              >
                <div className="flex flex-col gap-2">
                  <div className="flex items-center gap-1 font-bold">
                    <item.icon
                      className={cn(
                        "mr-2 size-4",
                        selected && "text-accent-foreground",
                        item.value === "ultra" && "text-[#dabb5e]",
                      )}
                    />
                    <span
                      className={cn(item.value === "ultra" && "golden-text")}
                    >
                      {item.label}
                    </span>
                  </div>
                  <div className="pl-7 text-xs">{item.description}</div>
                </div>
                {selected ? (
                  <CheckIcon className="ml-auto size-4" />
                ) : (
                  <div className="ml-auto size-4" />
                )}
              </PromptInputActionMenuItem>
            );
          })}
        </DropdownMenuGroup>
      </PromptInputActionMenuContent>
    </PromptInputActionMenu>
  );
}
