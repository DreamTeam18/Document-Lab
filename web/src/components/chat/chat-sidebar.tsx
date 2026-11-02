"use client";

import {
  ChevronsUpDown,
  HouseIcon,
  MessageSquarePlus,
  MessagesSquare,
  MonitorIcon,
  MoonIcon,
  SettingsIcon,
  SunIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { site } from "@/config/site";
import { useChatStore } from "@/core/chat/store";
import { cn } from "@/lib/utils";

import { DocumentsPanel } from "./documents-panel";
import { WorkspaceSidebarTrigger } from "./workspace-sidebar-trigger";

function SidebarBrand() {
  const { isMobile, open } = useSidebar();
  const pathname = usePathname();
  const expanded = isMobile || open;

  return (
    <>
      <div className="group/workspace-header flex h-12 flex-col justify-center">
        {!expanded ? (
          <div className="flex w-full cursor-pointer items-center justify-center">
            <div className="text-primary block pt-1 font-serif group-hover/workspace-header:hidden">
              {site.shortName}
            </div>
            <WorkspaceSidebarTrigger className="hidden pl-2 group-hover/workspace-header:block" />
          </div>
        ) : (
          <div className="flex items-center justify-between gap-2">
            <Link href="/" className="text-primary ml-2 font-serif">
              {site.name}
            </Link>
            <WorkspaceSidebarTrigger />
          </div>
        )}
      </div>
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton
            isActive={pathname === "/workspace/chats/new"}
            asChild
          >
            <Link className="text-muted-foreground" href="/workspace/chats/new">
              <MessageSquarePlus size={16} />
              <span>New chat</span>
            </Link>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    </>
  );
}

function SidebarNav() {
  const pathname = usePathname();
  return (
    <SidebarGroup className="pt-1">
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton isActive={pathname === "/workspace/chats"} asChild>
            <Link className="text-muted-foreground" href="/workspace/chats">
              <MessagesSquare />
              <span>Chats</span>
            </Link>
          </SidebarMenuButton>
        </SidebarMenuItem>
        {site.chat.placeholderNav.map((item) => (
          <SidebarMenuItem key={item.label}>
            {/* aria-disabled makes the button inert, so the span takes hover. */}
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="block w-full cursor-not-allowed">
                  <SidebarMenuButton
                    className="text-muted-foreground/50"
                    aria-disabled
                  >
                    <item.icon />
                    <span>{item.label}</span>
                  </SidebarMenuButton>
                </span>
              </TooltipTrigger>
              <TooltipContent side="right">Feature not enabled</TooltipContent>
            </Tooltip>
          </SidebarMenuItem>
        ))}
      </SidebarMenu>
    </SidebarGroup>
  );
}

function RecentChats() {
  const { threads } = useChatStore();
  const pathname = usePathname();
  const { isMobile, open } = useSidebar();
  if (!(isMobile || open) || threads.length === 0) return null;

  return (
    <SidebarGroup>
      <SidebarGroupLabel>Recent chats</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {threads.map((thread) => (
            <SidebarMenuItem key={thread.id}>
              <SidebarMenuButton
                isActive={pathname === `/workspace/chats/${thread.id}`}
                asChild
              >
                <Link
                  className="text-muted-foreground"
                  href={`/workspace/chats/${thread.id}`}
                >
                  <span className="truncate">{thread.title}</span>
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  );
}

const THEMES = [
  { value: "light", label: "Light", icon: SunIcon },
  { value: "dark", label: "Dark", icon: MoonIcon },
  { value: "system", label: "System", icon: MonitorIcon },
];

function SettingsMenu() {
  const { isMobile, open } = useSidebar();
  const { theme, setTheme } = useTheme();
  // Radix ids differ between server and client until hydration has finished.
  const [mounted, setMounted] = useState(false);
  const expanded = isMobile || open;

  useEffect(() => {
    setMounted(true);
  }, []);

  const trigger = expanded ? (
    <div className="text-muted-foreground flex w-full items-center gap-2 text-left text-sm">
      <SettingsIcon className="size-4" />
      <span>Settings and more</span>
      <ChevronsUpDown className="text-muted-foreground ml-auto size-4" />
    </div>
  ) : (
    <div className="flex size-full items-center justify-center">
      <SettingsIcon className="text-muted-foreground size-4" />
    </div>
  );

  return (
    <SidebarMenu className="w-full">
      <SidebarMenuItem>
        {mounted ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <SidebarMenuButton
                aria-label="Settings and more"
                size="lg"
                className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
              >
                {trigger}
              </SidebarMenuButton>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              className="w-(--radix-dropdown-menu-trigger-width) min-w-56"
              side="top"
              align="start"
              sideOffset={4}
            >
              <DropdownMenuGroup>
                <DropdownMenuLabel className="text-muted-foreground text-xs">
                  Theme
                </DropdownMenuLabel>
                {THEMES.map((item) => (
                  <DropdownMenuItem
                    key={item.value}
                    className={cn(theme === item.value && "bg-accent")}
                    onClick={() => setTheme(item.value)}
                  >
                    <item.icon className="size-4" />
                    {item.label}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuGroup>
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <Link href="/">
                  <HouseIcon className="size-4" />
                  Home page
                </Link>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ) : (
          <SidebarMenuButton size="lg">{trigger}</SidebarMenuButton>
        )}
      </SidebarMenuItem>
    </SidebarMenu>
  );
}

export function ChatSidebar() {
  const { isMobile } = useSidebar();
  return (
    <Sidebar variant="sidebar" collapsible="icon">
      <SidebarHeader className="py-0">
        <SidebarBrand />
      </SidebarHeader>
      <SidebarContent>
        <SidebarNav />
        <DocumentsPanel />
        <RecentChats />
      </SidebarContent>
      <SidebarFooter>
        <SettingsMenu />
      </SidebarFooter>
      {!isMobile && <SidebarRail />}
    </Sidebar>
  );
}
