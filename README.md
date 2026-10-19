# 智阅校园 · 开发交付说明（第 1 轮 + 第 2 轮全三项）

> 第 1 轮开发周期：2026-10-06 ~ 2026-10-18　｜　演示验收：10-18 21:00 线上会议
> 第 2 轮：2026-10-19 起，按 10-18 组会三项议程分三次推进（① 权限与角色 ② 本地数据库 ③ 智能体化）
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
| ③ 首版 API 接口定义 | 5 组共 34 个端点（第 1 轮）；第 2 轮新增权限 / 证书 / 总结 / 智能体接口。<br>接口清单以启动后的 `/docs`（OpenAPI，自动生成、始终最新）为准 | ✅ 已完成 |
| 全员任务：核心数据对象与统一字段 | `docs/核心数据对象与统一字段规范.md`（v1.2，含第九章「第 1 轮实现对照」） | ✅ 已完成 |
| 规范 v1.2 同步 | 按项目组《核心数据对象与统一字段规范》v1.2 对齐字段、报名规则、HTTP 状态码与首版活动接口 | ✅ 已完成 |

**验证结果**：后端冒烟测试覆盖登录、活动状态机、报名（重复报名 409）、ISBN 扫码、AI 解读、AI 对话、漂流池；前端 `npm run build` 通过。

---

## 一·补 第 2 轮①：权限与角色（10-18 组会第一项）

设计文档：`docs/第2阶段-权限与角色设计.md`（角色模型、15 个权限点总表、防越权约束、审批流、证书、总结推送、访客边界、9 步验证清单）

| 组会要求 | 落地情况 |
|---|---|
| 角色改为学生 / 管理员 / 访客，管理员再分普通与系统 | 4 个角色：`student`、`admin`、`super_admin`、`visitor`；旧 `librarian` 已数据迁移为 `admin` |
| 学生新增电子证书（可下载 PDF） | `certificate_service.py` 服务端 reportlab 渲染 A4 横版 PDF，含公章图形、唯一编号 `ZYYC-2026-S-XXXXXXXX`、8 位验真码；学生只能拿 PDF，拿不到模板 |
| 学生可申办并管理活动（限部分学生会成员） | 权限点 `activity:create` 逐人授予；林晓账号已授予，可申办 → 提交审批 → 管理自己的活动 |
| 普通管理员：申办 / 图书漂流 / 审批 / 定级 / 盖章 | `activity:review` 审批时可定级为校级 / 院级，等级决定证书上「校级活动 / 院级活动」标识与编号中的 S/C 位 |
| 系统管理员分配各项权限 | `PATCH /users/{id}/permissions` 逐项授予 / 收回，`PATCH /users/{id}/role` 调整角色；前端「系统管理 → 用户与权限」页可视化操作 |
| 访客：可看推送与漂流、不能报名、AI 推荐走降级 Mock | `get_optional_user` 提供访客上下文；`/books/recommend` 对访客强制 `mock_recommend_reasons`，返回 `degraded=true, model=mock`；报名 / 上架 / 证书等接口对访客默认 `code=1003`，访客可在个人中心提交权限申请，审批通过后按授予的权限开放 |
| 管理员写活动总结 + 现场照片，并作为推送发出 | `POST /activities/{id}/summary` → `POST /summaries/{id}/publish`（定向推给报名者，访客按角色广播），`GET /summaries` 全站流、`GET /notifications` 定向 + 广播并带个人已读状态 |
| 学生端活动要能看到「我发布的」 | `GET /activities/feed?scope=mine`：本人草稿、待审批、被驳回的活动都会列出并带状态标签，不用等发布才看得到 |
| 学生端智能体要有录书与触达 | 场景可用性改为「角色白名单 + 权限」双通道：学生可用录书（只出待确认书目）与触达（只出草稿），触达只能选自己发布的活动 |

