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
        <el-button type="primary" :disabled="detail.status === 'finished'" @click="$router.push(`/activities/${detail.activity_id}/edit`)">
          编辑活动
        </el-button>
      </div>
    </div>

    <el-row :gutter="16">
      <el-col :md="16">
        <div class="card-block">
          <el-descriptions :column="2" border>
            <el-descriptions-item label="分类">{{ labelOf(ACTIVITY_CATEGORY, detail.category) }}</el-descriptions-item>
            <el-descriptions-item label="地点">{{ detail.location || '—' }}</el-descriptions-item>
            <el-descriptions-item label="活动时间">{{ formatRange(detail.start_at, detail.end_at) }}</el-descriptions-item>
            <el-descriptions-item label="报名时间">{{ formatRange(detail.signup_start_at, detail.signup_end_at) }}</el-descriptions-item>
            <el-descriptions-item label="主办方">{{ detail.organizer_name || '—' }}</el-descriptions-item>
            <el-descriptions-item label="名额">{{ detail.capacity || '不限' }}</el-descriptions-item>
            <el-descriptions-item label="电子证书">{{ detail.need_certificate ? '自动颁发' : '不颁发' }}</el-descriptions-item>
            <el-descriptions-item label="发布时间">{{ formatDateTime(detail.published_at) }}</el-descriptions-item>
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

      <el-col :md="8">
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
            description="报名/签到明细由 ActivitySignup 承载，第 2 轮实现名单导出与扫码签到看板。"
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
import { getActivity } from '@/api/activity'
import { ACTIVITY_CATEGORY, ACTIVITY_STATUS, labelOf, typeOf } from '@/constants'
import { formatDateTime, formatRange } from '@/utils/format'

const route = useRoute()
const loading = ref(false)
const detail = ref({})

const signupPercent = computed(() => {
  if (!detail.value.capacity) return detail.value.signup_count ? 10 : 0
  return Math.min(100, Math.round(((detail.value.signup_count || 0) / detail.value.capacity) * 100))
})

// 状态机主干（不含 cancelled，取消是旁支）
const FLOW_ORDER = ['draft', 'published', 'signup_closed', 'ongoing', 'finished']
const statusFlow = computed(() =>
  ACTIVITY_STATUS.filter((s) => FLOW_ORDER.includes(s.value))
    .sort((a, b) => FLOW_ORDER.indexOf(a.value) - FLOW_ORDER.indexOf(b.value))
    .map((s) => ({ ...s, type: s.value === detail.value.status ? typeOf(ACTIVITY_STATUS, s.value) : 'info' }))
)

onMounted(async () => {
  loading.value = true
  try {
    detail.value = await getActivity(route.params.id)
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
