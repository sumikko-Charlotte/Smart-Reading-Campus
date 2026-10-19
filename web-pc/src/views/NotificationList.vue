<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">消息推送</h2>
        <p class="page-desc">按当前角色（{{ store.roleLabel || '—' }}）过滤的站内消息；活动回顾、证书颁发等都会推送到这里。</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="fetchList">刷新</el-button>
    </div>

    <div class="card-block">
      <el-table v-loading="loading" :data="list" stripe border>
        <el-table-column label="消息" min-width="320">
          <template #default="{ row }">
            <div class="cell-title">
              <el-tag :type="typeOf(NOTIFICATION_TYPE, row.type)" size="small" effect="plain">
                {{ labelOf(NOTIFICATION_TYPE, row.type) }}
              </el-tag>
              {{ row.title }}
            </div>
            <div class="text-muted cell-sub content-preview">{{ row.content }}</div>
          </template>
        </el-table-column>
        <el-table-column label="推送人" width="140" prop="created_by_name" />
        <el-table-column label="推送范围" width="170">
          <template #default="{ row }">
            {{ (row.target_roles || []).map((r) => labelOf(USER_ROLE, r)).join('、') }}
          </template>
        </el-table-column>
        <el-table-column label="时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.created_at, true) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.ref_type === 'activity_summary'" text type="primary" size="small" @click="$router.push('/summaries')">
              查看回顾
            </el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无消息" />
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
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { listNotifications } from '@/api/summary'
import { useUserStore } from '@/store/user'
import { NOTIFICATION_TYPE, USER_ROLE, labelOf, typeOf } from '@/constants'
import { formatDateTime } from '@/utils/format'

const store = useUserStore()
const loading = ref(false)
const list = ref([])
const total = ref(0)
const query = reactive({ page: 1, page_size: 10 })

async function fetchList() {
  loading.value = true
  try {
    const data = await listNotifications({ ...query })
    list.value = data.list
    total.value = data.total
  } finally {
    loading.value = false
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
  margin-top: 4px;
}

.content-preview {
  max-width: 520px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
