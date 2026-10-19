"""模型连通性自检：不发业务数据，只打一次最短请求；任何输出都不包含 Key 明文。

用法：python scripts/check_llm.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app.core.config import settings  # noqa: E402


def mask(value: str) -> str:
    return f"{value[:6]}…{value[-4:]}" if len(value) > 10 else ("(空)" if not value else "***")


def main() -> int:
    print("当前配置")
    print(f"  LLM_ENABLED   = {settings.LLM_ENABLED}")
    print(f"  LLM_PROVIDER  = {settings.LLM_PROVIDER}")
    print(f"  LLM_MODEL     = {settings.LLM_MODEL}")
    print(f"  LLM_API_BASE  = {settings.LLM_API_BASE}")
    print(f"  LLM_API_KEY   = {mask(settings.LLM_API_KEY)}")

    url = settings.LLM_API_BASE.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.LLM_MODEL,
        "messages": [{"role": "user", "content": "回复两个字：正常"}],
        "max_tokens": 16,
    }
    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    print("\n正在请求模型…")
    try:
        with httpx.Client(timeout=40, trust_env=False) as client:
            resp = client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        print(f"  ❌ 网络层失败：{type(exc).__name__} {exc}")
        print("     常见原因：本机代理拦截、DNS 不通、端点地址写错。")
        return 1

    if resp.status_code == 200:
        try:
            text = resp.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            text = resp.text[:120]
        print(f"  ✅ 调用成功，模型回复：{text}")
        return 0

    print(f"  ❌ HTTP {resp.status_code}")
    print(f"     {resp.text[:300]}")
    if resp.status_code == 401:
        print("     401 说明 Key 无效或已过期：请在 DeepSeek 开放平台创建/复制有效 API Key。")
    elif resp.status_code == 403:
        print("     403 通常表示当前 API Key 没有权限调用该模型。")
    elif resp.status_code == 404:
        print("     404 多为模型名或端点路径不对，检查 LLM_MODEL / LLM_API_BASE。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
