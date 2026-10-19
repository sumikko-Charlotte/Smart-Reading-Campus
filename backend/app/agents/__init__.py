"""智能体包：工具层 + 运行时 + 四个场景。

对外只需要用 `scenes.run_xxx`；`tools` 与 `runtime` 供测试和调试直接调用。
"""
from app.agents import fallback, prompts, runtime, scenes, tools  # noqa: F401

__all__ = ["fallback", "prompts", "runtime", "scenes", "tools"]
