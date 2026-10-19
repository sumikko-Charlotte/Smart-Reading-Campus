<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">证书管理</h2>
        <p class="page-desc">活动结束后按报名/签到名单批量颁发电子证书（自动加盖公章），支持撤销与验真。</p>
      </div>
      <div>
        <el-button :icon="Refresh" :loading="loading" @click="fetchList">刷新</el-button>
        <el-button type="primary" :icon="Stamp" @click="openIssue">批量颁发</el-button>
      </div>
    </div>

    <div class="filter-bar">
      <el-form :inline="true" :model="query" @submit.prevent>
        <el-form-item label="关键词">
          <el-input v-model="query.keyword" placeholder="姓名 / 学号 / 活动名 / 编号" clearable style="width: 220px" @keyup.enter="onSearch" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="query.status" placeholder="全部" clearable style="width: 130px">
            <el-option v-for="s in CERT_STATUS" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="onSearch">查询</el-button>
        </el-form-item>
      </el-form>
    </div>

    <div class="card-block">
      <el-table v-loading="loading" :data="list" stripe border>
        <el-table-column label="证书" min-width="240">
          <template #default="{ row }">
            <div class="cell-title">
              {{ row.certificate_name }}
              <el-tag :type="typeOf(ACTIVITY_LEVEL, row.activity_level)" size="small" effect="plain">
                {{ labelOf(ACTIVITY_LEVEL, row.activity_level) }}
              </el-tag>
              <el-tag :type="typeOf(CERT_STATUS, row.status)" size="small" effect="light">
                {{ labelOf(CERT_STATUS, row.status) }}
              </el-tag>
            </div>
            <div class="text-muted cell-sub">{{ row.activity_title }}</div>
          </template>
        </el-table-column>
        <el-table-column label="持有人" width="150">
          <template #default="{ row }">
            <div>{{ row.student_name }}</div>
            <div class="text-muted cell-sub">{{ row.student_no }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="serial_no" label="证书编号" width="200" />
        <el-table-column prop="verify_code" label="验真码" width="110" />
        <el-table-column label="颁发" width="160">
          <template #default="{ row }">
            <div>{{ formatDateTime(row.issued_at) }}</div>
            <div class="text-muted cell-sub">{{ row.issued_by_name }}</div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status === 'issued'" text type="primary" size="small" @click="onDownload(row)">下载</el-button>
            <el-button text size="small" @click="onVerify(row)">验真</el-button>
            <el-button v-if="row.status === 'issued'" text type="danger" size="small" @click="onRevoke(row)">撤销</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无证书记录" />
        </template>
      </el-table>

      <div class="pager">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.page_size"
          :total="total"
          layout="total, prev, pager, next"
          background
          @current-change="fetchList"
        />
      </div>
    </div>

    <!-- 批量颁发 -->
    <el-dialog v-model="issueVisible" title="批量颁发电子证书" width="520px">
      <el-alert
        class="mb-12"
        type="warning"
        :closable="false"
        show-icon
        title="仅「已结束且已定级」的活动可以颁发；同一学生同一活动只会颁发一张"
      />
      <el-form label-width="110px">
        <el-form-item label="选择活动" required>
          <el-select v-model="issueForm.activity_id" filterable placeholder="选择已结束的活动" style="width: 100%">
            <el-option
              v-for="act in eligibleActivities"
              :key="act.activity_id"
              :label="`${labelOf(ACTIVITY_LEVEL, act.level)} · ${act.title}`"
              :value="act.activity_id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="证书名称">
          <el-input v-model="issueForm.certificate_name" maxlength="64" />
        </el-form-item>
        <el-form-item label="颁发范围">
          <el-radio-group v-model="issueForm.only_checked_in">
            <el-radio :value="false">全部报名学生</el-radio>
            <el-radio :value="true">仅已签到学生</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="issueVisible = false">取消</el-button>
        <el-button type="primary" :loading="issuing" @click="onIssue">确认颁发</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CircleCheck, Download, Refresh, Search, Stamp } from '@element-plus/icons-vue'
import {
  downloadCertificatePdf,
  issueCertificates,
  listCertificates,
  revokeCertificate,
  verifyCertificate
} from '@/api/certificate'
import { listActivities } from '@/api/activity'
import { ACTIVITY_LEVEL, CERT_STATUS, labelOf, typeOf } from '@/constants'
import { formatDateTime } from '@/utils/format'

const route = useRoute()
const loading = ref(false)
const issuing = ref(false)
const list = ref([])
const total = ref(0)
const finishedActivities = ref([])
const query = reactive({
  page: 1,
  page_size: 10,
  keyword: '',
  status: '',
  activity_id: route.query.activity_id || ''
})

const issueVisible = ref(false)
const issueForm = reactive({ activity_id: '', certificate_name: '荣誉证书', only_checked_in: true })

/** 只能对「已结束 + 已定级」的活动颁发 */
const eligibleActivities = computed(() =>
  finishedActivities.value.filter((a) => a.level && a.level !== 'none')
)

async function fetchList() {
  loading.value = true
  try {
    const data = await listCertificates({
      ...query,
      keyword: query.keyword || undefined,
      status: query.status || undefined,
      activity_id: query.activity_id || undefined
    })
    list.value = data.list
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function fetchFinishedActivities() {
  const data = await listActivities({ status: 'finished', page: 1, page_size: 100 })
  finishedActivities.value = data.list
}

function onSearch() {
  query.page = 1
  fetchList()
}

function openIssue() {
  if (query.activity_id) issueForm.activity_id = query.activity_id
  issueVisible.value = true
}

async function onIssue() {
  if (!issueForm.activity_id) {
    ElMessage.warning('请选择活动')
    return
  }
  issuing.value = true
  try {
    const data = await issueCertificates(issueForm.activity_id, {
      only_checked_in: issueForm.only_checked_in,
      certificate_name: issueForm.certificate_name
    })
    ElMessage.success(`已颁发 ${data.issued} 张，跳过 ${data.skipped} 张${data.skipped_reason ? `（${data.skipped_reason}）` : ''}`)
    issueVisible.value = false
    fetchList()
  } finally {
    issuing.value = false
  }
}

async function onDownload(cert) {
  try {
    await downloadCertificatePdf(cert)
  } catch {
    /* 拦截器提示 */
  }
}

async function onVerify(cert) {
  const result = await verifyCertificate(cert.verify_code)
  ElMessage[result.valid ? 'success' : 'warning'](
    result.valid ? `证书有效：${result.holder_name} · ${result.activity_title}` : result.message
  )
}

async function onRevoke(cert) {
  await ElMessageBox.confirm(
    `撤销后 ${cert.student_name} 将无法下载该证书（编号 ${cert.serial_no}），确认撤销？`,
    '撤销证书',
    { type: 'warning', confirmButtonText: '确认撤销' }
  )
  await revokeCertificate(cert.certificate_id)
  ElMessage.success('已撤销')
  fetchList()
}

onMounted(async () => {
  await Promise.all([fetchList(), fetchFinishedActivities()])
})
</script>

<style scoped>
.mb-12 {
  margin-bottom: 12px;
}

.cell-title {
  display: flex;
  align-items: center;
  gap: 6px;
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