**权限模型要点**：有效权限 = 角色默认 − 收回 + 额外授予（`granted_permissions` / `revoked_permissions`），token 里的角色只作兜底，每次请求都查库重算，所以**收回权限立即失效、无需重新登录**。

**防越权硬约束**（全部有测试覆盖）：不能改自己的权限或角色；接口不能创建 / 提级 `super_admin`；`system:permission` 不可下放；审批人不能审批自己申办的活动；每次变更写 `permission_logs`，无实际变化的操作不落流水。

**验证**：`.venv/Scripts/python.exe tests/test_api_smoke.py` 10 组场景全过（权限矩阵 / 访客边界 / 申办审批 / 分配权限 / 电子证书 / 总结推送 / 状态机 / 注册入口 / 权限申请 / 站内消息）；脚本每次在 `backend/tests/.test_smoke.db` 建独立库并灌 seed 数据，不读写演示库，可随时重复运行。

---

## 一·补 1.5 账号入口、个人中心与权限申请（10-19 追加）

| 需求 | 落地情况 |
|---|---|
| 开始界面不要一上来列角色，只要「注册 / 登录 / 访客」 | `Login.vue` 顶部三个入口按钮；演示账号收进折叠面板，不再占据主界面 |
| 注册时再选学生还是管理员 | `Register.vue` 两张身份卡：学生（报名、漂流、证书、AI 伴读）/ 管理员（审批、漂流运营、活动总结）；`super_admin` 与 `visitor` 不开放注册 |
| 注册之后直接登录 | `POST /auth/register` 返回 token，注册成功即进入首页，无需二次输入 |
| 访客入口 | `POST /auth/guest` 一键进入只读身份，不需要账号密码 |
| 个人中心 | 侧边栏与头像下拉均可进入：个人资料、我的权限（含来源标注）、我的申请、账号安全（改密） |
| 个人中心提交权限申请 | `POST /permission-requests`：勾选需要的权限 + 填写理由；可撤回，可在「我的申请」查看审批意见 |
| 只有系统管理员能看到申请 | `GET /permission-requests` 与 `/summary` 均校验 `system:permission`；学生与普通管理员访问返回 `code=1003` |
| 系统管理员赋予权限 | 「用户与权限 → 权限申请」逐条通过 / 驳回；通过后权限**立即写入并生效**，同时补一条 `permission_logs` 变更流水 |

**密码策略**：注册用户的密码经 PBKDF2-HMAC-SHA256（每用户随机盐）哈希存储，登录只认自己的密码；seed 写入的演示账号没有哈希，仍可用统一密码 `123456`，一旦在个人中心改过密码就只认新密码。

**安全约束**：不能申请 `system:permission`；不能注册系统管理员；不能审批自己提交的申请；同一权限在审批中时不能重复提交；审批通过时若目标已拥有该权限则跳过，不重复记账。

**验收路径**：`admin` 登录 → 用户与权限 → 权限申请（待审批 1 条）→ 审批通过；换成 `2025211994` 登录 → 个人中心 → 我的权限，能看到该权限被标为「额外授予」。

---

## 一·补2 第 2 轮②：本地数据库与脱敏数据申请（10-18 组会第二项）

设计文档：`docs/第2阶段-本地数据库与脱敏数据申请.md`
申请材料：`docs/数据字段清单-脱敏数据申请.xlsx`（5 个 sheet，可直接发老师）｜完整字段：`docs/数据字典.md`

| 组会要求 | 落地情况 |
|---|---|
| 先搭本地库，后续再迁云端 | SQLite 单文件库 + Alembic 版本化迁移；切 MySQL 只改 `DATABASE_URL` 一行 |
| 整理数据字段清单，向老师申请脱敏数据 | 自动生成申请材料：30 个需申请的字段（其余 176 个系统自建）、4 条脱敏规则、不申请字段及原因、数据量估算 |
| 为智能体准备数据 | 新增 `borrow_records`（借阅）、`book_favorites`（收藏评分）、`reading_events`（行为埋点）3 张表；`books` 补齐中图法分类号、索书号、页数、定价、目录等 8 个字段 |
| 数据怎么进来 | `scripts/import_school_data.py`：学生 / 书目 / 借阅三类 CSV，内置脱敏（HMAC-SHA256）与幂等，支持 `--dry-run` |

