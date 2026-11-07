import pytest
from app.tools import (
    CalculatorError,
    create_media_crawler_tools,
    create_tavily_tool,
    evaluate_expression,
    media_crawler_endpoint,
    tavily_search_endpoint,
    tools_for_runtime,
)


def test_calculator_handles_precedence() -> None:
    assert evaluate_expression("(18 * 24) / 6") == 72


def test_calculator_rejects_code_execution() -> None:
    with pytest.raises(CalculatorError):
        evaluate_expression("__import__('os').system('whoami')")


def test_tavily_endpoint_is_normalized() -> None:
    assert (
        tavily_search_endpoint("https://api.tavily.com")
        == "https://api.tavily.com/search"
    )
    assert (
        tavily_search_endpoint("https://api.tavily.com/search/")
        == "https://api.tavily.com/search"
    )


def test_web_search_tool_is_added_only_when_configured() -> None:
    base_tools = tools_for_runtime(
        web_search_enabled=False,
        tavily_api_key=None,
        tavily_api_url=None,
    )
    search_tools = tools_for_runtime(
        web_search_enabled=True,
        tavily_api_key="tvly-test",
        tavily_api_url="https://api.tavily.com",
    )

    assert [tool.name for tool in base_tools] == [
        "get_current_time",
        "calculator",
    ]
    assert "web_search" in [tool.name for tool in search_tools]


def test_media_crawler_endpoint_accepts_base_or_api_url() -> None:
    assert (
        media_crawler_endpoint("http://127.0.0.1:8080", "crawler/start")
        == "http://127.0.0.1:8080/api/crawler/start"
    )
    assert (
        media_crawler_endpoint("https://crawler.example/api/", "health")
        == "https://crawler.example/api/health"
    )


def test_media_crawler_tools_are_scoped_to_builtin_agent() -> None:
    generic = tools_for_runtime(
        web_search_enabled=False,
        tavily_api_key=None,
        tavily_api_url=None,
    )
    crawler = tools_for_runtime(
        web_search_enabled=False,
        tavily_api_key=None,
        tavily_api_url=None,
        agent_key="media-crawler",
    )

    assert "start_media_crawler_task" not in [tool.name for tool in generic]
    assert [tool.name for tool in crawler][-3:] == [
        "start_media_crawler_task",
        "get_media_crawler_status",
        "list_media_crawler_files",
    ]


@pytest.mark.asyncio
async def test_media_crawler_preview_contains_executable_request() -> None:
    tools = create_media_crawler_tools(None)
    start_tool = tools[0]
    result = await start_tool.ainvoke(
        {
            "platform": "xhs",
            "crawler_type": "search",
            "keywords": "AI 工具",
            "targets": [],
            "max_items": 10,
            "max_comments": 5,
            "include_comments": True,
            "include_sub_comments": False,
            "download_media": False,
            "save_option": "csv",
            "login_type": "cookie",
            "start_page": 1,
            "headless": True,
        }
    )

    assert result["source"] == "mediacrawler"
    assert result["status"] == "preview"
    assert result["request"]["platform"] == "xhs"
    assert result["request"]["keywords"] == "AI 工具"
    assert result["request"]["save_option"] == "csv"
    assert result["execution_ready"] is False


@pytest.mark.asyncio
async def test_media_crawler_starts_remote_task(monkeypatch) -> None:
    captured: list[dict] = []

    class FakeResponse:
        status_code = 200
        text = ""

        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.payload

    class FakeClient:
        def __init__(self, timeout: int) -> None:
            captured.append({"timeout": timeout})

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def request(
            self,
            method: str,
            url: str,
            *,
            json=None,
            params=None,
            headers=None,
        ) -> FakeResponse:
            captured.append(
                {
                    "method": method,
                    "url": url,
                    "json": json,
                    "params": params,
                    "headers": headers,
                }
            )
            if url.endswith("/health"):
                return FakeResponse({"status": "ok"})
            return FakeResponse(
                {"status": "ok", "message": "Crawler started successfully"}
            )

    monkeypatch.setattr("app.tools.httpx.AsyncClient", FakeClient)
    tools = create_media_crawler_tools(
        "http://127.0.0.1:8080",
        "secret-token",
    )
    result = await tools[0].ainvoke(
        {
            "platform": "bili",
            "crawler_type": "detail",
            "keywords": "",
            "targets": ["BV1example"],
            "max_items": 3,
            "max_comments": 6,
            "include_comments": True,
            "include_sub_comments": True,
            "download_media": False,
            "save_option": "json",
            "login_type": "cookie",
            "start_page": 1,
            "headless": True,
        }
    )

    assert result["status"] == "accepted"
    assert result["request"]["specified_ids"] == "BV1example"
    request_calls = [item for item in captured if "url" in item]
    assert request_calls[0]["url"] == "http://127.0.0.1:8080/api/health"
    assert request_calls[1]["url"] == (
        "http://127.0.0.1:8080/api/crawler/start"
    )
    assert request_calls[1]["json"]["enable_sub_comments"] is True
    assert request_calls[1]["headers"] == {
        "Authorization": "Bearer secret-token"
    }


@pytest.mark.asyncio
async def test_tavily_tool_formats_search_results(monkeypatch) -> None:
    captured: dict = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "answer": "A short answer.",
                "results": [
                    {
                        "title": "Example result",
                        "url": "https://example.com/news",
                        "content": "Useful result content.",
                    }
                ],
            }

    class FakeClient:
        def __init__(self, timeout: int) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, url: str, json: dict) -> FakeResponse:
            captured["url"] = url
            captured["payload"] = json
            return FakeResponse()

    monkeypatch.setattr("app.tools.httpx.AsyncClient", FakeClient)
    search_tool = create_tavily_tool("tvly-test", "https://api.tavily.com")
    result = await search_tool.ainvoke({"query": "AI news"})

    assert captured["url"] == "https://api.tavily.com/search"
    assert captured["payload"]["api_key"] == "tvly-test"
    assert "A short answer." in result
    assert "Example result" in result
    assert "https://example.com/news" in result

