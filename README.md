# 智阅校园 · 开发交付说明（第 1 轮 + 第 2 轮·权限与角色）

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
| ③ 首版 API 接口定义 | `docs/API接口定义-v1.md`，5 组共 34 个端点；启动后可访问 `/docs` 查看 OpenAPI | ✅ 已完成 |
| 全员任务：核心数据对象与统一字段 | `docs/核心数据对象与统一字段规范.md`（v1.2，含第九章「第 1 轮实现对照」） | ✅ 已完成 |
| 规范 v1.2 同步 | 按项目组《核心数据对象与统一字段规范》v1.2 对齐字段、报名规则、HTTP 状态码与首版活动接口 | ✅ 已完成 |

**验证结果**：后端冒烟测试覆盖登录、活动状态机、报名（重复报名 409）、ISBN 扫码、AI 解读、AI 对话、漂流池；前端 `npm run build` 通过。

---

## 一·补 第 2 轮①：权限与角色（10-18 组会第一项）

设计文档：`docs/第2阶段-权限与角色设计.md`（角色模型、16 个权限点总表、防越权约束、审批流、证书、总结推送、访客边界、9 步验证清单）

| 组会要求 | 落地情况 |
|---|---|
| 角色改为学生 / 管理员 / 访客，管理员再分普通与系统 | 4 个角色：`student`、`admin`、`super_admin`、`visitor`；旧 `librarian` 已数据迁移为 `admin` |
| 学生新增电子证书（可下载 PDF） | `certificate_service.py` 服务端 reportlab 渲染 A4 横版 PDF，含公章图形、唯一编号 `ZYYC-2026-S-XXXXXXXX`、8 位验真码；学生只能拿 PDF，拿不到模板 |
| 学生可申办并管理活动（限部分学生会成员） | 权限点 `activity:create` 逐人授予；万贝账号已授予，可申办 → 提交审批 → 管理自己的活动 |
| 普通管理员：申办 / 图书漂流 / 审批 / 定级 / 盖章 | `activity:review` 审批时可定级为校级 / 院级，等级决定证书上「校级活动 / 院级活动」标识与编号中的 S/C 位 |
| 系统管理员分配各项权限 | `PATCH /users/{id}/permissions` 逐项授予 / 收回，`PATCH /users/{id}/role` 调整角色；前端「系统管理 → 用户与权限」页可视化操作 |
| 访客：可看推送与漂流、不能报名、AI 推荐走降级 Mock | `get_optional_user` 提供访客上下文；`/books/recommend` 对访客强制 `mock_recommend_reasons`，返回 `degraded=true, model=mock`；报名 / 上架 / 证书等接口对访客一律 `code=1003` |
| 管理员写活动总结 + 现场照片，并作为推送发出 | `POST /activities/{id}/summary` → `POST /summaries/{id}/publish`（按 `target_roles` 推送），`GET /summaries` 全站流、`GET /notifications` 按角色过滤 |

**权限模型要点**：有效权限 = 角色默认 − 收回 + 额外授予（`granted_permissions` / `revoked_permissions`），token 里的角色只作兜底，每次请求都查库重算，所以**收回权限立即失效、无需重新登录**。

**防越权硬约束**（全部有测试覆盖）：不能改自己的权限或角色；接口不能创建 / 提级 `super_admin`；`system:permission` 不可下放；审批人不能审批自己申办的活动；每次变更写 `permission_logs`，无实际变化的操作不落流水。

**验证**：`.venv/Scripts/python.exe tests/test_api_smoke.py` 7 组场景全过（权限矩阵 / 访客边界 / 申办审批 / 分配权限 / 电子证书 / 总结推送 / 状态机）；该脚本可重复运行，测试数据按 `[SMOKE]` 前缀自清理。

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

## 二、目录结构

```text
智阅校园/
├── .vscode/                           ← 调试 / 任务 / 插件推荐
├── 开发指南.md                        ← 日常开发指南
├── start-backend.bat / start-frontend.bat
├── docs/
│   ├── 核心数据对象与统一字段规范.md       ← 双端字段口径（v1.2 + 实现对照）
│   ├── API接口定义-v1.md                 ← API 与请求/响应示例
│   ├── 第2阶段-权限与角色设计.md          ← 角色 / 16 个权限点 / 审批流 / 证书
│   ├── 第2阶段-本地数据库与脱敏数据申请.md ← 建库 / 迁移 / 备份 / 导入 / 上云路径
│   ├── 数据字典.md                       ← 13 张表全部字段（脚本生成）
│   ├── 数据字段清单-脱敏数据申请.xlsx      ← 发给老师的申请表
│   └── 组会提交材料-第1轮.md              ← 组会对齐用（变更点 / 落地状态 / 待确认）
├── backend/                           ← FastAPI 工程
│   ├── alembic/versions/              版本化迁移（基线 + 增量）
│   ├── app/core/                      配置 / 枚举 / 响应 / 鉴权 / 权限点
│   ├── app/db/                        SQLAlchemy 模型
│   ├── app/schemas/                   请求响应契约
│   ├── app/api/v1/                    用户 / 活动 / 图书 / AI / 漂流 / 证书 / 权限
│   ├── samples/                       导入用示例 CSV
│   ├── scripts/                       seed / migrate / backup / import / export
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
.venv/Scripts/python.exe scripts/seed.py          # 建表 + 演示数据（内部会自动跑迁移）
.venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000
```

