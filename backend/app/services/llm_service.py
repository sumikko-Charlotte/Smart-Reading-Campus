"""AI 能力服务层（本轮为 Mock 实现，接口契约即最终契约）。

第 2 轮把 `_call_llm` 换成真实 DeepSeek / 通义千问 调用即可，
上层路由与 Schema 不需要改动。
"""
import json
from datetime import datetime, timezone

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


def _call_llm(prompt: str, scene: str) -> tuple[str, int]:
    """真实环境下替换为 HTTP 调用；现在返回可预测的 Mock 文本，方便双端联调。"""
    if settings.LLM_API_KEY:
        # 预留：httpx.post(f"{settings.LLM_API_BASE}/chat/completions", ...)
        pass
    mock = (
        f"[Mock/{settings.LLM_MODEL}] 场景：{scene}\n"
        f"（第 1 轮为占位输出，接入真实模型后此段将被替换）\n\n"
        f"提示词摘要：{prompt[:120]}...\n\n"
        "**参考输出结构**：\n"
        "1. 一句话主旨：…\n2. 核心观点：…\n3. 适合人群：…\n4. 延伸阅读：…"
    )
    return mock, len(prompt) // 2


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


def recommend_reason(book: Book, rank: int, extra: str) -> str:
    heat = f"近一年借阅 {book.borrow_count} 次" if book.borrow_count else "馆藏新书"
    return f"第 {rank} 位推荐：《{book.title}》与你的偏好契合（{heat}；标签 {'、'.join(book.tags or []) or '综合'}）。{extra}".strip()


def generate_copy(topic: str, style: str) -> str:
    prompt = PROMPT_TEMPLATES[ConversationScene.COPYWRITING.value].format(topic=topic, style=style)
    text, _ = _call_llm(prompt, ConversationScene.COPYWRITING.value)
    return text


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def dump_messages(messages: list) -> str:
    return json.dumps(messages, ensure_ascii=False)
