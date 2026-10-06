# 智阅校园 · 第 1 轮开发交付（万贝）

> 开发周期：2026-10-06 ~ 2026-10-18　｜　演示验收：10-18 21:00 线上会议
> 交付人：万贝（PC 端研发 + AI 系统数据联通）
> 本次一并完成全员任务：**User / Activity / Book / AIConversation 四类核心数据对象与统一字段**

---

## 一、对照组长分工：本次交付了什么

| 组长分配任务 | 交付物 | 状态 |
|---|---|---|
| ① PC 端 Vue 项目基础框架 | `web-pc/`：Vue3 + Vite + Element Plus + Pinia + Vue Router，含统一布局、路由鉴权、axios 封装、字典常量、SSE 流式工具 | ✅ 已完成 |
| ① 活动管理后台首版页面 | `web-pc/src/views/activity/`：列表（筛选/分页/报名进度）、新建与编辑表单、详情页、**状态机流转**按钮（含取消原因）、AI 推文一键生成 | ✅ 已完成 |
| ② AI 推荐 / AI 阅读助手 / 图书漂流页面骨架 | `views/ai/Recommend.vue`、`views/ai/Assistant.vue`、`views/drift/DriftList.vue` | ✅ 已完成（**非空壳**，均接真实接口可跑通） |
| ③ FastAPI 基础工程 | `backend/`：配置、统一响应体、统一异常处理、RBAC 骨架、SQLAlchemy 数据层、Pydantic Schema、种子数据、冒烟测试 | ✅ 已完成 |
| ③ 首版 API 接口定义 | `docs/API接口定义-v1.md`，5 组共 29 个端点；启动后可访问 `/docs` 查看 OpenAPI 交互文档 | ✅ 已完成 |
| 全员任务：4 类核心数据对象与统一字段 | `docs/核心数据对象与统一字段规范.md`（含主键/时间/枚举/空值/分页/响应体全局约定） | ✅ 已完成 |

**验证结果**：后端冒烟测试 8 组场景全部通过（登录 → 活动状态机 → ISBN 扫码 → AI 解读 → AI 对话 → 漂流池），前端 `npm run build` 通过。

---

## 二、目录结构

```
智阅校园/
├── .vscode/                           ← 调试 / 任务 / 插件推荐（VS Code 打开即用）
├── 开发指南.md                        ← ★ 日常开发看这份（启动、约定、下一步清单）
├── start-backend.bat / start-frontend.bat  ← 双击即启动
├── docs/
│   ├── 核心数据对象与统一字段规范.md   ← 全员任务交付物（先看这份）
│   └── API接口定义-v1.md              ← 29 个端点 + 请求/响应示例 + SSE 帧格式
├── backend/                           ← FastAPI 工程
│   ├── app/
│   │   ├── main.py                    启动入口（含 /docs）
│   │   ├── core/                      配置 / 枚举 / 统一响应 / 鉴权与脱敏
│   │   ├── db/                        SQLAlchemy 引擎 + 4 类核心模型 + 2 类派生模型
│   │   ├── schemas/                   Pydantic 请求响应契约
│   │   ├── services/llm_service.py    AI 能力层（本轮 Mock，接口即最终契约）
│   │   └── api/v1/                    用户 / 活动 / 图书 / AI / 漂流 五组路由
│   ├── scripts/seed.py                演示数据
│   └── tests/test_api_smoke.py        冒烟测试
└── web-pc/                            ← PC 端 Vue 工程
    └── src/
        ├── api/                       request.js 统一封装 + 各业务模块
        ├── constants/                 枚举字典（与后端 enums.py 严格对齐）
        ├── router/                    路由 + 登录/角色守卫
        ├── store/                     Pinia 登录态
        ├── layouts/BasicLayout.vue    侧边菜单 + 顶栏 + 后端连通性标记
        └── views/                     登录 / 概览 / 活动 / AI / 漂流
```

---

## 三、如何跑起来

> **最快的两条路**：① 双击 `start-backend.bat` 与 `start-frontend.bat`；
> ② VS Code 里 `Ctrl+Shift+P` → `Tasks: Run Task` → `★ 一键启动全栈（后端 + 前端）`。
> 本工作区的前端依赖与后端虚拟环境**均已装好**，无需重复安装。详见 `开发指南.md`。

### 后端

```bash
cd backend
python -m venv .venv && .venv/Scripts/activate      # Windows
pip install -r requirements.txt
python scripts/seed.py                              # 初始化演示数据（可重复执行）
python -m uvicorn app.main:app --reload --port 8000
```

- 交互式接口文档：http://127.0.0.1:8000/docs
- 冒烟测试：`python tests/test_api_smoke.py`

### 前端

```bash
cd web-pc
npm install
npm run dev        # http://localhost:5173（已配置 /api 代理到 8000）
```

### 演示账号（密码统一 `123456`）

