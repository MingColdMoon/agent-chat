import asyncio
import json
import sys
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
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
from app.config import (
    Settings,
    application_home,
    get_settings,
    resolve_runtime_config,
)
from app.database import Database
from app.events import RunManager, RunState
from app.files import (
    AttachmentError,
    AttachmentStore,
    attachment_to_summary,
)
from app.models import (
    AgentCreateRequest,
    AgentListResponse,
    AgentResponse,
    ApplyAgentRequest,
    AttachmentListResponse,
    AttachmentResponse,
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
    ToolTrace,
    UserInfo,
)
from app.rag import RagStore
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
    upload_root = Path(settings.upload_dir)
    if not upload_root.is_absolute():
        upload_root = application_home() / upload_root
    attachment_store = AttachmentStore(
        database.session_factory,
        upload_root,
        settings.max_upload_bytes,
    )
    rag_store = RagStore(database.session_factory)
    runs = RunManager()
    agent = AgentRunner(settings)
    run_tasks: set[asyncio.Task[None]] = set()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await database.initialize()
        upload_root.mkdir(parents=True, exist_ok=True)
        await attachment_store.cleanup_stale_unbound()
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
        tools = [
            "get_current_time",
            "calculator",
            "generate_pc_build",
            "search_knowledge_base",
            "start_media_crawler_task",
            "get_media_crawler_status",
            "list_media_crawler_files",
        ]
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
            media_crawler_configured=settings.media_crawler_configured,
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

    @app.get(
        "/api/conversations/{conversation_id}/attachments",
        response_model=AttachmentListResponse,
    )
    async def list_conversation_attachments(
        conversation_id: str,
        user: CurrentUser,
    ) -> AttachmentListResponse:
        conversation = await conversation_store.get(
            user.id,
            conversation_id,
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        return AttachmentListResponse(
            attachments=await attachment_store.list_conversation(
                user.id,
                conversation_id,
            )
        )

    @app.post(
        "/api/conversations/{conversation_id}/attachments",
        response_model=AttachmentResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_conversation_attachment(
        conversation_id: str,
        user: CurrentUser,
        file: UploadFile = File(...),
    ) -> AttachmentResponse:
        conversation = await conversation_store.get(
            user.id,
            conversation_id,
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="会话不存在")

        data = await file.read(settings.max_upload_bytes + 1)
        try:
            attachment = await attachment_store.create(
                user.id,
                conversation_id,
                file.filename or "未命名文件",
                file.content_type or "application/octet-stream",
                data,
            )
            await rag_store.index_attachment(
                attachment_id=attachment.id,
                user_id=user.id,
                conversation_id=conversation_id,
                filename=attachment.filename,
                text=attachment.extracted_text,
            )
        except AttachmentError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        finally:
            await file.close()
        return AttachmentResponse(attachment=attachment)

    @app.get("/api/attachments/{attachment_id}/download")
    async def download_attachment(
        attachment_id: str,
        user: CurrentUser,
    ):
        attachment = await attachment_store.get_owned(
            user.id,
            attachment_id,
        )
        if attachment is None:
            raise HTTPException(status_code=404, detail="附件不存在")
        path = Path(attachment.storage_path)
        if not path.exists():
            raise HTTPException(status_code=404, detail="附件文件已丢失")
        return FileResponse(
            path=path,
            filename=attachment.filename,
            media_type=attachment.content_type,
        )

    @app.delete(
        "/api/attachments/{attachment_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_attachment(
        attachment_id: str,
        user: CurrentUser,
    ) -> None:
        deleted = await attachment_store.delete_unbound(
            user.id,
            attachment_id,
        )
        if not deleted:
            raise HTTPException(
                status_code=404,
                detail="附件不存在或已被消息引用",
            )

    @app.delete(
        "/api/conversations/{conversation_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def delete_conversation(
        conversation_id: str,
        user: CurrentUser,
    ) -> None:
        files = await attachment_store.conversation_file_paths(
            user.id,
            conversation_id,
        )
        deleted = await conversation_store.delete(
            user.id,
            conversation_id,
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="会话不存在")
        attachment_store.delete_paths(files)

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
        if len(payload.attachment_ids) > settings.max_attachments_per_message:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"每条消息最多引用 "
                    f"{settings.max_attachments_per_message} 个文件"
                ),
            )
        if not content and not payload.attachment_ids:
            raise HTTPException(
                status_code=400,
                detail="消息不能为空",
            )
        try:
            attachment_records = await attachment_store.validate_pending(
                user.id,
                conversation_id,
                payload.attachment_ids,
            )
        except AttachmentError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        attachment_summaries = [
            attachment_to_summary(record)
            for record in attachment_records
        ]
        try:
            runtime = resolve_runtime_config(payload.runtime, settings)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

        user_message = Message(
            id=str(uuid4()),
            role="user",
            content=content,
            created_at=utc_now(),
            attachments=attachment_summaries,
        )
        try:
            await conversation_store.add_message(
                user.id,
                conversation_id,
                user_message,
                payload.attachment_ids,
            )
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
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
                rag_store=rag_store,
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
    rag_store: RagStore,
) -> None:
    agui_activity: dict[str, Any] | None = None

    async def emit(event_type: str, payload: dict[str, Any]) -> None:
        await runs.publish(run, event_type, **payload)
        if event_type == "assistant.delta":
            await runs.publish(
                run,
                "TEXT_MESSAGE_CONTENT",
                messageId=assistant_id,
                delta=payload["delta"],
            )
        elif event_type == "tool.started":
            tool = payload["tool"]
            await runs.publish(
                run,
                "TOOL_CALL_START",
                toolCallId=tool["id"],
                toolCallName=tool["name"],
                parentMessageId=assistant_id,
            )
        elif event_type == "tool.finished":
            tool = payload["tool"]
            await runs.publish(
                run,
                "TOOL_CALL_END",
                toolCallId=tool["id"],
            )
            await runs.publish(
                run,
                "TOOL_CALL_RESULT",
                messageId=f"tool-{tool['id']}",
                toolCallId=tool["id"],
                content=json.dumps(tool.get("output"), ensure_ascii=False),
                role="tool",
            )

    try:
        conversation = await store.get(user_id, conversation_id)
        if conversation is None:
            raise RuntimeError("会话已被删除")

        await runs.publish(
            run,
            "RUN_STARTED",
            threadId=conversation_id,
            runId=run.id,
        )
        await runs.publish(
            run,
            "TEXT_MESSAGE_START",
            messageId=assistant_id,
            role="assistant",
        )
        knowledge: dict[str, Any] | None = None
        rag_trace: ToolTrace | None = None
        agent_key = conversation.agent.key if conversation.agent else None
        last_user_message = next(
            (
                message
                for message in reversed(conversation.messages)
                if message.role == "user"
            ),
            None,
        )
        if agent_key == "rag-assistant":
            query = (last_user_message.content if last_user_message else "").strip()
            if not query and last_user_message and last_user_message.attachments:
                query = " ".join(
                    attachment.filename
                    for attachment in last_user_message.attachments
                )
            rag_trace = ToolTrace(
                id=str(uuid4()),
                name="search_knowledge_base",
                input={
                    "query": query,
                    "candidate_limit": 24,
                    "top_k": 5,
                },
            )
            await emit(
                "tool.started",
                {"tool": rag_trace.model_dump(mode="json")},
            )
            try:
                knowledge = await rag_store.search(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    query=query,
                    candidate_limit=24,
                    top_k=5,
                )
                rag_trace.state = "complete"
                rag_trace.output = {
                    key: value
                    for key, value in knowledge.items()
                    if key != "context"
                }
            except Exception as error:
                rag_trace.state = "error"
                rag_trace.output = str(error)
                knowledge = None
            await emit(
                "tool.finished",
                {"tool": rag_trace.model_dump(mode="json")},
            )

        answer, tools = await agent.run(
            conversation.messages,
            emit,
            runtime,
            agent_name=conversation.agent.name if conversation.agent else None,
            agent_key=agent_key,
            agent_prompt=conversation.agent_prompt,
            knowledge=knowledge,
        )
        if rag_trace:
            tools = [rag_trace, *tools]
        pc_build_trace = next(
            (
                trace
                for trace in reversed(tools)
                if trace.name == "generate_pc_build"
                and isinstance(trace.output, dict)
            ),
            None,
        )
        if pc_build_trace:
            agui_activity = {
                "activityType": "pc-build-plan",
                "content": pc_build_trace.output,
            }
            await runs.publish(
                run,
                "STATE_SNAPSHOT",
                snapshot={"pcBuild": pc_build_trace.output},
            )
            await runs.publish(
                run,
                "ACTIVITY_SNAPSHOT",
                messageId=assistant_id,
                activityType="pc-build-plan",
                content=pc_build_trace.output,
                replace=True,
            )
        media_crawler_trace = next(
            (
                trace
                for trace in reversed(tools)
                if trace.name == "start_media_crawler_task"
                and isinstance(trace.output, dict)
                and trace.output.get("source") == "mediacrawler"
            ),
            None,
        )
        if media_crawler_trace:
            agui_activity = {
                "activityType": "media-crawler-task",
                "content": media_crawler_trace.output,
            }
            await runs.publish(
                run,
                "STATE_SNAPSHOT",
                snapshot={"mediaCrawler": media_crawler_trace.output},
            )
            await runs.publish(
                run,
                "ACTIVITY_SNAPSHOT",
                messageId=assistant_id,
                activityType="media-crawler-task",
                content=media_crawler_trace.output,
                replace=True,
            )
        if rag_trace and rag_trace.output:
            rag_content = (
                rag_trace.output
                if isinstance(rag_trace.output, dict)
                else {"query": "", "items": [], "error": rag_trace.output}
            )
            agui_activity = {
                "activityType": "rag-retrieval",
                "content": rag_content,
            }
            await runs.publish(
                run,
                "STATE_SNAPSHOT",
                snapshot={"ragRetrieval": rag_content},
            )
            await runs.publish(
                run,
                "ACTIVITY_SNAPSHOT",
                messageId=assistant_id,
                activityType="rag-retrieval",
                content=rag_content,
                replace=True,
            )
        assistant_message = Message(
            id=assistant_id,
            role="assistant",
            content=answer,
            created_at=utc_now(),
            tools=tools,
            provider=runtime.provider,
            model=runtime.model or "demo",
            activity=agui_activity,
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
        await runs.publish(
            run,
            "TEXT_MESSAGE_END",
            messageId=assistant_id,
        )
        await runs.publish(
            run,
            "RUN_FINISHED",
            threadId=conversation_id,
            runId=run.id,
            result={
                "messageId": assistant_id,
                "activity": agui_activity,
            },
        )
        await runs.publish(run, "done")
        await runs.finish(run)
    except Exception as error:
        await runs.publish(
            run,
            "RUN_ERROR",
            message=str(error) or "Agent 运行失败",
            code="AGENT_RUN_ERROR",
        )
        await runs.publish(
            run,
            "run.error",
            error=str(error) or "Agent 运行失败",
        )
        await runs.publish(
            run,
            "TEXT_MESSAGE_END",
            messageId=assistant_id,
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

