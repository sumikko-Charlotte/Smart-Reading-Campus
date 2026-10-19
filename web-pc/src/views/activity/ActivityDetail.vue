<template>
  <div v-loading="loading" class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">
          {{ detail.title || '活动详情' }}
          <el-tag v-if="detail.status" :type="typeOf(ACTIVITY_STATUS, detail.status)" effect="light" class="ml-8">
            {{ detail.status_label || labelOf(ACTIVITY_STATUS, detail.status) }}
          </el-tag>
        </h2>
        <p class="page-desc">{{ detail.subtitle || detail.summary || '—' }}</p>
      </div>
      <div>
        <el-button @click="$router.push('/activities')">返回列表</el-button>
        <template v-if="!store.isStaff">
          <el-button v-if="canSignupNow" type="primary" :loading="acting" @click="onSignup">报名参加</el-button>
          <el-button v-if="canCheckinNow" type="warning" :loading="acting" @click="onCheckin">签到</el-button>
          <el-button v-if="canCheckoutNow" type="success" :loading="acting" @click="onCheckout">签退</el-button>
          <el-button v-if="mySignup?.checked_out_at" type="primary" plain @click="$router.push('/certificates')">我的证书</el-button>
        </template>
        <el-button
          v-if="canOperate && !['finished', 'pending_review'].includes(detail.status)"
          type="primary"
          @click="$router.push(`/activities/${detail.activity_id}/edit`)"
        >编辑活动</el-button>
        <el-button
          v-if="canOperate && ['draft', 'rejected', 'cancelled'].includes(detail.status)"
          type="warning"
          @click="onSubmitReview"
        >提交审批</el-button>
        <el-button
          v-if="canWriteSummary"
          type="success"
          @click="$router.push(`/activities/${detail.activity_id}/summary`)"
        >{{ hasSummary ? '查看/编辑总结' : '撰写总结' }}</el-button>
      </div>
    </div>

    <el-row :gutter="16">
      <el-col :md="store.isStaff ? 16 : 24">
        <div class="card-block">
          <el-descriptions :column="2" border>
            <el-descriptions-item label="分类">{{ labelOf(ACTIVITY_CATEGORY, detail.category) }}</el-descriptions-item>
            <el-descriptions-item label="地点">{{ detail.location || '—' }}</el-descriptions-item>
            <el-descriptions-item label="活动时间">{{ formatRange(detail.start_at, detail.end_at) }}</el-descriptions-item>
            <el-descriptions-item label="报名时间">{{ formatRange(detail.signup_start_at, detail.signup_end_at) }}</el-descriptions-item>
            <el-descriptions-item label="主办方">{{ detail.organizer_name || '—' }}</el-descriptions-item>
            <el-descriptions-item label="名额">{{ detail.capacity || '不限' }}</el-descriptions-item>
            <el-descriptions-item label="电子证书">{{ detail.need_certificate ? '签到并签退后自动发放' : '不颁发' }}</el-descriptions-item>
            <el-descriptions-item label="活动等级">
              <el-tag v-if="detail.level && detail.level !== 'none'" :type="typeOf(ACTIVITY_LEVEL, detail.level)" effect="plain">
                {{ labelOf(ACTIVITY_LEVEL, detail.level) }}
              </el-tag>
              <span v-else class="text-muted">未定级</span>
            </el-descriptions-item>
            <el-descriptions-item label="发布时间">{{ formatDateTime(detail.published_at) }}</el-descriptions-item>
            <el-descriptions-item v-if="detail.review_comment" label="审批意见" :span="2">
              {{ detail.review_comment }}（{{ detail.reviewed_by_name }}）
            </el-descriptions-item>
            <el-descriptions-item label="创建时间">{{ formatDateTime(detail.created_at, true) }}</el-descriptions-item>
            <el-descriptions-item label="更新时间">{{ formatDateTime(detail.updated_at, true) }}</el-descriptions-item>
          </el-descriptions>

          <h3 class="section-title mt-16">活动详情</h3>
          <div class="detail-content">{{ detail.content || '暂无详情内容' }}</div>
        </div>

        <div v-if="detail.ai_copy" class="card-block mt-16">
          <h3 class="section-title">AI 生成的宣传推文</h3>
          <div class="detail-content">{{ detail.ai_copy }}</div>
        </div>
      </el-col>

      <el-col v-if="store.isStaff" :md="8">
        <div class="card-block">
          <h3 class="section-title">报名与签到</h3>
          <el-progress type="dashboard" :percentage="signupPercent" :width="140" class="dashboard-block" />
          <div class="metric-row">
            <span>已报名</span><strong>{{ detail.signup_count ?? 0 }} 人</strong>
          </div>
          <div class="metric-row">
            <span>已签到</span><strong>{{ detail.checkin_count ?? 0 }} 人</strong>
          </div>
          <div class="metric-row">
            <span>名额上限</span><strong>{{ detail.capacity || '不限' }}</strong>
          </div>
          <el-divider />
          <el-alert
            type="info"
            :closable="false"
            show-icon
            title="报名名单与扫码签到"
            description="报名与签到记录可在活动运营中查看。"
          />
        </div>

        <div class="card-block mt-16">
          <h3 class="section-title">状态流转</h3>
          <el-timeline>
            <el-timeline-item v-for="s in statusFlow" :key="s.value" :type="s.type" :hollow="s.value !== detail.status">
              <span :class="{ 'text-muted': s.value !== detail.status }">{{ s.label }}</span>
            </el-timeline-item>
          </el-timeline>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { checkinActivity, checkoutActivity, getActivity, signupActivity, submitActivity } from '@/api/activity'
