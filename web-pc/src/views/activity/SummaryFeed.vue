<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">活动回顾</h2>
        <p class="page-desc">活动结束后的图文总结，全站可见（含访客）；由管理员发布，AI 只提供草稿建议。</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="fetchList">刷新</el-button>
    </div>

    <div v-loading="loading" class="summary-list">
      <el-empty v-if="!list.length && !loading" description="暂无活动回顾" />

      <el-card v-for="item in list" :key="item.summary_id" class="summary-card" shadow="hover">
        <div class="card-head">
          <div>
            <div class="card-title">{{ item.title }}</div>
            <div class="text-muted card-sub">
              {{ item.activity_title }} · {{ item.author_name }} 发布于 {{ formatDateTime(item.published_at) }} · {{ item.view_count }} 次阅读
            </div>
          </div>
          <el-button text type="primary" @click="openDetail(item)">阅读全文</el-button>
        </div>
        <div class="card-excerpt">{{ excerpt(item.content) }}</div>
        <div v-if="item.images?.length" class="card-images">
          <el-image
            v-for="(img, index) in item.images.slice(0, 4)"
            :key="index"
            :src="img"
            :preview-src-list="item.images"
            :initial-index="index"
            fit="cover"
            class="card-image"
          />
        </div>
      </el-card>
    </div>

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

    <el-dialog v-model="detailVisible" :title="detail?.title" width="680px">
      <div class="text-muted detail-sub">
        {{ detail?.activity_title }} · {{ detail?.author_name }} · {{ formatDateTime(detail?.published_at) }}
      </div>
      <div class="detail-content">{{ detail?.content }}</div>
      <div v-if="detail?.images?.length" class="detail-images">
        <el-image
          v-for="(img, index) in detail.images"
          :key="index"
          :src="img"
          :preview-src-list="detail.images"
          :initial-index="index"
          fit="cover"
          class="detail-image"
        />
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { listSummaries } from '@/api/summary'
import { formatDateTime } from '@/utils/format'

const loading = ref(false)
const list = ref([])
const total = ref(0)
const query = reactive({ page: 1, page_size: 10 })
const detailVisible = ref(false)
const detail = ref(null)

function excerpt(text = '', length = 120) {
  return text.length > length ? `${text.slice(0, length)}…` : text
}

async function fetchList() {
  loading.value = true
  try {
    const data = await listSummaries({ ...query, keyword: '' })
    list.value = data.list
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function openDetail(item) {
  detail.value = item
  detailVisible.value = true
}

onMounted(fetchList)
</script>

<style scoped>
.summary-list {
  min-height: 200px;
}

.summary-card {
  margin-bottom: 14px;
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
}

.card-sub {
  font-size: 12px;
  margin-top: 4px;
}

.card-excerpt {
  margin-top: 10px;
  color: #4b5563;
  line-height: 1.7;
}

.card-images {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}

.card-image {
  width: 96px;
  height: 64px;
  border-radius: 6px;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}

.detail-sub {
  margin-bottom: 12px;
  font-size: 13px;
}

.detail-content {
  white-space: pre-wrap;
  line-height: 1.9;
  color: #374151;
}

.detail-images {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}

.detail-image {
  width: 140px;
  height: 92px;
  border-radius: 6px;
}
</style>
