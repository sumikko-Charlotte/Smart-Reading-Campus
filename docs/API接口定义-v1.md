# 「智阅校园」API 接口定义（v1.2）

> Base URL：本地 `http://127.0.0.1:8000/api/v1`（前端通过 Vite 代理 `/api` 访问）
> 在线调试：启动后端后打开 `http://127.0.0.1:8000/docs`（FastAPI 自动生成的 OpenAPI 文档）
> 统一响应体与错误码见《核心数据对象与统一字段规范.md》1.6 / 1.7 节
> 鉴权：除登录与健康检查外，均需请求头 `Authorization: Bearer <token>`

---

## 0. 接口总览

| 分组 | 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|---|
| 系统 | GET | `/health` | 健康检查（前端顶栏连通性标记） | 公开 |
| 鉴权 | POST | `/auth/login` | 登录 | 公开 |
| 用户 | GET | `/users/me` | 当前用户 | 登录 |
| 用户 | GET | `/users` | 用户列表 | librarian/admin |
| 用户 | POST | `/users` | 新增用户 | admin |
| 用户 | PATCH | `/users/{user_id}` | 更新用户 | 本人/admin |
| 活动 | GET | `/activities` | 活动列表（分页/筛选） | 登录 |
| 活动 | GET | `/activities/stats` | 活动总览统计 | 公开 |
| 活动 | GET | `/activities/{activity_id}` | 活动详情 | 登录；草稿仅管理人员 |
| 活动 | POST | `/activities` | 新建活动（草稿） | librarian/admin |
| 活动 | POST | `/activities/{activity_id}/publish` | 发布草稿活动 | librarian/admin |
| 活动 | PATCH | `/activities/{activity_id}` | 编辑活动 | librarian/admin |
| 活动 | POST | `/activities/{activity_id}/status` | 状态流转（状态机校验） | librarian/admin |
| 活动 | DELETE | `/activities/{activity_id}` | 软删除活动 | admin |
| 活动 | POST | `/activities/{activity_id}/ai-copy` | AI 生成宣传推文并回存 | 登录 |
| 活动 | POST | `/activities/{activity_id}/signups` | 当前学生报名 | student |
| 活动 | GET | `/activities/{activity_id}/signups` | 活动报名名单 | librarian/admin |
| 图书 | GET | `/books` | 图书列表（分页/筛选） | 公开 |
| 图书 | GET | `/books/isbn/{isbn}` | 按 ISBN 查书（小程序扫码入口） | 公开 |
| 图书 | GET | `/books/{book_id}` | 图书详情 | 公开 |
| 图书 | POST | `/books` | 录入图书 | librarian/admin |
| 图书 | PATCH | `/books/{book_id}` | 更新图书 | librarian/admin |
| 图书 | POST | `/books/{book_id}/ai-summary` | 生成/刷新 AI 深度解读 | 登录 |
| 图书 | POST | `/books/recommend` | AI 智能推荐（含推荐理由） | 登录 |
| AI | POST | `/ai/chat` | 多轮对话（`stream=true` 返回 SSE） | 登录 |
| AI | GET | `/ai/conversations` | 我的会话列表 | 登录 |
| AI | GET | `/ai/conversations/{id}` | 会话详情（消息流） | 本人 |
| AI | DELETE | `/ai/conversations/{id}` | 删除会话（软删除） | 本人 |
| AI | POST | `/ai/copywriting` | 生成推文/文案 | 登录 |
| 漂流 | GET | `/drift/books` | 漂流池列表 | 公开 |
| 漂流 | POST | `/drift/books` | 扫码上架 | 登录 |
| 漂流 | POST | `/drift/records/{drift_id}/claim` | 申领单册漂流书 | 登录 |
| 漂流 | GET | `/drift/records` | 流转记录 | 公开 |
| 漂流 | GET | `/drift/stats` | 漂流数据概览 | 公开 |

---

## 0.1 统一响应与错误码（v1.2）

所有非流式接口统一返回 `{ code, message, data, trace_id }`；失败时 `data=null`。HTTP 状态码与 `code` 的对应关系如下：

| HTTP 状态 | code | 用途 |
|---|---:|---|
| 200 / 201 | 0 | 查询/更新成功；创建成功 |
| 422 | 1001 | 字段、时间或枚举校验失败；`order_by` 不在白名单 |
| 401 | 1002 | 缺少或失效登录凭证 |
| 403 | 1003 | 权限不足（RBAC 拦截或访问他人资源） |
| 404 | 1004 | 资源不存在、已删除或对请求者不可见 |
| 409 | 1005 | 重复报名、满员、报名截止、非法状态流转 |
| 500 | 5000 | 内部错误；不返回堆栈或密钥 |

