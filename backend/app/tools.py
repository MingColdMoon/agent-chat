import ast
import math
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from langchain_core.tools import StructuredTool, tool
from pydantic import BaseModel, Field


class CalculatorError(ValueError):
    pass


def _evaluate_node(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _evaluate_node(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _evaluate_node(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        left = _evaluate_node(node.left)
        right = _evaluate_node(node.right)
        if isinstance(node.op, ast.Add):
            result = left + right
        elif isinstance(node.op, ast.Sub):
            result = left - right
        elif isinstance(node.op, ast.Mult):
            result = left * right
        elif isinstance(node.op, ast.Div):
            if right == 0:
                raise CalculatorError("不能除以零")
            result = left / right
        elif isinstance(node.op, ast.Mod):
            if right == 0:
                raise CalculatorError("不能对零取模")
            result = left % right
        elif isinstance(node.op, ast.Pow):
            if abs(right) > 10:
                raise CalculatorError("指数绝对值不能超过 10")
            result = left**right
        else:
            raise CalculatorError("不支持该运算符")

        if not math.isfinite(result) or abs(result) > 1e100:
            raise CalculatorError("计算结果超出支持范围")
        return result
    raise CalculatorError("只支持数字、括号、+、-、*、/、% 和 **")


def evaluate_expression(expression: str) -> float:
    if not expression.strip() or len(expression) > 200:
        raise CalculatorError("表达式为空或过长")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as error:
        raise CalculatorError("表达式格式不正确") from error
    return _evaluate_node(tree)


@tool
def get_current_time() -> str:
    """获取服务器当前日期、时间和时区。用户询问现在几点或今天日期时使用。"""
    now = datetime.now().astimezone()
    return now.strftime("%Y-%m-%d %H:%M:%S %Z%z")


@tool
def calculator(expression: str) -> str:
    """安全计算基础数学表达式。支持数字、括号及 + - * / % ** 运算符。"""
    result = evaluate_expression(expression)
    if result.is_integer():
        return str(int(result))
    return f"{result:.12g}"


TOOLS = [get_current_time, calculator]
TOOL_MAP = {item.name: item for item in TOOLS}


async def execute_tool(name: str, arguments: dict[str, Any]) -> Any:
    selected_tool = TOOL_MAP.get(name)
    if selected_tool is None:
        raise ValueError(f"未知工具：{name}")
    return await selected_tool.ainvoke(arguments)


class TavilySearchInput(BaseModel):
    query: str = Field(
        min_length=2,
        max_length=500,
        description="需要联网搜索的完整问题或关键词",
    )


def tavily_search_endpoint(api_url: str) -> str:
    parsed = urlsplit(api_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Tavily API 地址必须是有效的 http 或 https 地址")
    path = parsed.path.rstrip("/")
    if not path.endswith("/search"):
        path = f"{path}/search"
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, ""))


def create_tavily_tool(api_key: str, api_url: str) -> StructuredTool:
    endpoint = tavily_search_endpoint(api_url)

    async def _search(query: str) -> str:
        payload = {
            "api_key": api_key,
            "query": query,
            "search_depth": "basic",
            "include_answer": "basic",
            "include_raw_content": False,
            "max_results": 5,
        }
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                response = await client.post(endpoint, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as error:
            detail = error.response.text.strip()[:300]
            raise RuntimeError(
                f"Tavily 搜索失败（HTTP {error.response.status_code}）："
                f"{detail or '服务返回错误'}"
            ) from error
        except (httpx.HTTPError, ValueError) as error:
            raise RuntimeError(f"Tavily 搜索失败：{error}") from error

        results = data.get("results") or []
        sections: list[str] = []
        answer = data.get("answer")
        if answer:
            sections.append(f"摘要：{answer}")
        for index, result in enumerate(results[:5], start=1):
            title = str(result.get("title") or "未命名结果").strip()
            url = str(result.get("url") or "").strip()
            content = " ".join(str(result.get("content") or "").split())
            if len(content) > 700:
                content = f"{content[:700]}..."
            sections.append(
                f"{index}. {title}\n"
                f"来源：{url}\n"
                f"{content}"
            )
        if not sections:
            return f"没有找到与“{query}”相关的联网结果。"
        return "\n\n".join(sections)

    return StructuredTool.from_function(
        coroutine=_search,
        name="web_search",
        description=(
            "使用 Tavily 搜索实时互联网信息。回答新闻、最新动态、事实核查、"
            "网站内容或任何需要外部资料的问题时必须使用此工具。"
            "输入应是清晰的搜索查询。"
        ),
        args_schema=TavilySearchInput,
    )


def tools_for_runtime(
    *,
    web_search_enabled: bool,
    tavily_api_key: str | None,
    tavily_api_url: str | None,
) -> list[Any]:
    tools: list[Any] = [*TOOLS]
    if web_search_enabled and tavily_api_key:
        tools.append(
            create_tavily_tool(
                tavily_api_key,
                tavily_api_url or "https://api.tavily.com",
            )
        )
    return tools

