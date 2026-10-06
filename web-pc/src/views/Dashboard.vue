<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">首页概览</h2>
        <p class="page-desc">数据来自 <code>GET /api/v1/activities/stats</code> 与 <code>GET /api/v1/drift/stats</code>，第 1 轮为真实接口骨架数据。</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="loadAll">刷新数据</el-button>
    </div>

    <el-row :gutter="16">
      <el-col v-for="card in cards" :key="card.label" :xs="12" :sm="8" :md="4">
        <div class="stat-card">
          <div class="stat-label">{{ card.label }}</div>
          <div class="stat-value" :style="{ color: card.color }">{{ card.value }}</div>
          <div class="stat-extra text-muted">{{ card.extra }}</div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="mt-16">
      <el-col :md="24">
        <div class="card-block">
          <div class="flex-between">
            <h3 class="section-title">活动状态分布</h3>
            <el-button text type="primary" @click="$router.push('/activities')">进入活动管理 →</el-button>
          </div>
          <div class="status-list">
            <div v-for="item in statusRows" :key="item.value" class="status-row">
              <span class="status-name">
                <el-tag size="small" :type="item.type" effect="plain">{{ item.label }}</el-tag>
              </span>
              <el-progress :percentage="item.percent" :stroke-width="10" :show-text="false" class="status-bar" />
              <span class="status-count">{{ item.count }}</span>
            </div>
          </div>
        </div>
      </el-col>

    </el-row>

    <div class="card-block mt-16">
      <h3 class="section-title">快速入口</h3>
      <div class="quick-entries">
        <el-card v-for="q in quickEntries" :key="q.path" shadow="hover" class="quick-card" @click="$router.push(q.path)">
          <el-icon :size="26" color="#2f54eb"><component :is="q.icon" /></el-icon>
          <div class="quick-title">{{ q.title }}</div>
          <div class="text-muted quick-desc">{{ q.desc }}</div>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { activityStats } from '@/api/activity'
import { driftStats } from '@/api/modules'
import { ACTIVITY_STATUS, typeOf, labelOf } from '@/constants'

const loading = ref(false)
const actData = ref({ total: 0, by_status: {}, signup_total: 0, checkin_total: 0 })
const driftData = ref({ total: 0, by_status: {} })

const cards = computed(() => [
  { label: '活动总数', value: actData.value.total, extra: '全部状态', color: '#2f54eb' },
  { label: '报名中活动', value: actData.value.by_status?.published ?? 0, extra: labelOf(ACTIVITY_STATUS, 'published'), color: '#22a06b' },
  { label: '累计报名', value: actData.value.signup_total ?? 0, extra: '人次', color: '#d97706' },
  { label: '累计签到', value: actData.value.checkin_total ?? 0, extra: '人次', color: '#0ea5e9' },
  { label: '漂流图书', value: driftData.value.total ?? 0, extra: '册', color: '#7c3aed' },
  { label: '待领取漂流书', value: driftData.value.by_status?.idle ?? 0, extra: '册', color: '#db2777' }
])

const statusRows = computed(() => {
  const total = actData.value.total || 1
  return ACTIVITY_STATUS.map((s) => {
    const count = actData.value.by_status?.[s.value] ?? 0
    return { ...s, type: typeOf(ACTIVITY_STATUS, s.value), count, percent: Math.round((count / total) * 100) }
  })
})

const quickEntries = [
  { path: '/activities', title: '活动管理', desc: '发起 / 招募 / 公示全流程', icon: 'Calendar' },
  { path: '/ai/recommend', title: 'AI 智能推荐', desc: '借阅榜单 + 个性化荐书', icon: 'MagicStick' },
  { path: '/ai/assistant', title: 'AI 阅读助手', desc: '多轮伴读与书目解读', icon: 'ChatDotRound' },
  { path: '/drift', title: '图书漂流', desc: '上架 / 申领 / 流转追踪', icon: 'Van' }
]

async function loadAll() {
  loading.value = true
  try {
    const [a, d] = await Promise.all([activityStats(), driftStats()])
    actData.value = a
    driftData.value = d
  } finally {
    loading.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.stat-card {
  background: #fff;
  border-radius: var(--sr-card-radius);
  padding: 16px;
  margin-bottom: 12px;
}

.stat-label {
  color: #6b7280;
  font-size: 13px;
}

.stat-value {
  font-size: 26px;
  font-weight: 600;
  line-height: 1.4;
}

.stat-extra {
  font-size: 12px;
}

.section-title {
  font-size: 15px;
  margin: 0 0 10px;
}

.status-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 6px;
}

.status-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-name {
  width: 92px;
}

.status-bar {
  flex: 1;
}

.status-count {
  width: 42px;
  text-align: right;
  font-weight: 600;
}

.quick-entries {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px;
}

.quick-card {
  cursor: pointer;
  text-align: center;
}

.quick-title {
  margin-top: 8px;
  font-weight: 600;
}

.quick-desc {
  font-size: 12px;
}
</style>
