import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi import Query as QueryParam
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models import Query
from app.pinecone import PineconeVectors
from app.providers import ProviderError, Providers
from app.storage import Conflict, NotFound, Storage, recent_context
from app.uploads import MAX_BYTES, extract_document
from app.workflow import Workflow
from scripts.ingest import ingest

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app):
    config = settings()
    app.state.storage = None
    async with httpx.AsyncClient(timeout=45) as client:
        app.state.providers = Providers(config, client)
        if config.database_url.get_secret_value():
            vectors = (
                PineconeVectors(config, client) if config.vector_backend == "pinecone" else None
            )
            store = Storage(config.database_url.get_secret_value(), vectors)
            await store.pool.open()
            app.state.storage = store
        try:
            yield
        finally:
            if app.state.storage:
                await app.state.storage.pool.close()


app = FastAPI(title="Agentic RAG Clone", lifespan=lifespan)
frontend = Path(__file__).resolve().parent.parent / "frontend"


class LocalFrontendFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store"
        return response


app.mount("/static", LocalFrontendFiles(directory=frontend), name="static")


@app.get("/", include_in_schema=False)
async def test_interface():
    return RedirectResponse(settings().web_frontend_url, status_code=307)


@app.get("/legacy", include_in_schema=False)
async def legacy_landing():
    return FileResponse(frontend / "landing.html", headers={"Cache-Control": "no-store"})


@app.get("/chat", include_in_schema=False)
async def chat_interface():
    return RedirectResponse(settings().web_frontend_url + "/workspace/chats/new", status_code=307)


@app.get("/legacy/chat", include_in_schema=False)
async def legacy_chat():
    return FileResponse(frontend / "index.html", headers={"Cache-Control": "no-store"})


if settings().cors_origin:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings().cors_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )


def storage(request: Request):
    store = getattr(request.app.state, "storage", None)
    if store is None:
        raise HTTPException(503, "DATABASE_URL is not configured")
    return store


@app.get("/health")
async def health():
    return {"status": "ok", "service": "agentic-rag-clone"}


@app.get("/documents")
async def documents(store=Depends(storage)):
    return await store.documents()


@app.get("/conversations/{thread_id}/messages")
async def messages(
    thread_id: UUID,
    before: int = QueryParam(default=2**63 - 1, ge=1),
    limit: int = QueryParam(default=20, ge=1, le=50),
    store=Depends(storage),
):
    try:
        return await store.history(thread_id, before, limit)
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from exc


def event(name, data):
    return f"event: {name}\ndata: {json.dumps(data, default=str)}\n\n"


@app.post("/query")
async def query(body: Query, request: Request, store=Depends(storage)):
    config = settings()
    try:
        thread_id, version, history = await store.conversation(
            body.thread_id,
            body.document_ids,
            config.embedding_signature,
            config.history_exchanges * 2,
        )
    except NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc

    async def stream():
        yield event("session", {"thread_id": thread_id})
        workflow = Workflow(request.app.state.providers, store, stream_answer=True)
        final = {}
        try:
            async with asyncio.timeout(config.request_timeout_seconds):
                async for mode, update in workflow.graph.astream(
                    {
                        "question": body.user_query,
                        "document_ids": body.document_ids,
                        "history": recent_context(history, config.history_max_chars),
                    },
                    stream_mode=["updates", "custom"],
                ):
                    if mode == "custom":
                        yield event("token", update)
                        continue
                    for step, values in update.items():
                        final.update(values)
                        yield event("progress", {"step": step, "status": "completed"})
                await store.save_turn(
                    thread_id, version, body.user_query, final["answer"], final["citations"]
                )
                yield event(
                    "result",
                    {
                        "thread_id": thread_id,
                        "answer": final["answer"],
                        "citations": final["citations"],
                        "warnings": list(dict.fromkeys(final.get("warnings", []))),
                    },
                )
        except TimeoutError:
            yield event("error", {"message": "Request timed out; retry with a narrower question."})
        except (ProviderError, Conflict) as exc:
            yield event("error", {"message": str(exc)})
        except Exception as exc:
            # Do not log database DSNs, prompts, provider bodies or exception messages.
            logger.error("Query failed (%s)", type(exc).__name__)
            yield event("error", {"message": "Request failed. Check backend configuration."})

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


@app.post("/documents/upload", status_code=201)
async def upload_document(
    request: Request,
    filename: str = QueryParam(min_length=1, max_length=255),
    store=Depends(storage),
):
    data = bytearray()
    async for part in request.stream():
        if len(data) + len(part) > MAX_BYTES:
            raise HTTPException(413, "File exceeds 10 MB.")
        data.extend(part)
    try:
        document = await asyncio.to_thread(extract_document, filename, bytes(data))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        async with asyncio.timeout(settings().upload_timeout_seconds):
            count = await ingest(document, settings(), request.app.state.providers)
    except TimeoutError:
        raise HTTPException(504, "Indexing timed out. Try a smaller document.") from None
    except ProviderError as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        logger.error("Upload failed (%s)", type(exc).__name__)
        raise HTTPException(500, "Indexing failed. Check backend configuration.") from None
    return {
        "id": document.id,
        "title": document.title,
        "edition": document.edition,
        "chunks": count,
    }