请求体只接受接口白名单字段，未知字段（如 `organizer_id`、`user_id`、`role`）一律返回 422 / `1001`；身份只从 `Authorization: Bearer <token>` 解析。

---

## 1. 鉴权

### POST /auth/login

请求：

```json
{ "student_no": "T2009", "password": "123456" }
```

响应 `data`：

```json
{
  "token": "eyJzdWIi...abc",
  "token_type": "Bearer",
  "expires_in": 43200,
  "user": {
    "user_id": "usr_9f2a1c77b0d4",
    "student_no": "T2009",
    "name": "图书馆老师",
    "role": "librarian",
    "college": "图书馆",
    "phone": "",
    "email": "",
    "status": "active",
    "created_at": "2026-10-06T16:20:00+08:00",
    "updated_at": "2026-10-06T16:20:00+08:00"
  }
}
```

> 第 1 轮密码校验为固定演示值 `123456`；第 2 轮改真实密码哈希（bcrypt）后接口形态不变。

### GET /users/me

返回当前用户信息。联系方式仅本人或管理员可见原值；其他场景返回脱敏值。完整 User 对象不得用于公共页面。

---

## 2. 活动管理

> **字段白名单（v1.2）：**`ActivityPublic` = `activity_id`、`title`、`subtitle`、`category`、`cover_url`、`summary`、`content`、`location`、`organizer_name`、`signup_start_at`、`signup_end_at`、`start_at`、`end_at`、`capacity`、`signup_count`、`status`、`need_certificate`；`ActivityAdmin` 在此之上增加 `organizer_id`、`checkin_count`、`certificate_template_id`、`ai_copy`、`published_at`、`created_at`、`updated_at`。响应一律不返回 `is_deleted`。

### GET /activities

查询参数：`page`、`page_size`、`keyword`、`status`、`category`、`order_by`、`order`

响应 `data`：

```json
{
  "list": [
    {
      "activity_id": "act_3d1c9a7f0b52",
      "title": "「书海拾贝」秋季读书分享会",
      "subtitle": "与同好共读一本好书",
      "category": "reading_share",
      "status": "published",
      "location": "图书馆三层报告厅",
      "organizer_name": "图书馆老师",
      "start_at": "2026-10-11T14:00:00+08:00",
      "end_at": "2026-10-11T17:00:00+08:00",
      "signup_start_at": "2026-10-01T14:00:00+08:00",
      "signup_end_at": "2026-10-09T14:00:00+08:00",
      "capacity": 60,
      "signup_count": 42,
      "need_certificate": true,
      "cover_url": "",
      "summary": "",
      "content": ""
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 4
}
```

### POST /activities

请求体（`ActivityCreate`）：

```json
{
  "title": "AI 时代的深度阅读主题讲座",
  "subtitle": "当大模型遇见图书馆",
  "category": "lecture",
  "location": "学术交流中心 201",
  "summary": "面向全校师生的阅读与 AI 主题讲座",
  "content": "活动详情正文……",
  "signup_start_at": "2026-10-07T09:00:00+08:00",
  "signup_end_at": "2026-10-15T18:00:00+08:00",
  "start_at": "2026-10-16T14:00:00+08:00",
  "end_at": "2026-10-16T17:00:00+08:00",
  "capacity": 120,
  "need_certificate": true,
  "certificate_template_id": ""
}
```

> 新建后 `status` 固定为 `draft`；`organizer_id` 不接受客户端传入，由服务端取当前管理人员身份。创建成功为 HTTP 201。

### POST /activities/{activity_id}/publish

请求 `{}`。仅草稿可发布；服务端校验报名开始/截止时间、活动开始/结束时间后写入 `published_at`。

### POST /activities/{activity_id}/status — 状态机流转

请求：`{ "target_status": "published", "reason": "" }`

合法流转表（后端强校验，非法流转返回 `code=1005`）：

| 当前状态 | 可流转到 |
|---|---|
| `draft` | `published`、`cancelled` |
| `published` | `signup_closed`、`cancelled` |
| `signup_closed` | `ongoing`、`cancelled` |
| `ongoing` | `finished` |
| `finished` / `cancelled` | 终态，不可再流转 |

流转为 `published` 时服务端自动写入 `published_at`。

### POST /activities/{activity_id}/signups

student 发送空对象 `{}`；用户身份只从 Bearer token 读取。成功直接创建 `approved` 报名并返回 HTTP 201；重复报名、活动截止或满员返回 HTTP 409、`code=1005`。同一活动每位用户仅有一条报名关系。

