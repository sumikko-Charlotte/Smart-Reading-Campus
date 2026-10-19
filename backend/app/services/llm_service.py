"""AI 能力服务层（本轮为 Mock 实现，接口契约即最终契约）。

第 2 轮把 `_call_llm` 换成真实 DeepSeek / 通义千问 调用即可，
上层路由与 Schema 不需要改动。
"""
import json
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import settings
from app.core.enums import ConversationScene
from app.db.models import Book

PROMPT_TEMPLATES: dict[str, str] = {
    ConversationScene.BOOK_ANALYSIS.value: (
        "你是高校图书馆的阅读推广助手。请基于以下图书信息，输出结构化深度解读：\n"
        "1）一句话主旨 2）核心观点（3-5 条）3）章节脉络 4）适合人群 5）延伸阅读建议。\n"
        "图书信息：{book_context}\n要求：简体中文，面向大学生，禁止编造未经提供的信息。"
    ),
    ConversationScene.RECOMMEND.value: (
        "你是高校图书馆的荐书助手。根据用户偏好「{extra}」与候选书单，推荐 {limit} 本书，"
        "每本给出 40 字以内的推荐理由，理由需结合借阅热度与主题契合度。\n候选书单：{book_context}"
    ),
    ConversationScene.QA.value: (
        "你是「智阅校园」AI 伴读助手，正在与读者多轮对话。已知图书信息：{book_context}\n"
        "请用简洁、口语化的中文回答读者问题；涉及借阅规则时提示以图书馆官方信息为准。"
    ),
    ConversationScene.COPYWRITING.value: (
        "你是校园阅读推广的新媒体编辑。请围绕主题「{topic}」撰写一篇 {style} 风格的推文，"
        "包含吸睛标题、3 段正文与话题标签，语气贴近大学生，禁止夸大宣传。"
    ),
}


def _book_context(book: Book | None) -> str:
    if book is None:
        return "（无关联图书，通用问答场景）"
    return (
        f"书名《{book.title}》，作者 {book.author}，出版社 {book.publisher}，"
        f"分类 {book.category}，标签 {'、'.join(book.tags or []) or '无'}，简介：{book.summary or '暂无'}"
    )


class LLMServiceError(RuntimeError):
    """模型服务不可用或返回了无法解析的响应。"""


def _call_llm(
    prompt: str,
    scene: str,
    response_format: dict[str, str] | None = None,
) -> tuple[str, int]:
    """通过 DeepSeek OpenAI 兼容接口生成内容，不允许静默回退为 Mock。"""
    if not settings.LLM_ENABLED:
        raise LLMServiceError("AI 调用已关闭；确认账户余额后，在 backend/.env 设置 LLM_ENABLED=true")
    if not settings.LLM_API_KEY:
        raise LLMServiceError("后端未配置 LLM_API_KEY")

    base_url = settings.LLM_API_BASE.rstrip("/")
    endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
    request_body: dict[str, Any] = {
        "model": settings.LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": settings.LLM_MAX_TOKENS,
    }
    if response_format is not None:
        request_body["response_format"] = response_format
    try:
        response = httpx.post(
            endpoint,
            headers={"Authorization": f"Bearer {settings.LLM_API_KEY}"},
            json=request_body,
            timeout=30.0,
        )
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise LLMServiceError("模型服务返回了空内容")
        tokens = result.get("usage", {}).get("total_tokens", 0)
        return content.strip(), int(tokens or 0)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 402:
            message = "DeepSeek 账户余额不足，请充值后重试"
        elif exc.response.status_code == 401:
            message = "DeepSeek API key 无效，请检查后端配置"
        elif exc.response.status_code == 429:
            message = "DeepSeek 请求频率受限，请稍后重试"
        else:
            message = f"DeepSeek 请求失败（HTTP {exc.response.status_code}）"
        raise LLMServiceError(message) from exc
    except LLMServiceError:
        raise
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise LLMServiceError("DeepSeek 服务请求失败，请检查网络和模型配置") from exc


