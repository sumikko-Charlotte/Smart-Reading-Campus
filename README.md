# 智阅校园 · 第 1 轮开发交付

> 开发周期：2026-10-06 ~ 2026-10-18　｜　演示验收：10-18 21:00 线上会议
> 交付角色：PC 端研发 + AI 系统数据联通
> 本次一并完成全员任务：**User / Activity / Book / AIConversation 四类核心数据对象与统一字段**

---

## 一、对照组长分工：本次交付了什么

| 组长分配任务 | 交付物 | 状态 |
|---|---|---|
| ① PC 端 Vue 项目基础框架 | `web-pc/`：Vue3 + Vite + Element Plus + Pinia + Vue Router，含统一布局、路由鉴权、axios 封装、字典常量、SSE 流式工具 | ✅ 已完成 |
| ① 活动管理后台首版页面 | `web-pc/src/views/activity/`：列表（筛选/分页/报名进度）、新建与编辑表单、详情页、状态机流转按钮、AI 推文一键生成 | ✅ 已完成 |
| ② AI 推荐 / AI 阅读助手 / 图书漂流页面 | `views/ai/Recommend.vue`、`views/ai/Assistant.vue`、`views/drift/DriftList.vue` | ✅ 已完成（均接真实接口） |
| ③ FastAPI 基础工程 | `backend/`：配置、统一响应体、统一异常处理、RBAC、SQLAlchemy 数据层、Pydantic Schema、种子数据、冒烟测试 | ✅ 已完成 |
| ③ 首版 API 接口定义 | `docs/API接口定义-v1.md`，5 组共 34 个端点；启动后可访问 `/docs` 查看 OpenAPI | ✅ 已完成 |
| 全员任务：核心数据对象与统一字段 | `docs/核心数据对象与统一字段规范.md`（v1.2，含第九章「第 1 轮实现对照」） | ✅ 已完成 |
| 规范 v1.2 同步 | 按项目组《核心数据对象与统一字段规范》v1.2 对齐字段、报名规则、HTTP 状态码与首版活动接口 | ✅ 已完成 |

**验证结果**：后端冒烟测试覆盖登录、活动状态机、报名（重复报名 409）、ISBN 扫码、AI 解读、AI 对话、漂流池；前端 `npm run build` 通过。

---

## 二、目录结构

```text
智阅校园/
├── .vscode/                           ← 调试 / 任务 / 插件推荐
├── 开发指南.md                        ← 日常开发指南
├── start-backend.bat / start-frontend.bat
├── docs/
│   ├── 核心数据对象与统一字段规范.md   ← 双端字段口径（v1.2 + 实现对照）
│   ├── API接口定义-v1.md              ← API 与请求/响应示例
│   └── 组会提交材料-第1轮.md           ← 组会对齐用（变更点 / 落地状态 / 待确认）
├── backend/                           ← FastAPI 工程
│   ├── app/core/                      配置 / 枚举 / 响应 / 鉴权
│   ├── app/db/                        SQLAlchemy 模型
│   ├── app/schemas/                   请求响应契约
│   ├── app/api/v1/                    用户 / 活动 / 图书 / AI / 漂流路由
│   ├── scripts/seed.py                演示数据
│   └── tests/test_api_smoke.py        冒烟测试
└── web-pc/                            ← PC 端 Vue 工程
```

---

## 三、如何跑起来

> 双击 `start-backend.bat` 与 `start-frontend.bat`，或在 VS Code 运行「★ 一键启动全栈（后端 + 前端）」。

### 后端

```bash
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe scripts/seed.py
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

- 接口文档：<http://127.0.0.1:8000/docs>
- 冒烟测试：`.venv/Scripts/python.exe tests/test_api_smoke.py`

### 前端

```bash
cd web-pc
npm install
npm run dev
```

演示账号（密码统一 `123456`）：

| 学号/工号 | 姓名 | 角色 | 用途 |
|---|---|---|---|
| `T2009` | 图书馆老师 | librarian | 管理端主账号 |
| `admin` | 系统管理员 | admin | 用户与系统管理 |
| `2025211987` | Alice | student | 学生端权限验证 |

---

## 四、核心数据对象与状态机

完整字段见 `docs/核心数据对象与统一字段规范.md`。JSON 字段为 `snake_case`；对外 ID 使用带前缀字符串；时间统一序列化为 ISO 8601 `+08:00`；响应体与分页结构全项目统一。

| 对象 | 主键 | 关键字段 |
|---|---|---|
| User | `user_id` | `student_no`、`name`、`role`、`status`、学院/专业/班级 |
| Activity | `activity_id` | `title`、`category`、`status`、活动/报名时间、名额和人数、证书配置 |
| Book | `book_id` | `isbn`、书目元数据、馆藏数量、AI 解读；source 支持 library/drift/both |
| AIConversation | `conversation_id` | `user_id`、`scene`、`book_id`、`messages[]`、`prompt_version` |
| ActivitySignup | `signup_id` | 活动报名与签到关系 |
| DriftRecord | `drift_id` | 单册漂流状态、持有者、交接地点和流转次数 |

```text
draft → published → signup_closed → ongoing → finished
  └────────┴───────────┴────────────→ cancelled
```

状态合法性由后端校验，前端仅作按钮提示；非法流转统一返回 `code=1005`。

---

## 五、已知后续工作

| 项目 | 说明 |
|---|---|
| 大模型真实调用 | `backend/app/services/llm_service.py` 当前为 Mock，填入 `LLM_API_KEY` 即切换 |
| RAG 向量知识库 | 后续建设书目向量化与检索增强 |
| `ActivityReport` | 字段已在规范 3.3 定义（`rpt_` 前缀），表与接口待实现周期确认 |
| 扫码签到 | `ActivitySignup.checked_in_at` 字段已就位；签到凭证规则规范标注为非本轮必做 |
| 取消报名接口 | 规范 7.2.6 标注非本轮必做；数据层已支持 `cancelled` 记录窗口内重新激活 |
| 电子证书自动颁发 | 字段已预留，证书模板管理待接入 |
| 用户管理前端 | 后端接口已提供，前端页面待补 |
| 图片上传 | 当前为 URL 输入，后续接对象存储 |
| 微信小程序端 | 按统一字段规范接入 |

---

## 六、验收参考

1. `.venv/Scripts/python.exe tests/test_api_smoke.py` 输出「冒烟测试全部通过」。
2. `/docs` 可访问，活动非法状态流转返回 `code=1005`。
3. PC 端以 `T2009` 登录，管理活动可创建草稿并发布。
4. AI 推荐、AI 解读和阅读助手可通过接口返回内容。
5. 学生账号看不到管理端活动菜单，不能查看草稿活动。
6. 漂流书按 `drift_id` 独立申领并更新对应 DriftRecord。

---

## 七、变更记录

| 版本 | 日期 | 维护角色 | 内容 |
|---|---|---|---|
| v1.2 | 2026-10-07 | 项目组 | 同步字段规范与接口行为；补 v1.2 实现对照（规范第九章）与组会提交材料；修正演示数据与冒烟测试口径 |
| v1.2 | 2026-10-07 | 项目组 | 同步字段规范与接口行为，移除演示老师的具体身份信息 |
| v1.0 | 2026-10-06 | 项目组 | 第 1 轮交付说明 |
