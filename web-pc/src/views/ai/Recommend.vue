<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">AI 智能推荐</h2>
        <p class="page-desc">
          第 1 轮实现：借阅热度榜 Top N + AI 推荐理由（后端 <code>POST /api/v1/books/recommend</code>）；
          个性化算法与向量召回在第 2 轮接入。
        </p>
      </div>
      <el-tag type="warning" effect="plain">骨架页 · 接口已通</el-tag>
    </div>

    <div class="filter-bar">
      <el-form :inline="true" :model="form" @submit.prevent>
        <el-form-item label="阅读偏好">
          <el-input v-model="form.extra_prompt" placeholder="如：偏计算机类、篇幅不要太长" clearable style="width: 280px" @keyup.enter="onRecommend" />
        </el-form-item>
        <el-form-item label="推荐数量">
          <el-input-number v-model="form.limit" :min="1" :max="20" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="MagicStick" :loading="loading" @click="onRecommend">生成推荐</el-button>
        </el-form-item>
      </el-form>
    </div>

    <div v-loading="loading" class="recommend-wrap">
      <el-empty v-if="!items.length && !loading" description="点击「生成推荐」拉取借阅榜单并生成推荐理由" />

      <el-row v-else :gutter="16">
        <el-col v-for="(item, index) in items" :key="item.book.book_id" :xs="24" :sm="12" :md="8">
          <el-card class="book-card" shadow="hover">
            <div class="rank">TOP {{ index + 1 }}</div>
            <div class="book-head">
              <div class="cover">
                <el-icon :size="26"><Reading /></el-icon>
              </div>
              <div class="book-meta">
                <div class="book-title">{{ item.book.title }}</div>
                <div class="text-muted book-author">{{ item.book.author }} · {{ item.book.publisher || '—' }}</div>
                <div class="book-tags">
                  <el-tag v-for="t in item.book.tags" :key="t" size="small" effect="plain">{{ t }}</el-tag>
                </div>
              </div>
            </div>

            <el-divider />

            <div class="reason">
              <el-icon color="#d97706"><MagicStick /></el-icon>
              <span>{{ item.reason }}</span>
            </div>

            <div class="book-foot">
              <span class="text-muted">借阅 {{ item.book.borrow_count }} 次 · 可借 {{ item.book.available_copies }}/{{ item.book.total_copies }}</span>
              <el-button text type="primary" size="small" @click="onAnalyze(item.book)">
                {{ item.book.ai_summary ? '查看 AI 解读' : '生成 AI 解读' }}
              </el-button>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="640px">
      <div v-loading="analysisLoading" class="analysis-body">
        <div v-if="analysisText" class="detail-content">{{ analysisText }}</div>
        <el-empty v-else description="暂无解读内容" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, Reading } from '@element-plus/icons-vue'
import { buildBookAiSummary, recommendBooks } from '@/api/modules'

const loading = ref(false)
const items = ref([])
const form = reactive({ extra_prompt: '', limit: 6 })

const dialogVisible = ref(false)
const dialogTitle = ref('AI 书目深度解读')
const analysisLoading = ref(false)
const analysisText = ref('')

async function onRecommend() {
  loading.value = true
  try {
    const data = await recommendBooks({ extra_prompt: form.extra_prompt, limit: form.limit })
    items.value = data.items
    ElMessage.success(`已生成 ${data.items.length} 条推荐（模型：${data.model} / 提示词 ${data.prompt_version}）`)
  } finally {
    loading.value = false
  }
}

async function onAnalyze(book) {
  dialogTitle.value = `AI 书目深度解读 · ${book.title}`
  analysisText.value = book.ai_summary || ''
  dialogVisible.value = true
  if (book.ai_summary) return
  analysisLoading.value = true
  try {
    const data = await buildBookAiSummary(book.book_id)
    analysisText.value = data.ai_summary
    // 同步回卡片，避免重复请求
    const target = items.value.find((i) => i.book.book_id === book.book_id)
    if (target) {
      target.book.ai_summary = data.ai_summary
      target.book.ai_tags = data.ai_tags
    }
  } finally {
    analysisLoading.value = false
  }
}

onMounted(onRecommend)
</script>

<style scoped>
.recommend-wrap {
  min-height: 260px;
}

.book-card {
  position: relative;
  margin-bottom: 16px;
  border-radius: var(--sr-card-radius);
}

.rank {
  position: absolute;
  top: 12px;
  right: 14px;
  font-size: 12px;
  font-weight: 700;
  color: #2f54eb;
}

.book-head {
  display: flex;
  gap: 12px;
}

.cover {
  width: 46px;
  height: 62px;
  border-radius: 6px;
  background: #eef2ff;
  color: #2f54eb;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
}

.book-meta {
  min-width: 0;
}

.book-title {
  font-weight: 600;
  font-size: 15px;
  margin-bottom: 4px;
}

.book-author,
.book-tags {
  font-size: 12px;
}

.book-tags {
  margin-top: 6px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.reason {
  display: flex;
  gap: 8px;
  font-size: 13px;
  line-height: 1.7;
  color: #4b5563;
}

.book-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
  font-size: 12px;
}

.analysis-body {
  max-height: 60vh;
  overflow-y: auto;
}

.detail-content {
  white-space: pre-wrap;
  line-height: 1.8;
  color: #374151;
  background: #fafbfe;
  border-radius: 8px;
  padding: 12px 14px;
}
</style>
