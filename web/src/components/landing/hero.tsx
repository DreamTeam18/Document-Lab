"use client";

import { ChevronRightIcon } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { AuroraText } from "@/components/ui/aurora-text";
import { Button } from "@/components/ui/button";
import { FlickeringGrid } from "@/components/ui/flickering-grid";
import { site } from "@/config/site";
import {
  useRenderActivity,
  usePrefersReducedMotion,
} from "@/core/dom/render-activity";
import { cn } from "@/lib/utils";

const Galaxy = dynamic(() => import("@/components/ui/galaxy"), { ssr: false });

export function Hero({ className }: { className?: string }) {
  const galaxyContainerRef = useRef<HTMLDivElement>(null);
  const renderGalaxy = useRenderActivity(galaxyContainerRef);

  return (
    <div
      className={cn(
        "relative flex size-full flex-col items-center justify-center",
        className,
      )}
    >
      <div
        ref={galaxyContainerRef}
        className="absolute inset-0 z-0 bg-[radial-gradient(ellipse_at_center,#252019_0%,#0a0a0a_70%)]"
      >
        {renderGalaxy && (
          <Galaxy
            mouseRepulsion={false}
            starSpeed={0.2}
            density={0.6}
            glowIntensity={0.35}
            twinkleIntensity={0.3}
            speed={0.5}
          />
        )}
      </div>
      <FlickeringGrid
        className="absolute inset-0 z-0 mask-size-[140.4vw] mask-center mask-no-repeat md:mask-size-[100.8vh]"
        style={{ maskImage: `url(${site.logoMaskUrl})` }}
        squareSize={4}
        gridGap={4}
        color={"white"}
        maxOpacity={0.3}
        flickerChance={0.25}
      />
      <div className="container-md relative z-10 mx-auto flex min-h-[92svh] flex-col items-center justify-center px-4 pt-20 pb-14">
        <h1 className="text-center text-5xl leading-tight font-bold break-words md:text-6xl">
          {site.hero.title}
        </h1>
        <div className="mt-3 flex w-full max-w-full min-w-0 items-center justify-center gap-x-2 text-center text-2xl font-semibold md:text-4xl">
          <HeroWordRotate words={site.hero.rotatingWords} />
          <span className="whitespace-nowrap">{site.hero.rotatingSuffix}</span>
        </div>
        <p className="text-muted-foreground mt-8 max-w-4xl text-center text-base leading-7 text-shadow-sm sm:text-xl md:text-2xl">
          {site.hero.description}
        </p>
        <Link href={site.hero.ctaHref}>
          <Button className="mt-8 h-11 px-5" size="lg">
            <span className="text-md">{site.hero.ctaLabel}</span>
            <ChevronRightIcon className="size-4" />
          </Button>
        </Link>
      </div>
    </div>
  );
}

function HeroWordRotate({
  words,
  duration = 2200,
}: {
  words: string[];
  duration?: number;
}) {
  const [index, setIndex] = useState(0);
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    if (reduced) return;
    const interval = setInterval(() => {
      setIndex((prevIndex) => (prevIndex + 1) % words.length);
    }, duration);

    return () => clearInterval(interval);
  }, [words, duration, reduced]);

  return (
    <div className="relative max-w-full min-w-0 overflow-hidden py-2">
      <AnimatePresence mode="popLayout">
        <motion.div
          key={index}
          className="max-w-full"
          initial={{ opacity: 0, y: -50, filter: "blur(16px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          exit={{ opacity: 0, y: 50, filter: "blur(16px)" }}
          transition={{ duration: 0.3, ease: "easeOut" }}
        >
          <AuroraText
            className="max-w-full [overflow-wrap:anywhere] whitespace-normal"
            speed={3}
            colors={["#efefbb", "#e9c665", "#e3a812"]}
          >
            {words[index]}
          </AuroraText>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
