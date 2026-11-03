import re
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from app.providers import vector_literal


class Conflict(Exception):
    pass


class NotFound(Exception):
    pass


def recent_context(messages, max_chars):
    """Keep the newest complete messages; never load unlimited history from SQL."""
    result, used = [], 0
    for item in reversed(messages):
        line = f"{item['role']}: {item['content']}"
        if used + len(line) > max_chars:
            break
        result.append(line)
        used += len(line)
    return "\n".join(reversed(result))


def explicit_numbers(query):
    return list(
        dict.fromkeys(re.findall(r"\b(?:section|table|chapter)\s+(\d+(?:\.\d+)*)", query, re.I))
    )


class Storage:
    def __init__(self, dsn, vectors=None):
        self.vectors = vectors
        self.pool = AsyncConnectionPool(
            dsn,
            min_size=0,
            max_size=3,
            open=False,
            timeout=10,
            kwargs={"row_factory": dict_row, "prepare_threshold": None, "connect_timeout": 10},
        )

    async def documents(self):
        async with self.pool.connection() as conn:
            cur = await conn.execute("SELECT id, title, edition FROM rag.documents ORDER BY title")
            return await cur.fetchall()

    async def conversation(self, thread_id, document_ids, signature, history_limit):
        async with self.pool.connection() as conn:
            cur = await conn.execute(
                "SELECT id, embedding_signature FROM rag.documents WHERE id = ANY(%s)",
                (document_ids,),
            )
            documents = await cur.fetchall()
            if {d["id"] for d in documents} != set(document_ids):
                raise NotFound("One or more documents do not exist")
            if any(d["embedding_signature"] != signature for d in documents):
                raise Conflict("Embedding configuration differs from the indexed documents")
            if thread_id is None:
                thread_id = uuid4()
                await conn.execute(
                    "INSERT INTO rag.conversations(id, document_ids) VALUES (%s, %s)",
                    (thread_id, document_ids),
                )
                return thread_id, 0, []
            cur = await conn.execute(
                "SELECT document_ids, version FROM rag.conversations WHERE id=%s", (thread_id,)
            )
            conversation = await cur.fetchone()
            if not conversation:
                raise NotFound("Conversation does not exist")
            if set(conversation["document_ids"]) != set(document_ids):
                raise Conflict("Start a new conversation to change the document selection")
            cur = await conn.execute(
                "SELECT role, content FROM rag.messages WHERE conversation_id=%s "
                "ORDER BY id DESC LIMIT %s",
                (thread_id, history_limit),
            )
            return thread_id, conversation["version"], list(reversed(await cur.fetchall()))

    async def history(self, thread_id, before, limit):
        async with self.pool.connection() as conn:
            cur = await conn.execute("SELECT 1 FROM rag.conversations WHERE id=%s", (thread_id,))
            if not await cur.fetchone():
                raise NotFound("Conversation does not exist")
            cur = await conn.execute(
                "SELECT id, role, content, citations FROM rag.messages "
                "WHERE conversation_id=%s AND id < %s ORDER BY id DESC LIMIT %s",
                (thread_id, before, limit),
            )
            return list(reversed(await cur.fetchall()))

    async def save_turn(self, thread_id, version, question, answer, citations):
        async with self.pool.connection() as conn:
            cur = await conn.execute(
                "UPDATE rag.conversations SET version=version+1 WHERE id=%s AND version=%s "
                "RETURNING id",
                (thread_id, version),
            )
            if not await cur.fetchone():
                raise Conflict(
                    "Conversation changed during this request; retry with latest history"
                )
            await conn.execute(
                "INSERT INTO rag.messages(conversation_id, role, content, citations) "
                "VALUES (%s, 'user', %s, '[]'), (%s, 'assistant', %s, %s)",
                (thread_id, question, thread_id, answer, Jsonb(citations)),
            )

    async def search(self, query, document_ids, embedding):
        # Parameterized and document-scoped throughout. Exact references precede
        # vectors; full-text is a fallback, matching the sample's retrieval design.
        numbers = explicit_numbers(query)
        fields = """c.id, c.document_id, c.section_id, c.text, c.page, s.number,
            s.title, s.kind, d.title AS document_title, d.edition"""
        joins = """FROM rag.chunks c JOIN rag.sections s
            ON (s.document_id, s.id)=(c.document_id, c.section_id)
            JOIN rag.documents d ON d.id=c.document_id"""
        vector_docs = None
        vector_ids = None
        if embedding is not None and self.vectors is not None:
            async with self.pool.connection() as conn:
                await conn.execute("SET LOCAL statement_timeout = '15000ms'")
                cur = await conn.execute(
                    "SELECT id, vector_generation FROM rag.documents WHERE id=ANY(%s)",
                    (document_ids,),
                )
                vector_docs = await cur.fetchall()
            if {d["id"] for d in vector_docs} != set(document_ids) or any(
                not d["vector_generation"] for d in vector_docs
            ):
                raise Conflict("Documents must be migrated to Pinecone before semantic search")
            vector_ids = await self.vectors.query(
                embedding, [(d["id"], d["vector_generation"]) for d in vector_docs]
            )
        async with self.pool.connection() as conn:
            await conn.execute("SET LOCAL statement_timeout = '15000ms'")
            hits = []
            if numbers:
                cur = await conn.execute(
                    f"SELECT {fields} {joins} WHERE c.document_id=ANY(%s) "
                    "AND s.number=ANY(%s) ORDER BY c.chunk_index, c.id LIMIT 6",
                    (document_ids, numbers),
                )
                hits = await cur.fetchall()
            if vector_docs is not None:
                # Revalidate after network I/O and hold a shared row lock through
                # hydration so a concurrent reindex cannot swap generations.
                cur = await conn.execute(
                    "SELECT id, vector_generation FROM rag.documents WHERE id=ANY(%s) FOR SHARE",
                    (document_ids,),
                )
                current = await cur.fetchall()
                if {d["id"]: d["vector_generation"] for d in current} != {
                    d["id"]: d["vector_generation"] for d in vector_docs
                }:
                    raise Conflict("Document index changed during search; retry the request")
                cur = await conn.execute(
                    f"SELECT {fields} {joins} WHERE c.document_id=ANY(%s) AND c.id=ANY(%s) "
                    "ORDER BY array_position(%s::bigint[], c.id)",
                    (document_ids, vector_ids, vector_ids),
                )
            elif embedding is not None:
                vector = vector_literal(embedding)
                cur = await conn.execute(
                    f"SELECT {fields} {joins} WHERE c.document_id=ANY(%s) "
                    "ORDER BY c.embedding OPERATOR(extensions.<=>) %s::extensions.vector LIMIT 6",
                    (document_ids, vector),
                )
            else:
                cur = await conn.execute(
                    f"SELECT {fields} {joins} WHERE c.document_id=ANY(%s) "
                    "AND c.search_text @@ websearch_to_tsquery('english', %s) "
                    "ORDER BY ts_rank(c.search_text, websearch_to_tsquery('english', %s)) DESC "
                    "LIMIT 6",
                    (document_ids, query, query),
                )
            hits += await cur.fetchall()
            unique = {h["id"]: h for h in hits}
            hits = list(unique.values())[:8]
            # One bounded expansion: parents, children and explicitly referenced sections.
            for hit in hits[:3]:
                cur = await conn.execute(
                    f"SELECT {fields} {joins} WHERE c.document_id=%s AND (s.id IN "
                    "(SELECT parent_id FROM rag.sections WHERE document_id=%s AND id=%s) "
                    "OR s.parent_id=%s OR s.id IN (SELECT target_id FROM rag.section_references "
                    "WHERE document_id=%s AND source_id=%s)) "
                    "ORDER BY c.chunk_index, c.id LIMIT 2",
                    (
                        hit["document_id"],
                        hit["document_id"],
                        hit["section_id"],
                        hit["section_id"],
                        hit["document_id"],
                        hit["section_id"],
                    ),
                )
                for row in await cur.fetchall():
                    unique.setdefault(row["id"], row)
            return list(unique.values())[:10]
