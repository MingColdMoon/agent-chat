from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.database import Database
from app.main import create_app
from app.sessions import MemorySessionStore


def build_app(
    tmp_path: Path,
    *,
    login_rate_limit: int = 5,
) -> TestClient:
    settings = Settings(
        openai_api_key=None,
        deepseek_api_key=None,
        tavily_api_key=None,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        redis_url="redis://127.0.0.1:6399/15",
        login_rate_limit=login_rate_limit,
        jwt_secret="test-jwt-secret-with-at-least-32-characters",
    )
    app = create_app(
        settings,
        database=Database(settings.database_url),
        session_store=MemorySessionStore(),
    )
    return TestClient(app)


def register(
    client: TestClient,
    username: str = "alice",
    password: str = "password123",
) -> dict:
    response = client.post(
        "/api/auth/register",
        json={"username": username, "password": password},
    )
    assert response.status_code == 201, response.text
    assert "set-cookie" not in response.headers
    return response.json()


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def read_stream(
    client: TestClient,
    stream_url: str,
    access_token: str,
) -> str:
    with client.stream(
        "GET",
        stream_url,
        headers=auth_headers(access_token),
    ) as response:
        return "".join(response.iter_text())


def test_auth_required_for_conversations(tmp_path: Path) -> None:
    with build_app(tmp_path) as client:
        response = client.get("/api/conversations")
        assert response.status_code == 401
        assert response.json()["detail"] == "缺少 Bearer JWT"


def test_jwt_register_login_logout_and_rate_limit(tmp_path: Path) -> None:
    with build_app(tmp_path, login_rate_limit=2) as client:
        auth = register(client)
        access_token = auth["access_token"]
        assert auth["token_type"] == "bearer"
        assert auth["expires_in"] == 3600
        assert auth["user"]["username"] == "alice"

        me = client.get(
            "/api/auth/me",
            headers=auth_headers(access_token),
        )
        assert me.status_code == 200
        assert me.json()["user"]["username"] == "alice"

        tampered = client.get(
            "/api/auth/me",
            headers=auth_headers(f"{access_token[:-1]}x"),
        )
        assert tampered.status_code == 401

        duplicate = client.post(
            "/api/auth/register",
            json={"username": "alice", "password": "password123"},
        )
        assert duplicate.status_code == 409

        logout = client.post(
            "/api/auth/logout",
            headers=auth_headers(access_token),
        )
        assert logout.status_code == 204
        revoked = client.get(
            "/api/auth/me",
            headers=auth_headers(access_token),
        )
        assert revoked.status_code == 401
        assert revoked.json()["detail"] == "JWT 已注销"

        wrong_one = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "wrong-pass"},
        )
        wrong_two = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "wrong-pass"},
        )
        limited = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "wrong-pass"},
        )
        assert wrong_one.status_code == 401
        assert wrong_two.status_code == 401
        assert limited.status_code == 429


def test_chat_streams_and_persists_for_current_user(tmp_path: Path) -> None:
    with build_app(tmp_path) as client:
        auth = register(client)
        headers = auth_headers(auth["access_token"])

        created = client.post("/api/conversations", headers=headers)
        assert created.status_code == 201
        conversation_id = created.json()["conversation"]["id"]

        sent = client.post(
            f"/api/conversations/{conversation_id}/messages",
            headers=headers,
            json={
                "content": "算一下 (18 * 24) / 6",
                "runtime": {"provider": "demo"},
            },
        )
        assert sent.status_code == 202
        stream_body = read_stream(
            client,
            sent.json()["stream_url"],
            auth["access_token"],
        )
        assert '"type": "tool.started"' in stream_body
        assert '"type": "assistant.final"' in stream_body
        assert '"type": "done"' in stream_body

        conversation = client.get(
            f"/api/conversations/{conversation_id}",
            headers=headers,
        ).json()["conversation"]
        assert len(conversation["messages"]) == 2
        assert "72" in conversation["messages"][-1]["content"]
        assert conversation["messages"][-1]["provider"] == "demo"


def test_users_cannot_read_each_others_conversations(tmp_path: Path) -> None:
    with build_app(tmp_path) as client:
        alice = register(client, "alice")
        alice_headers = auth_headers(alice["access_token"])
        conversation_id = client.post(
            "/api/conversations",
            headers=alice_headers,
        ).json()["conversation"]["id"]

        bob = register(client, "bob")
        bob_headers = auth_headers(bob["access_token"])
        assert client.get(
            "/api/conversations",
            headers=bob_headers,
        ).json()["conversations"] == []
        assert (
            client.get(
                f"/api/conversations/{conversation_id}",
                headers=bob_headers,
            ).status_code
            == 404
        )

        conversations = client.get(
            "/api/conversations",
            headers=alice_headers,
        ).json()["conversations"]
        assert [item["id"] for item in conversations] == [conversation_id]


