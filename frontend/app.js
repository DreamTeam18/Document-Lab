import { readEvents } from "/static/stream.js";

const $ = (id) => document.getElementById(id);
let thread = null, busy = false, connected = false;
const selected = () => Array.from(document.querySelectorAll("#documents input:checked"), el => el.value);

function controls() {
  $("send").disabled = busy || !connected || !selected().length;
  $("connect").disabled = busy;
  $("upload").disabled = busy;
  $("new-chat").disabled = busy;
  $("question").disabled = busy;
  document.querySelectorAll("#documents input").forEach(el => { el.disabled = busy || !!thread; });
  $("count").textContent = `${selected().length} selected`;
  $("thread").textContent = thread ? `SESSION ${thread.slice(0, 8)}` : "NEW SESSION";
  $("thread").title = thread || "";
}

function resetChat() {
  thread = null;
  $("messages").querySelectorAll(".message").forEach(el => el.remove());
  $("empty").hidden = false;
  $("progress").textContent = connected ? "Select documents and send a question." : "Connect and select a document to begin.";
  controls();
}

function message(role, text, citations = [], warnings = []) {
  $("empty").hidden = true;
  const article = document.createElement("article");
  article.className = `message ${role}`;
  const label = document.createElement("div"); label.className = "role"; label.textContent = role;
  const body = document.createElement("div"); body.className = "body"; body.textContent = text;
  article.append(label, body);
  if (citations.length) {
    const sources = document.createElement("div"); sources.className = "sources"; sources.textContent = "Sources";
    for (const cite of citations) {
      const source = document.createElement("div"); source.className = "source";
      source.textContent = `[${cite.citation}] ${cite.document_title} · ${cite.edition} · ${cite.kind} ${cite.number}${cite.page ? ` · Page ${cite.page}` : ""}`;
      sources.append(source);
    }
    article.append(sources);
  }
  for (const warning of warnings) {
    const p = document.createElement("p"); p.className = "warning"; p.textContent = warning; article.append(p);
  }
  $("messages").append(article);
  article.scrollIntoView({ block: "nearest" });
}

async function requireOK(response) {
  if (response.ok) return response;
  let detail;
  try { detail = (await response.json()).detail; } catch { /* Non-JSON server error. */ }
  throw new Error(typeof detail === "string" ? detail : `Request failed (HTTP ${response.status}).`);
}

async function loadDocuments(selectId = null) {
  if (busy) return;
  busy = true; connected = false; resetChat();
  $("connection").className = "status";
  $("connection").textContent = "Connecting…";
  $("documents").replaceChildren();
  try {
    const response = await requireOK(await fetch("/documents", { signal: AbortSignal.timeout(20000) }));
    const documents = await response.json();
    for (const doc of documents) {
      const label = document.createElement("label"); label.className = "document";
      const input = document.createElement("input"); input.type = "checkbox"; input.value = doc.id; input.checked = doc.id === selectId;
      input.addEventListener("change", () => {
        if (selected().length > 5) { input.checked = false; $("progress").textContent = "Choose at most five documents."; }
        controls();
      });
      const text = document.createElement("span"); text.textContent = doc.title;
      const edition = document.createElement("small"); edition.textContent = doc.edition; text.append(edition);
      label.append(input, text); $("documents").append(label);
    }
    connected = true;
    $("connection").textContent = `Connected · ${documents.length} document${documents.length === 1 ? "" : "s"}`;
    if (!documents.length) $("documents").textContent = "No indexed documents yet. Use Upload document to add your first file.";
    $("progress").textContent = "Select a document to begin.";
  } catch (error) {
    $("connection").className = "status error";
    $("connection").textContent = error.message;
    $("documents").textContent = "Check your backend database configuration, then reconnect.";
  } finally { busy = false; controls(); }
}

$("connect-form").addEventListener("submit", event => {
  event.preventDefault();
  loadDocuments();
});

$("question-form").addEventListener("submit", async event => {
  event.preventDefault();
  const question = $("question").value.trim();
  if (busy || !connected || !question || !selected().length) return;
  busy = true; controls(); message("user", question);
  $("progress").textContent = "Starting retrieval…";
  let completed = false;
  const abort = new AbortController();
  const deadline = setTimeout(() => abort.abort(), 250000);
  try {
    const response = await requireOK(await fetch("/query", {
      method: "POST", signal: abort.signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_query: question, document_ids: selected(), thread_id: thread })
    }));
    if (!response.body) throw new Error("Streaming is unavailable in this browser.");
    const stages = { plan: "Search planned", retrieve: "Evidence retrieved", assess: "Evidence checked", refine: "Search refined", answer: "Answer prepared" };
    await readEvents(response.body, (name, data) => {
      if (name === "session") { thread = data.thread_id; controls(); }
      if (name === "progress") $("progress").textContent = `${stages[data.step] || data.step}…`;
      if (name === "error") throw new Error(data.message || "Query failed.");
      if (name === "result") {
        completed = true;
        message("assistant", data.answer, data.citations || [], data.warnings || []);
        $("question").value = "";
        $("progress").textContent = "Complete. Ask a follow-up or start a new chat.";
      }
    });
    if (!completed) throw new Error("Connection ended before an answer arrived. Retry your question.");
  } catch (error) {
    abort.abort();
    message("error", error.name === "AbortError" ? "Request timed out. Try a narrower question." : error.message);
    $("progress").textContent = "Request failed. Your question is kept below for retry.";
  } finally { clearTimeout(deadline); busy = false; controls(); $("question").focus(); }
});

$("new-chat").addEventListener("click", resetChat);
$("example").addEventListener("click", () => { $("question").value = "What must archive labels contain?"; $("question").focus(); });
$("question").addEventListener("keydown", event => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault(); $("question-form").requestSubmit();
  }
});
controls();


$("upload").addEventListener("click", () => $("upload-file").click());
$("upload-file").addEventListener("change", async () => {
  const file = $("upload-file").files[0];
  if (!file || busy) return;
  const status = $("upload-status");
  status.hidden = false; status.className = "status";
  if (file.size > 10 * 1024 * 1024 || !file.size) {
    status.textContent = "Choose a nonempty file no larger than 10 MB.";
    status.className = "status error"; $("upload-file").value = ""; return;
  }
  busy = true; controls();
  status.textContent = `Uploading and indexing ${file.name}… Large documents can take up to 30 minutes. Keep this page open.`;
  let uploaded;
  try {
    const response = await requireOK(await fetch(`/documents/upload?filename=${encodeURIComponent(file.name)}`, {
      method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: file,
      signal: AbortSignal.timeout(1830000)
    }));
    uploaded = await response.json();
    status.textContent = `Indexed ${uploaded.title} · ${uploaded.chunks} text chunks. Starting a new chat.`;
  } catch (error) {
    status.className = "status error";
    status.textContent = error.name === "TimeoutError" ? "Upload timed out. Refresh the document list before retrying." : error.message;
  } finally { busy = false; $("upload-file").value = ""; controls(); }
  if (uploaded) await loadDocuments(uploaded.id);
});


$("sidebar-toggle").addEventListener("click", () => {
  const open = document.body.classList.toggle("sidebar-open");
  $("sidebar-toggle").setAttribute("aria-expanded", String(open));
});
document.addEventListener("keydown", event => {
  if (event.key === "Escape") {
    document.body.classList.remove("sidebar-open");
    $("sidebar-toggle").setAttribute("aria-expanded", "false");
  }
});
document.querySelectorAll("[data-question]").forEach(button => {
  button.addEventListener("click", () => {
    $("question").value = button.dataset.question;
    $("question").focus();
  });
});
loadDocuments();