- 接口文档：<http://127.0.0.1:8000/docs>
- 冒烟测试：`.venv/Scripts/python.exe tests/test_api_smoke.py`（可重复运行，测试数据自动清理）
- 重置演示数据：`.venv/Scripts/python.exe scripts/seed.py --reset`
- 查看 / 执行迁移：`.venv/Scripts/python.exe scripts/migrate.py --status` / `scripts/migrate.py`
- 备份数据库：`.venv/Scripts/python.exe scripts/backup_db.py --tag 组会前`
- 重新生成字段清单：`.venv/Scripts/python.exe scripts/export_data_dictionary.py`
- 数据库：SQLite 文件固定在 `backend/smart_reading.db`（`DATABASE_URL` 用绝对路径），从仓库根目录或 `backend/` 启动都指向同一个库。

### 前端

```bash
cd web-pc
npm install
npm run dev
```

演示账号（密码统一 `123456`）：

| 学号/工号 | 姓名 | 角色 | 权限数 | 用途 |
|---|---|---|---|---|
| `T2009` | 图书馆老师 | 普通管理员 | 15 | 管理端主账号（含审批） |
| `T2010` | 图书馆老师（无审批权） | 普通管理员 | 14 | 演示「逐项收回权限」 |
| `admin` | 系统管理员 | 系统管理员 | 16 | 用户与权限分配 |
| `2025211987` | Alice | 学生 | 7 | 学生默认权限 |
| `2025211995` | 万贝 | 学生 | 8 | 额外授予 `activity:create`（学生会成员） |
| `2025211996` | Bob | 学生 | 7 | 普通学生对照 |
| `guest` | 访客 | 访客 | 3 | 只读 + Mock 推荐 |

> 演示「权限即时生效」：用 `admin` 收回 `2025211987` 的 `activity:signup`，该账号**不用重新登录**即刻无法报名。

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

状态合法性由后端校验，前端仅作按钮提示；非法流转统一返回 `code=1005`。审批通过时必须定级（`school` 校级 / `college` 院级），证书颁发要求活动已结束且已定级。

---

## 五、已知后续工作

| 项目 | 说明 |
|---|---|
| 大模型真实调用 | 已接入 DeepSeek：填写 `backend/.env` 的 `LLM_API_KEY` 并保持 `LLM_ENABLED=true` |
| RAG 向量知识库 | 后续建设书目向量化与检索增强 |
| 扫码签到 | `ActivitySignup.checked_in_at` 字段已就位；签到凭证规则规范标注为非本轮必做 |
| 取消报名接口 | 规范 7.2.6 标注非本轮必做；数据层已支持 `cancelled` 记录窗口内重新激活 |
| 活动照片上传 | 总结已支持填图片 URL；对象存储接入待做（第 2 轮②一并考虑） |
| 证书模板可视化配置 | 当前模板参数在代码中固定，后续做成可配置 |
| 微信小程序端 | 按统一字段规范接入 |
| 第 2 轮③ | 全面转向智能体：AI 录书 / AI 匹配 / AI 触达 / AI 伴读 |

---

## 六、验收参考

**第 2 轮①（权限与角色）**

1. `admin` 登录 → 系统管理 → 用户与权限：可见 16 个权限点按 6 组分类，可对任意用户勾选授予 / 收回，变更后立刻生效（被改的账号不重新登录也生效）。
2. `T2010` 登录看不到「审批」入口；`T2009` 能看到。两者角色相同，差别只在一项被收回的权限。
3. `2025211995`（万贝）可申办活动 → 提交审批 → `T2009` 审批并选「校级 / 院级」→ 发布；若由申办人自己审批，返回「不能审批自己申办的活动」。
4. 学生端「我的证书」可下载 PDF（A4 横版、含公章与验真码）；`/certificates/verify/{code}` 无 token 也能查，姓名脱敏为「万*」。
5. 活动结束后写总结并发布 → 学生 / 访客端「活动推送」流可见，访客消息中心收到推送。
6. 未登录打开首页：可看活动、看漂流状态、用 AI 推荐（页面提示「访客体验模式，推荐理由由本地规则生成」），但报名按钮不出现。

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
| v2.1 | 2026-10-19 | 万贝 | 第 2 轮②：Alembic 版本化迁移、备份/恢复、三类 CSV 导入（含脱敏与幂等）、13 张表（新增借阅/收藏/行为）、脱敏数据申请清单与云迁移路径 |
| v2.0 | 2026-10-19 | 万贝 | 第 2 轮①：角色改为 4 类 + 16 权限点、逐项分配与即时生效、活动审批定级、电子证书 PDF、活动总结推送、访客降级 Mock；`DATABASE_URL` 改为绝对路径避免两个库文件；冒烟测试改为可重复运行 |
| v1.2 | 2026-10-07 | 项目组 | 同步字段规范与接口行为；补 v1.2 实现对照（规范第九章）与组会提交材料；修正演示数据与冒烟测试口径 |
| v1.2 | 2026-10-07 | 项目组 | 同步字段规范与接口行为，移除演示老师的具体身份信息 |
| v1.0 | 2026-10-06 | 项目组 | 第 1 轮交付说明 |
