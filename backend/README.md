# 智阅校园 · FastAPI 后端（第 1 轮骨架）

## 快速开始

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
python scripts/seed.py          # 初始化演示数据（幂等，可重复执行）
python -m uvicorn app.main:app --reload --port 8000
```

- 接口文档（Swagger）：http://127.0.0.1:8000/docs
- 替代文档（ReDoc）：http://127.0.0.1:8000/redoc
- 冒烟测试：`python tests/test_api_smoke.py`（或 `pytest tests -q`）

## 配置

复制 `.env.example` 为 `.env` 后按需修改。AI 计费开关默认为关闭，页面不会自动调用模型。确认 DeepSeek 账户有余额后，才在本机 `.env` 中填写 API key 并设置 `LLM_ENABLED=true`；`.env` 已加入 Git 忽略，严禁把 key 写入源码、前端或提交记录。修改配置后重启后端。

```dotenv
LLM_ENABLED=false
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-chat
LLM_API_BASE=https://api.deepseek.com/v1
LLM_API_KEY=
LLM_MAX_TOKENS=512
```

只有同时配置 `LLM_ENABLED=true` 和 `LLM_API_KEY` 时，AI 阅读助手、书目解读和 `/api/v1/books/recommend` 才会调用 DeepSeek。否则接口明确返回 503，不会回退成预设回答。推荐理由以候选顺序映射、最多调用一次；`LLM_MAX_TOKENS` 限制单次回复长度。模型不可用、余额不足或响应格式无效时会显示明确错误。

关键配置项：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `DATABASE_URL` | `sqlite:///<backend>/smart_reading.db`（绝对路径） | 切 MySQL：`mysql+pymysql://user:pwd@host:3306/smart_reading?charset=utf8mb4` |
| `LLM_ENABLED` | `false` | 必须显式设为 `true` 才允许产生计费请求 |
| `LLM_API_KEY` | 空 | 本机配置；非空且已启用时调用 DeepSeek |
| `LLM_MODEL` | `deepseek-chat` | 底层模型标识，会写入会话 `model` 字段 |
| `LLM_MAX_TOKENS` | `512` | 限制单次模型回复长度 |
| `PROMPT_VERSION` | `v1.0` | 提示词版本，用于效果回溯 |
| `CORS_ORIGINS` | 本地 5173 | 前端本地开发端口白名单 |

## 目录说明

```
app/
├── main.py              启动入口：注册中间件、异常处理、路由、启动时执行迁移
├── core/
│   ├── config.py        全局配置
│   ├── enums.py         所有枚举 + 活动状态机流转表（双端唯一来源）
│   ├── permissions.py   权限点、角色默认权限、有效权限计算
│   ├── response.py      统一响应体/分页/错误码 + 全局异常处理
│   └── security.py      主键生成、token、权限依赖、手机号邮箱脱敏
├── db/
│   ├── base.py          引擎/会话/init_db（新库建表+打版本，旧库升级到 head）
│   └── models.py        14 张表的 ORM 定义
├── agents/              智能体层
│   ├── runtime.py       ReAct 循环：步数 / token 预算 / 工具白名单
│   ├── tools.py         10 个只读工具 + 场景白名单 + 调用轨迹
│   ├── prompts.py       四场景系统提示词
│   ├── scenes.py        四场景编排 + 模型输出校验（防编造）
│   └── fallback.py      无模型时的规则降级（四套）
├── schemas/             Pydantic 请求响应契约（与规范文档一一对应）
├── services/            llm_client（工具调用）/ llm_service（旧接口兼容）/ certificate_service
└── api/v1/              user / activity / book / ai / agent / drift / certificate / summary / permission

alembic/versions/        数据库迁移链（基线 + 增量），改表结构走这里
scripts/                 seed / simulate_data / migrate / backup_db / import_school_data / export_data_dictionary
samples/                 导入用示例 CSV
```

## 约定（新增接口时遵守）

1. 新字段先改 `docs/核心数据对象与统一字段规范.md`，再改 `db/models.py` 与 `schemas/`，最后改前端 `constants`/页面。
2. 所有成功返回统一走 `app.core.response.ok()`，分页走 `page_result()`，业务异常抛 `BizError(code, message)`。
3. 权限统一用 `Depends(require_roles("librarian", "admin"))`，不要在函数体里手写角色判断。
4. 时间字段一律 `DateTime(timezone=True)`，序列化走 ISO8601。