### GET /activities/{activity_id}/signups

仅 librarian/admin 可分页查看报名名单；`name` 与 `student_no` 不会出现在公开响应中。

### POST /activities/{activity_id}/ai-copy?style=xiaohongshu

响应：

```json
{ "activity_id": "act_xxx", "ai_copy": "【标题】……正文……#话题", "conversation_id": "cnv_xxx" }
```

生成的推文会回存到活动的 `ai_copy` 字段，同时在 `AIConversation`（`scene=copywriting`）留痕以便效果回溯。

---

## 3. 图书

### GET /books/isbn/{isbn}

`isbn` 自动去除连字符。未找到时返回 `code=1004`，消息提示「可发起漂流上架」——小程序扫码走这个接口。

### POST /books/{book_id}/ai-summary?force_refresh=false

响应：

```json
{
  "book_id": "bok_7a1f0c33e8b9",
  "ai_summary": "**一句话主旨**：……",
  "ai_tags": ["人工智能", "机器学习", "AI解读"],
  "cached": false,
  "conversation_id": "cnv_xxx",
  "model": "deepseek-chat",
  "prompt_version": "v1.0"
}
```

`cached=true` 表示命中已有解读（未重复调用大模型），`force_refresh=true` 时强制重算。

### POST /books/recommend

请求：

```json
{ "scene": "recommend", "limit": 6, "extra_prompt": "偏计算机类、篇幅不要太长" }
```

响应 `data.items[]` 为 `{ book, reason }`，`reason` 由 AI 按推荐场景生成。第 1 轮排序规则为「借阅热度降序 + 更新时间」，第 2 轮替换为向量召回 + 个性化排序。

---

## 4. AI 会话

### POST /ai/chat

请求：

```json
{
  "conversation_id": null,
  "content": "这本书适合零基础的同学读吗？",
  "scene": "qa",
  "book_id": "bok_xxx",
  "stream": false
}
```

- 请求仅接受 `conversation_id`、`book_id`、`scene`、`content`、`stream`；模型和 Prompt 版本由服务端维护。
- `conversation_id` 为 `null` → 新建会话；`book_id` 可为 `null`（通用问答）
- `stream=false`：返回 `data = { conversation_id, message_id, content }`
- `stream=true`：`Content-Type: text/event-stream`，帧格式：

```
data: {"delta": "这本书", "conversation_id": "cnv_xxx", "finished": false}

data: {"delta": "适合零基础", "conversation_id": "cnv_xxx", "finished": false}

data: {"delta": "", "conversation_id": "cnv_xxx", "finished": true, "message_id": "msg_xxx"}

data: [DONE]
```

> 无论是否流式，消息都会完整落库到 `AIConversation.messages`，保证双端可续聊、可回溯。

---

## 5. 图书漂流

### POST /drift/books（扫码上架）

请求：`{ "isbn": "9787115428028", "location": "图书馆一层大厅" }`；上架人从登录身份取得。

- ISBN 未建档 → 自动新建图书档案（`source=drift`）后上架
- 返回 `{ book, drift_id }`，漂流状态及持有者保存在 DriftRecord，不写入 Book

### POST /drift/records/{drift_id}/claim（申领）

- 仅 `idle` / `reserved` 可申领，否则 `code=1005`
- 不能申领自己上架的图书
- 成功后：仅更新对应实体册的 `DriftRecord` 状态、持有者和流转次数，不影响同一 Book 下的其他实体册

---

## 6. 前端调用示例

```js
// web-pc/src/api/activity.js
import request from './request'
export const listActivities = (params) => request.get('/activities', { params })
```

`request.js` 已统一处理：自动带 token、剥掉 `{code,message,data,trace_id}` 外壳、`code=1002` 自动跳登录、错误统一 `ElMessage` 提示。**前端业务代码里不要再出现 `res.data.data` 这种写法。**

---

## 7. 变更记录

| 版本 | 日期 | 变更人 | 内容 |
|---|---|---|---|
| v1.2 | 2026-10-07 | 项目组 | 对齐字段规范 v1.2，补充活动报名、身份边界、AI content 和 DriftRecord 单册路径 |
| v1.2 | 2026-10-07 | 万贝 | 补 0.1 节 HTTP 状态码与 code 对应表、活动公开/管理字段白名单；修正示例中的重复键 |
| v1.0 | 2026-10-06 | 万贝 | 首版接口定义，覆盖用户/活动/图书/AI/漂流 5 组端点 |