**新增脚本**

| 脚本 | 作用 |
|---|---|
| `scripts/migrate.py` | 备份 → 升级 → 校验（一条命令完成，避免 SQLite 迁移失败留残） |
| `scripts/backup_db.py` | 备份 / 列表 / 恢复（`VACUUM INTO` 快照，默认保留 20 份） |
| `scripts/import_school_data.py` | 学校脱敏数据导入（学生 / 书目 / 借阅） |
| `scripts/export_data_dictionary.py` | 从 ORM 模型生成数据字典与脱敏申请清单，改字段后重跑即可 |

**验证**：`alembic check` 无差异；`downgrade -1` 再 `upgrade head` 往返正常；三类 CSV 首次导入创建、二次导入全部 skipped；冒烟测试仍 7 组全过。

---

## 一·补3 第 2 轮③：全面转向智能体（10-18 组会第三项）

设计文档：`docs/第2阶段-智能体架构.md`

之前是「拼提示词 → 调模型 → 拿文字」，模型不知道馆里有什么书。现在换成「派一件事，它自己去查」：
模型可以调 10 个只读工具读真实馆藏与读者画像，每次运行的过程都留痕。

| 组会要求 | 落地情况 |
|---|---|
| 全部接入智能体，不再只是接 API | 新增 `app/agents/`：场景层 + ReAct 运行时 + 工具层 + 模型层；OpenAI 兼容协议，DeepSeek / 通义 / 本地 Ollama 同一套代码 |
| AI 录书 | `POST /agents/intake/run`：ISBN/书名/文字 → 查重 → 结构化书目 + 置信度 + 缺失字段，人工确认后才入库 |
| AI 匹配 | `POST /agents/match/run`：读画像 → 召回 → 核库存 → 带证据的理由；**模型给的书必须真实存在，否则剔除** |
| AI 触达 | `POST /agents/outreach/run`：查活动真实信息 + 报名人群 → 标题/正文/推送摘要，固定 `needs_human_approval`，只出草稿 |
| AI 伴读 | `POST /agents/companion/run`：判断意图 → 查馆藏/活动 → 回答带引用（索书号、馆藏地） |
| 数据字段整理 | 第 2 轮②已完成，另加了 `agent_runs` 表记录每次运行的轨迹 |
| 各种模型都能调 | 换模型只改 `.env` 三行；不支持 function calling 的模型走文本协议兜底 |

**关键设计**

| 问题 | 做法 |
|---|---|
| 模型编造书目 | 所有 `book_id` / 引用回库核对，核不上就剔除；全核不上则整次降级 |
| 成本失控 | 最多 4 步、6000 token 预算、45 秒超时，超了强制收尾 |
| 越权查数据 | 工具声明允许的场景，伴读场景根本拿不到「报名人群分布」这类工具 |
| 谁能用哪个场景 | 录书与触达只产出草稿、不写库，学生也能用；触达只能针对自己发布的活动；访客仅开放匹配 |
| 没 key 就演示不了 | 完整规则降级链（匹配/录书/触达/伴读四套），降级必标 `degraded` + 原因 |
| 真实数据没到 | `scripts/simulate_data.py` 按学院-兴趣分布生成带 `data_source='simulated'` 标记的样本，真实数据到位后 `--purge` 精确替换 |

**验证**：`tests/test_agent_smoke.py` 25 项全过（含用假模型驱动完整 ReAct 循环：两轮调用、工具结果回灌、防编造剔除、四场景降级）；原有 7 组回归测试仍全过；前端 `/agents` 工作台构建通过。

---

## 二、目录结构与文档导航

