"""切换 backend/.env 的模型配置（保留其余内容，不传 --key 时保留现有 Key）。

用法：
  python scripts/set_llm_env.py
  python scripts/set_llm_env.py --base https://...   # 只改端点
  python scripts/set_llm_env.py --show               # 只看当前配置（Key 打码）
"""
from __future__ import annotations

import argparse
from pathlib import Path

ENV = Path(__file__).resolve().parents[1] / ".env"

DEFAULTS = {
    "LLM_ENABLED": "true",
    "LLM_PROVIDER": "deepseek",
    "LLM_MODEL": "deepseek-chat",
    "LLM_API_BASE": "https://api.deepseek.com/v1",
}


def read_env() -> list[str]:
    return ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []


def current() -> dict[str, str]:
    data: dict[str, str] = {}
    for line in read_env():
        if "=" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition("=")
            data[k.strip()] = v.strip()
    return data


def mask(value: str) -> str:
    if not value:
        return "(空)"
    return f"{value[:6]}…{value[-4:]}（{len(value)} 位）"


def write_env(changes: dict[str, str]) -> None:
    out, seen = [], set()
    for line in read_env():
        key = line.split("=", 1)[0].strip()
        if key in changes:
            out.append(f"{key}={changes[key]}")
            seen.add(key)
        else:
            out.append(line)
    for key, value in changes.items():
        if key not in seen:
            out.append(f"{key}={value}")
    ENV.write_text("\n".join(out) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="切换模型配置")
    parser.add_argument("--key", help="API Key；不传则保留现有值")
    parser.add_argument("--model", help="模型名，默认 deepseek-chat")
    parser.add_argument("--base", help="OpenAI 兼容端点")
    parser.add_argument("--show", action="store_true", help="仅打印当前配置")
    args = parser.parse_args()

    if args.show:
        data = current()
        for key in ("LLM_ENABLED", "LLM_PROVIDER", "LLM_MODEL", "LLM_API_BASE"):
            print(f"{key} = {data.get(key, '(未设置)')}")
        print(f"LLM_API_KEY = {mask(data.get('LLM_API_KEY', ''))}")
        return

    changes = dict(DEFAULTS)
    if args.model:
        changes["LLM_MODEL"] = args.model
    if args.base:
        changes["LLM_API_BASE"] = args.base
    if args.key:
        changes["LLM_API_KEY"] = args.key

    old = current()
    write_env(changes)
    print("已更新：")
    for key in sorted(changes):
        print(f"  {key} = {changes[key] if 'KEY' not in key else mask(changes[key])}")
    if not args.key and old.get("LLM_API_KEY"):
        print("LLM_API_KEY 未改动，沿用原值。")
    print("提示：改完需重启后端进程才会生效。")


if __name__ == "__main__":
    main()
