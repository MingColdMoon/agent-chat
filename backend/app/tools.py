import ast
import math
from datetime import datetime
from typing import Any, Literal
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


MediaCrawlerPlatform = Literal[
    "xhs",
    "dy",
    "ks",
    "bili",
    "wb",
    "tieba",
    "zhihu",
]
MediaCrawlerTaskType = Literal["search", "detail", "creator"]

MEDIA_CRAWLER_PLATFORM_LABELS = {
    "xhs": "小红书",
    "dy": "抖音",
    "ks": "快手",
    "bili": "B站",
    "wb": "微博",
    "tieba": "百度贴吧",
    "zhihu": "知乎",
}


class MediaCrawlerTaskInput(BaseModel):
    platform: MediaCrawlerPlatform = Field(
        default="xhs",
        description="目标平台：xhs、dy、ks、bili、wb、tieba 或 zhihu",
    )
    crawler_type: MediaCrawlerTaskType = Field(
        default="search",
        description="任务类型：search 关键词搜索、detail 指定内容、creator 指定创作者",
    )
    keywords: str = Field(
        default="",
        max_length=500,
        description="搜索任务的关键词，多个关键词用中文或英文逗号分隔",
    )
    targets: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="详情或创作者任务的内容 ID、创作者 ID 或完整主页链接",
    )
    max_items: int = Field(
        default=15,
        ge=1,
        le=100,
        description="最多采集的内容数量",
    )
    max_comments: int = Field(
        default=10,
        ge=0,
        le=100,
        description="每篇内容最多采集的一级评论数量",
    )
    include_comments: bool = Field(
        default=True,
        description="是否采集一级评论",
    )
    include_sub_comments: bool = Field(
        default=False,
        description="是否采集二级评论",
    )
    download_media: bool = Field(
        default=False,
        description="是否下载封面、图片或视频",
    )
    save_option: Literal["jsonl", "json", "csv", "excel", "sqlite"] = Field(
        default="jsonl",
        description="结果保存格式",
    )
    login_type: Literal["cookie", "qrcode", "phone"] = Field(
        default="cookie",
        description="MediaCrawler 服务端登录方式",
    )
    start_page: int = Field(
        default=1,
        ge=1,
        le=100,
        description="搜索任务起始页码",
    )
    headless: bool = Field(
        default=True,
        description="是否使用无头浏览器",
    )


class MediaCrawlerStatusInput(BaseModel):
    include_logs: bool = Field(
        default=True,
        description="是否同时读取最近运行日志",
    )


class MediaCrawlerFilesInput(BaseModel):
    platform: MediaCrawlerPlatform | None = Field(
        default=None,
        description="按平台过滤数据文件",
    )
    file_type: Literal["json", "csv", "xlsx", "xls"] | None = Field(
        default=None,
        description="按文件类型过滤",
    )


def media_crawler_endpoint(api_url: str, path: str) -> str:
    """Append an API path while accepting a base URL with or without /api."""
    parsed = urlsplit(api_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("MediaCrawler API 地址必须是有效的 http 或 https 地址")
    base_path = parsed.path.rstrip("/")
    if base_path.endswith("/api"):
        base_path = base_path[:-4]
    normalized_path = f"/{path.strip('/')}"
    return urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            f"{base_path}/api{normalized_path}",
            parsed.query,
            "",
        )
    )


