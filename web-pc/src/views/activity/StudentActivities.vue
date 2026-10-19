<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">活动</h2>
        <p class="page-desc">浏览平台发布的阅读推广活动{{ store.can(PERM.ACTIVITY_SIGNUP) ? '，报名参加并积累第二课堂证书' : '' }}</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="refresh">刷新</el-button>
    </div>

    <div class="summary-grid">
      <div class="summary-item">
        <span class="summary-label">我参加的活动</span>
        <strong>{{ myTotal }}</strong>
      </div>
      <div class="summary-item">
        <span class="summary-label">已完成签到</span>
        <strong>{{ checkinCount }}</strong>
      </div>
      <div class="summary-item">
        <span class="summary-label">老师发布</span>
        <strong>{{ activityTotal }}</strong>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="activity-tabs">
      <el-tab-pane :label="store.can(PERM.ACTIVITY_SIGNUP) ? '可报名活动' : '活动通知'" name="announcements">
        <div class="list-heading">
          <span>活动通知</span>
          <span class="text-muted">按活动开始时间排序</span>
        </div>
        <el-table v-loading="loading" :data="activities" stripe style="width: 100%">
          <el-table-column label="活动" min-width="240">
            <template #default="{ row }">
              <div class="activity-title">{{ row.title }}</div>
              <div class="text-muted cell-sub">{{ row.subtitle || row.summary || '暂无简介' }}</div>
            </template>
          </el-table-column>
          <el-table-column label="分类" width="140">
            <template #default="{ row }">{{ labelOf(ACTIVITY_CATEGORY, row.category) }}</template>
          </el-table-column>
          <el-table-column label="活动时间" width="190">
            <template #default="{ row }">{{ formatDateTime(row.start_at) }}</template>
          </el-table-column>
          <el-table-column prop="location" label="地点" min-width="130" show-overflow-tooltip />
          <el-table-column label="报名情况" width="140">
            <template #default="{ row }">
              <el-tag :type="typeOf(ACTIVITY_STATUS, row.status)" effect="plain">
                {{ labelOf(ACTIVITY_STATUS, row.status) }}
              </el-tag>
              <div class="text-muted cell-sub">{{ row.signup_count }} 人已报名</div>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button text type="primary" @click="router.push(`/activities/${row.activity_id}`)">查看详情</el-button>
              <el-button
                v-if="canSignup(row)"
                type="primary"
                size="small"
                :loading="signingId === row.activity_id"
                @click="signup(row)"
              >报名</el-button>
              <el-tag v-else-if="myActivityIds.has(row.activity_id)" type="success" effect="plain" size="small">已报名</el-tag>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty description="暂无老师发布的活动" />
          </template>
        </el-table>
      </el-tab-pane>

      <el-tab-pane v-if="store.can(PERM.ACTIVITY_SIGNUP)" :label="`我的参与 (${myTotal})`" name="mine">
        <div class="list-heading">
          <span>参与记录</span>
          <span class="text-muted">签到状态以现场核验记录为准</span>
        </div>
        <el-table v-loading="loading" :data="myActivities" stripe style="width: 100%">
          <el-table-column label="活动" min-width="240">
            <template #default="{ row }">
              <el-link type="primary" :underline="false" @click="router.push(`/activities/${row.activity_id}`)">{{ row.title }}</el-link>
              <div class="text-muted cell-sub">报名于 {{ formatDateTime(row.signed_up_at) }}</div>
            </template>
          </el-table-column>
          <el-table-column label="活动时间" width="190">
            <template #default="{ row }">{{ formatDateTime(row.start_at) }}</template>
          </el-table-column>
          <el-table-column label="活动状态" width="130">
            <template #default="{ row }">
              <el-tag :type="typeOf(ACTIVITY_STATUS, row.status)" effect="plain">{{ labelOf(ACTIVITY_STATUS, row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="签到" width="150">
            <template #default="{ row }">
              <el-tag :type="row.checked_in_at ? 'success' : 'info'" effect="plain">
                {{ row.checked_in_at ? '已签到' : '未签到' }}
              </el-tag>
              <div v-if="row.checked_in_at" class="text-muted cell-sub">{{ formatDateTime(row.checked_in_at) }}</div>
            </template>
          </el-table-column>
          <el-table-column label="报名状态" width="130">
            <template #default="{ row }">{{ signupStatusLabel(row.signup_status) }}</template>
          </el-table-column>
          <template #empty>
            <el-empty description="还没有参加活动" />
          </template>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { listActivities, listMyActivities, signupActivity } from '@/api/activity'
import { useUserStore } from '@/store/user'
import { ACTIVITY_CATEGORY, ACTIVITY_STATUS, PERM, labelOf, typeOf } from '@/constants'
import { formatDateTime } from '@/utils/format'

const store = useUserStore()
const router = useRouter()
const loading = ref(false)
const signingId = ref('')
const activeTab = ref('announcements')
const activities = ref([])
const activityTotal = ref(0)
const myActivities = ref([])
const myTotal = ref(0)
const checkinCount = ref(0)
const myActivityIds = computed(() => new Set(myActivities.value.map((item) => item.activity_id)))

function canSignup(activity) {
  if (!store.can(PERM.ACTIVITY_SIGNUP)) return false
  if (activity.status !== 'published' || myActivityIds.value.has(activity.activity_id)) return false
  const now = Date.now()
  const signupStart = activity.signup_start_at ? Date.parse(activity.signup_start_at) : 0
  const signupEnd = Date.parse(activity.signup_end_at || activity.start_at)
  return now >= signupStart && now < signupEnd && now < Date.parse(activity.start_at)
    && (!activity.capacity || activity.signup_count < activity.capacity)
}

function signupStatusLabel(status) {
  return ({ approved: '报名成功', pending: '待确认', cancelled: '已取消', rejected: '未通过' })[status] || status || '—'
}

async function refresh() {
  loading.value = true
  try {
    const requests = [listActivities({ page: 1, page_size: 100, order_by: 'start_at', order: 'asc' })]
    if (store.can(PERM.ACTIVITY_SIGNUP)) requests.push(listMyActivities({ page: 1, page_size: 100 }))
    const [activityData, myData] = await Promise.all(requests)
    activities.value = activityData.list
    activityTotal.value = activityData.total
    myActivities.value = myData?.list ?? []
    myTotal.value = myData?.total ?? 0
    checkinCount.value = myData?.checkin_count ?? 0
  } finally {
    loading.value = false
  }
}

async function signup(activity) {
  signingId.value = activity.activity_id
  try {
    await signupActivity(activity.activity_id)
    ElMessage.success('报名成功')
    await refresh()
  } finally {
    signingId.value = ''
  }
}

onMounted(refresh)
</script>

<style scoped>
.summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1px;
  background: #e8ebf2;
  border: 1px solid #e8ebf2;
  margin-bottom: 16px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px 20px;
  background: #fff;
}

.summary-label,
.text-muted {
  color: #7b8190;
}

.summary-item strong {
  color: #1f2430;
  font-size: 24px;
  font-weight: 600;
}

.activity-tabs {
  background: #fff;
  padding: 0 16px 16px;
}

.list-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0 12px;
  font-weight: 600;
}

.activity-title {
  font-weight: 500;
}

.cell-sub {
  font-size: 12px;
  margin-top: 4px;
}

@media (max-width: 640px) {
  .summary-grid {
    grid-template-columns: 1fr;
  }
}
</style>
