from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


JSON_VALUE = JSON().with_variant(JSONB, "postgresql")


def utc_now_datetime() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class UserRecord(Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(
        String(16),
        default="user",
        server_default="user",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now_datetime,
    )


class AgentRecord(Base):
    __tablename__ = "agents"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    slug: Mapped[str | None] = mapped_column(
        String(80),
        unique=True,
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(40))
    icon: Mapped[str] = mapped_column(String(32), default="bot")
    instructions: Mapped[str] = mapped_column(Text)
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now_datetime,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now_datetime,
    )


class ConversationRecord(Base):
    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    agent_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(120), default="新会话")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now_datetime,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now_datetime,
        index=True,
    )


class MessageRecord(Base):
    __tablename__ = "messages"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    tools: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON_VALUE,
        default=list,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    activity: Mapped[dict[str, Any] | None] = mapped_column(
        "agui_activity",
        JSON_VALUE,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now_datetime,
        index=True,
    )

    __table_args__ = (
        Index(
            "ix_messages_conversation_created",
            "conversation_id",
            "created_at",
        ),
    )


class AttachmentRecord(Base):
    __tablename__ = "attachments"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    extension: Mapped[str] = mapped_column(String(32), default="")
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_path: Mapped[str] = mapped_column(Text)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    excerpt: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now_datetime,
        index=True,
    )


class MessageAttachmentRecord(Base):
    __tablename__ = "message_attachments"

    message_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("messages.id", ondelete="CASCADE"),
        primary_key=True,
    )
    attachment_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("attachments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now_datetime,
    )


class RagChunkRecord(Base):
    __tablename__ = "rag_chunks"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    attachment_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("attachments.id", ondelete="CASCADE"),
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    conversation_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    filename: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now_datetime,
        index=True,
    )

    __table_args__ = (
        Index(
            "ix_rag_chunks_conversation_attachment",
            "conversation_id",
            "attachment_id",
        ),
    )


class ProjectRagDocumentRecord(Base):
    __tablename__ = "rag_documents"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_path: Mapped[str] = mapped_column(
        String(500),
        unique=True,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    content_hash: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now_datetime,
    )
    file_modified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now_datetime,
    )


class ProjectRagChunkRecord(Base):
    __tablename__ = "rag_project_chunks"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("rag_documents.id", ondelete="CASCADE"),
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    source_path: Mapped[str] = mapped_column(String(500))
    filename: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now_datetime,
        index=True,
    )

    __table_args__ = (
        Index(
            "ix_rag_project_chunks_document_chunk",
            "document_id",
            "chunk_index",
        ),
    )


class KnowledgeDocumentRecord(Base):
    __tablename__ = "knowledge_documents"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(200))
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    extension: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now_datetime,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now_datetime,
        index=True,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class KnowledgeVersionRecord(Base):
    __tablename__ = "knowledge_versions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(120))
    extension: Mapped[str] = mapped_column(String(32), default="")
    content_hash: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_path: Mapped[str] = mapped_column(Text)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now_datetime,
    )

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "version",
            name="uq_knowledge_document_version",
        ),
    )


class KnowledgeChunkRecord(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
        index=True,
    )
    version_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("knowledge_versions.id", ondelete="CASCADE"),
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    source_title: Mapped[str] = mapped_column(String(200))
    source_filename: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now_datetime,
    )

    __table_args__ = (
        Index(
            "ix_knowledge_chunks_version_chunk",
            "version_id",
            "chunk_index",
        ),
    )


class KnowledgeStateRecord(Base):
    __tablename__ = "knowledge_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    bootstrap_completed: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now_datetime,
    )


class Database:
    def __init__(self, database_url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(
            database_url,
            pool_pre_ping=True,
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            expire_on_commit=False,
        )

    async def initialize(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            if connection.dialect.name == "postgresql":
                await connection.execute(
                    text(
                        "ALTER TABLE conversations "
                        "ADD COLUMN IF NOT EXISTS agent_id UUID "
                        "REFERENCES agents(id) ON DELETE SET NULL"
                    )
                )
                await connection.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS "
                        "ix_conversations_agent_id "
                        "ON conversations (agent_id)"
                    )
                )
                await connection.execute(
                    text(
                        "ALTER TABLE messages "
                        "ADD COLUMN IF NOT EXISTS agui_activity JSONB"
                    )
                )
                await connection.execute(
                    text(
                        "ALTER TABLE users "
                        "ADD COLUMN IF NOT EXISTS role VARCHAR(16) "
                        "NOT NULL DEFAULT 'user'"
                    )
                )
            elif connection.dialect.name == "sqlite":
                columns = {
                    row[1]
                    for row in (
                        await connection.execute(
                            text("PRAGMA table_info(users)")
                        )
                    ).all()
                }
                if "role" not in columns:
                    await connection.execute(
                        text(
                            "ALTER TABLE users "
                            "ADD COLUMN role VARCHAR(16) "
                            "NOT NULL DEFAULT 'user'"
                        )
                    )

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session

    async def dispose(self) -> None:
        await self.engine.dispose()

