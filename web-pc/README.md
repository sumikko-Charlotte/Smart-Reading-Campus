# 智阅校园 · PC 端管理平台（Vue 3 骨架）

## 快速开始

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # 产物在 dist/
```

前提：后端已在 `http://127.0.0.1:8000` 运行（`vite.config.js` 已把 `/api` 代理过去）。

演示账号（密码 `123456`）：`T2009`（图书馆老师）、`admin`（管理员）、`2025211995`（学生）。

## 技术选型

| 能力 | 选型 | 说明 |
|---|---|---|
| 构建 | Vite 6 | 秒级冷启动 |
| 框架 | Vue 3（`<script setup>`） | 组合式 API |
| UI | Element Plus（中文语言包） | 与申请书里声明的技术栈一致 |
| 状态 | Pinia | 目前只放登录态，后续扩展为业务 store |
| 路由 | Vue Router（hash 模式） | 含登录守卫与 `meta.roles` 角色过滤 |
| 请求 | axios 封装 | 统一剥壳、统一报错、401 自动跳登录 |

## 目录约定

```
src/
├── api/          request.js（唯一出网口）+ activity.js / modules.js / user.js
├── constants/    枚举字典（与后端 app/core/enums.py 严格对齐）
├── router/       路由表 + 守卫。新增页面记得配 meta.title / meta.roles
├── store/        Pinia
├── layouts/      BasicLayout（侧边菜单 + 顶栏 + 后端连通性标记）
├── utils/        format.js（日期等格式化）
└── views/        login / Dashboard / activity / ai / drift
```

## 给后续开发的几条约定

1. **不要在页面里直接 `axios.get`**，一律走 `src/api/*.js`；`request.js` 已经剥掉 `{code,message,data}` 外壳，业务层拿到的就是 `data`。
2. **枚举值不要手写字符串**，用 `constants/index.js` 的 `labelOf()` / `typeOf()`，否则改枚举会漏改。
3. **状态流转按钮的禁用逻辑**用 `ACTIVITY_STATUS_FLOW` 镜像，但真正校验在后端（非法流转返回 `code=1005`），前端不要自行"纠正"状态。
4. 流式对话统一走 `api/modules.js` 的 `chatStream()`，返回的 `AbortController` 可用于"停止生成"按钮。

## 本轮页面完成度

| 页面 | 路由 | 状态 |
|---|---|---|
| 登录 | `/login` | ✅ 可用（含演示账号一键填充） |
| 首页概览 | `/dashboard` | ✅ 可用（真实统计接口） |
| 活动列表 | `/activities` | ✅ 首版完成（筛选/分页/状态流转/报名进度） |
| 新建 / 编辑活动 | `/activities/create`、`/activities/:id/edit` | ✅ 可用（含 AI 推文生成） |
| 活动详情 | `/activities/:id` | ✅ 可用（含状态流转时间轴） |
| AI 智能推荐 | `/ai/recommend` | ✅ 骨架可用（接口已通） |
| AI 阅读助手 | `/ai/assistant` | ✅ 骨架可用（支持流式/非流式对比） |
| 图书漂流 | `/drift` | ✅ 骨架可用（漂流池 + 上架 + 申领 + 流转记录） |