def _media_crawler_headers(api_token: str | None) -> dict[str, str]:
    token = (api_token or "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def _media_crawler_request(payload: MediaCrawlerTaskInput) -> dict[str, Any]:
    keywords = payload.keywords.strip()
    targets = [item.strip() for item in payload.targets if item.strip()]
    if payload.crawler_type == "search" and not keywords:
        raise ValueError("关键词搜索任务必须填写 keywords")
    if payload.crawler_type != "search" and not targets:
        raise ValueError("详情或创作者任务必须至少填写一个 targets")

    specified_ids = ",".join(targets)
    return {
        "platform": payload.platform,
        "login_type": payload.login_type,
        "crawler_type": payload.crawler_type,
        "keywords": keywords if payload.crawler_type == "search" else "",
        "specified_ids": (
            specified_ids if payload.crawler_type == "detail" else ""
        ),
        "creator_ids": (
            specified_ids if payload.crawler_type == "creator" else ""
        ),
        "start_page": payload.start_page,
        "enable_comments": payload.include_comments,
        "enable_sub_comments": payload.include_sub_comments,
        "enable_media": payload.download_media,
        "save_option": payload.save_option,
        "headless": payload.headless,
        "max_notes_count": payload.max_items,
        "max_comments_count": (
            payload.max_comments if payload.include_comments else None
        ),
    }


def _media_crawler_preview(
    payload: MediaCrawlerTaskInput,
    request: dict[str, Any],
) -> dict[str, Any]:
    mode_labels = {
        "search": "关键词搜索",
        "detail": "指定内容详情",
        "creator": "创作者主页",
    }
    warnings = [
        "仅采集公开信息，并遵守目标平台服务条款、robots.txt 与适用法律。",
        "请控制采集数量和频率，不要用于大规模抓取、绕过访问控制或商业转售。",
        "登录 Cookie 应由 MediaCrawler 独立服务在本机安全保存，不要发送到聊天中。",
    ]
    if payload.include_sub_comments:
        warnings.append("二级评论会增加请求数量和运行时间。")
    if payload.download_media:
        warnings.append("媒体下载需要 ffmpeg，部分直链可能受平台防盗链限制。")
    targets = [item.strip() for item in payload.targets if item.strip()]
    return {
        "source": "mediacrawler",
        "status": "preview",
        "execution_ready": False,
        "platform": payload.platform,
        "platform_label": MEDIA_CRAWLER_PLATFORM_LABELS[payload.platform],
        "crawler_type": payload.crawler_type,
        "crawler_type_label": mode_labels[payload.crawler_type],
        "request": request,
        "summary": {
            "query": payload.keywords.strip(),
            "targets": targets,
            "max_items": payload.max_items,
            "max_comments": payload.max_comments,
            "comments": payload.include_comments,
            "sub_comments": payload.include_sub_comments,
            "media": payload.download_media,
            "save_option": payload.save_option,
        },
        "warnings": warnings,
        "message": (
            "尚未连接 MediaCrawler 服务，已生成可执行任务参数。"
            "配置 MEDIACRAWLER_API_URL 后可启动真实采集。"
        ),
        "setup": {
            "api_url_env": "MEDIACRAWLER_API_URL",
            "token_env": "MEDIACRAWLER_API_TOKEN",
            "service_command": (
                "uv run uvicorn api.main:app --host 127.0.0.1 --port 8080"
            ),
            "upstream": "https://github.com/NanmiCoder/MediaCrawler",
        },
    }


def create_media_crawler_tools(
    api_url: str | None,
    api_token: str | None = None,
) -> list[StructuredTool]:
    base_url = (api_url or "").strip()
    headers = _media_crawler_headers(api_token)

    async def _request_json(
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        timeout: int = 15,
    ) -> dict[str, Any]:
        if not base_url:
            raise RuntimeError("MediaCrawler 服务尚未配置")
        endpoint = media_crawler_endpoint(base_url, path)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(
                method,
                endpoint,
                json=payload,
                params=params,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {"data": data}

    async def _start_media_crawler_task(
        platform: MediaCrawlerPlatform,
        crawler_type: MediaCrawlerTaskType,
        keywords: str,
        targets: list[str],
        max_items: int,
        max_comments: int,
        include_comments: bool,
        include_sub_comments: bool,
        download_media: bool,
        save_option: Literal["jsonl", "json", "csv", "excel", "sqlite"],
        login_type: Literal["cookie", "qrcode", "phone"],
        start_page: int,
        headless: bool,
    ) -> dict[str, Any]:
        payload = MediaCrawlerTaskInput(
            platform=platform,
            crawler_type=crawler_type,
            keywords=keywords,
            targets=targets,
            max_items=max_items,
            max_comments=max_comments,
            include_comments=include_comments,
            include_sub_comments=include_sub_comments,
            download_media=download_media,
            save_option=save_option,
            login_type=login_type,
            start_page=start_page,
            headless=headless,
        )
        request = _media_crawler_request(payload)
        if not base_url:
            return _media_crawler_preview(payload, request)

        try:
            health = await _request_json("GET", "health", timeout=4)
            started = await _request_json(
                "POST",
                "crawler/start",
                payload=request,
                timeout=20,
            )
        except httpx.HTTPStatusError as error:
            detail = error.response.text.strip()[:500]
            if error.response.status_code == 400:
                return {
                    "source": "mediacrawler",
                    "status": "busy",
                    "execution_ready": True,
                    "platform": payload.platform,
                    "platform_label": MEDIA_CRAWLER_PLATFORM_LABELS[
                        payload.platform
                    ],
                    "crawler_type": payload.crawler_type,
                    "request": request,
                    "message": (
                        "MediaCrawler 已有任务在运行，请先读取状态或等待任务结束。"
                    ),
                    "detail": detail,
                }
            return {
                "source": "mediacrawler",
                "status": "error",
                "execution_ready": True,
                "platform": payload.platform,
                "platform_label": MEDIA_CRAWLER_PLATFORM_LABELS[
                    payload.platform
                ],
                "crawler_type": payload.crawler_type,
                "request": request,
                "message": (
                    f"MediaCrawler 返回 HTTP {error.response.status_code}，"
                    "任务未启动。"
                ),
                "detail": detail,
            }
        except (httpx.HTTPError, ValueError, RuntimeError) as error:
            return {
                "source": "mediacrawler",
                "status": "unavailable",
                "execution_ready": False,
                "platform": payload.platform,
                "platform_label": MEDIA_CRAWLER_PLATFORM_LABELS[payload.platform],
                "crawler_type": payload.crawler_type,
                "request": request,
                "message": f"无法连接 MediaCrawler 服务：{error}",
            }

        return {
            "source": "mediacrawler",
            "status": "accepted",
            "execution_ready": True,
            "platform": payload.platform,
            "platform_label": MEDIA_CRAWLER_PLATFORM_LABELS[payload.platform],
            "crawler_type": payload.crawler_type,
            "crawler_type_label": {
                "search": "关键词搜索",
                "detail": "指定内容详情",
                "creator": "创作者主页",
            }[payload.crawler_type],
            "request": request,
            "service": {
                "health": health.get("status", "ok"),
                "start": started.get("status", "ok"),
            },
            "summary": {
                "query": keywords.strip(),
                "targets": targets,
                "max_items": max_items,
                "max_comments": max_comments,
                "comments": include_comments,
                "sub_comments": include_sub_comments,
                "media": download_media,
                "save_option": save_option,
            },
            "warnings": [
                "任务在 MediaCrawler 独立服务中异步运行。",
                "请使用状态工具查看进度，并使用文件工具定位导出结果。",
                "合规使用公开数据，禁止大规模采集和绕过平台访问控制。",
            ],
            "message": "MediaCrawler 任务已提交，当前在独立服务中异步运行。",
        }

    async def _get_media_crawler_status(
        include_logs: bool,
    ) -> dict[str, Any]:
        if not base_url:
            return {
                "source": "mediacrawler",
                "status": "unavailable",
                "message": (
                    "尚未连接 MediaCrawler 服务。请配置 "
                    "MEDIACRAWLER_API_URL 后重试。"
                ),
            }
        try:
            status = await _request_json("GET", "crawler/status", timeout=8)
            logs: list[dict[str, Any]] = []
            if include_logs:
                log_data = await _request_json(
                    "GET",
                    "crawler/logs",
                    params={"limit": 30},
                    timeout=8,
                )
                raw_logs = log_data.get("logs", [])
                if isinstance(raw_logs, list):
                    logs = raw_logs[-30:]
        except (httpx.HTTPError, ValueError, RuntimeError) as error:
            return {
                "source": "mediacrawler",
                "status": "unavailable",
                "message": f"无法读取 MediaCrawler 状态：{error}",
            }
        return {
            "source": "mediacrawler",
            "status": status.get("status", "unknown"),
            "platform": status.get("platform"),
            "crawler_type": status.get("crawler_type"),
            "started_at": status.get("started_at"),
            "error_message": status.get("error_message"),
            "logs": logs,
            "message": "已读取 MediaCrawler 最新运行状态。",
        }

    async def _list_media_crawler_files(
        platform: MediaCrawlerPlatform | None,
        file_type: Literal["json", "csv", "xlsx", "xls"] | None,
    ) -> dict[str, Any]:
        if not base_url:
            return {
                "source": "mediacrawler",
                "status": "unavailable",
                "files": [],
                "message": "尚未连接 MediaCrawler 服务，无法读取导出文件。",
            }
        params = {
            key: value
            for key, value in {
                "platform": platform,
                "file_type": file_type,
            }.items()
            if value
        }
        try:
            data = await _request_json(
                "GET",
                "data/files",
                params=params,
                timeout=12,
            )
        except (httpx.HTTPError, ValueError, RuntimeError) as error:
            return {
                "source": "mediacrawler",
                "status": "unavailable",
                "files": [],
                "message": f"无法读取 MediaCrawler 数据文件：{error}",
            }
        files = data.get("files", [])
        return {
            "source": "mediacrawler",
            "status": "ok",
            "files": files[:50] if isinstance(files, list) else [],
            "message": "已读取 MediaCrawler 导出文件列表。",
        }

    return [
        StructuredTool.from_function(
            coroutine=_start_media_crawler_task,
            name="start_media_crawler_task",
            description=(
                "在 MediaCrawler 独立服务中启动公开社交媒体数据采集任务。"
                "支持小红书、抖音、快手、B站、微博、贴吧和知乎，"
                "可选择关键词搜索、指定内容详情或创作者主页。"
                "仅在用户明确要求采集数据时调用。"
            ),
            args_schema=MediaCrawlerTaskInput,
        ),
        StructuredTool.from_function(
            coroutine=_get_media_crawler_status,
            name="get_media_crawler_status",
            description=(
                "读取 MediaCrawler 当前任务状态和最近日志，"
                "用于检查运行进度或排查失败。"
            ),
            args_schema=MediaCrawlerStatusInput,
        ),
        StructuredTool.from_function(
            coroutine=_list_media_crawler_files,
            name="list_media_crawler_files",
            description=(
                "列出 MediaCrawler 已导出的 JSON、CSV 或 Excel 数据文件，"
                "可按平台和文件类型过滤。"
            ),
            args_schema=MediaCrawlerFilesInput,
        ),
    ]


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
    media_crawler_api_url: str | None = None,
    media_crawler_api_token: str | None = None,
) -> list[Any]:
    tools: list[Any] = [*TOOLS]
    if agent_key == "pc-builder":
        tools.append(generate_pc_build)
    if agent_key == "media-crawler":
        tools.extend(
            create_media_crawler_tools(
                media_crawler_api_url,
                media_crawler_api_token,
            )
        )
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

