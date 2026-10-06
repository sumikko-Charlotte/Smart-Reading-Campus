<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">活动管理</h2>
        <p class="page-desc">阅读推广活动全流程闭环管理：发起 → 招募 → 签到 → 公示 → 电子证书 → 成果展示</p>
      </div>
      <div>
        <el-button :icon="Refresh" :loading="loading" @click="fetchList">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="$router.push('/activities/create')">新建活动</el-button>
      </div>
    </div>

    <!-- 筛选区 -->
    <div class="filter-bar">
      <el-form :inline="true" :model="query" @submit.prevent>
        <el-form-item label="关键词">
          <el-input v-model="query.keyword" placeholder="活动标题 / 简介 / 地点" clearable style="width: 220px" @keyup.enter="onSearch" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" placeholder="全部状态" clearable style="width: 140px">
            <el-option v-for="s in ACTIVITY_STATUS" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="query.category" placeholder="全部分类" clearable style="width: 160px">
            <el-option v-for="c in ACTIVITY_CATEGORY" :key="c.value" :label="c.label" :value="c.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="onSearch">查询</el-button>
          <el-button @click="onReset">重置</el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 列表区 -->
    <div class="card-block">
      <el-table v-loading="loading" :data="list" stripe border style="width: 100%">
        <el-table-column label="活动" min-width="260">
          <template #default="{ row }">
            <div class="cell-title">
              <el-link type="primary" :underline="false" @click="goDetail(row)">{{ row.title }}</el-link>
              <el-tag v-if="row.need_certificate" size="small" type="warning" effect="plain">发证书</el-tag>
            </div>
            <div class="text-muted cell-sub">{{ row.subtitle || row.summary || '—' }}</div>
          </template>
        </el-table-column>

        <el-table-column label="分类" width="130">
          <template #default="{ row }">{{ labelOf(ACTIVITY_CATEGORY, row.category) }}</template>
        </el-table-column>

        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="typeOf(ACTIVITY_STATUS, row.status)" effect="light">{{ row.status_label || labelOf(ACTIVITY_STATUS, row.status) }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column label="活动时间" width="180">
          <template #default="{ row }">
            <div>{{ formatDateTime(row.start_at) }}</div>
            <div class="text-muted cell-sub">报名截止 {{ formatDateTime(row.signup_end_at) }}</div>
          </template>
        </el-table-column>

        <el-table-column label="报名 / 名额" width="170">
          <template #default="{ row }">
            <el-progress
              :percentage="percentOf(row)"
              :stroke-width="8"
              :status="row.capacity && row.signup_count >= row.capacity ? 'exception' : undefined"
            />
            <div class="text-muted cell-sub">{{ row.signup_count }} / {{ row.capacity || '不限' }}（签到 {{ row.checkin_count }}）</div>
          </template>
        </el-table-column>

        <el-table-column prop="location" label="地点" min-width="140" show-overflow-tooltip />

        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="goDetail(row)">详情</el-button>
            <el-button text type="primary" size="small" :disabled="row.status === 'finished'" @click="$router.push(`/activities/${row.activity_id}/edit`)">
              编辑
            </el-button>

            <el-dropdown @command="(cmd) => onStatusCommand(row, cmd)">
              <el-button text type="primary" size="small" :disabled="!nextStatuses(row).length">
                状态流转<el-icon><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item v-for="s in nextStatuses(row)" :key="s" :command="s">
                    流转为「{{ labelOf(ACTIVITY_STATUS, s) }}」
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
        </el-table-column>

        <template #empty>
          <el-empty description="暂无活动数据，点击右上角「新建活动」开始" />
        </template>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.page_size"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @size-change="fetchList"
          @current-change="fetchList"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowDown, Plus, Refresh, Search } from '@element-plus/icons-vue'
import { changeActivityStatus, listActivities } from '@/api/activity'
import { ACTIVITY_CATEGORY, ACTIVITY_STATUS, ACTIVITY_STATUS_FLOW, labelOf, typeOf } from '@/constants'
import { formatDateTime } from '@/utils/format'

const router = useRouter()
const loading = ref(false)
const list = ref([])
const total = ref(0)

const query = reactive({ page: 1, page_size: 10, keyword: '', status: '', category: '' })

/** 报名进度百分比（名额为 0 表示不限，按 10% 展示） */
function percentOf(row) {
  if (!row.capacity) return row.signup_count ? 10 : 0
  return Math.min(100, Math.round((row.signup_count / row.capacity) * 100))
}

/** 前端镜像状态机：只控制按钮可用性，真正校验在后端 */
function nextStatuses(row) {
  return ACTIVITY_STATUS_FLOW[row.status] ?? []
}

async function fetchList() {
  loading.value = true
  try {
    const data = await listActivities({ ...query, keyword: query.keyword || undefined, status: query.status || undefined, category: query.category || undefined })
    list.value = data.list
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function onSearch() {
  query.page = 1
  fetchList()
}

function onReset() {
  Object.assign(query, { page: 1, page_size: 10, keyword: '', status: '', category: '' })
  fetchList()
}

function goDetail(row) {
  router.push(`/activities/${row.activity_id}`)
}

async function onStatusCommand(row, target) {
  const label = labelOf(ACTIVITY_STATUS, target)
  const needReason = target === 'cancelled'
  try {
    const { value } = await ElMessageBox.prompt(
      needReason ? `将「${row.title}」流转为「${label}」，请填写取消原因（会记录到日志）：` : `确认将「${row.title}」流转为「${label}」吗？`,
      '状态流转确认',
      {
        type: 'warning',
        inputType: needReason ? 'textarea' : 'text',
        inputValue: '',
        inputPlaceholder: needReason ? '如：场地冲突，延期举行' : '可填写备注（选填）',
        confirmButtonText: '确认流转',
        cancelButtonText: '再想想'
      }
    )
    const data = await changeActivityStatus(row.activity_id, target, value || '')
    ElMessage.success(`已流转为「${data.status_label}」`)
    fetchList()
  } catch (err) {
    if (err !== 'cancel') {
      // 后端已通过统一响应体给出错误提示（如非法流转 1005）
    }
  }
}

onMounted(fetchList)
</script>

<style scoped>
.cell-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
}

.cell-sub {
  font-size: 12px;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
