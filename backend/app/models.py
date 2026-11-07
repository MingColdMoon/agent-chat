from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


Role = Literal["user", "assistant"]
ProviderId = Literal["demo", "openai", "deepseek", "custom"]


class ToolTrace(BaseModel):
    id: str
    name: str
    input: dict[str, Any] = Field(default_factory=dict)
    state: Literal["running", "complete", "error"] = "running"
    output: Any | None = None


class Message(BaseModel):
    id: str
    role: Role
    content: str
    created_at: str
    tools: list[ToolTrace] = Field(default_factory=list)
    error: str | None = None
    provider: str | None = None
    model: str | None = None
    activity: dict[str, Any] | None = None


class AgentSummary(BaseModel):
    id: str
    name: str
    description: str
    category: str
    icon: str
    key: str | None = None
    is_builtin: bool = False
    created_at: str


class Conversation(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: list[Message] = Field(default_factory=list)
    agent: AgentSummary | None = None
    agent_prompt: str | None = Field(default=None, exclude=True)


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int
    agent: AgentSummary | None = None


class AgentCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=4, max_length=300)
    category: str = Field(default="自定义", min_length=1, max_length=40)
    icon: str = Field(default="bot", max_length=32)
    instructions: str = Field(min_length=10, max_length=8_000)


class AgentListResponse(BaseModel):
    agents: list[AgentSummary]


class AgentResponse(BaseModel):
    agent: AgentSummary


class CreateConversationRequest(BaseModel):
    agent_id: str | None = None


class ApplyAgentRequest(BaseModel):
    agent_id: str


class CreateConversationResponse(BaseModel):
    conversation: Conversation


class ConversationResponse(BaseModel):
    conversation: Conversation


class ConversationListResponse(BaseModel):
    conversations: list[ConversationSummary]


class RuntimeConfig(BaseModel):
    provider: ProviderId = "demo"
    api_key: str | None = Field(default=None, max_length=2_048)
    base_url: str | None = Field(default=None, max_length=2_048)
    model: str | None = Field(default=None, max_length=200)
    web_search_enabled: bool = False
    tavily_api_key: str | None = Field(default=None, max_length=2_048)
    tavily_api_url: str | None = Field(default=None, max_length=2_048)


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)


class SendMessageResponse(BaseModel):
    run_id: str
    conversation_id: str
    user_message: Message
    stream_url: str
    provider: ProviderId
    model: str


class HealthResponse(BaseModel):
    ok: bool
    mode: Literal["demo", "live"]
    model: str
    tools: list[str]
    providers: list[ProviderId]
    server_credentials: list[ProviderId]
    tavily_configured: bool
    media_crawler_configured: bool = False


class AuthCredentials(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        username = value.strip().lower()
        if len(username) < 3:
            raise ValueError("用户名至少需要 3 个字符")
        if not all(
            character.isalnum() or character in "._-"
            for character in username
        ):
            raise ValueError("用户名只能包含字母、数字、点、下划线和短横线")
        return username


class UserInfo(BaseModel):
    id: str
    username: str
    created_at: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    expires_at: str
    user: UserInfo


class MeResponse(BaseModel):
    user: UserInfo