| 学号/工号 | 姓名 | 角色 | 用途 |
|---|---|---|---|
| `T2009` | 施怀鹃 | librarian | 管理端主账号（看得到「活动管理」菜单） |
| `admin` | 系统管理员 | admin | 增删用户、删除活动 |
| `2025211995` | 万贝 | student | 验证学生角色看不到管理菜单 |

---

## 四、核心数据对象（本轮全员任务的结论）

> 完整字段表见 `docs/核心数据对象与统一字段规范.md`，此处只列**必须双端一致**的关键决定。

### 4.1 全局约定（这几条是防联调翻车的关键）

1. **主键统一字符串**：`usr_` / `act_` / `bok_` / `cnv_` / `drf_` + 12 位十六进制。
   不用自增 int64 —— 小程序端 JS 数字精度会截断长整型 ID。
2. **JSON 字段统一 `snake_case`**，前后端不做驼峰自动转换，避免"到底谁转"扯皮。
3. **时间统一 ISO 8601 + `+08:00`**：`2026-10-18T12:00:00+08:00`。
4. **空值**：字符串无值用 `""`（语义确实不存在才用 `null`），数组用 `[]`，计数用 `0`。
5. **统一响应体** `{code, message, data, trace_id}`；**统一分页** `{list, page, page_size, total}`。
6. **枚举一律英文小写**，中文只在展示层映射（前端 `src/constants/index.js` 是唯一字典表）。

### 4.2 四类对象与最小字段集

| 对象 | 主键 | 双端必用的核心字段 |
|---|---|---|
| **User** | `user_id` | `student_no`（登录账号）、`name`、`role`(student/librarian/admin)、`status`、学院专业班级 |
| **Activity** | `activity_id` | `title`、`category`、`status`（6 态状态机）、`start_at`/`end_at`、`signup_start_at`/`signup_end_at`、`capacity`/`signup_count`/`checkin_count`、`need_certificate`、`ai_copy` |
| **Book** | `book_id` | `isbn`（扫码唯一键）、`title`/`author`/`publisher`、`tags[]`、`source`(library/drift)、`borrow_count`、`ai_summary`/`ai_tags`、漂流扩展 `drift_status`/`current_holder_id` |
| **AIConversation** | `conversation_id` | `user_id`、`scene`(book_analysis/recommend/qa/copywriting)、`book_id`、`messages[]`（`role`/`content`/`tokens`/`created_at`）、`prompt_version` |

### 4.3 活动状态机（双端必须共用，后端强校验）

```
draft ──→ published ──→ signup_closed ──→ ongoing ──→ finished
  └──────────┴──────────┴──→ cancelled（旁支终态）
```

前端只做按钮可用性提示，**合法性以后端 `POST /activities/{id}/status` 的返回为准**，非法流转统一返回 `code=1005` 并带明确文案。

---

## 五、本轮已知未完成项（第 2 轮计划）

| 项目 | 说明 |
|---|---|
| 大模型真实调用 | `app/services/llm_service.py` 当前为 Mock（返回可预测文本，便于双端联调）；填入 `LLM_API_KEY` 即切换真实模型，上层不改 |
| RAG 向量知识库 | 第 2 轮建设：书目元数据 → 向量化 → 检索增强 |
| 报名名单与扫码签到 | `ActivitySignup` 模型已就绪，名单导出/签到看板待做 |
| 电子证书自动颁发 | 字段已预留（`need_certificate`、`certificate_template_id`） |
| 用户管理页 | 接口已通（`/users`），前端管理页第 2 轮补 |
| 图片上传 | 现为 URL 直填，待接对象存储 |
| 微信小程序端 | 由杨可馨负责，接口与字段已按本规范对齐 |

---

## 六、给组长/康馨戈做验收清单时的建议

可直接抽取以下条目作为本轮验收项（都有明确判定方式）：

1. `python tests/test_api_smoke.py` 输出「冒烟测试全部通过 ✅」
2. `/docs` 能看到 5 组接口，活动状态非法流转返回 `code=1005`
3. PC 端用 `T2009` 登录 → 活动管理列表有 4 条演示数据 → 新建活动为草稿 → 流转为「报名中」成功
4. AI 推荐页点击「生成推荐」返回 6 条带推荐理由的书；点击「生成 AI 解读」返回解读文本
5. AI 阅读助手开启「流式输出」提问，回复逐字出现，左侧会话列表新增记录
6. 图书漂流页「扫码上架」一本书后状态为「待领取」，申领后生成流转记录
7. 学生账号 `2025211995` 登录后看不到「活动管理」菜单

---

## 七、变更记录

| 版本 | 日期 | 变更人 | 内容 |
|---|---|---|---|
| v1.0 | 2026-10-06 | 万贝 | 第 1 轮交付：前端框架 + 活动管理首版 + 三个骨架页 + FastAPI 工程 + 接口定义 + 数据对象规范 |
