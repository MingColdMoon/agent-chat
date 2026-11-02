import pytest
from app.tools import (
    CalculatorError,
    create_tavily_tool,
    evaluate_expression,
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