def test_conversations_survive_app_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "test.db"
    settings = Settings(
        openai_api_key=None,
        database_url=f"sqlite+aiosqlite:///{database_path}",
        redis_url="redis://127.0.0.1:6399/15",
        jwt_secret="test-jwt-secret-with-at-least-32-characters",
    )

    first_app = create_app(
        settings,
        database=Database(settings.database_url),
        session_store=MemorySessionStore(),
    )
    with TestClient(first_app) as client:
        auth = register(client)
        headers = auth_headers(auth["access_token"])
        conversation_id = client.post(
            "/api/conversations",
            headers=headers,
        ).json()["conversation"]["id"]

    second_app = create_app(
        settings,
        database=Database(settings.database_url),
        session_store=MemorySessionStore(),
    )
    with TestClient(second_app) as client:
        login = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "password123"},
        )
        assert login.status_code == 200
        conversations = client.get(
            "/api/conversations",
            headers=auth_headers(login.json()["access_token"]),
        ).json()["conversations"]
        assert [item["id"] for item in conversations] == [conversation_id]


def test_health_lists_supported_providers(tmp_path: Path) -> None:
    with build_app(tmp_path) as client:
        health = client.get("/api/health").json()

    assert health["providers"] == ["demo", "openai", "deepseek", "custom"]
    assert health["server_credentials"] == []
    assert health["tavily_configured"] is False


def test_builtin_agents_are_seeded_for_every_user(tmp_path: Path) -> None:
    with build_app(tmp_path) as client:
        auth = register(client)
        headers = auth_headers(auth["access_token"])

        response = client.get("/api/agents", headers=headers)

    assert response.status_code == 200
    agents = response.json()["agents"]
    assert [agent["name"] for agent in agents] == [
        "智能客服",
        "智能自动化报表",
        "装机大师",
        "MediaCrawler 采集助手",
    ]
    assert all(agent["is_builtin"] for agent in agents)


def test_custom_agent_create_apply_and_delete(tmp_path: Path) -> None:
    with build_app(tmp_path) as client:
        auth = register(client)
        headers = auth_headers(auth["access_token"])

        created_agent = client.post(
            "/api/agents",
            headers=headers,
            json={
                "name": "产品文案助手",
                "description": "为产品生成清晰、有行动感的营销文案。",
                "category": "内容创作",
                "icon": "sparkles",
                "instructions": (
                    "你是产品文案助手。先识别目标用户和核心卖点，"
                    "再给出三个不同风格的文案方案。"
                ),
            },
        )
        assert created_agent.status_code == 201
        custom_agent = created_agent.json()["agent"]
        assert custom_agent["is_builtin"] is False

        conversation = client.post(
            "/api/conversations",
            headers=headers,
            json={"agent_id": custom_agent["id"]},
        )
        assert conversation.status_code == 201
        conversation_data = conversation.json()["conversation"]
        assert conversation_data["agent"]["id"] == custom_agent["id"]

        sent = client.post(
            f"/api/conversations/{conversation_data['id']}/messages",
            headers=headers,
            json={
                "content": "为智能水杯写一段新品介绍",
                "runtime": {"provider": "demo"},
            },
        )
        stream_body = read_stream(
            client,
            sent.json()["stream_url"],
            auth["access_token"],
        )
        assert "产品文案助手" in stream_body
        assert '"type": "done"' in stream_body

        deleted = client.delete(
            f"/api/agents/{custom_agent['id']}",
            headers=headers,
        )
        assert deleted.status_code == 204
        conversation_after = client.get(
            f"/api/conversations/{conversation_data['id']}",
            headers=headers,
        ).json()["conversation"]
        assert conversation_after["agent"] is None


def test_custom_agents_are_private_and_can_be_applied_to_existing_chat(
    tmp_path: Path,
) -> None:
    with build_app(tmp_path) as client:
        alice = register(client, "alice")
        alice_headers = auth_headers(alice["access_token"])
        custom_agent = client.post(
            "/api/agents",
            headers=alice_headers,
            json={
                "name": "私有分析助手",
                "description": "只对创建者可见的数据分析智能体。",
                "category": "数据分析",
                "icon": "chart",
                "instructions": "你需要用表格整理指标并给出异常说明。",
            },
        ).json()["agent"]

        bob = register(client, "bob")
        bob_headers = auth_headers(bob["access_token"])
        bob_agents = client.get(
            "/api/agents",
            headers=bob_headers,
        ).json()["agents"]
        assert all(agent["id"] != custom_agent["id"] for agent in bob_agents)
        assert (
            client.post(
                "/api/conversations",
                headers=bob_headers,
                json={"agent_id": custom_agent["id"]},
            ).status_code
            == 404
        )

        conversation_id = client.post(
            "/api/conversations",
            headers=alice_headers,
        ).json()["conversation"]["id"]
        applied = client.patch(
            f"/api/conversations/{conversation_id}/agent",
            headers=alice_headers,
            json={"agent_id": custom_agent["id"]},
        )
        assert applied.status_code == 200
        assert applied.json()["conversation"]["agent"]["id"] == (
            custom_agent["id"]
        )


