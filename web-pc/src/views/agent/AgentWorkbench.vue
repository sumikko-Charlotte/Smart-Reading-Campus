<template>
  <div class="agent-workbench">
    <!-- 模型状态：不可用时说明是降级在跑，避免被误认为"AI 坏了" -->
    <el-alert
      v-if="health && !health.available"
      type="warning"
      show-icon
      :closable="false"
      class="status-bar"
    >
      <template #title>
        当前为降级模式运行：{{ health.reason }}。四个场景仍可正常出水，但不做语义理解。
      </template>
    </el-alert>

    <!-- 数据来源：模拟数据必须说清楚，否则演示时容易被当成真实馆藏行为 -->
    <el-alert
      v-if="dataset && dataset.has_simulated"
      type="info"
      show-icon
      :closable="false"
      class="status-bar"
    >
      <template #title>
        当前数据包含 AI 模拟样本（模拟学生 {{ dataset.users.simulated || 0 }} 人、借阅
        {{ dataset.borrows.simulated || 0 }} 条）。真实脱敏数据到位后可一键替换。
      </template>
    </el-alert>

    <el-row :gutter="16">
      <!-- 左：选场景 + 填需求 -->
      <el-col :xs="24" :md="9">
        <el-card shadow="never" class="panel">
          <template #header>
            <div class="panel-head">
              <span>选一个场景</span>
              <el-tag v-if="health" size="small" :type="health.available ? 'success' : 'warning'" effect="plain">
                {{ health.available ? health.model : '降级模式' }}
              </el-tag>
            </div>
          </template>

          <div class="scene-grid">
            <div
              v-for="item in visibleScenes"
              :key="item.scene"
              class="scene-card"
              :class="{ active: scene === item.scene }"
              @click="switchScene(item.scene)"
            >
              <div class="scene-title">{{ item.label }}</div>
              <div class="scene-desc">{{ item.description }}</div>
              <div class="scene-tools">{{ item.tools.length }} 个工具</div>
            </div>
          </div>

          <el-form label-position="top" class="scene-form">
            <!-- 匹配 -->
            <template v-if="scene === 'match'">
              <el-form-item label="想读什么（可留空，按我的借阅画像推荐）">
                <el-input
                  v-model="form.query"
                  type="textarea"
                  :rows="2"
                  placeholder="例：想找讲机器学习入门、不要太厚的书"
                  maxlength="200"
                  show-word-limit
                />
              </el-form-item>
              <el-form-item label="推荐几本">
                <el-input-number v-model="form.limit" :min="1" :max="10" />
              </el-form-item>
            </template>

            <!-- 录书 -->
            <template v-else-if="scene === 'intake'">
              <el-form-item label="ISBN">
                <el-input v-model="form.isbn" placeholder="9787115428028" maxlength="20" />
              </el-form-item>
              <el-form-item label="书名（可选）">
                <el-input v-model="form.title" placeholder="深度学习" maxlength="60" />
              </el-form-item>
              <el-form-item label="或粘贴拍到的文字 / 书目信息">
                <el-input
                  v-model="form.raw_text"
                  type="textarea"
                  :rows="4"
                  placeholder="书名：深度学习&#10;作者：Ian Goodfellow&#10;出版社：人民邮电出版社"
                  maxlength="1000"
                />
              </el-form-item>
            </template>

            <!-- 触达 -->
            <template v-else-if="scene === 'outreach'">
              <el-form-item label="选一场活动">
                <el-select v-model="form.activity_id" filterable clearable placeholder="选择活动" style="width: 100%">
                  <el-option
                    v-for="act in activities"
                    :key="act.activity_id"
                    :label="`${act.title}（${act.status}）`"
                    :value="act.activity_id"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="没有指定活动时，用主题词">
                <el-input v-model="form.topic" placeholder="例：秋季读书分享会" maxlength="60" />
              </el-form-item>
              <el-form-item label="投放渠道">
                <el-radio-group v-model="form.channel">
                  <el-radio-button value="push">站内推送</el-radio-button>
                  <el-radio-button value="wechat">公众号</el-radio-button>
                  <el-radio-button value="poster">海报文案</el-radio-button>
                </el-radio-group>
              </el-form-item>
            </template>

            <!-- 伴读 -->
            <template v-else>
              <el-form-item label="问点什么">
                <el-input
                  v-model="form.question"
                  type="textarea"
                  :rows="3"
                  placeholder="例：《人类简史》在哪个馆藏区？还有同类的书吗？"
                  maxlength="500"
                />
              </el-form-item>
            </template>

            <el-button type="primary" :loading="loading" class="run-btn" @click="run">
              {{ loading ? '智能体思考中…' : '让智能体开始' }}
            </el-button>
          </el-form>
        </el-card>
      </el-col>

      <!-- 右：过程 + 结果 -->
      <el-col :xs="24" :md="15">
        <!-- 空态 -->
        <el-card v-if="!result && !loading" shadow="never" class="panel empty-panel">
          <div class="empty-hint">
            <div class="empty-title">与「接 API」的区别在这里</div>
            <p>
              以前是把提示词发给模型、拿回一段文字。现在你只描述目标，智能体自己决定去查什么：
              先看你的借阅画像，再按分类找候选，再核对库存，最后才写理由。
            </p>
            <p>它每查一次，右边就会多一条轨迹——那是它真正做过的事。</p>
          </div>
        </el-card>

        <el-card v-if="loading" shadow="never" class="panel">
          <el-skeleton :rows="6" animated />
          <div class="loading-hint">正在检索馆藏、核对数据…</div>
        </el-card>

        <el-card v-if="result" shadow="never" class="panel">
          <template #header>
            <div class="panel-head">
              <span>智能体运行轨迹</span>
              <div class="meta">
                <el-tag size="small" effect="plain">{{ result.steps }} 步</el-tag>
                <el-tag size="small" effect="plain">{{ result.tokens }} tokens</el-tag>
                <el-tag size="small" effect="plain">{{ result.elapsed_ms }} ms</el-tag>
                <el-tag v-if="result.degraded" size="small" type="warning">降级</el-tag>
              </div>
            </div>
          </template>

          <el-alert v-if="result.degraded" type="warning" :closable="false" show-icon class="degrade-note">
            {{ result.degraded_reason }}
          </el-alert>

          <!-- 轨迹：这是"智能体"和"调 API"最直观的差别 -->
          <el-timeline v-if="result.trace && result.trace.length" class="trace">
            <el-timeline-item
              v-for="(step, index) in result.trace"
              :key="index"
              :type="step.ok ? 'primary' : 'danger'"
              :timestamp="`${step.elapsed_ms} ms`"
              placement="top"
            >
              <div class="trace-head">
                <code>{{ step.tool }}</code>
                <el-tag size="small" :type="step.ok ? 'success' : 'danger'" effect="plain">
                  {{ step.ok ? '成功' : '失败' }}
                </el-tag>
              </div>
              <div class="trace-args">{{ formatArgs(step.arguments) }}</div>
              <div class="trace-summary">{{ step.summary }}</div>
            </el-timeline-item>
          </el-timeline>
          <div v-else class="trace-empty">本次未调用工具（模型直接给出了答复）</div>

          <el-divider />

          <!-- ============ 结果分区 ============ -->

          <!-- 匹配 -->
          <template v-if="result.scene === 'match'">
            <div class="result-explain">{{ result.result.explanation }}</div>
            <div v-for="book in result.result.items" :key="book.book_id" class="book-card">
              <div class="book-main">
                <div class="book-title">{{ book.title }}</div>
                <div class="book-author">{{ book.author }}</div>
                <div class="book-reason">{{ book.reason }}</div>
                <div class="book-tags">
                  <el-tag v-for="tag in book.evidence" :key="tag" size="small" effect="plain" type="info">
                    {{ tag }}
                  </el-tag>
                </div>
              </div>
              <div class="book-side">
                <div :class="['stock', book.available_copies ? 'ok' : 'out']">
                  {{ book.available_copies ? `可借 ${book.available_copies} 册` : '已借完' }}
                </div>
                <div class="loc">{{ book.lib_location || '馆藏地待确认' }}</div>
                <div class="call-no">{{ book.call_no }}</div>
              </div>
            </div>
            <el-empty v-if="!result.result.items?.length" description="没有找到合适的书" :image-size="80" />
          </template>

          <!-- 录书 -->
          <template v-else-if="result.scene === 'intake'">
            <el-alert
              v-if="result.result.duplicate?.is_duplicate"
              type="error"
              :closable="false"
              show-icon
              title="馆藏中已存在这本书，无需重复录入"
              :description="`已有记录：${result.result.duplicate.book_id}`"
            />
            <el-descriptions :column="2" border size="small" class="intake-table">
              <el-descriptions-item label="书名">{{ result.result.book?.title || '—' }}</el-descriptions-item>
              <el-descriptions-item label="作者">{{ result.result.book?.author || '—' }}</el-descriptions-item>
              <el-descriptions-item label="出版社">{{ result.result.book?.publisher || '—' }}</el-descriptions-item>
              <el-descriptions-item label="出版年">{{ result.result.book?.publish_date || '—' }}</el-descriptions-item>
              <el-descriptions-item label="ISBN">{{ result.result.book?.isbn || '—' }}</el-descriptions-item>
              <el-descriptions-item label="中图法">{{ result.result.book?.clc_code || '—' }}</el-descriptions-item>
              <el-descriptions-item label="索书号">{{ result.result.book?.call_no || '—' }}</el-descriptions-item>
              <el-descriptions-item label="馆藏地">{{ result.result.book?.lib_location || '—' }}</el-descriptions-item>
              <el-descriptions-item label="页数">{{ result.result.book?.pages || '—' }}</el-descriptions-item>
              <el-descriptions-item label="定价">{{ result.result.book?.price || '—' }}</el-descriptions-item>
            </el-descriptions>
            <div class="field-block">
              <div class="field-label">置信度</div>
              <el-progress :percentage="Math.round((result.result.confidence || 0) * 100)" :stroke-width="10" />
            </div>
            <div v-if="result.result.missing_fields?.length" class="field-block">
              <div class="field-label">待补字段</div>
              <el-tag v-for="field in result.result.missing_fields" :key="field" type="warning" effect="plain" size="small">
                {{ field }}
              </el-tag>
            </div>
            <div v-if="result.result.review_notes?.length" class="field-block">
              <div class="field-label">需人工确认</div>
              <ul class="note-list">
                <li v-for="note in result.result.review_notes" :key="note">{{ note }}</li>
              </ul>
            </div>
          </template>

          <!-- 触达 -->
          <template v-else-if="result.scene === 'outreach'">
            <div class="copy-block">
              <div class="copy-head">
                <span>标题</span>
                <el-button link size="small" @click="copy(result.result.title)">复制</el-button>
              </div>
              <div class="copy-title">{{ result.result.title }}</div>
            </div>
            <div class="copy-block">
              <div class="copy-head">
                <span>正文</span>
                <el-button link size="small" @click="copy(result.result.body)">复制</el-button>
              </div>
              <div class="copy-body">{{ result.result.body }}</div>
            </div>
            <div class="copy-block">
              <div class="copy-head">
                <span>推送摘要（{{ (result.result.push_text || '').length }} 字）</span>
                <el-button link size="small" @click="copy(result.result.push_text)">复制</el-button>
              </div>
              <div class="copy-push">{{ result.result.push_text }}</div>
            </div>
            <el-alert
              v-if="result.result.needs_human_approval"
              type="warning"
              :closable="false"
              show-icon
              title="AI 只出草稿，不会自动发送"
              description="确认时间、地点、名额无误后，由主办方手动发布。"
            />
            <div v-if="result.result.risk_notes?.length" class="field-block">
              <div class="field-label">发布前请确认</div>
              <ul class="note-list">
                <li v-for="note in result.result.risk_notes" :key="note">{{ note }}</li>
              </ul>
            </div>
          </template>

          <!-- 伴读 -->
          <template v-else>
            <div class="answer">{{ result.result.answer }}</div>
            <div v-if="result.result.citations?.length" class="citations">
              <div class="field-label">依据</div>
              <div v-for="cite in result.result.citations" :key="cite.ref_id" class="citation">
                <el-icon><Link /></el-icon>
                <span class="cite-title">{{ cite.title }}</span>
                <span class="cite-snippet">{{ cite.snippet }}</span>
              </div>
            </div>
            <div v-if="result.result.followups?.length" class="followups">
              <el-button
                v-for="item in result.result.followups"
                :key="item"
                size="small"
                round
                @click="askFollowup(item)"
              >
                {{ item }}
              </el-button>
            </div>
          </template>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Link } from '@element-plus/icons-vue'
