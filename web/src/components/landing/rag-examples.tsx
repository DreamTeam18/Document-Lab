"use client";
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  ArrowRight,
  BookOpen,
  Check,
  FileText,
  Pause,
  Play,
  Search,
} from "lucide-react";
import Link from "next/link";
import {
  usePrefersReducedMotion,
  useRenderActivity,
} from "@/core/dom/render-activity";
import { Section } from "./section";
const examples = [
  {
    label: "Find a requirement",
    file: "Archive manual.pdf",
    question: "What must archive labels contain?",
    excerpt:
      "Every archive label must include the document title and edition. Labels should be blue.",
    answer:
      "Include the document title and edition on every archive label. The manual recommends blue labels.",
    page: 1,
  },
  {
    label: "Connect the details",
    file: "Onboarding guide.pdf",
    question: "What should I do before requesting access?",
    excerpt:
      "Before requesting workspace access, complete orientation and ask your team lead to approve your role.",
    answer:
      "Complete orientation and obtain your team lead’s approval before requesting workspace access.",
    page: 8,
  },
  {
    label: "Know what’s missing",
    file: "Equipment handbook.pdf",
    question: "What is the replacement cost?",
    excerpt:
      "Inspect the filter each month. Replace it when damaged. Contact the facilities team to arrange a replacement.",
    answer:
      "This excerpt explains when and how to replace the filter, but it does not specify a price.",
    page: 12,
  },
];
export function RagExamples() {
  const [selected, setSelected] = useState(0),
    [step, setStep] = useState(0),
    [paused, setPaused] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const active = useRenderActivity(ref, false),
    reduced = usePrefersReducedMotion();
  useEffect(() => {
    setStep(0);
  }, [selected]);
  useEffect(() => {
    if (!active || paused || reduced) return;
    const timer = setInterval(() => setStep((s) => (s + 1) % 5), 1800);
    return () => clearInterval(timer);
  }, [active, paused, reduced]);
  const item = examples[selected]!;
  const shown = reduced ? 4 : step;
  return (
    <Section
      id="examples"
      title="Watch a question become an answer"
      subtitle="Three simplified examples. The app chooses a search path for your question and checks evidence before combining an answer."
    >
      <div ref={ref} className="mx-auto mt-10 max-w-6xl">
        <div
          className="mb-6 flex flex-wrap justify-center gap-3"
          role="tablist"
          aria-label="Example scenarios"
        >
          {examples.map((x, i) => (
            <button
              key={x.label}
              role="tab"
              tabIndex={selected === i ? 0 : -1}
              onKeyDown={(event) => {
                if (
                  ["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)
                ) {
                  event.preventDefault();
                  const next =
                    event.key === "Home"
                      ? 0
                      : event.key === "End"
                        ? examples.length - 1
                        : (selected +
                            (event.key === "ArrowRight" ? 1 : -1) +
                            examples.length) %
                          examples.length;
                  setSelected(next);
                  document.getElementById(`example-tab-${next}`)?.focus();
                }
              }}
              aria-selected={selected === i}
              aria-controls="example-panel"
              id={`example-tab-${i}`}
              onClick={() => setSelected(i)}
              className={`rounded-full border px-5 py-3 text-sm transition-colors ${selected === i ? "border-amber-200/40 bg-amber-200/10 text-amber-100" : "text-muted-foreground hover:bg-white/5"}`}
            >
              {x.label}
            </button>
          ))}
        </div>
        <div
          id="example-panel"
          role="tabpanel"
          aria-labelledby={`example-tab-${selected}`}
          className="overflow-hidden rounded-2xl border border-white/15 bg-white/[0.025] shadow-2xl"
        >
          <div className="flex items-center justify-between border-b border-white/10 px-6 py-4 text-sm">
            <span className="flex items-center gap-2">
              <span className="size-2 rounded-full bg-amber-200" /> Document Lab{" "}
              <span className="text-muted-foreground">
                / Interactive preview
              </span>
            </span>
            <button
              aria-label={paused ? "Play preview" : "Pause preview"}
              onClick={() => setPaused((p) => !p)}
              className="rounded-md border p-2"
            >
              {paused ? <Play size={14} /> : <Pause size={14} />}
            </button>
          </div>
          <div className="grid min-h-[460px] md:grid-cols-[0.9fr_1.1fr]">
            <div className="border-b border-white/10 p-6 md:border-r md:border-b-0 sm:p-9">
              <div className="mb-6 flex items-center gap-3 text-sm text-muted-foreground">
                <FileText size={18} />
                {item.file}
              </div>
              <div className="rounded-xl border border-white/10 bg-black/20 p-6">
                <div className="mb-4 text-xs uppercase tracking-widest text-muted-foreground">
                  Source excerpt · Page {item.page}
                </div>
                <p className="font-serif text-xl leading-relaxed text-white/85">
                  {item.excerpt}
                </p>
              </div>
              <div className="mt-7 flex flex-wrap gap-2">
                {["Plan", "Retrieve", "Check", "Answer"].map((label, i) => (
                  <button
                    onClick={() => {
                      setPaused(true);
                      setStep(i + 1);
                    }}
                    key={label}
                    className={`flex items-center gap-2 rounded-full border px-3 py-2 text-xs transition-colors ${shown > i ? "border-amber-200/30 bg-amber-200/10 text-amber-100" : "text-muted-foreground"}`}
                  >
                    {shown > i ? (
                      <Check size={12} />
                    ) : (
                      <span className="size-3 rounded-full border" />
                    )}
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <div className="p-6 sm:p-9">
              <div className="ml-4 rounded-2xl bg-white/10 px-5 py-4 text-sm">
                {item.question}
              </div>
              <AnimatePresence mode="wait">
                <motion.div
                  key={`${selected}-${shown}`}
                  initial={reduced ? false : { opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.25 }}
                  className="mt-8"
                >
                  <div className="mb-4 flex items-center gap-2 text-xs text-amber-100">
                    <Search size={14} />
                    {
                      [
                        "Ready to explore",
                        "Choosing a search path",
                        "Retrieving matching passages",
                        "Checking evidence coverage",
                        "Answer with source references",
                      ][shown]
                    }
                  </div>
                  {shown < 4 ? (
                    <div className="space-y-3" aria-label="Preview processing">
                      <div className="h-2 w-5/6 rounded bg-white/10" />
                      <div className="h-2 w-4/6 rounded bg-white/10" />
                      <div className="h-2 w-3/6 rounded bg-white/10" />
                    </div>
                  ) : (
                    <>
                      <p className="text-base leading-8">
                        {item.answer}{" "}
                        <span className="text-amber-200">[1]</span>
                      </p>
                      <div className="mt-6 flex items-center gap-2 rounded-lg border border-amber-200/20 bg-amber-200/5 p-3 text-xs text-amber-100">
                        <BookOpen size={15} />
                        [1] {item.file} · Page {item.page}
                      </div>
                    </>
                  )}
                </motion.div>
              </AnimatePresence>
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/10 px-6 py-4 text-xs text-muted-foreground">
            <span>
              Simplified workflow · scripted illustration using fictional excerpts · no model calls
            </span>
            <Link
              href="/workspace"
              className="flex items-center gap-2 text-white"
            >
              Try your documents <ArrowRight size={14} />
            </Link>
          </div>
        </div>
      </div>
    </Section>
  );
}
