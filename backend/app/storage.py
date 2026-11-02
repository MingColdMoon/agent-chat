from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import (
    AgentRecord,
    ConversationRecord,
    MessageRecord,
    UserRecord,
)
from app.models import (
    AgentCreateRequest,
    AgentSummary,
    Conversation,
    ConversationSummary,
    Message,
    ToolTrace,
)


BUILTIN_AGENTS = (
    {
        "slug": "customer-service",
        "name": "智能客服",
        "description": "处理售前咨询、订单问题、投诉受理与服务流程引导。",
        "category": "客户服务",
        "icon": "headset",
        "instructions": (
            "你是专业、耐心的中文智能客服。先准确理解用户问题，再给出可执行的处理建议。"
            "遇到订单、退款、物流、账户或投诉问题时，要主动确认缺失信息，说明服务边界，"
            "不能编造订单状态或承诺未经授权的结果。回答结构清晰、语气友好，优先解决当前问题。"
        ),
    },
    {
        "slug": "automated-reports",
        "name": "智能自动化报表",
        "description": "把业务数据整理成摘要、指标、趋势、异常与行动建议。",
        "category": "数据分析",
        "icon": "chart",
        "instructions": (
            "你是自动化报表分析助手。将用户提供的数据整理为结构化的 Markdown 报表，"
            "包含执行摘要、核心指标、趋势观察、异常项和下一步建议。需要计算时调用计算器，"
            "需要当前时间时调用时间工具。不得虚构未提供的数据；数据不足时明确说明假设，"
            "并给出补充字段建议。"
        ),
    },
)


class DuplicateUsernameError(ValueError):
    pass


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as error:
        raise KeyError(value) from error


def builtin_agent_id(slug: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"agent-chat/builtin/{slug}")


def agent_to_summary(agent: AgentRecord) -> AgentSummary:
    return AgentSummary(
        id=str(agent.id),
        name=agent.name,
        description=agent.description,
        category=agent.category,
        icon=agent.icon,
        key=agent.slug,
        is_builtin=agent.is_builtin,
        created_at=to_iso(agent.created_at),
    )


class UserStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def create(
        self,
        username: str,
        password_hash: str,
    ) -> UserRecord:
        async with self.session_factory() as session:
            user = UserRecord(
                id=uuid4(),
                username=username,
                password_hash=password_hash,
                created_at=datetime.now(UTC),
            )
            session.add(user)
            try:
                await session.commit()
            except IntegrityError as error:
                await session.rollback()
                raise DuplicateUsernameError(username) from error
            return user

    async def by_username(self, username: str) -> UserRecord | None:
        async with self.session_factory() as session:
            return await session.scalar(
                select(UserRecord).where(UserRecord.username == username)
            )

    async def by_id(self, user_id: str) -> UserRecord | None:
        try:
            parsed_id = UUID(user_id)
        except ValueError:
            return None
        async with self.session_factory() as session:
            return await session.get(UserRecord, parsed_id)


class AgentStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def seed_builtins(self) -> None:
        async with self.session_factory() as session:
            for item in BUILTIN_AGENTS:
                agent = await session.scalar(
                    select(AgentRecord).where(
                        AgentRecord.slug == item["slug"]
                    )
                )
                if agent is None:
                    agent = AgentRecord(
                        id=builtin_agent_id(item["slug"]),
                        owner_id=None,
                        slug=item["slug"],
                        is_builtin=True,
                        created_at=datetime.now(UTC),
                    )
                    session.add(agent)
                agent.name = item["name"]
                agent.description = item["description"]
                agent.category = item["category"]
                agent.icon = item["icon"]
                agent.instructions = item["instructions"]
                agent.updated_at = datetime.now(UTC)
            await session.commit()

    async def list_accessible(self, user_id: str) -> list[AgentSummary]:
        user_uuid = parse_uuid(user_id)
        async with self.session_factory() as session:
            agents = (
                await session.scalars(
                    select(AgentRecord)
                    .where(
                        or_(
                            AgentRecord.is_builtin.is_(True),
                            AgentRecord.owner_id == user_uuid,
                        )
                    )
                    .order_by(
                        AgentRecord.is_builtin.desc(),
                        AgentRecord.created_at.asc(),
                    )
                )
            ).all()
            return [agent_to_summary(agent) for agent in agents]

    async def get_accessible(
        self,
        user_id: str,
        agent_id: str,
    ) -> AgentRecord | None:
        try:
            user_uuid = parse_uuid(user_id)
            parsed_agent_id = parse_uuid(agent_id)
        except KeyError:
            return None
        async with self.session_factory() as session:
            return await session.scalar(
                select(AgentRecord).where(
                    AgentRecord.id == parsed_agent_id,
                    or_(
                        AgentRecord.is_builtin.is_(True),
                        AgentRecord.owner_id == user_uuid,
                    ),
                )
            )

    async def create(
        self,
        user_id: str,
        payload: AgentCreateRequest,
    ) -> AgentSummary:
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            agent = AgentRecord(
                id=uuid4(),
                owner_id=parse_uuid(user_id),
                slug=None,
                name=payload.name.strip(),
                description=payload.description.strip(),
                category=payload.category.strip(),
                icon=payload.icon.strip() or "bot",
                instructions=payload.instructions.strip(),
                is_builtin=False,
                created_at=now,
                updated_at=now,
            )
            session.add(agent)
            await session.commit()
            return agent_to_summary(agent)

    async def delete(self, user_id: str, agent_id: str) -> bool:
        try:
            user_uuid = parse_uuid(user_id)
            parsed_agent_id = parse_uuid(agent_id)
        except KeyError:
            return False
        async with self.session_factory() as session:
            result = await session.execute(
                delete(AgentRecord).where(
                    AgentRecord.id == parsed_agent_id,
                    AgentRecord.owner_id == user_uuid,
                    AgentRecord.is_builtin.is_(False),
                )
            )
            await session.commit()
            return bool(result.rowcount)


class ConversationStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def list(self, user_id: str) -> list[ConversationSummary]:
        parsed_user_id = parse_uuid(user_id)
        async with self.session_factory() as session:
            rows = (
                await session.execute(
                    select(
                        ConversationRecord,
                        func.count(MessageRecord.id),
                        AgentRecord,
                    )
                    .outerjoin(
                        MessageRecord,
                        MessageRecord.conversation_id
                        == ConversationRecord.id,
                    )
                    .outerjoin(
                        AgentRecord,
                        AgentRecord.id == ConversationRecord.agent_id,
                    )
                    .where(ConversationRecord.user_id == parsed_user_id)
                    .group_by(ConversationRecord.id, AgentRecord.id)
                    .order_by(ConversationRecord.updated_at.desc())
                )
            ).all()
            return [
                ConversationSummary(
                    id=str(conversation.id),
                    title=conversation.title,
                    created_at=to_iso(conversation.created_at),
                    updated_at=to_iso(conversation.updated_at),
                    message_count=int(message_count),
                    agent=agent_to_summary(agent) if agent else None,
                )
                for conversation, message_count, agent in rows
            ]

    async def get(
        self,
        user_id: str,
        conversation_id: str,
    ) -> Conversation | None:
        try:
            user_uuid = parse_uuid(user_id)
            conversation_uuid = parse_uuid(conversation_id)
        except KeyError:
            return None

        async with self.session_factory() as session:
            conversation = await session.scalar(
                select(ConversationRecord).where(
                    ConversationRecord.id == conversation_uuid,
                    ConversationRecord.user_id == user_uuid,
                )
            )
            if conversation is None:
                return None
            agent = (
                await session.get(AgentRecord, conversation.agent_id)
                if conversation.agent_id
                else None
            )
            message_rows = (
                await session.scalars(
                    select(MessageRecord)
                    .where(MessageRecord.conversation_id == conversation_uuid)
                    .order_by(MessageRecord.created_at.asc())
                )
            ).all()
            return Conversation(
                id=str(conversation.id),
                title=conversation.title,
                created_at=to_iso(conversation.created_at),
                updated_at=to_iso(conversation.updated_at),
                agent=agent_to_summary(agent) if agent else None,
                agent_prompt=agent.instructions if agent else None,
                messages=[
                    Message(
                        id=str(message.id),
                        role=message.role,
                        content=message.content,
                        created_at=to_iso(message.created_at),
                        tools=[
                            ToolTrace.model_validate(tool)
                            for tool in (message.tools or [])
                        ],
                        error=message.error,
                        provider=message.provider,
                        model=message.model,
                    )
                    for message in message_rows
                ],
            )

    async def create(
        self,
        user_id: str,
        agent_id: str | None = None,
    ) -> Conversation:
        user_uuid = parse_uuid(user_id)
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            agent = await self._resolve_agent(
                session,
                user_uuid,
                agent_id,
            )
            conversation = ConversationRecord(
                id=uuid4(),
                user_id=user_uuid,
                agent_id=agent.id if agent else None,
                title="新会话",
                created_at=now,
                updated_at=now,
            )
            session.add(conversation)
            await session.commit()
            return Conversation(
                id=str(conversation.id),
                title=conversation.title,
                created_at=to_iso(conversation.created_at),
                updated_at=to_iso(conversation.updated_at),
                agent=agent_to_summary(agent) if agent else None,
                agent_prompt=agent.instructions if agent else None,
            )

    async def set_agent(
        self,
        user_id: str,
        conversation_id: str,
        agent_id: str,
    ) -> Conversation | None:
        user_uuid = parse_uuid(user_id)
        conversation_uuid = parse_uuid(conversation_id)
        async with self.session_factory() as session:
            conversation = await session.scalar(
                select(ConversationRecord).where(
                    ConversationRecord.id == conversation_uuid,
                    ConversationRecord.user_id == user_uuid,
                )
            )
            if conversation is None:
                return None
            agent = await self._resolve_agent(
                session,
                user_uuid,
                agent_id,
            )
            conversation.agent_id = agent.id if agent else None
            conversation.updated_at = datetime.now(UTC)
            await session.commit()
        return await self.get(user_id, conversation_id)

    async def delete(self, user_id: str, conversation_id: str) -> bool:
        try:
            user_uuid = parse_uuid(user_id)
            conversation_uuid = parse_uuid(conversation_id)
        except KeyError:
            return False
        async with self.session_factory() as session:
            result = await session.execute(
                delete(ConversationRecord).where(
                    ConversationRecord.id == conversation_uuid,
                    ConversationRecord.user_id == user_uuid,
                )
            )
            await session.commit()
            return bool(result.rowcount)

    async def add_message(
        self,
        user_id: str,
        conversation_id: str,
        message: Message,
    ) -> list[Message]:
        user_uuid = parse_uuid(user_id)
        conversation_uuid = parse_uuid(conversation_id)
        now = datetime.now(UTC)
        async with self.session_factory() as session:
            conversation = await session.scalar(
                select(ConversationRecord).where(
                    ConversationRecord.id == conversation_uuid,
                    ConversationRecord.user_id == user_uuid,
                )
            )
            if conversation is None:
                raise KeyError(conversation_id)

            session.add(
                MessageRecord(
                    id=parse_uuid(message.id),
                    conversation_id=conversation_uuid,
                    role=message.role,
                    content=message.content,
                    tools=[
                        tool.model_dump(mode="json")
                        for tool in message.tools
                    ],
                    error=message.error,
                    provider=message.provider,
                    model=message.model,
                    created_at=now,
                )
            )
            conversation.updated_at = now
            if message.role == "user" and conversation.title == "新会话":
                compact = " ".join(message.content.split())
                conversation.title = (
                    compact if len(compact) <= 30 else f"{compact[:30]}..."
                )
            await session.commit()
        stored = await self.get(user_id, conversation_id)
        return stored.messages if stored else []

    @staticmethod
    async def _resolve_agent(
        session: AsyncSession,
        user_id: UUID,
        agent_id: str | None,
    ) -> AgentRecord | None:
        if not agent_id:
            return None
        try:
            parsed_agent_id = parse_uuid(agent_id)
        except KeyError as error:
            raise ValueError("智能体不存在") from error
        agent = await session.scalar(
            select(AgentRecord).where(
                AgentRecord.id == parsed_agent_id,
                or_(
                    AgentRecord.is_builtin.is_(True),
                    AgentRecord.owner_id == user_id,
                ),
            )
        )
        if agent is None:
            raise ValueError("智能体不存在或无权使用")
        return agent