> 组会只需看本文件 + `docs/` 下三份「第2阶段」文档；数据申请另用 xlsx / 微信消息两份。

```text
智阅校园/
├── .vscode/                           ← 调试 / 任务 / 插件推荐
├── README.md                          ← 本文：交付说明 / 运行 / 验收
├── start-backend.bat / start-frontend.bat
├── docs/
│   ├── 核心数据对象与统一字段规范.md        ← 双端字段口径（v1.2 + 实现对照）
│   ├── 第2阶段-权限与角色设计.md            ← 角色 / 15 个权限点 / 审批流 / 证书
│   ├── 第2阶段-本地数据库与脱敏数据申请.md   ← 建库 / 迁移 / 备份 / 导入 / 上云路径
│   ├── 第2阶段-智能体架构.md                ← 四场景 / 工具清单 / 降级链 / 换模型
│   ├── 数据字典.md                         ← 16 张表全部字段（脚本生成，勿手改）
│   ├── 数据字段清单-脱敏数据申请.xlsx        ← 发给老师的申请表
│   └── 给老师的微信消息-数据申请.md          ← 微信直发版（xlsx 的简版）
├── backend/                           ← FastAPI 工程
│   ├── alembic/versions/              版本化迁移（基线 + 增量）
│   ├── app/core/                      配置 / 枚举 / 响应 / 鉴权 / 权限点
│   ├── app/db/                        SQLAlchemy 模型
│   ├── app/schemas/                   请求响应契约
│   ├── app/agents/                    智能体：运行时 / 工具 / 四场景 / 降级
│   ├── app/api/v1/                    用户 / 活动 / 图书 / AI / 智能体 / 漂流 / 证书 / 权限
│   ├── samples/                       导入用示例 CSV
│   ├── scripts/                       seed / simulate / migrate / backup / import / export
│   └── tests/                         test_api_smoke / test_agent_smoke
└── web-pc/                            ← PC 端 Vue 工程
```

---

## 三、如何跑起来

> 双击 `start-backend.bat` 与 `start-frontend.bat`，或在 VS Code 运行「★ 一键启动全栈（后端 + 前端）」。

### 后端

模型配置：在 `backend/.env` 中设置 `LLM_API_KEY` 为 DeepSeek 控制台创建的 API Key。
默认配置已使用 `deepseek`、`deepseek-chat` 和 `https://api.deepseek.com/v1`；
普通 AI 接口和智能体共用同一套模型配置。保存后重启后端，并运行
`.venv/Scripts/python.exe scripts/check_llm.py` 验证连通性。

