import asyncio
import json
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.agent import AgentRunner
from app.auth import (
    AuthContext,
    AuthTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    user_to_info,
    verify_password,
)
from app.config import Settings, get_settings, resolve_runtime_config
from app.database import Database
from app.events import RunManager, RunState
from app.models import (
    AgentCreateRequest,
    AgentListResponse,
    AgentResponse,
    ApplyAgentRequest,
    AuthCredentials,
    AuthResponse,
    ConversationListResponse,
    ConversationResponse,
    CreateConversationRequest,
    CreateConversationResponse,
    HealthResponse,
    MeResponse,
    Message,
    RuntimeConfig,
    SendMessageRequest,
    SendMessageResponse,
    UserInfo,
)
from app.sessions import RedisSessionStore, SessionStore
from app.storage import (
    AgentStore,
    ConversationStore,
    DuplicateUsernameError,
    UserStore,
    utc_now,
)


def create_app(
    settings: Settings | None = None,
    database: Database | None = None,
    session_store: SessionStore | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    database = database or Database(settings.database_url)
    session_store = session_store or RedisSessionStore(settings.redis_url)
    user_store = UserStore(database.session_factory)
    agent_store = AgentStore(database.session_factory)
    conversation_store = ConversationStore(database.session_factory)
    runs = RunManager()
    agent = AgentRunner(settings)
    run_tasks: set[asyncio.Task[None]] = set()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await database.initialize()
        await agent_store.seed_builtins()
        await session_store.initialize()
        try:
            yield
        finally:
            tasks = list(run_tasks)
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await runs.shutdown()
            await session_store.close()
            await database.dispose()

    app = FastAPI(
        title="LangChain Agent Chat",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    async def get_auth_context(request: Request) -> AuthContext:
        authorization = request.headers.get("authorization", "")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="缺少 Bearer JWT",
                headers={"WWW-Authenticate": "Bearer"},
            )
        try:
            payload = decode_access_token(token, settings)
        except AuthTokenError as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(error),
                headers={"WWW-Authenticate": "Bearer"},
            ) from error
        jti = str(payload["jti"])
        if await session_store.is_token_revoked(jti):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="JWT 已注销",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user_id = str(payload["sub"])
        user = await user_store.by_id(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户不存在",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return AuthContext(
            user=user_to_info(user),
            token=token,
            payload=payload,
        )

    async def get_current_user(
        auth: Annotated[AuthContext, Depends(get_auth_context)],
    ) -> UserInfo:
        return auth.user

    CurrentUser = Annotated[UserInfo, Depends(get_current_user)]
    CurrentAuth = Annotated[AuthContext, Depends(get_auth_context)]

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        tools = ["get_current_time", "calculator"]
        if settings.tavily_api_key:
            tools.append("web_search")
        server_credentials = []
        if settings.openai_api_key:
            server_credentials.append("openai")
        if settings.deepseek_api_key:
            server_credentials.append("deepseek")
        return HealthResponse(
            ok=True,
            mode="live" if settings.live_mode else "demo",
            model=settings.provider_name,
            tools=tools,
            providers=["demo", "openai", "deepseek", "custom"],
            server_credentials=server_credentials,
            tavily_configured=bool(settings.tavily_api_key),
        )

    @app.post(
        "/api/auth/register",
        response_model=AuthResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def register(
        payload: AuthCredentials,
    ) -> AuthResponse:
        try:
            user = await user_store.create(
                payload.username,
                await hash_password(payload.password),
            )
        except DuplicateUsernameError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="用户名已存在",
            ) from error

        token, expires_at, _ = create_access_token(user, settings)
        return AuthResponse(
            access_token=token,
            expires_in=settings.jwt_expiration_minutes * 60,
            expires_at=expires_at.isoformat().replace("+00:00", "Z"),
            user=user_to_info(user),
        )

    @app.post("/api/auth/login", response_model=AuthResponse)
    async def login(
        payload: AuthCredentials,
        request: Request,
    ) -> AuthResponse:
        client_host = request.client.host if request.client else "unknown"
        failure_key = f"{client_host}:{payload.username}"
        failures = await session_store.failure_count(failure_key)
        if failures >= settings.login_rate_limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="登录尝试过多，请稍后再试",
            )

        user = await user_store.by_username(payload.username)
        valid = bool(
            user
            and await verify_password(payload.password, user.password_hash)
        )
        if not valid or user is None:
            await session_store.record_failure(
                failure_key,
                settings.login_rate_window_seconds,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
            )

        await session_store.clear_failures(failure_key)
        token, expires_at, _ = create_access_token(user, settings)
        return AuthResponse(
            access_token=token,
            expires_in=settings.jwt_expiration_minutes * 60,
            expires_at=expires_at.isoformat().replace("+00:00", "Z"),
            user=user_to_info(user),
        )

    @app.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
    async def logout(auth: CurrentAuth) -> None:
        expires_at = int(auth.payload["exp"])
        ttl = max(1, expires_at - int(datetime.now(UTC).timestamp()))
        await session_store.revoke_token(
            str(auth.payload["jti"]),
            ttl,
        )

    @app.get("/api/auth/me", response_model=MeResponse)
    async def me(user: CurrentUser) -> MeResponse:
        return MeResponse(user=user)

    @app.get("/api/agents", response_model=AgentListResponse)
    async def list_agents(user: CurrentUser) -> AgentListResponse:
        return AgentListResponse(
            agents=await agent_store.list_accessible(user.id)
        )

    @app.post(
        "/api/agents",
        response_model=AgentResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_agent(
        payload: AgentCreateRequest,
        user: CurrentUser,
    ) -> AgentResponse:
        return AgentResponse(
            agent=await agent_store.create(user.id, payload)
        )

    @app.delete(
        "/api/agents/{agent_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_agent(
        agent_id: str,
        user: CurrentUser,
    ) -> None:
        deleted = await agent_store.delete(user.id, agent_id)
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail="智能体不存在或不可删除",
            )

    @app.get(
        "/api/conversations",
        response_model=ConversationListResponse,
    )
    async def list_conversations(
        user: CurrentUser,
    ) -> ConversationListResponse:
        return ConversationListResponse(
            conversations=await conversation_store.list(user.id)
        )

    @app.post(
        "/api/conversations",
        response_model=CreateConversationResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_conversation(
        user: CurrentUser,
        payload: CreateConversationRequest | None = None,
    ) -> CreateConversationResponse:
        try:
            conversation = await conversation_store.create(
                user.id,
                payload.agent_id if payload else None,
            )
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return CreateConversationResponse(conversation=conversation)

    @app.get(
        "/api/conversations/{conversation_id}",
        response_model=ConversationResponse,
    )
    async def get_conversation(
        conversation_id: str,
        user: CurrentUser,
    ) -> ConversationResponse:
        conversation = await conversation_store.get(
            user.id,
            conversation_id,
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        return ConversationResponse(conversation=conversation)

    @app.patch(
        "/api/conversations/{conversation_id}/agent",
        response_model=ConversationResponse,
    )
    async def set_conversation_agent(
        conversation_id: str,
        payload: ApplyAgentRequest,
        user: CurrentUser,
    ) -> ConversationResponse:
        try:
            conversation = await conversation_store.set_agent(
                user.id,
                conversation_id,
                payload.agent_id,
            )
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        if conversation is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        return ConversationResponse(conversation=conversation)

    @app.delete(
        "/api/conversations/{conversation_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_conversation(
        conversation_id: str,
        user: CurrentUser,
    ) -> None:
        deleted = await conversation_store.delete(
            user.id,
            conversation_id,
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="会话不存在")

    @app.post(
        "/api/conversations/{conversation_id}/messages",
        response_model=SendMessageResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def send_message(
        conversation_id: str,
        payload: SendMessageRequest,
        user: CurrentUser,
    ) -> SendMessageResponse:
        conversation = await conversation_store.get(
            user.id,
            conversation_id,
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="会话不存在")

        content = payload.content.strip()
        if not content:
            raise HTTPException(status_code=400, detail="消息不能为空")
        try:
            runtime = resolve_runtime_config(payload.runtime, settings)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        user_message = Message(
            id=str(uuid4()),
            role="user",
            content=content,
            created_at=utc_now(),
        )
        await conversation_store.add_message(
            user.id,
            conversation_id,
            user_message,
        )
        run = await runs.create(conversation_id, user.id)
        assistant_id = str(uuid4())
        await runs.publish(
            run,
            "run.started",
            conversation_id=conversation_id,
            assistant_id=assistant_id,
            user_message=user_message.model_dump(mode="json"),
            provider=runtime.provider,
            model=runtime.model,
            agent=(
                conversation.agent.model_dump(mode="json")
                if conversation.agent
                else None
            ),
        )
        task = asyncio.create_task(
            _execute_run(
                run=run,
                user_id=user.id,
                assistant_id=assistant_id,
                conversation_id=conversation_id,
                store=conversation_store,
                agent=agent,
                runs=runs,
                runtime=runtime,
            )
        )
        run_tasks.add(task)
        task.add_done_callback(run_tasks.discard)
        return SendMessageResponse(
            run_id=run.id,
            conversation_id=conversation_id,
            user_message=user_message,
            stream_url=f"/api/runs/{run.id}/events",
            provider=runtime.provider,
            model=runtime.model or "demo",
        )

    @app.get("/api/runs/{run_id}/events")
    async def stream_events(
        run_id: str,
        request: Request,
        user: CurrentUser,
    ):
        run = runs.get(run_id)
        if run is None or run.user_id != user.id:
            raise HTTPException(status_code=404, detail="事件流不存在或已过期")

        last_event_id = _parse_last_event_id(request)
        return StreamingResponse(
            _sse_events(run, runs, last_event_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    if getattr(sys, "frozen", False):
        frontend_dist = Path(sys._MEIPASS) / "frontend_dist"
    else:
        frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount(
            "/",
            StaticFiles(directory=frontend_dist, html=True),
            name="frontend",
        )

    return app


async def _execute_run(
    *,
    run: RunState,
    user_id: str,
    assistant_id: str,
    conversation_id: str,
    store: ConversationStore,
    agent: AgentRunner,
    runs: RunManager,
    runtime: RuntimeConfig,
) -> None:
    async def emit(event_type: str, payload: dict[str, Any]) -> None:
        await runs.publish(run, event_type, **payload)

    try:
        conversation = await store.get(user_id, conversation_id)
        if conversation is None:
            raise RuntimeError("会话已被删除")

        answer, tools = await agent.run(
            conversation.messages,
            emit,
            runtime,
            agent_name=conversation.agent.name if conversation.agent else None,
            agent_key=conversation.agent.key if conversation.agent else None,
            agent_prompt=conversation.agent_prompt,
        )
        assistant_message = Message(
            id=assistant_id,
            role="assistant",
            content=answer,
            created_at=utc_now(),
            tools=tools,
            provider=runtime.provider,
            model=runtime.model or "demo",
        )
        await store.add_message(
            user_id,
            conversation_id,
            assistant_message,
        )
        await runs.publish(
            run,
            "assistant.final",
            message=assistant_message.model_dump(mode="json"),
        )
        await runs.publish(run, "done")
        await runs.finish(run)
    except Exception as error:
        await runs.publish(
            run,
            "run.error",
            error=str(error) or "Agent 运行失败",
        )
        await runs.publish(run, "done")
        await runs.finish(run, status="error")


async def _sse_events(
    run: RunState,
    runs: RunManager,
    last_event_id: int,
):
    cursor = max(0, last_event_id)
    yield "retry: 1000\n\n"
    while True:
        events = await runs.events_after(run, cursor)
        for event in events:
            cursor = event["id"]
            yield f"id: {cursor}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"

        if run.status != "running" and cursor >= run.last_event_id:
            break

        changed = await runs.wait_for_change(run, cursor)
        if not changed:
            yield ": keepalive\n\n"


def _parse_last_event_id(request: Request) -> int:
    raw = request.headers.get("last-event-id", "0")
    try:
        return int(raw)
    except ValueError:
        return 0


app = create_app()

