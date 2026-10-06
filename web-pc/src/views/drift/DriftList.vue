<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">图书漂流</h2>
        <p class="page-desc">
          线上线下联动的闲置图书流转：扫码上架 → 待领取 → 申领交接 → 流转追踪。
          小程序端负责扫码，PC 端负责管理与看板。
        </p>
      </div>
      <div>
        <el-button :icon="Refresh" @click="loadAll">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="dialogVisible = true">扫码上架</el-button>
      </div>
    </div>

    <el-row :gutter="16" class="mb-12">
      <el-col v-for="s in statCards" :key="s.label" :xs="12" :sm="6">
        <div class="stat-card">
          <div class="stat-label">{{ s.label }}</div>
          <div class="stat-value" :style="{ color: s.color }">{{ s.value }}</div>
        </div>
      </el-col>
    </el-row>

    <div class="card-block">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="漂流池" name="pool">
          <el-form :inline="true" class="inline-filter">
            <el-form-item label="关键词">
              <el-input v-model="poolQuery.keyword" placeholder="书名 / 作者 / ISBN" clearable style="width: 220px" @keyup.enter="fetchPool" />
            </el-form-item>
            <el-form-item label="状态">
              <el-select v-model="poolQuery.drift_status" placeholder="全部" clearable style="width: 140px">
                <el-option v-for="s in DRIFT_STATUS" :key="s.value" :label="s.label" :value="s.value" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :icon="Search" @click="fetchPool">查询</el-button>
            </el-form-item>
          </el-form>

          <el-table v-loading="loading" :data="pool" stripe border>
            <el-table-column label="图书" min-width="220">
              <template #default="{ row }">
                <div class="cell-title">{{ row.title }}</div>
                <div class="text-muted cell-sub">ISBN {{ row.isbn }} · {{ row.author || '待补充作者' }}</div>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="110" align="center">
              <template #default="{ row }">
                <el-tag :type="typeOf(DRIFT_STATUS, row.drift_status)" effect="light">{{ labelOf(DRIFT_STATUS, row.drift_status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="drift_location" label="交接地点" min-width="150" show-overflow-tooltip />
            <el-table-column prop="drift_count" label="流转次数" width="100" align="center" />
            <el-table-column prop="current_holder_id" label="当前持有者" width="150" show-overflow-tooltip />
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button
                  text
                  type="primary"
                  size="small"
                  :disabled="!['idle', 'reserved'].includes(row.drift_status)"
                  @click="onClaim(row)"
                >
                  申领
                </el-button>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty description="漂流池暂无图书，点击右上角「扫码上架」" />
            </template>
          </el-table>

          <div class="pager">
            <el-pagination
              v-model:current-page="poolQuery.page"
              v-model:page-size="poolQuery.page_size"
              :total="poolTotal"
              layout="total, prev, pager, next"
              background
              @current-change="fetchPool"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane label="流转记录" name="records">
          <el-table v-loading="recordsLoading" :data="records" stripe border>
            <el-table-column prop="drift_id" label="漂流记录 ID" width="180" />
            <el-table-column prop="book_id" label="图书 ID" width="180" />
            <el-table-column prop="from_user_id" label="上一持有者" min-width="150">
              <template #default="{ row }">{{ row.from_user_id || '首次上架' }}</template>
            </el-table-column>
            <el-table-column prop="holder_id" label="当前持有者" min-width="150" />
            <el-table-column label="状态" width="110" align="center">
              <template #default="{ row }">
                <el-tag :type="typeOf(DRIFT_STATUS, row.status)" effect="light">{{ labelOf(DRIFT_STATUS, row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="location" label="地点" min-width="140" />
            <el-table-column label="发生时间" width="170">
              <template #default="{ row }">{{ formatDateTime(row.created_at, true) }}</template>
            </el-table-column>
            <template #empty>
              <el-empty description="暂无流转记录" />
            </template>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>

    <!-- 扫码上架 -->
    <el-dialog v-model="dialogVisible" title="扫码上架漂流书" width="520px">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="小程序端扫码后同样调用 POST /api/v1/drift/books"
        description="PC 端此处为手工补录入口：填入 ISBN 与交接地点即可上架。"
        class="mb-12"
      />
      <el-form ref="shelfFormRef" :model="shelfForm" :rules="shelfRules" label-width="90px">
        <el-form-item label="ISBN" prop="isbn">
          <el-input v-model="shelfForm.isbn" placeholder="扫描或输入 ISBN（可含连字符）" />
        </el-form-item>
        <el-form-item label="交接地点" prop="location">
          <el-input v-model="shelfForm.location" placeholder="如：图书馆一层大厅" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="shelfForm.note" type="textarea" :rows="2" placeholder="图书成色、联系方式等" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="shelfSubmitting" @click="onShelfSubmit">确认上架</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh, Search } from '@element-plus/icons-vue'
import { claimDriftBook, driftStats, listDriftBooks, listDriftRecords, putBookOnShelf } from '@/api/modules'
import { DRIFT_STATUS, labelOf, typeOf } from '@/constants'
import { formatDateTime } from '@/utils/format'

const activeTab = ref('pool')
const loading = ref(false)
const recordsLoading = ref(false)
const pool = ref([])
const records = ref([])
const poolTotal = ref(0)
const stats = ref({ total: 0, by_status: {} })

const poolQuery = reactive({ page: 1, page_size: 10, keyword: '', drift_status: '' })

const dialogVisible = ref(false)
const shelfSubmitting = ref(false)
const shelfFormRef = ref()
const shelfForm = reactive({ isbn: '', location: '', note: '' })
const shelfRules = {
  isbn: [{ required: true, message: '请输入 ISBN', trigger: 'blur' }],
  location: [{ required: true, message: '请填写交接地点', trigger: 'blur' }]
}

const statCards = computed(() => [
  { label: '漂流图书总数', value: stats.value.total ?? 0, color: '#2f54eb' },
  { label: '待领取', value: stats.value.by_status?.idle ?? 0, color: '#22a06b' },
  { label: '流转中', value: stats.value.by_status?.in_transit ?? 0, color: '#0ea5e9' },
  { label: '已领用', value: stats.value.by_status?.claimed ?? 0, color: '#7c3aed' }
])

async function fetchPool() {
  loading.value = true
  try {
    const data = await listDriftBooks({
      ...poolQuery,
      keyword: poolQuery.keyword || undefined,
      drift_status: poolQuery.drift_status || undefined
    })
    pool.value = data.list
    poolTotal.value = data.total
  } finally {
    loading.value = false
  }
}

async function fetchRecords() {
  recordsLoading.value = true
  try {
    const data = await listDriftRecords({ page: 1, page_size: 20 })
    records.value = data.list
  } finally {
    recordsLoading.value = false
  }
}

async function loadAll() {
  await Promise.all([fetchPool(), fetchRecords(), driftStats().then((d) => (stats.value = d))])
}

async function onShelfSubmit() {
  const valid = await shelfFormRef.value.validate().catch(() => false)
  if (!valid) return
  shelfSubmitting.value = true
  try {
    const data = await putBookOnShelf({ ...shelfForm })
    ElMessage.success(`《${data.book.title}》已上架，等待领取`)
    dialogVisible.value = false
    Object.assign(shelfForm, { isbn: '', location: '', note: '' })
    loadAll()
  } finally {
    shelfSubmitting.value = false
  }
}

async function onClaim(row) {
  await ElMessageBox.confirm(`确认申领《${row.title}》？确认后将生成一条流转记录。`, '申领确认', { type: 'warning' })
  await claimDriftBook(row.book_id)
  ElMessage.success('申领成功，请与上一持有者线下交接')
  loadAll()
}

watch(activeTab, (v) => {
  if (v === 'records') fetchRecords()
})

onMounted(loadAll)
</script>

<style scoped>
.mb-12 {
  margin-bottom: 12px;
}

.stat-card {
  background: #fff;
  border-radius: var(--sr-card-radius);
  padding: 14px 16px;
  margin-bottom: 12px;
}

.stat-label {
  color: #6b7280;
  font-size: 13px;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
}

.inline-filter {
  margin-bottom: 4px;
}

.cell-title {
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
