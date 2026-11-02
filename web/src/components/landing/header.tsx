import Link from "next/link";

import { Button } from "@/components/ui/button";
import { site } from "@/config/site";
import { cn } from "@/lib/utils";

import { MobileNav } from "./mobile-nav";

export function Header({ className }: { className?: string }) {
  return (
    <header
      className={cn(
        "container-md fixed top-0 right-0 left-0 z-20 mx-auto flex h-16 items-center justify-between gap-3 px-4 backdrop-blur-xs",
        className,
      )}
    >
      <div className="flex min-w-0 items-center gap-6">
        <Link href="/" className="font-serif text-xl whitespace-nowrap">
          {site.name}
        </Link>
      </div>
      <nav className="ml-auto hidden items-center gap-5 text-sm font-medium sm:flex md:mr-8 md:gap-8">
        {site.header.links.map((link) => (
          <Link
            key={link.href}
            href={link.href}
            className="text-secondary-foreground hover:text-foreground transition-colors"
          >
            {link.label}
          </Link>
        ))}
      </nav>
      <div className="relative">
        <div
          className="pointer-events-none absolute inset-0 z-0 h-full w-full rounded-full opacity-30 blur-2xl"
          style={{
            background: "linear-gradient(90deg, #ff80b5 0%, #9089fc 100%)",
            filter: "blur(16px)",
          }}
        />
        <Button
          variant="outline"
          size="sm"
          asChild
          className="group relative z-10"
        >
          <a
            href={site.repositoryUrl}
            rel="noopener noreferrer"
            aria-label={site.header.ctaLabel}
          >
            <span aria-hidden="true">↗</span>
            <span className="hidden sm:inline">{site.header.ctaLabel}</span>
          </a>
        </Button>
      </div>
      <MobileNav links={site.header.links} />
      <hr className="from-border/0 via-border/70 to-border/0 absolute top-16 right-0 left-0 z-10 m-0 h-px w-full border-none bg-linear-to-r" />
    </header>
  );
}
