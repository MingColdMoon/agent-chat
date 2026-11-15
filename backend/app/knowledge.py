from __future__ import annotations

import asyncio
import hashlib
import mimetypes
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import (
    KnowledgeChunkRecord,
    KnowledgeDocumentRecord,
    KnowledgeStateRecord,
    KnowledgeVersionRecord,
    UserRecord,
)
from app.files import extract_file_text, sanitize_filename
from app.rag import (
    _bm25_scores,
    _html_to_text,
    _normalize_document_text,
    _tokens,
    split_text_into_chunks,
)


SUPPORTED_KNOWLEDGE_EXTENSIONS = {
    ".c",
    ".cc",
    ".css",
    ".csv",
    ".docx",
    ".go",
    ".h",
    ".hpp",
    ".htm",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsonl",
    ".jsx",
    ".log",
    ".markdown",
    ".md",
    ".pdf",
    ".php",
    ".properties",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".tex",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}


class KnowledgeError(ValueError):
    pass


def _parse_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as error:
        raise KnowledgeError("知识库文档不存在") from error


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _default_title(filename: str) -> str:
    return Path(filename).stem.strip() or filename


class KnowledgeStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        root: Path,
        bootstrap_dir: Path,
        max_file_bytes: int,
    ) -> None:
        self.session_factory = session_factory
        self.root = root
        self.bootstrap_dir = bootstrap_dir
        self.max_file_bytes = max_file_bytes

    async def _get_state(
        self,
        session: AsyncSession,
        *,
        create: bool = False,
    ) -> KnowledgeStateRecord | None:
        state = await session.get(KnowledgeStateRecord, 1)
        if state is None and create:
            state = KnowledgeStateRecord(
                id=1,
                revision=0,
                bootstrap_completed=False,
            )
            session.add(state)
            await session.flush()
        return state

    async def _bump_revision(self, session: AsyncSession) -> int:
        state = await self._get_state(session, create=True)
        assert state is not None
        state.revision += 1
        state.updated_at = datetime.now(UTC)
        return state.revision

    def _validate_file(self, filename: str, data: bytes) -> tuple[str, str]:
        safe_name = sanitize_filename(filename)
        extension = Path(safe_name).suffix.lower()
        if extension not in SUPPORTED_KNOWLEDGE_EXTENSIONS:
            raise KnowledgeError(
                "不支持该知识文件类型，请使用 HTML、PDF、DOCX、Markdown 或文本文件"
            )
        if not data:
            raise KnowledgeError("知识文件不能为空")
        if len(data) > self.max_file_bytes:
            raise KnowledgeError(
                f"知识文件不能超过 {self.max_file_bytes // (1024 * 1024)} MB"
            )
        content_type = (
            mimetypes.guess_type(safe_name)[0]
            or "application/octet-stream"
        )
        return safe_name, content_type

    async def _extract_content(
        self,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> str:
        extracted, _ = await asyncio.to_thread(
            extract_file_text,
            filename,
            content_type,
            data,
        )
        extension = Path(filename).suffix.lower()
        if extension in {".html", ".htm"}:
            extracted = await asyncio.to_thread(
                _html_to_text,
                extracted or "",
            )
        return _normalize_document_text(extracted or "")

    async def _store_version(
        self,
        *,
        session: AsyncSession,
        document: KnowledgeDocumentRecord,
        version_number: int,
        filename: str,
        content_type: str,
        data: bytes,
        created_by: UUID | None,
    ) -> KnowledgeVersionRecord:
        extension = Path(filename).suffix.lower()
        version_id = uuid4()
        version_dir = self.root / str(document.id)
        version_dir.mkdir(parents=True, exist_ok=True)
        storage_path = version_dir / f"v{version_number}{extension}"
        await asyncio.to_thread(storage_path.write_bytes, data)
        extracted_text = await self._extract_content(
            filename,
            content_type,
            data,
        )
        version = KnowledgeVersionRecord(
            id=version_id,
            document_id=document.id,
            version=version_number,
            filename=filename,
            content_type=content_type,
            extension=extension,
            content_hash=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
            storage_path=str(storage_path),
            extracted_text=extracted_text,
            created_by=created_by,
        )
        session.add(version)
        await session.flush()
        chunks = split_text_into_chunks(extracted_text)
        for index, content in enumerate(chunks):
            session.add(
                KnowledgeChunkRecord(
                    id=uuid4(),
                    document_id=document.id,
                    version_id=version.id,
                    chunk_index=index,
                    content=content,
                    source_title=document.title,
                    source_filename=filename,
                )
            )
        return version

    async def create_document(
        self,
        *,
        title: str,
        filename: str,
        data: bytes,
        created_by: str | None,
    ) -> dict:
        safe_name, content_type = self._validate_file(filename, data)
        document = KnowledgeDocumentRecord(
            id=uuid4(),
            title=title.strip() or _default_title(safe_name),
            filename=safe_name,
            content_type=content_type,
            extension=Path(safe_name).suffix.lower(),
            status="active",
            current_version=1,
            created_by=_parse_uuid(created_by) if created_by else None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        try:
            async with self.session_factory() as session:
                session.add(document)
                await self._store_version(
                    session=session,
                    document=document,
                    version_number=1,
                    filename=safe_name,
                    content_type=content_type,
                    data=data,
                    created_by=document.created_by,
                )
                await self._bump_revision(session)
                await session.commit()
        except Exception:
            if document.id:
                self._delete_document_files(document.id)
            raise
        return await self.document_summary(document.id)

    async def update_document(
        self,
        document_id: str,
        *,
        title: str | None,
        filename: str | None,
        data: bytes | None,
        updated_by: str | None,
    ) -> dict:
        parsed_id = _parse_uuid(document_id)
        async with self.session_factory() as session:
            document = await session.get(KnowledgeDocumentRecord, parsed_id)
            if document is None or document.status != "active":
                raise KnowledgeError("知识库文档不存在")
            next_title = (title or "").strip() or document.title
            changed = next_title != document.title

            if data is not None and filename:
                document.title = next_title
                safe_name, content_type = self._validate_file(filename, data)
                next_version = document.current_version + 1
                await self._store_version(
                    session=session,
                    document=document,
                    version_number=next_version,
                    filename=safe_name,
                    content_type=content_type,
                    data=data,
                    created_by=(
                        _parse_uuid(updated_by) if updated_by else None
                    ),
                )
                document.filename = safe_name
                document.content_type = content_type
                document.extension = Path(safe_name).suffix.lower()
                document.current_version = next_version
                changed = True

            if changed:
                document.title = next_title
                document.updated_at = datetime.now(UTC)
                await self._bump_revision(session)
                await session.commit()
        return await self.document_summary(document_id)

    async def archive_document(self, document_id: str) -> None:
        parsed_id = _parse_uuid(document_id)
        async with self.session_factory() as session:
            document = await session.get(KnowledgeDocumentRecord, parsed_id)
            if document is None or document.status != "active":
                raise KnowledgeError("知识库文档不存在")
            document.status = "archived"
            document.deleted_at = datetime.now(UTC)
            document.updated_at = datetime.now(UTC)
            await self._bump_revision(session)
            await session.commit()

    async def bootstrap_from_directory(self) -> dict:
        async with self.session_factory() as session:
            state = await self._get_state(session, create=True)
            assert state is not None
            if state.bootstrap_completed or not self.bootstrap_dir.exists():
                return await self.status()

        files = sorted(
            path
            for path in self.bootstrap_dir.rglob("*")
            if path.is_file()
            and path.suffix.lower() in SUPPORTED_KNOWLEDGE_EXTENSIONS
            and not any(
                part.startswith(".")
                for part in path.relative_to(self.bootstrap_dir).parts
            )
        )
        for path in files:
            try:
                await self.create_document(
                    title=path.stem,
                    filename=path.name,
                    data=path.read_bytes(),
                    created_by=None,
                )
            except (OSError, KnowledgeError):
                continue

        async with self.session_factory() as session:
            state = await self._get_state(session, create=True)
            assert state is not None
            state.bootstrap_completed = True
            state.updated_at = datetime.now(UTC)
            await session.commit()
        return await self.status()

    async def document_summary(self, document_id: UUID | str) -> dict:
        parsed_id = (
            document_id
            if isinstance(document_id, UUID)
            else _parse_uuid(document_id)
        )
        async with self.session_factory() as session:
            document = await session.get(KnowledgeDocumentRecord, parsed_id)
            if document is None:
                raise KnowledgeError("知识库文档不存在")
            version = await session.scalar(
                select(KnowledgeVersionRecord).where(
                    KnowledgeVersionRecord.document_id == document.id,
                    KnowledgeVersionRecord.version == document.current_version,
                )
            )
            chunk_count = await session.scalar(
                select(func.count(KnowledgeChunkRecord.id)).where(
                    KnowledgeChunkRecord.version_id == version.id
                )
            ) if version else 0
            creator = (
                await session.get(UserRecord, document.created_by)
                if document.created_by
                else None
            )
            return self._document_to_summary(
                document,
                version,
                int(chunk_count or 0),
                creator.username if creator else "system",
            )

    async def list_documents(
        self,
        *,
        include_archived: bool = True,
    ) -> dict:
        async with self.session_factory() as session:
            query = select(KnowledgeDocumentRecord).order_by(
                KnowledgeDocumentRecord.updated_at.desc()
            )
            if not include_archived:
                query = query.where(
                    KnowledgeDocumentRecord.status == "active"
                )
            documents = (await session.scalars(query)).all()
            versions = (
                await session.scalars(select(KnowledgeVersionRecord))
            ).all()
            version_map = {
                (item.document_id, item.version): item for item in versions
            }
            chunk_counts = dict(
                (
                    await session.execute(
                        select(
                            KnowledgeChunkRecord.version_id,
                            func.count(KnowledgeChunkRecord.id),
                        ).group_by(KnowledgeChunkRecord.version_id)
                    )
                ).all()
            )
            user_ids = {
                document.created_by
                for document in documents
                if document.created_by
            }
            users = (
                (
                    await session.scalars(
                        select(UserRecord).where(UserRecord.id.in_(user_ids))
                    )
                ).all()
                if user_ids
                else []
            )
            user_map = {user.id: user.username for user in users}
            state = await self._get_state(session)
            summaries = []
            for document in documents:
                version = version_map.get(
                    (document.id, document.current_version)
                )
                summaries.append(
                    self._document_to_summary(
                        document,
                        version,
                        int(chunk_counts.get(version.id, 0)) if version else 0,
                        user_map.get(document.created_by, "system")
                        if document.created_by
                        else "system",
                    )
                )
            return {
                "revision": state.revision if state else 0,
                "documents": summaries,
            }

    async def status(self) -> dict:
        listing = await self.list_documents(include_archived=False)
        return {
            "available": True,
            "root": str(self.root),
            "source_count": len(listing["documents"]),
            "chunk_count": sum(
                document["chunk_count"]
                for document in listing["documents"]
            ),
            "revision": listing["revision"],
            "indexed_at": max(
                (
                    document["updated_at"]
                    for document in listing["documents"]
                ),
                default=None,
            ),
            "sources": [
                {
                    "id": document["id"],
                    "title": document["title"],
                    "filename": document["filename"],
                    "version": document["current_version"],
                    "chunk_count": document["chunk_count"],
                    "size_bytes": document["size_bytes"],
                }
                for document in listing["documents"]
            ],
        }

    async def list_versions(self, document_id: str) -> list[dict]:
        parsed_id = _parse_uuid(document_id)
        async with self.session_factory() as session:
            versions = (
                await session.scalars(
                    select(KnowledgeVersionRecord)
                    .where(
                        KnowledgeVersionRecord.document_id == parsed_id
                    )
                    .order_by(KnowledgeVersionRecord.version.desc())
                )
            ).all()
            user_ids = {
                version.created_by
                for version in versions
                if version.created_by
            }
            users = (
                (
                    await session.scalars(
                        select(UserRecord).where(UserRecord.id.in_(user_ids))
                    )
                ).all()
                if user_ids
                else []
            )
            user_map = {user.id: user.username for user in users}
            return [
                {
                    "id": str(version.id),
                    "version": version.version,
                    "filename": version.filename,
                    "size_bytes": version.size_bytes,
                    "content_hash": version.content_hash,
                    "created_by": (
                        user_map.get(version.created_by, "system")
                        if version.created_by
                        else "system"
                    ),
                    "created_at": _to_iso(version.created_at),
                }
                for version in versions
            ]

    async def version_file(
        self,
        document_id: str,
        version_number: int,
    ) -> KnowledgeVersionRecord | None:
        parsed_id = _parse_uuid(document_id)
        async with self.session_factory() as session:
            return await session.scalar(
                select(KnowledgeVersionRecord).where(
                    KnowledgeVersionRecord.document_id == parsed_id,
                    KnowledgeVersionRecord.version == version_number,
                )
            )

    async def search(
        self,
        *,
        query: str,
        candidate_limit: int = 24,
        top_k: int = 5,
    ) -> dict:
        normalized_query = " ".join(query.split()).strip()
        query_tokens = _tokens(normalized_query)
        async with self.session_factory() as session:
            state = await self._get_state(session)
            revision = state.revision if state else 0
            rows = (
                await session.execute(
                    select(
                        KnowledgeChunkRecord,
                        KnowledgeDocumentRecord,
                        KnowledgeVersionRecord,
                    )
                    .join(
                        KnowledgeDocumentRecord,
                        KnowledgeDocumentRecord.id
                        == KnowledgeChunkRecord.document_id,
                    )
                    .join(
                        KnowledgeVersionRecord,
                        KnowledgeVersionRecord.id
                        == KnowledgeChunkRecord.version_id,
                    )
                    .where(
                        KnowledgeDocumentRecord.status == "active",
                        KnowledgeVersionRecord.version
                        == KnowledgeDocumentRecord.current_version,
                    )
                    .order_by(KnowledgeChunkRecord.created_at.asc())
                )
            ).all()
        empty_result = {
            "query": normalized_query,
            "candidate_count": 0,
            "items": [],
            "context": "",
            "rerank": "lexical-coverage-v1",
            "knowledge_available": True,
            "revision": revision,
        }
        if not rows or not normalized_query or not query_tokens:
            return empty_result

        chunks = [row[0] for row in rows]
        document_tokens = [_tokens(chunk.content) for chunk in chunks]
        retrieval_scores = _bm25_scores(query_tokens, document_tokens)
        candidate_pairs = sorted(
            zip(rows, retrieval_scores, document_tokens),
            key=lambda item: item[1],
            reverse=True,
        )
        candidates = [
            pair for pair in candidate_pairs[:candidate_limit] if pair[1] > 0
        ]
        if not candidates:
            return empty_result

        query_token_set = set(query_tokens)
        query_compact = normalized_query.lower().replace(" ", "")
        max_retrieval = max(item[1] for item in candidates) or 1.0
        reranked = []
        for row, retrieval, doc_tokens in candidates:
            chunk, document, version = row
            token_set = set(doc_tokens)
            coverage = len(query_token_set & token_set) / max(
                1,
                len(query_token_set),
            )
            content_compact = chunk.content.lower().replace(" ", "")
            phrase = 1.0 if query_compact in content_compact else 0.0
            filename_tokens = set(_tokens(document.filename))
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
            reranked.append(
                (
                    chunk,
                    document,
                    version,
                    retrieval,
                    rerank_score,
                    coverage,
                )
            )

        reranked.sort(key=lambda item: item[4], reverse=True)
        items = [
            {
                "document_id": str(document.id),
                "title": document.title,
                "filename": document.filename,
                "version": version.version,
                "content_hash": version.content_hash,
                "chunk_index": chunk.chunk_index,
                "retrieval_score": round(retrieval, 4),
                "rerank_score": round(rerank_score, 4),
                "coverage": round(coverage, 4),
                "preview": " ".join(chunk.content.split())[:360],
            }
            for (
                chunk,
                document,
                version,
                retrieval,
                rerank_score,
                coverage,
            ) in reranked[:top_k]
        ]
        context_sections = [
            (
                f'<knowledge_chunk title="{document.title}" '
                f'source="{document.filename}" version="{version.version}" '
                f'chunk="{chunk.chunk_index + 1}" '
                f'revision="{revision}" '
                f'rerank="{rerank_score:.4f}">\n'
                f"{chunk.content}\n"
                "</knowledge_chunk>"
            )
            for (
                chunk,
                document,
                version,
                _,
                rerank_score,
                _,
            ) in reranked[:top_k]
        ]
        return {
            "query": normalized_query,
            "candidate_count": len(candidates),
            "items": items,
            "context": "\n\n".join(context_sections),
            "rerank": "lexical-coverage-v1",
            "knowledge_available": True,
            "revision": revision,
        }

    @staticmethod
    def _document_to_summary(
        document: KnowledgeDocumentRecord,
        version: KnowledgeVersionRecord | None,
        chunk_count: int,
        created_by: str,
    ) -> dict:
        return {
            "id": str(document.id),
            "title": document.title,
            "filename": document.filename,
            "content_type": document.content_type,
            "extension": document.extension,
            "status": document.status,
            "current_version": document.current_version,
            "chunk_count": chunk_count,
            "size_bytes": version.size_bytes if version else 0,
            "created_by": created_by,
            "created_at": _to_iso(document.created_at),
            "updated_at": _to_iso(document.updated_at),
        }

    def _delete_document_files(self, document_id: UUID) -> None:
        directory = self.root / str(document_id)
        if not directory.exists():
            return
        for path in directory.rglob("*"):
            if path.is_file():
                path.unlink(missing_ok=True)
        for path in sorted(directory.rglob("*"), reverse=True):
            if path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    pass
        try:
            directory.rmdir()
        except OSError:
            pass
