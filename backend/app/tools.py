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


@tool
def generate_pc_build(
    budget: int,
    use_case: str,
    priorities: str = "",
) -> dict[str, Any]:
    """按预算和用途生成一套兼容的台式机装机方案。

    budget 为人民币预算，use_case 支持 gaming、productivity、ai、balanced
    或对应中文描述，priorities 可填写静音、外观、扩展性等偏好。
    价格均为预估价，不是实时市场报价。
    """
    normalized_budget = max(4000, min(30000, int(budget)))
    normalized_case = _normalize_pc_use_case(use_case)
    case_label = {
        "gaming": "游戏娱乐",
        "productivity": "生产力",
        "ai": "AI 与本地模型",
        "balanced": "均衡全能",
    }[normalized_case]

    cpu_ratio, gpu_ratio = {
        "gaming": (0.16, 0.39),
        "productivity": (0.25, 0.22),
        "ai": (0.16, 0.43),
        "balanced": (0.2, 0.31),
    }[normalized_case]
    cpu_price = max(650, normalized_budget * cpu_ratio)
    gpu_price = max(1500, normalized_budget * gpu_ratio)

    if normalized_case == "gaming":
        cpu = (
            "AMD Ryzen 7 7800X3D"
            if normalized_budget >= 11000
            else "Intel Core i5-14600KF"
            if normalized_budget >= 7500
            else "Intel Core i5-12400F"
        )
        gpu = (
            "NVIDIA RTX 4070 Ti SUPER 16GB"
            if normalized_budget >= 15000
            else "NVIDIA RTX 4070 SUPER 12GB"
            if normalized_budget >= 9500
            else "NVIDIA RTX 4060 Ti 8GB"
            if normalized_budget >= 6500
            else "NVIDIA RTX 3060 12GB"
        )
        motherboard = "B650M" if cpu.startswith("AMD") else "B760M"
    elif normalized_case == "ai":
        cpu = (
            "AMD Ryzen 9 7900X"
            if normalized_budget >= 12000
            else "AMD Ryzen 7 7700"
        )
        gpu = (
            "NVIDIA RTX 4070 Ti SUPER 16GB"
            if normalized_budget >= 14000
            else "NVIDIA RTX 4060 Ti 16GB"
        )
        motherboard = "B650M"
    elif normalized_case == "productivity":
        cpu = (
            "AMD Ryzen 9 7900X"
            if normalized_budget >= 10000
            else "Intel Core i5-14600K"
        )
        gpu = (
            "NVIDIA RTX 4070 SUPER 12GB"
            if normalized_budget >= 10000
            else "NVIDIA RTX 4060 8GB"
        )
        motherboard = "B650M" if cpu.startswith("AMD") else "B760M"
    else:
        cpu = "Intel Core i5-14600KF"
        gpu = (
            "NVIDIA RTX 4070 SUPER 12GB"
            if normalized_budget >= 10000
            else "NVIDIA RTX 4060 Ti 8GB"
        )
        motherboard = "B760M"

    ram_size = "64GB" if normalized_case == "ai" and normalized_budget >= 12000 else "32GB"
    ssd_size = "2TB" if normalized_budget >= 9000 else "1TB"
    psu_wattage = 850 if normalized_budget >= 10000 else 650
    cooler = (
        "360mm 一体式水冷"
        if normalized_budget >= 12000
        else "双塔风冷"
    )
    remaining_ratio = 1 - cpu_ratio - gpu_ratio
    component_prices = {
        "CPU": cpu_price,
        "显卡": gpu_price,
        "主板": normalized_budget * remaining_ratio * 0.24,
        "内存": normalized_budget * remaining_ratio * 0.18,
        "固态硬盘": normalized_budget * remaining_ratio * 0.2,
        "电源": normalized_budget * remaining_ratio * 0.14,
        "散热器": normalized_budget * remaining_ratio * 0.12,
        "机箱": normalized_budget * remaining_ratio * 0.12,
    }
    components = [
        {
            "category": "CPU",
            "name": cpu,
            "price": _pc_price(component_prices["CPU"]),
            "reason": "匹配主要用途的多核与单核性能需求",
        },
        {
            "category": "显卡",
            "name": gpu,
            "price": _pc_price(component_prices["显卡"]),
            "reason": "优先保证图形性能与显存容量",
        },
        {
            "category": "主板",
            "name": f"{motherboard} 主板",
            "price": _pc_price(component_prices["主板"]),
            "reason": "接口与供电满足当前平台",
        },
        {
            "category": "内存",
            "name": f"{ram_size} DDR5 6000",
            "price": _pc_price(component_prices["内存"]),
            "reason": "双通道容量满足多任务与模型加载",
        },
        {
            "category": "固态硬盘",
            "name": f"{ssd_size} PCIe 4.0 NVMe",
            "price": _pc_price(component_prices["固态硬盘"]),
            "reason": "兼顾容量、顺序读写和日常响应",
        },
        {
            "category": "电源",
            "name": f"{psu_wattage}W 80 PLUS Gold",
            "price": _pc_price(component_prices["电源"]),
            "reason": "预留显卡瞬态功耗与升级余量",
        },
        {
            "category": "散热器",
            "name": cooler,
            "price": _pc_price(component_prices["散热器"]),
            "reason": "压制高负载温度并兼顾噪声",
        },
        {
            "category": "机箱",
            "name": "中塔风道机箱",
            "price": _pc_price(component_prices["机箱"]),
            "reason": "保证显卡长度、散热器和走线空间",
        },
    ]
    total = sum(component["price"] for component in components)
    return {
        "title": f"{case_label}装机方案",
        "use_case": case_label,
        "budget": normalized_budget,
        "total_price": total,
        "budget_delta": normalized_budget - total,
        "price_basis": "预估参考价，非实时市场报价",
        "priorities": [
            item.strip()
            for item in priorities.replace("，", ",").split(",")
            if item.strip()
        ],
        "components": components,
        "compatibility_notes": [
            "内存建议开启 EXPO/XMP 并验证稳定性。",
            "显卡长度和散热器高度需在购买前对照机箱参数。",
            "高负载使用建议增加机箱进出风风扇。",
        ],
        "upgrade_path": (
            "优先升级存储和内存；后续可更换同平台更高一级显卡。"
        ),
    }


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
    agent_key: str | None = None,
) -> list[Any]:
    tools: list[Any] = [*TOOLS]
    if agent_key == "pc-builder":
        tools.append(generate_pc_build)
    if web_search_enabled and tavily_api_key:
        tools.append(
            create_tavily_tool(
                tavily_api_key,
                tavily_api_url or "https://api.tavily.com",
            )
        )
    return tools


def _normalize_pc_use_case(value: str) -> str:
    normalized = value.lower()
    if any(keyword in normalized for keyword in ("游戏", "gaming", "game")):
        return "gaming"
    if any(keyword in normalized for keyword in ("ai", "模型", "训练", "推理")):
        return "ai"
    if any(
        keyword in normalized
        for keyword in ("生产", "办公", "剪辑", "渲染", "productivity")
    ):
        return "productivity"
    return "balanced"


def _pc_price(value: float) -> int:
    return max(50, int(round(value / 50) * 50))