import { agentDataset, agentHealth, agentTools, runAgent } from '@/api/agent'
import { listActivities } from '@/api/activity'
import { useUserStore } from '@/store/user'

const store = useUserStore()

const scene = ref('match')
const loading = ref(false)
const result = ref(null)
const health = ref(null)
const dataset = ref(null)
const scenes = ref([])
const activities = ref([])

const form = reactive({
  query: '',
  limit: 5,
  raw_text: '',
  isbn: '',
  title: '',
  activity_id: '',
  topic: '',
  channel: 'push',
  question: ''
})

/** 只展示当前账号有权限调用的场景，避免点进去才发现 403 */
const visibleScenes = computed(() => scenes.value.filter((item) => store.can(item.permission)))

function switchScene(next) {
  scene.value = next
  result.value = null
}

function formatArgs(args) {
  if (!args || Object.keys(args).length === 0) return '无参数'
  return Object.entries(args)
    .map(([key, value]) => `${key}=${typeof value === 'object' ? JSON.stringify(value) : value}`)
    .join('  ')
}

async function run() {
  const payload = { ...form }
  if (scene.value === 'companion') payload.question = form.question || form.query
  if (scene.value === 'match' && !form.query) payload.query = ''

  loading.value = true
  result.value = null
  try {
    const data = await runAgent(scene.value, payload)
    result.value = data
    if (data.degraded) {
      ElMessage.warning('本次为降级结果，原因见上方提示')
    }
  } catch (error) {
    // 拦截器已提示，这里只保证不留下 loading
    result.value = null
  } finally {
    loading.value = false
  }
}