```bash
cd backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe scripts/seed.py          # 建表 + 演示数据（内部会自动跑迁移）
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

- 接口文档：<http://127.0.0.1:8000/docs>
- 冒烟测试：`.venv/Scripts/python.exe tests/test_api_smoke.py`（可重复运行，测试数据自动清理）
- 重置演示数据：`.venv/Scripts/python.exe scripts/seed.py --reset`
- 查看 / 执行迁移：`.venv/Scripts/python.exe scripts/migrate.py --status` / `scripts/migrate.py`
- 备份数据库：`.venv/Scripts/python.exe scripts/backup_db.py --tag 组会前`
- 重新生成字段清单：`.venv/Scripts/python.exe scripts/export_data_dictionary.py`
- 生成 AI 模拟数据（真实脱敏数据到位前）：`.venv/Scripts/python.exe scripts/simulate_data.py`
- 清除模拟数据（真实数据到了）：`.venv/Scripts/python.exe scripts/simulate_data.py --purge --purge-books`
- 智能体链路测试：`.venv/Scripts/python.exe tests/test_agent_smoke.py`
- 数据库：SQLite 文件固定在 `backend/smart_reading.db`（`DATABASE_URL` 用绝对路径），从仓库根目录或 `backend/` 启动都指向同一个库。

### 前端

```bash
cd web-pc
npm install
npm run dev
```

> 登录页提供三个入口：**登录 / 注册 / 访客**。新账号在注册页选择「学生」或「管理员」，注册成功直接进入系统；点击「访客」无需账号即可浏览。

演示账号（密码统一 `123456`）：

| 学号/工号 | 姓名 | 角色 | 权限数 | 用途 |
|---|---|---|---|---|
| `T2009` | 图书馆老师 | 普通管理员 | 13 | 管理端主账号（含审批） |
| `T2010` | 图书馆老师（无审批权） | 普通管理员 | 12 | 演示「逐项收回权限」 |
| `admin` | 系统管理员 | 系统管理员 | 15 | 用户与权限分配 |
| `2025211987` | Alice | 学生 | 7 | 学生默认权限 |
| `2025211994` | 林晓 | 学生 | 8 | 额外授予 `activity:create`（学生会成员） |
| `2025211996` | Bob | 学生 | 7 | 普通学生对照 |
| `guest` | 访客 | 访客 | 3 | 只看不报名，AI 推荐走降级 |
| `SIM20260000` 起 | 模拟学生 | 学生 | 7 | AI 模拟数据账号（`simulate_data.py` 生成），可直接登录演示 |

> 演示「权限即时生效」：用 `admin` 收回 `2025211987` 的 `activity:signup`，该账号**不用重新登录**即刻无法报名。

### 常见问题

| 现象 | 处理 |
|---|---|
| 前端报 `@esbuild/win32-x64` 找不到 | 安装与 `node_modules/esbuild` 同版本的 `@esbuild/win32-x64` |
| 端口被占用 | 后端改 `--port 8001` 并同步 `vite.config.js` 代理；前端 `npm run dev -- --port 5174` |
| 改了模型但库里没变化 | 执行 `scripts/migrate.py` 生成并应用迁移，别手工改表 |
| 后端启动报数据库缺列 | `scripts/migrate.py --status` 看当前版本，再 `scripts/migrate.py` 升级（会先自动备份） |

---

## 四、核心数据对象与状态机

完整字段见 `docs/核心数据对象与统一字段规范.md`。JSON 字段为 `snake_case`；对外 ID 使用带前缀字符串；时间统一序列化为 ISO 8601 `+08:00`；响应体与分页结构全项目统一。

| 对象 | 主键 | 关键字段 |
|---|---|---|
| User | `user_id` | `student_no`、`name`、`role`、`status`、学院/专业/班级；第 2 轮新增 `granted_permissions` / `revoked_permissions` |
| Activity | `activity_id` | `title`、`category`、`status`、活动/报名时间、名额和人数、证书配置；第 2 轮新增 `level`、`submitted_at`、`reviewed_by`、`reviewed_at`、`review_comment` |
| Book | `book_id` | `isbn`、书目元数据、馆藏数量、AI 解读；source 支持 library/drift/both |
| AIConversation | `conversation_id` | `user_id`、`scene`、`book_id`、`messages[]`、`prompt_version` |
| ActivitySignup | `signup_id` | 活动报名与签到关系 |
| DriftRecord | `drift_id` | 单册漂流状态、持有者、交接地点和流转次数 |
| Certificate | `certificate_id` | 第 2 轮新增：`serial_no`、`verify_code`、`activity_level`、`seal_name`、`status`（issued / revoked） |
| ActivitySummary | `summary_id` | 第 2 轮新增：活动总结正文、现场照片、`status`、`target_roles` |
| Notification | `notification_id` | 第 2 轮新增：`type`、`target_roles`、`ref_id`（指向活动 / 总结 / 证书） |
| PermissionLog | `log_id` | 第 2 轮新增：操作人、目标用户、`action`、`permission`、变更前后值 |
| BorrowRecord | `borrow_id` | 第 2 轮②新增：`reader_hash`、`isbn`、`borrowed_at`、`due_at`、`returned_at`、`renew_count`、`status` |
| BookFavorite | `favorite_id` | 第 2 轮②新增：收藏与评分（一人一书唯一） |
| ReadingEvent | `event_id` | 第 2 轮②新增：`event_type`、`book_id`、`keyword`、`duration_sec`、`scene` |

```text
draft → pending_review → published → signup_closed → ongoing → finished
  │  └──→ rejected ──┘         │
  └────────────────────────────┴──→ cancelled
