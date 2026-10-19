<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">活动</h2>
      </div>
      <div class="header-actions">
        <el-button :icon="Refresh" :loading="loading" @click="load()">刷新</el-button>
        <el-button v-if="canCreate" type="primary" :icon="Plus" @click="router.push('/activities/create')">
          申办活动
        </el-button>
      </div>
    </div>

    <el-tabs v-model="scope" class="feed-tabs" @tab-change="onScopeChange">
      <el-tab-pane label="全部推送" name="all" />
      <el-tab-pane v-if="canJoin" label="我参加的" name="joined" />
      <el-tab-pane v-if="canMine" label="我发布的" name="mine" />
    </el-tabs>

    <div v-loading="loading" class="feed-list">
      <el-empty v-if="!items.length && !loading" :description="emptyText" />

      <el-card
        v-for="item in items"
        :key="`${item.item_type}-${item.item_id}`"
        class="feed-card"
        shadow="hover"
      >
        <div class="feed-top">
          <el-tag v-if="item.item_type === 'summary'" type="success" effect="plain">活动总结</el-tag>
          <el-tag v-else :type="typeOf(ACTIVITY_STATUS, item.status)" effect="plain">
            {{ labelOf(ACTIVITY_STATUS, item.status) }}
          </el-tag>
          <span v-if="item.is_joined" class="feed-flag">我参加的</span>
          <span v-if="item.is_mine" class="feed-flag">我发布的</span>
          <span class="feed-time">{{ formatDateTime(item.published_at) }}</span>
        </div>

        <h3 class="feed-title" @click="openItem(item)">{{ item.title }}</h3>
        <p class="feed-excerpt">{{ item.excerpt || '—' }}</p>

        <div v-if="item.item_type === 'activity'" class="feed-meta">
          <span>{{ formatDateTime(item.start_at) }}</span>
          <span v-if="item.location">{{ item.location }}</span>
          <span>{{ item.signup_count }} 人报名{{ item.capacity ? ` / ${item.capacity}` : '' }}</span>
        </div>
        <div v-else class="feed-meta">
          <span>活动：{{ item.activity_title }}</span>
          <span>{{ item.author_name }} 发布</span>
          <span>{{ item.view_count }} 次阅读</span>
        </div>

        <div v-if="item.images?.length" class="feed-images">
          <el-image
            v-for="(img, index) in item.images.slice(0, 3)"
            :key="index"
            :src="img"
            :preview-src-list="item.images"
            :initial-index="index"
            fit="cover"
            class="feed-image"
          />
        </div>

        <div class="feed-actions">
          <el-button v-if="item.item_type === 'activity'" text type="primary" @click="router.push(`/activities/${item.activity_id}`)">
            查看详情
          </el-button>
          <el-button v-else text type="primary" @click="openSummary(item)">阅读全文</el-button>

          <el-button
            v-if="canSignup(item)"
            type="primary"
            size="small"
            :loading="signingId === item.activity_id"
            @click="signup(item)"
          >报名</el-button>

          <el-tag
            v-if="checkinHint(item)"
            type="warning"
            effect="plain"
            class="feed-checkin"
            @click="router.push(`/activities/${item.activity_id}`)"
          >{{ checkinHint(item) }}</el-tag>

          <el-tag v-if="item.item_type === 'activity' && item.is_joined" type="success" effect="plain" size="small">
            已报名
          </el-tag>
        </div>
      </el-card>
    </div>

    <div class="pager">
      <el-pagination
        v-model:current-page="query.page"
        :page-size="query.page_size"
        :total="total"
        layout="total, prev, pager, next"
        background
        @current-change="load()"
      />
    </div>

    <el-dialog v-model="summaryVisible" :title="summary?.title || '活动总结'" width="680px">
      <div class="text-muted summary-sub">
        {{ summary?.activity_title }} · {{ summary?.author_name }} · {{ formatDateTime(summary?.published_at) }}
      </div>
      <div class="summary-content">{{ summary?.content }}</div>
      <div v-if="summary?.images?.length" class="summary-images">
        <el-image
          v-for="(img, index) in summary.images"
          :key="index"
          :src="img"
          :preview-src-list="summary.images"
          :initial-index="index"
          fit="cover"
          class="summary-image"
        />
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import { getActivityFeed, signupActivity } from '@/api/activity'
import { getActivitySummary } from '@/api/summary'
import { useUserStore } from '@/store/user'
import { ACTIVITY_STATUS, PERM, labelOf, typeOf } from '@/constants'
import { formatDateTime } from '@/utils/format'

