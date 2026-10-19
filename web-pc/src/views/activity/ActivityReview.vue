<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">活动审批</h2>
        <p class="page-desc">审批通过时必须定级（校级 / 院级），定级决定电子证书的盖章口径；不能审批自己申办的活动。</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="fetchList">刷新</el-button>
    </div>

    <el-tabs v-model="activeTab" @tab-change="fetchList">
      <el-tab-pane label="待审批" name="pending_review" />
      <el-tab-pane label="已驳回" name="rejected" />
      <el-tab-pane label="已通过" name="published" />
    </el-tabs>

    <div class="card-block">
      <el-table v-loading="loading" :data="list" stripe border>
        <el-table-column label="活动" min-width="260">
          <template #default="{ row }">
            <div class="cell-title">{{ row.title }}</div>
            <div class="text-muted cell-sub">
              申办人 {{ row.organizer_name }} · 提交于 {{ formatDateTime(row.submitted_at) }}
            </div>
          </template>
        </el-table-column>
        <el-table-column label="时间 / 地点" min-width="200">
          <template #default="{ row }">
            <div>{{ formatDateTime(row.start_at) }}</div>
            <div class="text-muted cell-sub">{{ row.location || '未填写' }}</div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="typeOf(ACTIVITY_STATUS, row.status)" effect="light">{{ labelOf(ACTIVITY_STATUS, row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="等级" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.level !== 'none'" :type="typeOf(ACTIVITY_LEVEL, row.level)" effect="plain">
              {{ labelOf(ACTIVITY_LEVEL, row.level) }}
            </el-tag>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="审批意见" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.review_comment">{{ row.review_comment }}（{{ row.reviewed_by_name }}）</span>
            <span v-else class="text-muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="190" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="$router.push(`/activities/${row.activity_id}`)">详情</el-button>
            <template v-if="row.status === 'pending_review' && row.organizer_id !== store.profile?.user_id">
              <el-button text type="success" size="small" @click="openReview(row, true)">通过</el-button>
              <el-button text type="danger" size="small" @click="openReview(row, false)">驳回</el-button>
            </template>
            <span v-else-if="row.status === 'pending_review'" class="text-muted cell-sub">自己申办的活动不可自审</span>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty :description="`暂无${labelOf(ACTIVITY_STATUS, activeTab)}的活动`" />
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

    <!-- 审批对话框 -->
    <el-dialog v-model="dialog.visible" :title="dialog.approved ? '审批通过' : '驳回申请'" width="480px">
      <div class="dialog-activity">
        <strong>{{ dialog.row?.title }}</strong>
        <div class="text-muted cell-sub">申办人：{{ dialog.row?.organizer_name }}</div>
      </div>
      <el-form label-width="86px">
        <el-form-item v-if="dialog.approved" label="活动等级" required>
          <el-radio-group v-model="dialog.level">
            <el-radio-button value="school">校级</el-radio-button>
            <el-radio-button value="college">院级</el-radio-button>
          </el-radio-group>
          <div class="text-muted cell-sub" style="margin-top: 6px">
            等级将写入电子证书（校级盖图书馆公章），并随活动对全端展示。
          </div>
        </el-form-item>
        <el-form-item :label="dialog.approved ? '审批备注' : '驳回原因'">
          <el-input v-model="dialog.comment" type="textarea" :rows="3" placeholder="将展示给申办人" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button :type="dialog.approved ? 'success' : 'danger'" :loading="submitting" @click="onReview">
          {{ dialog.approved ? '通过并发布' : '确认驳回' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { listActivities, reviewActivity } from '@/api/activity'
import { useUserStore } from '@/store/user'
import { ACTIVITY_LEVEL, ACTIVITY_STATUS, labelOf, typeOf } from '@/constants'
import { formatDateTime } from '@/utils/format'

const route = useRoute()
const store = useUserStore()
const loading = ref(false)
const submitting = ref(false)
const activeTab = ref('pending_review')
const list = ref([])
const total = ref(0)
const query = reactive({ page: 1, page_size: 10 })

const dialog = reactive({ visible: false, approved: true, level: 'school', comment: '', row: null })

async function fetchList() {
  loading.value = true
  try {
    const data = await listActivities({ ...query, status: activeTab.value })
    list.value = data.list
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function openReview(row, approved) {
  dialog.row = row
  dialog.approved = approved
  dialog.level = 'school'
  dialog.comment = ''
  dialog.visible = true
}

async function onReview() {
  if (dialog.approved && !dialog.level) {
    ElMessage.warning('请选择活动等级')
    return
  }
  if (!dialog.approved && !dialog.comment.trim()) {
    ElMessage.warning('驳回时请填写原因，方便申办人修改')
    return
  }
  submitting.value = true
  try {
    const data = await reviewActivity(dialog.row.activity_id, {
      approved: dialog.approved,
      level: dialog.approved ? dialog.level : undefined,
      comment: dialog.comment
    })
    ElMessage.success(data.status === 'published' ? `已定为「${labelOf(ACTIVITY_LEVEL, data.level)}」并发布` : '已驳回')
    dialog.visible = false
    fetchList()
    // 待审批通知已在后端标为已读，这里让顶栏红点立即重算
    window.dispatchEvent(new Event('notify:refresh'))
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  if (route.query.activity_id) {
    // 从活动列表跳转过来时，定位到该活动所在的标签页
    activeTab.value = 'pending_review'
  }
  fetchList()
})
</script>

<style scoped>
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

.dialog-activity {
  margin-bottom: 14px;
}
</style>
