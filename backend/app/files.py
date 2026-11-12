from __future__ import annotations

import asyncio
import re
import zipfile
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4
from xml.etree import ElementTree

from pypdf import PdfReader
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import AttachmentRecord, MessageAttachmentRecord
from app.models import AttachmentSummary


TEXT_EXTENSIONS = {
    ".c",
    ".cc",
    ".conf",
    ".cpp",
    ".css",
    ".csv",
    ".env",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsonl",
    ".jsx",
    ".log",
    ".md",
    ".markdown",
    ".php",
    ".properties",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".svg",
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
IMAGE_EXTENSIONS = {".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".webp"}
BLOCKED_EXTENSIONS = {
    ".bat",
    ".cmd",
    ".com",
    ".dll",
    ".exe",
    ".msi",
    ".scr",
    ".so",
    ".dylib",
    ".vbs",
}
MAX_EXTRACT_CHARS = 160_000


class AttachmentError(ValueError):
    pass


def _parse_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as error:
        raise KeyError(value) from error


def _to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def sanitize_filename(filename: str) -> str:
    normalized = filename.replace("\\", "/")
    basename = Path(normalized).name.strip()
    basename = re.sub(r"[\x00-\x1f\x7f]", "", basename)
    if not basename:
        basename = "未命名文件"
    if len(basename) > 180:
        stem = Path(basename).stem[:150]
        suffix = Path(basename).suffix[:30]
        basename = f"{stem}{suffix}"
    return basename


def _decode_text(data: bytes) -> str | None:
    if b"\x00" in data[:8192]:
        return None
    for encoding in ("utf-8-sig", "utf-16", "gb18030", "big5", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def _extract_pdf(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    pages: list[str] = []
    for index, page in enumerate(reader.pages[:80], start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append(f"第 {index} 页\n{text}")
    return "\n\n".join(pages)


def _extract_docx(data: bytes) -> str:
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(BytesIO(data)) as archive:
        document = archive.read("word/document.xml")
    root = ElementTree.fromstring(document)
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        text = "".join(
            node.text or "" for node in paragraph.findall(".//w:t", namespace)
        ).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def extract_file_text(
    filename: str,
    content_type: str,
    data: bytes,
) -> tuple[str | None, str]:
    extension = Path(filename).suffix.lower()
    extracted: str | None = None

    if extension == ".pdf":
        try:
            extracted = _extract_pdf(data)
        except Exception:
            extracted = ""
    elif extension == ".docx":
        try:
            extracted = _extract_docx(data)
        except Exception:
            extracted = ""
    elif extension in TEXT_EXTENSIONS or content_type.startswith("text/"):
        extracted = _decode_text(data)
    elif extension in IMAGE_EXTENSIONS or content_type.startswith("image/"):
        extracted = f"[图片文件：{filename}]"
    else:
        extracted = _decode_text(data)

    if extracted is None:
        return None, "二进制文件，当前仅保留文件引用信息。"

    normalized = extracted.strip()
    if len(normalized) > MAX_EXTRACT_CHARS:
        normalized = (
            normalized[:MAX_EXTRACT_CHARS]
            + "\n\n[文件内容过长，后续内容已截断]"
        )
    compact = " ".join(normalized.split())
    excerpt = compact[:280]
    if not excerpt:
        excerpt = (
            "未从文件中提取到文本内容，仍保留文件引用。"
            if extension in {".pdf", ".docx"}
            else "文件已上传。"
        )
    return normalized, excerpt


def attachment_to_summary(
    record: AttachmentRecord,
    *,
    referenced: bool = False,
) -> AttachmentSummary:
    return AttachmentSummary(
        id=str(record.id),
        filename=record.filename,
        content_type=record.content_type,
        extension=record.extension,
        size_bytes=record.size_bytes,
        excerpt=record.excerpt,
        text_length=len(record.extracted_text or ""),
        referenced=referenced,
        created_at=_to_iso(record.created_at),
        extracted_text=record.extracted_text,
    )


class AttachmentStore:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        root: Path,
        max_upload_bytes: int,
    ) -> None:
        self.session_factory = session_factory
        self.root = root
        self.max_upload_bytes = max_upload_bytes

    async def create(
        self,
        user_id: str,
        conversation_id: str,
        filename: str,
        content_type: str,
        data: bytes,
    ) -> AttachmentSummary:
        if not data:
            raise AttachmentError("文件不能为空")
        if len(data) > self.max_upload_bytes:
            raise AttachmentError(
                f"文件不能超过 {self.max_upload_bytes // (1024 * 1024)} MB"
            )

        safe_name = sanitize_filename(filename)
        extension = Path(safe_name).suffix.lower()[:32]
        if extension in BLOCKED_EXTENSIONS:
            raise AttachmentError("出于安全考虑，不支持上传可执行文件")

        user_uuid = _parse_uuid(user_id)
        conversation_uuid = _parse_uuid(conversation_id)
        attachment_id = uuid4()
        storage_dir = self.root / str(user_uuid) / str(conversation_uuid)
        storage_dir.mkdir(parents=True, exist_ok=True)
        storage_path = storage_dir / f"{attachment_id}{extension}"
        normalized_type = (content_type or "application/octet-stream")[:120]

        await asyncio.to_thread(storage_path.write_bytes, data)
        try:
            extracted_text, excerpt = await asyncio.to_thread(
                extract_file_text,
                safe_name,
                normalized_type,
                data,
            )
            async with self.session_factory() as session:
                record = AttachmentRecord(
                    id=attachment_id,
                    user_id=user_uuid,
                    conversation_id=conversation_uuid,
                    filename=safe_name,
                    content_type=normalized_type,
                    extension=extension,
                    size_bytes=len(data),
                    storage_path=str(storage_path),
                    extracted_text=extracted_text,
                    excerpt=excerpt,
                )
                session.add(record)
                await session.commit()
                return attachment_to_summary(record)
        except Exception:
            storage_path.unlink(missing_ok=True)
            raise

    async def list_conversation(
        self,
        user_id: str,
        conversation_id: str,
    ) -> list[AttachmentSummary]:
        user_uuid = _parse_uuid(user_id)
        conversation_uuid = _parse_uuid(conversation_id)
        async with self.session_factory() as session:
            records = (
                await session.scalars(
                    select(AttachmentRecord)
                    .where(
                        AttachmentRecord.user_id == user_uuid,
                        AttachmentRecord.conversation_id == conversation_uuid,
                    )
                    .order_by(AttachmentRecord.created_at.asc())
                )
            ).all()
            referenced_ids = set(
                (
                    await session.scalars(
                        select(MessageAttachmentRecord.attachment_id).where(
                            MessageAttachmentRecord.attachment_id.in_(
                                [record.id for record in records]
                            )
                        )
                    )
                ).all()
            )
            return [
                attachment_to_summary(
                    record,
                    referenced=record.id in referenced_ids,
                )
                for record in records
            ]

    async def get_owned(
        self,
        user_id: str,
        attachment_id: str,
    ) -> AttachmentRecord | None:
        try:
            user_uuid = _parse_uuid(user_id)
            parsed_id = _parse_uuid(attachment_id)
        except KeyError:
            return None
        async with self.session_factory() as session:
            return await session.scalar(
                select(AttachmentRecord).where(
                    AttachmentRecord.id == parsed_id,
                    AttachmentRecord.user_id == user_uuid,
                )
            )

    async def validate_pending(
        self,
        user_id: str,
        conversation_id: str,
        attachment_ids: list[str],
    ) -> list[AttachmentRecord]:
        if not attachment_ids:
            return []
        try:
            parsed_user = _parse_uuid(user_id)
            parsed_conversation = _parse_uuid(conversation_id)
            parsed_ids = [
                _parse_uuid(item) for item in dict.fromkeys(attachment_ids)
            ]
        except KeyError as error:
            raise AttachmentError("附件不存在") from error

        async with self.session_factory() as session:
            records = (
                await session.scalars(
                    select(AttachmentRecord).where(
                        AttachmentRecord.id.in_(parsed_ids),
                        AttachmentRecord.user_id == parsed_user,
                        AttachmentRecord.conversation_id == parsed_conversation,
                    )
                )
            ).all()
        by_id = {record.id: record for record in records}
        if len(by_id) != len(parsed_ids):
            raise AttachmentError("附件不存在或不属于当前会话")
        return [by_id[item] for item in parsed_ids]

    async def delete_unbound(self, user_id: str, attachment_id: str) -> bool:
        try:
            parsed_user = _parse_uuid(user_id)
            parsed_id = _parse_uuid(attachment_id)
        except KeyError:
            return False
        async with self.session_factory() as session:
            record = await session.scalar(
                select(AttachmentRecord).where(
                    AttachmentRecord.id == parsed_id,
                    AttachmentRecord.user_id == parsed_user,
                )
            )
            if record is None:
                return False
            is_referenced = await session.scalar(
                select(MessageAttachmentRecord.attachment_id).where(
                    MessageAttachmentRecord.attachment_id == parsed_id
                )
            )
            if is_referenced is not None:
                return False
            storage_path = Path(record.storage_path)
            await session.execute(
                delete(AttachmentRecord).where(AttachmentRecord.id == parsed_id)
            )
            await session.commit()
        storage_path.unlink(missing_ok=True)
        return True

    async def conversation_file_paths(
        self,
        user_id: str,
        conversation_id: str,
    ) -> list[Path]:
        try:
            user_uuid = _parse_uuid(user_id)
            conversation_uuid = _parse_uuid(conversation_id)
        except KeyError:
            return []
        async with self.session_factory() as session:
            paths = (
                await session.scalars(
                    select(AttachmentRecord.storage_path).where(
                        AttachmentRecord.user_id == user_uuid,
                        AttachmentRecord.conversation_id == conversation_uuid,
                    )
                )
            ).all()
        return [Path(path) for path in paths]

    async def cleanup_stale_unbound(self, older_than_hours: int = 24) -> int:
        cutoff = datetime.now(UTC) - timedelta(hours=older_than_hours)
        referenced = select(MessageAttachmentRecord.attachment_id)
        async with self.session_factory() as session:
            records = (
                await session.scalars(
                    select(AttachmentRecord).where(
                        AttachmentRecord.created_at < cutoff,
                        AttachmentRecord.id.not_in(referenced),
                    )
                )
            ).all()
            if not records:
                return 0
            paths = [Path(record.storage_path) for record in records]
            ids = [record.id for record in records]
            await session.execute(
                delete(AttachmentRecord).where(
                    AttachmentRecord.id.in_(ids)
                )
            )
            await session.commit()
        self.delete_paths(paths)
        return len(paths)

    @staticmethod
    def delete_paths(paths: list[Path]) -> None:
        for path in paths:
            path.unlink(missing_ok=True)
        for parent in {path.parent for path in paths}:
            try:
                parent.rmdir()
            except OSError:
                pass


async def load_message_attachments(
    session: AsyncSession,
    conversation_id: UUID,
) -> dict[UUID, list[AttachmentSummary]]:
    rows = (
        await session.execute(
            select(
                MessageAttachmentRecord.message_id,
                AttachmentRecord,
            )
            .join(
                AttachmentRecord,
                AttachmentRecord.id
                == MessageAttachmentRecord.attachment_id,
            )
            .where(
                AttachmentRecord.conversation_id == conversation_id,
            )
            .order_by(MessageAttachmentRecord.created_at.asc())
        )
    ).all()
    by_message: dict[UUID, list[AttachmentSummary]] = {}
    for message_id, record in rows:
        by_message.setdefault(message_id, []).append(
            attachment_to_summary(record, referenced=True)
        )
    return by_message
