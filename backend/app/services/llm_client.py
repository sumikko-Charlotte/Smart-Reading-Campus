"""统一的模型客户端：所有场景都通过这里与模型对话。

和第一轮的 `_call_llm` 相比，这一层多了三件事：
1. **多轮 messages**：智能体要在上下文里累积「工具调用 → 工具结果」，单条 prompt 撑不住。
2. **工具调用（function calling）**：走 OpenAI 兼容的 `tools` 协议，DeepSeek / 通义 / 本地
   Ollama 都支持同一套结构，换模型不用改业务代码。
3. **错误分类**：配置缺失、余额不足、网络不通要能区分，上层据此决定是「直接降级」
   还是「提示用户稍后重试」。

没有 key 不等于不能演示：`is_available()` 为 False 时上层直接走规则引擎。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings

# 各 provider 的默认地址，只在 LLM_API_BASE 留空时兜底
PROVIDER_BASE_URLS = {
    "aliyun": "https://ws-ga8vgq305mnttsd5.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "openai": "https://api.openai.com/v1",
    "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "ollama": "http://127.0.0.1:11434/v1",
}

# 这些 provider 允许无 key（本地推理）
NO_KEY_PROVIDERS = {"ollama"}


class LLMError(RuntimeError):
    """模型调用的统一异常基类。"""


class LLMNotConfigured(LLMError):
    """没配 key / 主动关闭。属于「预期内不可用」，应静默降级。"""


class LLMUnavailable(LLMError):
    """网络、超时、5xx。可重试，重试失败后降级。"""


class LLMQuotaExceeded(LLMError):
    """余额不足或限流。降级并提示管理员。"""


class LLMBadResponse(LLMError):
    """返回内容无法解析成预期结构。"""


@dataclass
class ToolCall:
    """一次工具调用请求。arguments 已解析为 dict，解析失败则为空 dict 并带 raw。"""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    raw_arguments: str = ""


@dataclass
class ChatResult:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens: int = 0
    model: str = ""
    finish_reason: str = ""
    elapsed_ms: int = 0


def _resolve_base_url() -> str:
    base = (settings.LLM_API_BASE or "").strip()
    if base:
        return base.rstrip("/")
    return PROVIDER_BASE_URLS.get(settings.LLM_PROVIDER, PROVIDER_BASE_URLS["deepseek"])


def _endpoint() -> str:
    base = _resolve_base_url()
    return base if base.endswith("/chat/completions") else f"{base}/chat/completions"


def is_available() -> tuple[bool, str]:
    """返回 (可用, 原因)。原因用于前端提示与降级说明，不暴露密钥。"""
    if not settings.LLM_ENABLED:
        return False, "模型调用已关闭（LLM_ENABLED=false）"
    provider = (settings.LLM_PROVIDER or "").lower()
    if not settings.LLM_API_KEY and provider not in NO_KEY_PROVIDERS:
        return False, "后端未配置 LLM_API_KEY"
    return True, ""


def _classify_http_error(exc: httpx.HTTPStatusError) -> LLMError:
    status = exc.response.status_code
    body = ""
    try:
        body = exc.response.text[:300]
    except Exception:  # noqa: BLE001 - 读取响应体失败不应影响报错
        pass
    if status == 402:
        return LLMQuotaExceeded(f"模型账户余额不足（HTTP 402）：{body}")
    if status == 401:
        return LLMNotConfigured("API key 无效或已过期（HTTP 401）")
    if status == 403:
        return LLMNotConfigured("API key 无权访问该模型（HTTP 403）")
    if status == 429:
        return LLMQuotaExceeded("模型请求被限流（HTTP 429），请稍后重试")
    if status >= 500:
        return LLMUnavailable(f"模型服务异常（HTTP {status}）")
    return LLMBadResponse(f"模型请求失败（HTTP {status}）：{body}")


def chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    response_format: dict[str, str] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> ChatResult:
    """单次模型调用。带 1 次重试（仅对网络类错误重试）。"""
    available, reason = is_available()
    if not available:
        raise LLMNotConfigured(reason)

    body: dict[str, Any] = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens or settings.LLM_MAX_TOKENS,
        "temperature": settings.LLM_TEMPERATURE if temperature is None else temperature,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if response_format is not None:
        body["response_format"] = response_format

    headers = {"Content-Type": "application/json"}
    if settings.LLM_API_KEY:
        headers["Authorization"] = f"Bearer {settings.LLM_API_KEY}"

    attempts = max(1, settings.LLM_RETRY + 1)
    last_error: LLMError | None = None
    for attempt in range(attempts):
        started = time.perf_counter()
        try:
            response = httpx.post(_endpoint(), headers=headers, json=body, timeout=settings.LLM_TIMEOUT_SEC)
            response.raise_for_status()
            payload = response.json()
            return _parse_response(payload, int((time.perf_counter() - started) * 1000))
        except httpx.HTTPStatusError as exc:
            error = _classify_http_error(exc)
            last_error = error
            # 余额/鉴权类错误重试没有意义
            if isinstance(error, (LLMQuotaExceeded, LLMNotConfigured)):
                raise error from exc
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = LLMUnavailable(f"模型服务连接失败：{type(exc).__name__}")
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMBadResponse(f"模型响应结构异常：{exc}") from exc

        if attempt < attempts - 1:
            time.sleep(1.0)

    raise last_error or LLMUnavailable("模型调用失败")


def _parse_response(payload: dict[str, Any], elapsed_ms: int) -> ChatResult:
    choices = payload.get("choices") or []
    if not choices:
        raise LLMBadResponse("模型响应中没有 choices")
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    if not isinstance(content, str):
        content = str(content)

    tool_calls: list[ToolCall] = []
    for index, item in enumerate(message.get("tool_calls") or []):
        function = item.get("function") or {}
        raw_args = function.get("arguments") or ""
        parsed: dict[str, Any] = {}
        if isinstance(raw_args, dict):
            parsed = raw_args
            raw_args = json.dumps(raw_args, ensure_ascii=False)
        elif isinstance(raw_args, str) and raw_args.strip():
            try:
                loaded = json.loads(raw_args)
                parsed = loaded if isinstance(loaded, dict) else {}
            except json.JSONDecodeError:
                parsed = {}
        tool_calls.append(
            ToolCall(
                id=str(item.get("id") or f"call_{index}"),
                name=str(function.get("name") or ""),
                arguments=parsed,
                raw_arguments=raw_args if isinstance(raw_args, str) else "",
            )
        )

    usage = payload.get("usage") or {}
    return ChatResult(
        content=content.strip(),
        tool_calls=tool_calls,
        tokens=int(usage.get("total_tokens") or 0),
        model=str(payload.get("model") or settings.LLM_MODEL),
        finish_reason=str(choices[0].get("finish_reason") or ""),
        elapsed_ms=elapsed_ms,
    )


def extract_json(text: str) -> dict[str, Any] | None:
    """从模型输出里抠出第一个 JSON 对象。

    模型经常在 JSON 外面裹 ```json 或一句「好的，结果是：」，直接 json.loads 会失败，
    所以先尝试整体解析，再退化为按花括号配对扫描。
    """
    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
        stripped = "\n".join(lines).strip()
    try:
        loaded = json.loads(stripped)
        return loaded if isinstance(loaded, dict) else None
    except json.JSONDecodeError:
        pass

    depth = 0
    start = -1
    in_string = False
    escaped = False
    for index, char in enumerate(stripped):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    loaded = json.loads(stripped[start : index + 1])
                except json.JSONDecodeError:
                    start = -1
                    continue
                if isinstance(loaded, dict):
                    return loaded
                start = -1
    return None
