import {
  SearchIcon,
  CompassIcon,
  GraduationCapIcon,
  type LucideIcon,
  MicroscopeIcon,
  PenLineIcon,
  ShapesIcon,
} from "lucide-react";

/** Brand and capability copy for the RAG frontend. */

export type ChatSuggestion = {
  label: string;
  prompt: string;
  icon: LucideIcon;
};

export const site = {
  name: "Document Lab",
  /** Shown when the sidebar is collapsed to its icon rail. */
  shortName: "DL",
  description: "Explore your documents with evidence-grounded answers.",
  repositoryUrl: "/workspace",
  /** The SVG silhouette the hero's flickering grid is masked to. */
  logoMaskUrl: "/images/landing-logo-mask.svg",

  header: {
    links: [
      { href: "/workspace", label: "Workspace" },
      { href: "#examples", label: "Examples" },
    ],
    ctaLabel: "Open workspace",
  },

  hero: {
    title: "Document Lab",
    rotatingWords: [
      "Explore the details",
      "Find the evidence",
      "Connect your sources",
      "Ask better questions",
    ],
    rotatingSuffix: "",
    description:
      "A workspace for the knowledge. Bring your documents, ask a question, and follow the answer back to its source.",
    ctaLabel: "Explore your documents",
    ctaHref: "/workspace",
  },

  whatsNew: {
    title: "Built for a closer reading",
    subtitle:
      "From your first question to the supporting passage, keep the evidence in view.",
    features: [
      {
        label: "Your library",
        title: "Bring your documents",
        description:
          "Upload PDF, TXT, or Markdown. Search across up to five selected sources.",
      },
      {
        label: "Agentic retrieval",
        title: "Break down complex questions",
        description:
          "Simple questions go straight to document search. Complex questions can be split into smaller questions, with independent searches running together.",
      },
      {
        label: "Evidence",
        title: "Sources beside answers",
        description:
          "Answers combine evidence across your questions, with document titles, editions, section references, and available page numbers beside citations.",
      },
      {
        label: "Context",
        title: "Follow the conversation",
        description:
          "Ask follow-up questions using a bounded window of recent exchanges.",
      },
      {
        label: "Transparency",
        title: "Know the limits",
        description:
          "Evidence is checked for each question. A focused follow-up search can fill gaps; unresolved gaps and failed searches are reported.",
      },
      {
        label: "Your workspace",
        title: "Follow the answer as it arrives",
        description:
          "Watch the answer appear as it is generated. The completed response replaces the draft after its citation references are checked.",
      },
    ],
  },

  footer: {
    quote: "Less searching. More understanding.",
  },

  chat: {
    greeting: "What would you like to understand?",
    description:
      "Upload or select documents, then ask a question or compare details. Follow the search progress, streamed answer, and cited sources.",
    placeholder: "Ask a question about your documents…",
    disclaimer: "Answers can make mistakes. Check the cited sources.",
    surpriseMe: {
      label: "Demo question",
      prompt: "What must archive labels contain?",
    },
    createLabel: "Explore",
    suggestions: [
      {
        label: "Summarize",
        prompt: "Summarize the main points about [topic] in my documents",
        icon: PenLineIcon,
      },
      {
        label: "Research",
        prompt: "Find the requirements for [topic] in my documents.",
        icon: MicroscopeIcon,
      },
      {
        label: "Compare",
        prompt: "Compare what my selected documents say about [topic].",
        icon: ShapesIcon,
      },
      {
        label: "Learn",
        prompt: "Explain [topic] using my selected documents.",
        icon: GraduationCapIcon,
      },
    ] satisfies ChatSuggestion[],
    createSuggestions: [
      {
        label: "Find exceptions",
        prompt: "What exceptions do these documents mention?",
        icon: SearchIcon,
      },
      {
        label: "Next steps",
        prompt: "Which instructions should I follow first?",
        icon: CompassIcon,
      },
    ] satisfies ChatSuggestion[],
    models: [{ name: "default", displayName: "Configured OpenRouter model" }],
    placeholderNav: [] as { label: string; icon: LucideIcon }[],
  },
};