const store = useUserStore()
const router = useRouter()

const loading = ref(false)
const signingId = ref('')
const scope = ref('all')
const items = ref([])
const total = ref(0)
const query = reactive({ page: 1, page_size: 10 })

const summaryVisible = ref(false)
const summary = ref(null)

const canJoin = computed(() => store.can(PERM.ACTIVITY_SIGNUP))
const canCreate = computed(() => store.can(PERM.ACTIVITY_CREATE))
/** 学生与管理员都能看到自己发布的活动与总结；访客没有发布能力 */
const canMine = computed(() => store.isLoggedIn && !store.isVisitor)

const emptyText = computed(() => {
  if (scope.value === 'joined') return '还没有参加活动'
  if (scope.value === 'mine') return canCreate.value ? '还没有发布活动' : '还没有发布活动，开通活动申办权限后可在这里管理'
  return '暂无活动推送'
})

function canSignup(item) {
  if (item.item_type !== 'activity' || !canJoin.value) return false
  if (item.status !== 'published' || item.is_joined) return false
  const now = Date.now()
  const start = item.signup_start_at ? Date.parse(item.signup_start_at) : 0
  const end = Date.parse(item.signup_end_at || item.start_at)
  return now >= start && now < end && now < Date.parse(item.start_at)
    && (!item.capacity || item.signup_count < item.capacity)
}

function checkinHint(item) {
  if (item.item_type !== 'activity' || !item.is_joined) return ''
  const signup = item.my_signup || {}
  if (signup.checked_out_at) return ''
  if (signup.checked_in_at) return '去签退'
  if (!['published', 'signup_closed', 'ongoing', 'finished'].includes(item.status)) return ''
  const start = Date.parse(item.start_at)
  if (Number.isFinite(start) && Date.now() < start - 30 * 60 * 1000) return ''
  return '去签到'
}

function onScopeChange() {
  query.page = 1
  load()
}

async function load(silent = false) {
  if (!silent) loading.value = true
  try {
    const data = await getActivityFeed({ ...query, scope: scope.value })
    items.value = data.list
    total.value = data.total
  } catch {
    if (!silent) {
      items.value = []
      total.value = 0
    }
  } finally {
    if (!silent) loading.value = false
  }
}

async function signup(item) {
  signingId.value = item.activity_id
  try {
    await signupActivity(item.activity_id)
    ElMessage.success('报名成功')
    await load()
  } finally {
    signingId.value = ''
  }
}

function openItem(item) {
  router.push(`/activities/${item.activity_id}`)
}

async function openSummary(item) {
  summary.value = item
  summaryVisible.value = true
  try {
    const data = await getActivitySummary(item.activity_id)
    summary.value = data
  } catch {
    /* 详情拉取失败时保留列表里的摘录 */
  }
}

let refreshTimer = null

onMounted(() => {
  load()
  // 静默轮询：新活动发布、总结推送后无需手动刷新即可出现在流里
  refreshTimer = setInterval(() => load(true), 30000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<style scoped>
.feed-tabs {
  background: #fff;
  padding: 0 16px;
  border-radius: 10px;
  margin-bottom: 14px;
}

.feed-list {
  min-height: 220px;
}

.feed-card {
  margin-bottom: 12px;
}

.feed-top {
  display: flex;
  align-items: center;
  gap: 10px;
}

.feed-flag {
  font-size: 12px;
  color: var(--sr-primary);
  background: rgba(47, 84, 235, 0.08);
  border-radius: 4px;
  padding: 1px 6px;
}

.feed-time {
  margin-left: auto;
  font-size: 12px;
  color: #9aa1af;
}

.feed-title {
  margin: 10px 0 6px;
  font-size: 17px;
  cursor: pointer;
}

.feed-title:hover {
  color: var(--sr-primary);
}

.feed-excerpt {
  margin: 0;
  color: #4b5563;
  line-height: 1.7;
  white-space: pre-wrap;
}

.feed-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 10px;
  font-size: 12px;
  color: #7b8190;
}

.feed-images {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

.feed-image {
  width: 108px;
  height: 72px;
  border-radius: 6px;
}

.feed-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
}

.feed-checkin {
  cursor: pointer;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}

.summary-sub {
  font-size: 13px;
  margin-bottom: 12px;
}

.summary-content {
  white-space: pre-wrap;
  line-height: 1.9;
  color: #374151;
}

.summary-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.summary-image {
  width: 140px;
  height: 92px;
  border-radius: 6px;
}
</style>
