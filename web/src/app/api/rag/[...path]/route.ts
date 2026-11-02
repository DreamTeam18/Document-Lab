import { Agent, fetch } from "undici";

const uploadDispatcher = new Agent({
  headersTimeout: 1830000,
  bodyTimeout: 1830000,
  connectTimeout: 10000,
});
export const dynamic = "force-dynamic";
const origin = process.env.RAG_BACKEND_URL || "http://127.0.0.1:8001";
async function proxy(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  const endpoint = path.join("/");
  if (
    !/^(documents|documents\/upload|query|health|conversations\/[0-9a-f-]+\/messages)$/.test(
      endpoint,
    )
  )
    return new Response("Not found", { status: 404 });
  const url = new URL(request.url);
  try {
    const response = await fetch(`${origin}/${endpoint}${url.search}`, {
      method: request.method,
      headers: {
        "Content-Type":
          request.headers.get("content-type") || "application/json",
      },
      body: request.method === "GET" ? undefined : request.body,
      // Stream uploaded bytes and SSE responses without buffering the whole exchange.
      duplex: "half",
      ...(endpoint === "documents/upload"
        ? { dispatcher: uploadDispatcher }
        : {}),
      cache: "no-store",
      signal: request.signal,
    } as Parameters<typeof fetch>[1]);
    // Undici uses Node stream types; Next Response uses the DOM declaration
    // of the same runtime Web ReadableStream. Keep the body streaming.
    return new Response(response.body as ReadableStream<Uint8Array> | null, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("content-type") || "application/json",
        "Cache-Control": "no-store",
        "X-Accel-Buffering": "no",
      },
    });
  } catch {
    return Response.json(
      { detail: "Backend unavailable. Check that the RAG server is running." },
      { status: 502 },
    );
  }
}
export { proxy as GET, proxy as POST };
