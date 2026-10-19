<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">
          消息中心
          <el-tag v-if="unread" type="danger" effect="plain" size="small" class="title-badge">
            {{ unread }} 条未读
          </el-tag>
        </h2>
        <p class="page-desc">审批结果、权限变动、活动总结与证书颁发都会送到这里。</p>
      </div>
      <div class="header-actions">
        <el-button :icon="Refresh" :loading="loading" @click="fetchList()">刷新</el-button>
        <el-button type="primary" plain :icon="Check" :disabled="!unread" @click="readAll">全部已读</el-button>
      </div>
    </div>

    <div class="filter-bar">
      <el-radio-group v-model="query.only_unread" @change="onFilterChange">
        <el-radio-button :value="false">全部（{{ totalAll }}）</el-radio-button>
        <el-radio-button :value="true">未读（{{ unread }}）</el-radio-button>
      </el-radio-group>
      <el-select v-model="query.type" placeholder="全部类型" clearable class="type-select" @change="onFilterChange">
        <el-option v-for="item in NOTIFICATION_TYPE" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <span class="text-muted tip">每 15 秒自动刷新</span>
    </div>

    <div v-loading="loading" class="msg-list">
      <div
        v-for="row in list"
        :key="row.notification_id"
        class="msg-item"
        :class="{ unread: !row.is_read }"
        @click="openMessage(row)"
      >
        <div class="msg-dot" :class="{ on: !row.is_read }" />
        <div class="msg-body">
          <div class="msg-head">
            <el-tag :type="typeOf(NOTIFICATION_TYPE, row.type)" size="small" effect="plain">
              {{ labelOf(NOTIFICATION_TYPE, row.type) }}
            </el-tag>
            <span class="msg-title">{{ row.title }}</span>
            <span v-if="!row.is_read" class="unread-text">未读</span>
          </div>
          <div v-if="row.content" class="msg-content">{{ row.content }}</div>
          <div class="msg-meta">
            <span>{{ formatDateTime(row.created_at, true) }}</span>
            <span class="dot">·</span>
            <span>{{ row.scope === 'user' ? '发给我' : `角色广播：${(row.target_roles || []).map((r) => labelOf(USER_ROLE, r)).join('、')}` }}</span>
            <span v-if="row.created_by_name" class="dot">·</span>
            <span v-if="row.created_by_name">来自 {{ row.created_by_name }}</span>
          </div>
        </div>
        <div class="msg-actions" @click.stop>
          <el-button v-if="!row.is_read" text type="primary" size="small" @click="markRead(row)">标为已读</el-button>
          <el-button v-if="targetOf(row)" text size="small" @click="openMessage(row, true)">查看</el-button>
        </div>
      </div>

      <el-empty v-if="!loading && !list.length" :description="query.only_unread ? '没有未读消息' : '暂无消息'" />
    </div>

    <div class="pager">
      <el-pagination
        v-model:current-page="query.page"
        v-model:page-size="query.page_size"
        :total="total"
        layout="total, prev, pager, next"
        background
        @current-change="fetchList()"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, onActivated, onDeactivated, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Check, Refresh } from '@element-plus/icons-vue'
import { listNotifications, markAllNotificationsRead, markNotificationRead } from '@/api/notification'
import { useUserStore } from '@/store/user'
import { NOTIFICATION_TYPE, USER_ROLE, labelOf, typeOf } from '@/constants'
import { formatDateTime } from '@/utils/format'

const router = useRouter()
const store = useUserStore()
const loading = ref(false)
const list = ref([])
const total = ref(0)
const totalAll = ref(0)
const unread = computed(() => store.unread)
const query = reactive({ page: 1, page_size: 10, only_unread: false, type: '' })
let timer = null

async function fetchList(silent = false) {
  if (!silent) loading.value = true
  try {
    const data = await listNotifications({
      page: query.page,
      page_size: query.page_size,
      only_unread: query.only_unread,
      type: query.type || undefined
    })
    list.value = data.list
    total.value = data.total
    // 未读数以服务端为准：一次请求同时更新列表和顶栏红点
    store.setUnread(data.unread)
    if (!query.only_unread && !query.type) totalAll.value = data.total
  } finally {
    loading.value = false
  }
}

function onFilterChange() {
  query.page = 1
  fetchList()
}

/** 目标页面：让用户点消息能直接到处理它的地方 */
function targetOf(row) {
  switch (row.ref_type) {
    case 'activity_summary':
      return '/activities'
    case 'activity':
      return row.type === 'activity_review' ? '/activities/review' : `/activities/${row.ref_id}`
    case 'permission_request':
      return store.isSuperAdmin ? '/system/users?tab=requests' : '/profile?tab=requests'
    case 'certificate':
      return store.role === 'student' ? '/certificates' : '/activities'
    case 'user':
      return '/profile'
    default:
      return ''
  }
}

async function markRead(row, quiet = false) {
  if (row.is_read) return
  const data = await markNotificationRead(row.notification_id)
  row.is_read = true
  store.setUnread(data.unread)
  if (!quiet) ElMessage.success('已标记为已读')
}

/** 点整行只标记已读；点「查看」才跳转，避免误触 */
async function openMessage(row, jump = false) {
  await markRead(row, true)
  if (!jump) return
  const target = targetOf(row)
  if (target) router.push(target)
}

async function readAll() {
  const data = await markAllNotificationsRead()
  store.setUnread(data.unread)
  ElMessage.success(data.changed ? `已把 ${data.changed} 条消息标为已读` : '没有未读消息')
  await fetchList(true)
}

function startTimer() {
  stopTimer()
  timer = setInterval(() => fetchList(true), 15000)
}

function stopTimer() {
  if (timer) clearInterval(timer)
  timer = null
}

onMounted(fetchList)
onActivated(() => {
  fetchList(true)
  startTimer()
})
onDeactivated(stopTimer)
onUnmounted(stopTimer)
</script>

<style scoped>
.header-actions {
  display: flex;
  gap: 8px;
}

.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.type-select {
  width: 170px;
}

.tip {
  font-size: 12px;
}

.title-badge {
  margin-left: 8px;
  vertical-align: middle;
}

.msg-list {
  min-height: 200px;
  background: #fff;
  border: 1px solid #e8ebf2;
  border-radius: 10px;
  overflow: hidden;
}

.msg-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid #f1f3f8;
  cursor: pointer;
  transition: background 0.15s;
}

.msg-item:last-child {
  border-bottom: none;
}

.msg-item:hover {
  background: #f8faff;
}

.msg-item.unread {
  background: #f4f7ff;
}

.msg-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 8px;
  flex: none;
  background: transparent;
}

.msg-dot.on {
  background: #f56c6c;
}

.msg-body {
  flex: 1;
  min-width: 0;
}

.msg-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.msg-title {
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.msg-item.unread .msg-title {
  font-weight: 600;
}

.unread-text {
  font-size: 12px;
  color: #f56c6c;
}

.msg-content {
  margin-top: 6px;
  color: var(--el-text-color-regular);
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
}

.msg-meta {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.msg-actions {
  flex: none;
  display: flex;
  align-items: center;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
