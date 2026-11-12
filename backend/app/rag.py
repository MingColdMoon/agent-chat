from __future__ import annotations

import math
import re
from collections import Counter
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import RagChunkRecord


CHUNK_SIZE = 900
CHUNK_OVERLAP = 120
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]+")


def _parse_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as error:
        raise KeyError(value) from error


def split_text_into_chunks(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").strip()
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + CHUNK_SIZE)
        if end < len(normalized):
            boundary = max(
                normalized.rfind("\n\n", start, end),
                normalized.rfind("\n", start, end),
                normalized.rfind("。", start, end),
            )
            if boundary > start + CHUNK_SIZE // 2:
                end = boundary + 1
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(start + 1, end - CHUNK_OVERLAP)
    return chunks


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for match in TOKEN_PATTERN.findall(text.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", match):
            if len(match) <= 12:
                tokens.append(match)
            tokens.extend(
                match[index : index + 2]
                for index in range(max(0, len(match) - 1))
            )
        else:
            tokens.append(match)
    return tokens


def _bm25_scores(
    query_tokens: list[str],
    documents: list[list[str]],
) -> list[float]:
    if not documents:
        return []
    query_terms = list(dict.fromkeys(query_tokens))
    document_frequencies = Counter()
    for tokens in documents:
        token_set = set(tokens)
        for term in query_terms:
            if term in token_set:
                document_frequencies[term] += 1

    average_length = sum(len(tokens) for tokens in documents) / len(documents)
    average_length = max(1.0, average_length)
    document_count = len(documents)
    scores: list[float] = []
    for tokens in documents:
        frequencies = Counter(tokens)
        score = 0.0
        for term in query_terms:
            frequency = frequencies.get(term, 0)
            if frequency == 0:
                continue
            document_frequency = document_frequencies[term]
            inverse_frequency = math.log(
                1 + (document_count - document_frequency + 0.5)
                / (document_frequency + 0.5)
            )
            denominator = frequency + 1.5 * (
                1 - 0.75 + 0.75 * len(tokens) / average_length
            )
            score += inverse_frequency * (
                frequency * 2.5 / denominator
            )
        scores.append(score)
    return scores


class RagStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.session_factory = session_factory

    async def index_attachment(
        self,
        *,
        attachment_id: str,
        user_id: str,
        conversation_id: str,
        filename: str,
        text: str | None,
    ) -> int:
        parsed_attachment = _parse_uuid(attachment_id)
        parsed_user = _parse_uuid(user_id)
        parsed_conversation = _parse_uuid(conversation_id)
        chunks = split_text_into_chunks(text or "")
        async with self.session_factory() as session:
            await session.execute(
                delete(RagChunkRecord).where(
                    RagChunkRecord.attachment_id == parsed_attachment
                )
            )
            for index, content in enumerate(chunks):
                session.add(
                    RagChunkRecord(
                        id=uuid4(),
                        attachment_id=parsed_attachment,
                        user_id=parsed_user,
                        conversation_id=parsed_conversation,
                        chunk_index=index,
                        content=content,
                        filename=filename,
                    )
                )
            await session.commit()
        return len(chunks)

    async def search(
        self,
        *,
        user_id: str,
        conversation_id: str,
        query: str,
        candidate_limit: int = 24,
        top_k: int = 5,
    ) -> dict:
        parsed_user = _parse_uuid(user_id)
        parsed_conversation = _parse_uuid(conversation_id)
        normalized_query = " ".join(query.split()).strip()
        query_tokens = _tokens(normalized_query)
        if not normalized_query or not query_tokens:
            return {
                "query": normalized_query,
                "candidate_count": 0,
                "items": [],
                "context": "",
                "rerank": "lexical-coverage-v1",
            }

        async with self.session_factory() as session:
            chunks = (
                await session.scalars(
                    select(RagChunkRecord)
                    .where(
                        RagChunkRecord.user_id == parsed_user,
                        RagChunkRecord.conversation_id == parsed_conversation,
                    )
                    .order_by(RagChunkRecord.created_at.asc())
                )
            ).all()
        if not chunks:
            return {
                "query": normalized_query,
                "candidate_count": 0,
                "items": [],
                "context": "",
                "rerank": "lexical-coverage-v1",
            }

        document_tokens = [_tokens(chunk.content) for chunk in chunks]
        retrieval_scores = _bm25_scores(query_tokens, document_tokens)
        candidate_pairs = sorted(
            zip(chunks, retrieval_scores, document_tokens),
            key=lambda item: item[1],
            reverse=True,
        )
        candidates = [
            pair for pair in candidate_pairs[:candidate_limit] if pair[1] > 0
        ]
        if not candidates:
            return {
                "query": normalized_query,
                "candidate_count": 0,
                "items": [],
                "context": "",
                "rerank": "lexical-coverage-v1",
            }

        query_token_set = set(query_tokens)
        query_compact = normalized_query.lower().replace(" ", "")
        max_retrieval = max(item[1] for item in candidates) or 1.0
        reranked: list[tuple[RagChunkRecord, float, float, float]] = []
        for chunk, retrieval, doc_tokens in candidates:
            token_set = set(doc_tokens)
            coverage = len(query_token_set & token_set) / max(
                1,
                len(query_token_set),
            )
            content_compact = chunk.content.lower().replace(" ", "")
            phrase = 1.0 if query_compact in content_compact else 0.0
            filename_tokens = set(_tokens(chunk.filename))
            filename_match = len(query_token_set & filename_tokens) / max(
                1,
                len(query_token_set),
            )
            normalized_retrieval = retrieval / max_retrieval
            rerank_score = (
                normalized_retrieval * 0.55
                + coverage * 0.30
                + phrase * 0.10
                + filename_match * 0.05
            )
            reranked.append((chunk, retrieval, rerank_score, coverage))

        reranked.sort(key=lambda item: item[2], reverse=True)
        items = [
            {
                "attachment_id": str(chunk.attachment_id),
                "filename": chunk.filename,
                "chunk_index": chunk.chunk_index,
                "retrieval_score": round(retrieval, 4),
                "rerank_score": round(rerank_score, 4),
                "coverage": round(coverage, 4),
                "preview": " ".join(chunk.content.split())[:360],
            }
            for chunk, retrieval, rerank_score, coverage in reranked[:top_k]
        ]
        context_sections = [
            (
                f'<knowledge_chunk source="{chunk.filename}" '
                f'chunk="{chunk.chunk_index + 1}" '
                f'rerank="{rerank_score:.4f}">\n'
                f"{chunk.content}\n"
                "</knowledge_chunk>"
            )
            for chunk, _, rerank_score, _ in reranked[:top_k]
        ]
        return {
            "query": normalized_query,
            "candidate_count": len(candidates),
            "items": items,
            "context": "\n\n".join(context_sections),
            "rerank": "lexical-coverage-v1",
        }