import { getActivitySummary } from '@/api/summary'
import { useUserStore } from '@/store/user'
import { ACTIVITY_CATEGORY, ACTIVITY_LEVEL, ACTIVITY_STATUS, PERM, labelOf, typeOf } from '@/constants'
import { formatDateTime, formatRange } from '@/utils/format'

const route = useRoute()
const store = useUserStore()
const loading = ref(false)
const detail = ref({})
const hasSummary = ref(false)
const acting = ref(false)

const mySignup = computed(() => detail.value.my_signup || null)

const canSignupNow = computed(() => {
  if (!store.can(PERM.ACTIVITY_SIGNUP) || mySignup.value) return false
  if (detail.value.status !== 'published') return false
  const now = Date.now()
  const end = Date.parse(detail.value.signup_end_at || detail.value.start_at || '')
  return now < end && now < Date.parse(detail.value.start_at || '')
})

const canCheckinNow = computed(() => {
  const signup = mySignup.value
  if (!signup || signup.status !== 'approved' || signup.checked_in_at) return false
  return ['published', 'signup_closed', 'ongoing', 'finished'].includes(detail.value.status)
})

const canCheckoutNow = computed(() => {
  const signup = mySignup.value
  return Boolean(signup?.checked_in_at && !signup?.checked_out_at)
})

const canOperate = computed(() => {
  if (store.can(PERM.ACTIVITY_MANAGE_ALL)) return true
  return detail.value.organizer_id === store.profile?.user_id && store.can(PERM.ACTIVITY_CREATE)
})

const canWriteSummary = computed(() => {
  if (!['ongoing', 'finished'].includes(detail.value.status)) return false
  return store.can(PERM.ACTIVITY_SUMMARY) || (detail.value.organizer_id === store.profile?.user_id && store.can(PERM.ACTIVITY_CREATE))
})

const signupPercent = computed(() => {
  if (!detail.value.capacity) return detail.value.signup_count ? 10 : 0
  return Math.min(100, Math.round(((detail.value.signup_count || 0) / detail.value.capacity) * 100))
})

// 状态主干（不含驳回/取消旁支；审批在「活动审批」页操作）
const FLOW_ORDER = ['draft', 'pending_review', 'published', 'signup_closed', 'ongoing', 'finished']
const statusFlow = computed(() =>
  ACTIVITY_STATUS.filter((s) => FLOW_ORDER.includes(s.value))
    .sort((a, b) => FLOW_ORDER.indexOf(a.value) - FLOW_ORDER.indexOf(b.value))
    .map((s) => ({ ...s, type: s.value === detail.value.status ? typeOf(ACTIVITY_STATUS, s.value) : 'info' }))
)

async function onSubmitReview() {
  try {
    const { value } = await ElMessageBox.prompt('提交管理员审批，审批通过后将定级发布。可填写提交说明：', '提交审批', {
      type: 'info',
      inputPlaceholder: '选填'
    })
    await submitActivity(detail.value.activity_id, value || '')
    ElMessage.success('已提交审批')
    detail.value = await getActivity(route.params.id)
  } catch (err) {
    if (err !== 'cancel') {
      /* 统一提示 */
    }
  }
}

async function reload() {
  detail.value = await getActivity(route.params.id)
  try {
    await getActivitySummary(route.params.id)
    hasSummary.value = true
  } catch {
    hasSummary.value = false
  }
}

async function onSignup() {
  acting.value = true
  try {
    await signupActivity(detail.value.activity_id)
    ElMessage.success('报名成功')
    await reload()
  } finally {
    acting.value = false
  }
}

async function onCheckin() {
  acting.value = true
  try {
    await checkinActivity(detail.value.activity_id)
    ElMessage.success('签到成功')
    await reload()
  } finally {
    acting.value = false
  }
}

async function onCheckout() {
  acting.value = true
  try {
    const data = await checkoutActivity(detail.value.activity_id)
    if (data?.certificate) {
      ElMessage.success('签退成功，证书已发放，可在「我的证书」下载')
    } else {
      ElMessage.success('签退成功')
    }
    await reload()
  } finally {
    acting.value = false
  }
}

onMounted(async () => {
  loading.value = true
  try {
    await reload()
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.section-title {
  font-size: 15px;
  margin: 0 0 12px;
}

.detail-content {
  white-space: pre-wrap;
  line-height: 1.8;
  color: #374151;
  background: #fafbfe;
  border-radius: 8px;
  padding: 12px 14px;
}

.dashboard-block {
  display: block;
  margin: 0 auto 12px;
  text-align: center;
}

.metric-row {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px dashed #eef1f6;
}

.ml-8 {
  margin-left: 8px;
}
</style>
