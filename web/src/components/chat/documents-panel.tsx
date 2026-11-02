"use client";
import { useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { FileText, Loader2, RefreshCw, Upload } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { useSidebar } from "@/components/ui/sidebar";
import { useChatStore } from "@/core/chat/store";
export function DocumentsPanel() {
  const {
    documents,
    selectedIds,
    setSelectedIds,
    refreshDocuments,
    documentsError,
    threads,
    isStreaming,
  } = useChatStore();
  const pathname = usePathname(),
    router = useRouter(),
    { open, isMobile, setOpen } = useSidebar();
  const thread = threads.find((t) => pathname.endsWith("/" + t.id));
  const locked = !!thread?.messages.length;
  const selection = thread?.documentIds ?? selectedIds;
  const input = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false),
    [status, setStatus] = useState("");
  if (!open && !isMobile)
    return (
      <Button
        variant="ghost"
        size="icon"
        aria-label="Expand document library"
        onClick={() => setOpen(true)}
      >
        <FileText size={16} />
      </Button>
    );
  async function upload(file: File) {
    if (file.size > 10 * 1024 * 1024 || !file.size) {
      toast.error("Choose a nonempty file no larger than 10 MB.");
      return;
    }
    setUploading(true);
    setStatus(`Indexing ${file.name}… Keep this page open.`);
    try {
      const r = await fetch(
        "/api/rag/documents/upload?filename=" + encodeURIComponent(file.name),
        {
          method: "POST",
          headers: { "Content-Type": "application/octet-stream" },
          body: file,
          signal: AbortSignal.timeout(1830000),
        },
      );
      const data = await r.json();
      if (!r.ok)
        throw new Error(
          typeof data.detail === "string" ? data.detail : "Upload failed.",
        );
      await refreshDocuments();
      setSelectedIds([data.id]);
      setStatus(`Indexed ${data.title} · ${data.chunks} chunks`);
      router.push("/workspace/chats/new");
      toast.success("Document ready. Ask your first question.");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Upload failed");
      toast.error(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
      if (input.current) input.current.value = "";
    }
  }
  return (
    <section className="px-2 py-3" aria-label="Document library">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-muted-foreground text-xs font-medium">
          Sources · {selection.length}/5
        </h2>
        <Button
          size="icon-sm"
          variant="ghost"
          aria-label="Refresh documents"
          onClick={() => void refreshDocuments()}
        >
          <RefreshCw className="size-3" />
        </Button>
      </div>
      <Button
        className="mb-3 w-full gap-2"
        variant="outline"
        size="sm"
        disabled={uploading || threads.some((t) => isStreaming(t.id))}
        onClick={() => input.current?.click()}
      >
        {uploading ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <Upload className="size-4" />
        )}
        {uploading ? "Indexing document…" : "Upload document"}
      </Button>
      <input
        ref={input}
        type="file"
        accept=".pdf,.txt,.md"
        className="hidden"
        aria-label="Upload file"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void upload(f);
        }}
      />
      {status && (
        <p
          role="status"
          className="text-muted-foreground mb-3 text-xs break-words"
        >
          {status}
        </p>
      )}
      {documentsError ? (
        <p role="alert" className="text-destructive text-xs">
          {documentsError}
        </p>
      ) : documents.length === 0 ? (
        <p className="text-muted-foreground text-xs">
          Upload a document to get started.
        </p>
      ) : (
        <div className="max-h-60 space-y-1 overflow-y-auto">
          {documents.map((d) => (
            <label
              key={d.id}
              className={`flex cursor-pointer items-start gap-2 rounded-md border p-2 text-xs transition-colors ${selection.includes(d.id) ? "bg-accent border-border" : "border-transparent hover:bg-accent/50"}`}
            >
              <input
                type="checkbox"
                className="mt-0.5"
                checked={selection.includes(d.id)}
                disabled={locked || uploading}
                onChange={(e) => {
                  if (e.target.checked && selection.length >= 5) {
                    toast.error("Select up to five documents.");
                    return;
                  }
                  setSelectedIds(
                    e.target.checked
                      ? [...selection, d.id]
                      : selection.filter((id) => id !== d.id),
                  );
                }}
              />
              <span className="min-w-0 break-words">
                {d.title}
                <small className="text-muted-foreground mt-1 block">
                  {d.edition}
                </small>
              </span>
            </label>
          ))}
        </div>
      )}
      {locked && (
        <p className="text-muted-foreground mt-2 text-xs">
          Start a new chat to change sources.
        </p>
      )}
      <details className="text-muted-foreground mt-3 text-xs">
        <summary className="cursor-pointer">Upload limits</summary>
        <p className="mt-2 leading-5">
          PDF, TXT, Markdown. 10 MB, 100 pages, 1 million characters, 600
          chunks. Scanned PDFs need OCR. Indexing can take up to 30 minutes.
        </p>
      </details>
    </section>
  );
}