def chat_reply(scene: str, question: str, book: Book | None) -> tuple[str, int]:
    template = PROMPT_TEMPLATES.get(scene, PROMPT_TEMPLATES[ConversationScene.QA.value])
    try:
        prompt = template.format(book_context=_book_context(book), extra="", limit=6, topic=question, style="xiaohongshu")
    except KeyError:
        prompt = template
    prompt = f"{prompt}\n\n读者问题：{question}"
    return _call_llm(prompt, scene)


def analyze_book(book: Book) -> tuple[str, list[str], int]:
    prompt = PROMPT_TEMPLATES[ConversationScene.BOOK_ANALYSIS.value].format(book_context=_book_context(book))
    text, tokens = _call_llm(prompt, ConversationScene.BOOK_ANALYSIS.value)
    tags = list(dict.fromkeys([*(book.tags or []), "AI解读", book.category or "综合"]))[:6]
    return text, tags, tokens


def recommend_reasons(books: list[Book], extra: str, limit: int) -> tuple[dict[str, str], int]:
    """一次调用模型生成理由数组，严格按候选书顺序映射。"""
    if not books:
        return {}, 0

    candidates = [
        {
            "book_id": book.book_id,
            "title": book.title,
            "author": book.author,
            "category": book.category,
            "tags": book.tags or [],
            "summary": book.summary or "",
            "borrow_count": book.borrow_count,
        }
        for book in books
    ]
    prompt = (
        f"你是高校图书馆荐书助手。根据读者偏好“{extra or '未提供特定偏好'}”，从候选书目中为最多 {limit} 本书生成推荐理由。"
        "理由使用简体中文，单条不超过40字，只能依据给出的书目信息，不得编造。"
        "必须为每一本候选书按输入顺序生成一条理由。只返回 JSON 对象，格式为 "
        "{\"reasons\":[\"第一本书的理由\",\"第二本书的理由\"]}。不要返回书名、ID、序号或其他字段。"
        f"候选书目：{json.dumps(candidates, ensure_ascii=False)}"
    )
    content, tokens = _call_llm(
        prompt,
        ConversationScene.RECOMMEND.value,
        response_format={"type": "json_object"},
    )
    try:
        result = json.loads(content)
        reason_list = result["reasons"]
        if not isinstance(reason_list, list) or len(reason_list) != len(books):
            raise ValueError("reasons count must match candidate books")
        if any(not isinstance(reason, str) or not reason.strip() for reason in reason_list):
            raise ValueError("each reason must be a non-empty string")
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise LLMServiceError("DeepSeek 推荐结果格式无效") from exc

    reasons = {book.book_id: reason.strip() for book, reason in zip(books, reason_list)}
    return reasons, tokens


def generate_copy(topic: str, style: str) -> str:
    prompt = PROMPT_TEMPLATES[ConversationScene.COPYWRITING.value].format(topic=topic, style=style)
    text, _ = _call_llm(prompt, ConversationScene.COPYWRITING.value)
    return text


# ---------------------------------------------------------------- 降级 Mock


def mock_recommend_reasons(books: list[Book], extra: str = "") -> dict[str, str]:
    """访客降级推荐：不调用真实模型，用书目自身字段拼确定性理由。

    注意：理由只描述**书**，不出现「和你相似的同学」「你可能认识的人」这类
    可逆指向，符合脱敏数据的使用边界。
    """
    preference = (extra or "").strip() or "通识阅读"
    openers = [
        "借阅热度靠前，",
        "主题与你的偏好贴合，",
        "篇幅适中，适合课后翻读，",
        "读者评价稳定，",
        "入门友好，",
        "视角独特，",
    ]
    reasons: dict[str, str] = {}
    for index, book in enumerate(books):
        tag = (book.tags or [book.category or "综合"])[0]
        reason = f"{openers[index % len(openers)]}「{tag}」方向契合「{preference}」，可在馆藏区直接取阅。"
        reasons[book.book_id] = reason[:60]
    return reasons


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def dump_messages(messages: list) -> str:
    return json.dumps(messages, ensure_ascii=False)