```

状态合法性由后端校验，前端仅作按钮提示；非法流转统一返回 `code=1005`。审批通过时必须定级（`school` 校级 / `college` 院级），证书在活动定级后，由学生完成签到与签退自动发放。

---

## 五、已知后续工作

| 项目 | 说明 |
|---|---|
| 大模型真实调用 | 普通 AI 接口与智能体共用 DeepSeek OpenAI 兼容配置；在 `backend/.env` 配置有效的 `LLM_API_KEY` 并设 `LLM_ENABLED=true` 后启用 |
| RAG 向量知识库 | 后续建设书目向量化与检索增强 |
| 扫码签到 | `ActivitySignup.checked_in_at` 字段已就位；签到凭证规则规范标注为非本轮必做 |
| 取消报名接口 | 规范 7.2.6 标注非本轮必做；数据层已支持 `cancelled` 记录窗口内重新激活 |
| 活动照片上传 | 总结已支持填图片 URL；对象存储接入待做（第 2 轮②一并考虑） |
| 证书模板可视化配置 | 当前模板参数在代码中固定，后续做成可配置 |
| 微信小程序端 | 按统一字段规范接入 |
| 录书 OCR | 目前只接文字，图片识别待接第三方 OCR |
| 向量检索 | 当前用关键词 + 中图法分类召回，书目上万后需加向量索引 |
| 触达到期提醒 | 工具层已能取借阅与应还日期，等真实借阅数据进来再接 |

---

## 六、验收参考

**第 2 轮①（权限与角色）**

1. `admin` 登录 → 系统管理 → 用户与权限：可见 15 个权限点按 6 组分类，可对任意用户勾选授予 / 收回，变更后立刻生效（被改的账号不重新登录也生效）。
2. `T2010` 登录看不到「审批」入口；`T2009` 能看到。两者角色相同，差别只在一项被收回的权限。
3. `2025211994`（林晓）可申办活动 → 提交审批 → `T2009` 审批并选「校级 / 院级」→ 发布；若由申办人自己审批，返回「不能审批自己申办的活动」。
4. 学生端「我的证书」可下载 PDF（A4 横版、含公章与验真码）；`/certificates/verify/{code}` 无 token 也能查，姓名脱敏为「万*」。
5. 活动结束后写总结并发布 → 参加（报名）过该活动的学生会收到「你参加的活动发布了回顾」，未报名的人不会收到；访客按角色广播收到。
6. 未登录打开首页：可看活动、看漂流状态、用 AI 推荐（页面提示「访客体验模式，推荐理由由本地规则生成」），但报名按钮不出现。
7. 退出登录后，登录页点「访客」：不填任何账号直接进入，侧边栏只有浏览类菜单，没有审批、我的证书、用户与权限。
8. 登录页点「注册」→ 选「学生」→ 填学号、姓名、密码 → 提交后**直接进入首页**；退出后该学号只能用它自己的密码登录，`123456` 不再有效。
9. 学生登录 → 个人中心 → 我的权限 → 申请权限 → 勾选「申办活动」并填写理由 → 提交；再点「撤回」可取消。
10. `admin` 登录 → 用户与权限 → 权限申请：能看到上面那条申请（学生与管理员提交的都在这里）；点「审批」→ 通过 → 该学生账号权限立即增加，个人中心显示「额外授予」。学生或普通管理员访问该页会被拒绝（菜单也不显示）。

**消息中心（站内通知）**

11. 学生提交权限申请后，`admin` 顶栏「消息」右上角红点 +1；点开消息中心能看到「XXX 申请权限：申办活动」，未读条目浅蓝底 + 红点。
12. `admin` 在该条消息点「查看」直达「用户与权限 → 权限申请」；审批通过后，**审批人自己的红点自动减 1**（待办已处理），申请人那边红点 +1，消息为「你的权限申请已通过」。
13. 学生申办活动并提交审批 → 审批人收到「待审批活动」；审批通过后申办人收到「你申办的活动已通过审批」并写明定级（校级/院级）。
14. 活动结束后发布总结 → 报名者收到「你参加的活动发布了回顾」；颁发证书 → 获证学生收到「你获得了活动证书」。
15. 消息中心点整行即标为已读、红点立即减少；点「全部已读」归零；切换「未读」页签只剩未读条目。红点每 10 秒自动同步一次，无需手动刷新。

**第 2 轮②（本地数据库）**

1. `alembic check` 输出无差异；`alembic downgrade -1` 再 `upgrade head` 往返正常。
2. `scripts/import_school_data.py --students ... --dry-run` 可预演不写库；正式导入后二次执行全部 skipped（幂等）。
3. `scripts/backup_db.py --list` 能看到快照；`scripts/migrate.py` 会先备份再升级。

**第 2 轮③（智能体）**

1. 登录 `2025211994` → 左侧「智能体工作台」→ 选「AI 匹配」→ 直接点运行（不填需求）：右侧出现运行轨迹，能看到 `user_profile` / `search_books` / `book_stats` 等步骤，以及每步返回了什么。
2. 换 `2025211987`（Alice）登录再跑一次：推荐结果不同，因为两人借阅画像不同。
3. 用 `guest` 登录：只能看到「AI 匹配」场景；运行结果显示访客降级原因，不会调用真实模型。
4. 页面顶部有黄色提示条说明当前为降级模式（模型 key 失效），以及蓝色提示条说明包含模拟数据。
5. 选「AI 触达」→ 选一场活动 → 运行：生成的文案里时间地点名额与活动详情一致，且底部写明「AI 只出草稿，不自动发送」。
6. 选「AI 录书」→ 输入 ISBN `9787115428028`：提示「馆藏中已存在这本书」，不会重复录入。
7. `.venv/Scripts/python.exe tests/test_agent_smoke.py` 输出「冒烟测试全部通过 ✅（25 项）」。

**第 1 轮**

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
| v2.3 | 2026-10-19 | PC 端研发 | 账号入口改为「登录 / 注册 / 访客」三选一，注册时选择学生或管理员并自动登录；新增个人中心（资料、我的权限、申请记录、改密）与权限申请审批流（`permission_requests` 表）；密码改为 PBKDF2 哈希存储；移除原「万贝」演示账号，改用中性账号 `2025211994 林晓` |
| v2.2 | 2026-10-19 | PC 端研发 | 第 2 轮③：智能体层（ReAct 运行时 + 10 个只读工具 + 四场景 + 规则降级链）、`agent_runs` 运行轨迹、防编造校验、智能体工作台页面、AI 模拟数据集（带来源标记，可一键替换）；`/books/recommend` 契约不变、内部改为智能体实现 |
| v2.0 | 2026-10-19 | PC 端研发 | 第 2 轮①：角色改为 4 类 + 15 权限点、逐项分配与即时生效、活动审批定级、电子证书 PDF、活动总结推送、访客降级 Mock；`DATABASE_URL` 改为绝对路径避免两个库文件；冒烟测试改为可重复运行 |
| v1.2 | 2026-10-07 | 项目组 | 同步字段规范与接口行为；补 v1.2 实现对照（规范第九章，组会材料已并入本文件）；修正演示数据与冒烟测试口径 |
| v1.2 | 2026-10-07 | 项目组 | 同步字段规范与接口行为，移除演示老师的具体身份信息 |
| v1.0 | 2026-10-06 | 项目组 | 第 1 轮交付说明 |