def test_builtin_customer_service_uses_agent_persona(tmp_path: Path) -> None:
    with build_app(tmp_path) as client:
        auth = register(client)
        headers = auth_headers(auth["access_token"])
        customer_service = client.get(
            "/api/agents",
            headers=headers,
        ).json()["agents"][0]
        conversation = client.post(
            "/api/conversations",
            headers=headers,
            json={"agent_id": customer_service["id"]},
        ).json()["conversation"]
        sent = client.post(
            f"/api/conversations/{conversation['id']}/messages",
            headers=headers,
            json={
                "content": "我的订单一直没发货",
                "runtime": {"provider": "demo"},
            },
        )
        stream_body = read_stream(
            client,
            sent.json()["stream_url"],
            auth["access_token"],
        )

    assert "智能客服" in stream_body
    assert "订单号" in stream_body


def test_pc_builder_emits_agui_activity_and_persists_plan(
    tmp_path: Path,
) -> None:
    with build_app(tmp_path) as client:
        auth = register(client)
        headers = auth_headers(auth["access_token"])
        agents = client.get("/api/agents", headers=headers).json()["agents"]
        pc_builder = next(
            agent for agent in agents if agent["key"] == "pc-builder"
        )
        conversation = client.post(
            "/api/conversations",
            headers=headers,
            json={"agent_id": pc_builder["id"]},
        ).json()["conversation"]
        sent = client.post(
            f"/api/conversations/{conversation['id']}/messages",
            headers=headers,
            json={
                "content": "预算：10000 元；用途：游戏；偏好：静音、外观",
                "runtime": {"provider": "demo"},
            },
        )
        stream_body = read_stream(
            client,
            sent.json()["stream_url"],
            auth["access_token"],
        )
        stored = client.get(
            f"/api/conversations/{conversation['id']}",
            headers=headers,
        ).json()["conversation"]

    for event_type in (
        "RUN_STARTED",
        "TEXT_MESSAGE_CONTENT",
        "TOOL_CALL_START",
        "TOOL_CALL_RESULT",
        "STATE_SNAPSHOT",
        "ACTIVITY_SNAPSHOT",
        "RUN_FINISHED",
    ):
        assert f'"type": "{event_type}"' in stream_body
    assistant = stored["messages"][-1]
    assert assistant["activity"]["activityType"] == "pc-build-plan"
    assert assistant["activity"]["content"]["use_case"] == "游戏娱乐"
    assert len(assistant["activity"]["content"]["components"]) == 8


def test_media_crawler_emits_task_preview_activity(tmp_path: Path) -> None:
    with build_app(tmp_path) as client:
        auth = register(client)
        headers = auth_headers(auth["access_token"])
        agents = client.get("/api/agents", headers=headers).json()["agents"]
        media_crawler = next(
            agent for agent in agents if agent["key"] == "media-crawler"
        )
        conversation = client.post(
            "/api/conversations",
            headers=headers,
            json={"agent_id": media_crawler["id"]},
        ).json()["conversation"]
        sent = client.post(
            f"/api/conversations/{conversation['id']}/messages",
            headers=headers,
            json={
                "content": (
                    "请执行 MediaCrawler 公开数据采集任务。\n"
                    "平台：小红书（xhs）\n"
                    "任务：关键词（search）\n"
                    "关键词：AI 效率工具\n"
                    "内容上限：12\n"
                    "单篇评论上限：8\n"
                    "一级评论：开启\n"
                    "二级评论：关闭\n"
                    "下载媒体：关闭\n"
                    "导出格式：jsonl"
                ),
                "runtime": {"provider": "demo"},
            },
        )
        stream_body = read_stream(
            client,
            sent.json()["stream_url"],
            auth["access_token"],
        )
        stored = client.get(
            f"/api/conversations/{conversation['id']}",
            headers=headers,
        ).json()["conversation"]

    assert '"type": "ACTIVITY_SNAPSHOT"' in stream_body
    assert "MediaCrawler 任务预览" in stream_body
    assistant = stored["messages"][-1]
    assert assistant["activity"]["activityType"] == "media-crawler-task"
    assert assistant["activity"]["content"]["platform"] == "xhs"
    assert assistant["activity"]["content"]["status"] == "preview"
    assert assistant["activity"]["content"]["summary"]["max_items"] == 12

