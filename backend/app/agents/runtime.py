"""智能体运行时：一个精简的 ReAct 循环。

为什么不用 LangChain：本项目只需要「想一步 → 查一次 → 再想」这一种模式，
引框架带来的是几十个依赖、更重的调试成本，而真正要控制的是
**步数上限、工具白名单、token 预算、失败降级** 这四件事，自己写反而清楚。

循环形态：
    模型决定调工具 ──> 执行工具 ──> 结果回灌上下文 ──> 模型再决定
    直到模型给出最终答复，或达到步数上限 / 预算上限。

兼容两种模型：
- 支持 function calling 的（DeepSeek、GPT、通义、Qwen 系列）：走原生 tools 协议
- 不支持的老模型 / 本地小模型：走文本协议，让它输出 {"action": "...", "args": {...}}
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from app.agents import tools as tool_registry
from app.agents.tools import ToolContext
from app.core.config import settings
from app.services import llm_client
from app.services.llm_client import ChatResult, LLMError

# 单条工具结果注入上下文的字符上限。书目列表一次就上千字，不截断会挤爆预算。
TOOL_RESULT_CHAR_LIMIT = 3500

# 文本协议提示：只在模型没有返回 tool_calls 时使用
TEXT_PROTOCOL_HINT = """

【工具调用约定】
你可以调用下列工具来获取真实数据，不要凭空编造书目、库存和活动信息。
如果需要调用工具，只输出一行 JSON，不要输出别的：
{"action": "工具名", "args": {"参数名": "值"}}
如果已经能回答，输出：
{"action": "final", "answer": "给用户的答复"}
"""


@dataclass
class AgentResult:
    content: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    steps: int = 0
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    tokens: int = 0
    model: str = ""
    degraded: bool = False
    degraded_reason: str = ""
    elapsed_ms: int = 0


class AgentBudgetExceeded(RuntimeError):
    """达到步数或 token 上限。带上已有轨迹，交给上层决定怎么收尾。"""


def _tool_message(call_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) > TOOL_RESULT_CHAR_LIMIT:
        text = text[:TOOL_RESULT_CHAR_LIMIT] + "…（结果过长已截断）"
    return {"role": "tool", "tool_call_id": call_id, "content": text}


def _assistant_tool_message(result: ChatResult) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": result.content or "",
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.raw_arguments or json.dumps(call.arguments, ensure_ascii=False)},
            }
            for call in result.tool_calls
        ],
    }


def run(
    scene: str,
    system_prompt: str,
    user_message: str,
    ctx: ToolContext,
    max_steps: int | None = None,
    expect_json: bool = False,
) -> AgentResult:
    """执行一次智能体运行。

    expect_json=True 时会把最终答复按 JSON 解析后放进 data，
    解析失败则把原文留在 content，由调用方决定是否降级。
    """
    started = time.perf_counter()
    steps_limit = max_steps or settings.AGENT_MAX_STEPS
    schemas = tool_registry.schemas_for(scene) if settings.AGENT_TOOLS_ENABLED else []
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt + (TEXT_PROTOCOL_HINT if schemas else "")},
        {"role": "user", "content": user_message},
    ]

    result = AgentResult(tool_trace=ctx.trace)
    tokens_used = 0
    final_text = ""

    for step in range(steps_limit + 1):
        # 最后一步收网：不再给工具，要求基于已有信息作答
        last_chance = step >= steps_limit
        current_tools = [] if last_chance else schemas

        try:
            response = llm_client.chat(messages, tools=current_tools or None)
        except LLMError as exc:
            result.degraded = True
            result.degraded_reason = str(exc)
            result.content = final_text
            result.steps = step
            result.tokens = tokens_used
            result.elapsed_ms = int((time.perf_counter() - started) * 1000)
            result.data = _try_json(final_text) if expect_json else {}
            return result

        tokens_used += response.tokens
        result.model = response.model
        result.steps = step + 1

        # ---- 情况一：模型原生返回 tool_calls ----
        if response.tool_calls:
            messages.append(_assistant_tool_message(response))
            for call in response.tool_calls:
                payload = tool_registry.dispatch(call.name, call.arguments, ctx)
                messages.append(_tool_message(call.id, payload))
            if tokens_used >= settings.AGENT_TOKEN_BUDGET:
                result.degraded = True
                result.degraded_reason = "已达 token 预算上限"
                break
            continue

        # ---- 情况二：纯文本，可能是文本协议的工具调用 ----
        text = response.content
        action = llm_client.extract_json(text)
        if action and isinstance(action.get("action"), str) and not last_chance:
            name = action["action"]
            if name == "final":
                final_text = str(action.get("answer") or "").strip()
                break
            if name in tool_registry.REGISTRY:
                args = action.get("args") if isinstance(action.get("args"), dict) else {}
                payload = tool_registry.dispatch(name, args, ctx)
                # 文本协议没有 call_id，用伪 id 保证消息结构完整
                fake_id = f"text_{step}_{name}"
                messages.append(
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": fake_id,
                                "type": "function",
                                "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
                            }
                        ],
                    }
                )
                messages.append(_tool_message(fake_id, payload))
                continue

        # ---- 情况三：就是最终答复 ----
        final_text = text.strip()
        break

    result.content = final_text
    result.tokens = tokens_used
    result.steps = max(1, result.steps)
    result.elapsed_ms = int((time.perf_counter() - started) * 1000)
    result.data = _try_json(final_text) if expect_json else {}

    # 走到步数上限还没给出答案：再要一次纯文本总结，避免返回空
    if not final_text:
        result.degraded = True
        result.degraded_reason = result.degraded_reason or "模型未在步数上限内给出结论"
    return result


def _try_json(text: str) -> dict[str, Any]:
    if not text:
        return {}
    parsed = llm_client.extract_json(text)
    return parsed if isinstance(parsed, dict) else {}