function askFollowup(question) {
  form.question = question
  scene.value = 'companion'
  run()
}

async function copy(text) {
  if (!text) return
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制')
  } catch {
    ElMessage.warning('浏览器不允许自动复制，请手动选中')
  }
}

onMounted(async () => {
  try {
    const [toolData, healthData, datasetData] = await Promise.all([
      agentTools(),
      agentHealth(),
      agentDataset()
    ])
    scenes.value = toolData.scenes || []
    health.value = healthData
    dataset.value = datasetData
    // 默认落到第一个有权限的场景
    const first = visibleScenes.value[0]
    if (first) scene.value = first.scene
  } catch {
    // 接口异常时保留空态，拦截器已提示
  }

  try {
    const list = await listActivities({ page: 1, page_size: 50 })
    activities.value = list.list || []
  } catch {
    activities.value = []
  }
})
</script>

<style scoped>
.agent-workbench {
  padding: 4px;
}
.status-bar {
  margin-bottom: 12px;
}
.panel {
  border-radius: 10px;
  margin-bottom: 16px;
}
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
}
.meta {
  display: flex;
  gap: 6px;
}
.scene-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  margin-bottom: 16px;
}
.scene-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 10px 12px;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--el-fill-color-blank);
}
.scene-card:hover {
  border-color: var(--el-color-primary-light-5);
}
.scene-card.active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.scene-title {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 4px;
}
.scene-desc {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.45;
  min-height: 34px;
}
.scene-tools {
  font-size: 11px;
  color: var(--el-color-primary);
  margin-top: 6px;
}
.scene-form {
  margin-top: 4px;
}
.run-btn {
  width: 100%;
}
.empty-panel {
  min-height: 320px;
  display: flex;
  align-items: center;
}
.empty-hint {
  max-width: 520px;
  margin: 0 auto;
  color: var(--el-text-color-regular);
  line-height: 1.8;
  font-size: 14px;
}
.empty-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 8px;
}
.loading-hint {
  text-align: center;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-top: 12px;
}
.degrade-note {
  margin-bottom: 14px;
}
.trace {
  padding-left: 2px;
}
.trace-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.trace-head code {
  background: var(--el-fill-color-light);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 13px;
  color: var(--el-color-primary);
}
.trace-args {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
  font-family: monospace;
}
.trace-summary {
  font-size: 13px;
  margin-top: 4px;
  color: var(--el-text-color-regular);
}
.trace-empty {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.result-explain {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  margin-bottom: 12px;
}
.book-card {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  margin-bottom: 10px;
}
.book-title {
  font-weight: 600;
  font-size: 15px;
  margin-bottom: 2px;
}
.book-author {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
.book-reason {
  font-size: 13px;
  line-height: 1.6;
  margin-bottom: 8px;
}
.book-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.book-side {
  text-align: right;
  min-width: 110px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.stock {
  font-weight: 600;
  margin-bottom: 4px;
}
.stock.ok {
  color: var(--el-color-success);
}
.stock.out {
  color: var(--el-color-danger);
}
.call-no {
  font-family: monospace;
  margin-top: 2px;
}
.intake-table {
  margin-bottom: 14px;
}
.field-block {
  margin-top: 14px;
}
.field-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
.field-block :deep(.el-tag) {
  margin-right: 6px;
  margin-bottom: 6px;
}
.note-list {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--el-text-color-regular);
  line-height: 1.7;
}
.copy-block {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 12px;
}
.copy-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
.copy-title {
  font-size: 17px;
  font-weight: 600;
}
.copy-body {
  white-space: pre-wrap;
  line-height: 1.75;
  font-size: 14px;
}
.copy-push {
  background: var(--el-fill-color-light);
  padding: 10px 12px;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.6;
}
.answer {
  white-space: pre-wrap;
  line-height: 1.85;
  font-size: 14px;
  margin-bottom: 16px;
}
.citations {
  margin-bottom: 14px;
}
.citation {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  padding: 6px 0;
  color: var(--el-text-color-regular);
}
.cite-title {
  font-weight: 600;
}
.cite-snippet {
  color: var(--el-text-color-secondary);
}
.followups {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
