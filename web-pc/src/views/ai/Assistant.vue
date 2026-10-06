<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">AI 阅读助手</h2>
        <p class="page-desc">
          多轮伴读问答，双端共用同一份会话数据（AIConversation + messages）。流式开关可对比
          <code>POST /api/v1/ai/chat</code> 的两种返回形态。
        </p>
      </div>
      <div class="header-actions">
        <el-switch v-model="useStream" active-text="流式输出" />
        <el-button :icon="Refresh" @click="newConversation">新建会话</el-button>
      </div>
    </div>

    <el-row :gutter="16">
      <el-col :md="17">
        <div class="chat-panel">
          <div ref="scrollRef" class="chat-body">
            <el-empty v-if="!messages.length" description="选择一本图书，开始与 AI 伴读对话" />

            <div v-for="msg in messages" :key="msg.message_id" :class="['msg-row', msg.role]">
              <el-avatar :size="32" class="msg-avatar">
                {{ msg.role === 'user' ? (store.profile?.name?.slice(0, 1) || '我') : 'AI' }}
              </el-avatar>
              <div class="msg-bubble">
                <div class="msg-content">{{ msg.content }}</div>
                <div class="msg-meta text-muted">
                  {{ msg.created_at ? formatDateTime(msg.created_at, true) : '' }}
                  <span v-if="msg.tokens"> · {{ msg.tokens }} tokens</span>
                </div>
              </div>
            </div>

            <div v-if="streaming" class="msg-row assistant">
              <el-avatar :size="32" class="msg-avatar">AI</el-avatar>
              <div class="msg-bubble">
                <div class="msg-content">{{ streamBuffer || '正在思考…' }}<span class="cursor">▍</span></div>
              </div>
            </div>
          </div>

          <div class="chat-input">
            <el-input
              v-model="input"
              type="textarea"
              :rows="2"
              resize="none"
              placeholder="例如：这本书适合零基础的同学读吗？它的核心观点是什么？（Enter 发送，Shift+Enter 换行）"
              @keydown.enter.exact.prevent="onSend"
            />
            <div class="chat-actions">
              <el-select v-model="bookId" placeholder="关联图书（可选）" clearable filterable style="width: 240px">
                <el-option v-for="b in books" :key="b.book_id" :label="`${b.title} · ${b.author}`" :value="b.book_id" />
              </el-select>
              <el-button type="primary" :icon="Promotion" :loading="sending" :disabled="!input.trim()" @click="onSend">发送</el-button>
            </div>
          </div>
        </div>
      </el-col>

      <el-col :md="7">
        <div class="card-block">
          <div class="flex-between">
            <h3 class="section-title">我的会话</h3>
            <el-button text type="primary" size="small" @click="fetchConversations">刷新</el-button>
          </div>
          <div v-if="!conversations.length" class="text-muted">暂无历史会话</div>
          <div
            v-for="c in conversations"
            :key="c.conversation_id"
            :class="['conv-item', { active: c.conversation_id === conversationId }]"
            @click="openConversation(c)"
          >
            <div class="conv-title">{{ c.title || '未命名会话' }}</div>
            <div class="text-muted conv-sub">
              {{ labelOf(CONVERSATION_SCENE, c.scene) }} · {{ c.message_count }} 条 · {{ formatDateTime(c.updated_at) }}
            </div>
          </div>
        </div>

        <div class="card-block mt-16">
          <h3 class="section-title">接口说明</h3>
          <ul class="api-list">
            <li><code>POST /ai/chat</code> 多轮对话（stream 可选）</li>
            <li><code>GET /ai/conversations</code> 会话列表</li>
            <li><code>GET /ai/conversations/:id</code> 消息流</li>
            <li><code>DELETE /ai/conversations/:id</code> 删除会话</li>
          </ul>
          <el-alert
            type="info"
            :closable="false"
            show-icon
            title="与小程序的差异"
            description="小程序端使用同一套接口与字段，仅渲染方式不同（Markdown → 富文本）。"
          />
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { nextTick, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Promotion, Refresh } from '@element-plus/icons-vue'
import { chat, chatStream, getConversation, listBooks, listConversations } from '@/api/modules'
import { CONVERSATION_SCENE, labelOf } from '@/constants'
import { useUserStore } from '@/store/user'
import { formatDateTime } from '@/utils/format'

const store = useUserStore()
const messages = ref([])
const conversations = ref([])
const books = ref([])
const input = ref('')
const bookId = ref('')
const conversationId = ref('')
const sending = ref(false)
const streaming = ref(false)
const streamBuffer = ref('')
const useStream = ref(false)
const scrollRef = ref()
let controller = null

function scrollToBottom() {
  nextTick(() => {
    if (scrollRef.value) scrollRef.value.scrollTop = scrollRef.value.scrollHeight
  })
}

async function fetchConversations() {
  const data = await listConversations({ page: 1, page_size: 10 })
  conversations.value = data.list
}

async function fetchBooks() {
  const data = await listBooks({ page: 1, page_size: 50 })
  books.value = data.list
}

function newConversation() {
  conversationId.value = ''
  messages.value = []
  streamBuffer.value = ''
}

async function openConversation(c) {
  const data = await getConversation(c.conversation_id)
  conversationId.value = data.conversation_id
  messages.value = data.messages ?? []
  scrollToBottom()
}

async function onSend() {
  const text = input.value.trim()
  if (!text || sending.value) return

  const localUserMsg = { message_id: `local_${Date.now()}`, role: 'user', content: text, tokens: 0, created_at: new Date().toISOString() }
  messages.value.push(localUserMsg)
  input.value = ''
  sending.value = true
  scrollToBottom()

  try {
    if (useStream.value) {
      streaming.value = true
      streamBuffer.value = ''
      controller = chatStream(
        { conversation_id: conversationId.value, message: text, scene: 'qa', book_id: bookId.value || null },
        {
          onDelta: (delta) => {
            streamBuffer.value += delta
            scrollToBottom()
          },
          onDone: async () => {
            messages.value.push({ message_id: `local_${Date.now()}`, role: 'assistant', content: streamBuffer.value, tokens: 0, created_at: new Date().toISOString() })
            streamBuffer.value = ''
            streaming.value = false
            await fetchConversations()
            scrollToBottom()
          },
          onError: (err) => {
            streaming.value = false
            ElMessage.error(err?.message || '流式请求失败')
          }
        }
      )
    } else {
      const data = await chat({ conversation_id: conversationId.value, message: text, scene: 'qa', book_id: bookId.value || null })
      conversationId.value = data.conversation_id
      messages.value.push(data.message)
      await fetchConversations()
      scrollToBottom()
    }
  } finally {
    sending.value = false
  }
}

onMounted(async () => {
  await Promise.all([fetchConversations(), fetchBooks()])
})
</script>

<style scoped>
.header-actions {
  display: flex;
  align-items: center;
  gap: 14px;
}

.chat-panel {
  background: #fff;
  border-radius: var(--sr-card-radius);
  display: flex;
  flex-direction: column;
  height: calc(100vh - 190px);
  min-height: 460px;
}

.chat-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.msg-row {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}

.msg-row.user {
  flex-direction: row-reverse;
}

.msg-avatar {
  flex: 0 0 auto;
  background: #eef2ff;
  color: #2f54eb;
}

.msg-bubble {
  max-width: 74%;
}

.msg-content {
  white-space: pre-wrap;
  line-height: 1.75;
  padding: 10px 14px;
  border-radius: 10px;
  background: #f5f7fb;
}

.msg-row.user .msg-content {
  background: #e8f0ff;
}

.msg-meta {
  font-size: 11px;
  margin-top: 4px;
}

.cursor {
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.chat-input {
  border-top: 1px solid #eef1f6;
  padding: 12px 16px 16px;
}

.chat-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
}

.section-title {
  font-size: 15px;
  margin: 0 0 10px;
}

.conv-item {
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  border: 1px solid transparent;
}

.conv-item:hover {
  background: #f7f9ff;
}

.conv-item.active {
  background: #eef2ff;
  border-color: #c7d5ff;
}

.conv-title {
  font-size: 13px;
  font-weight: 500;
}

.conv-sub {
  font-size: 11px;
}

.api-list {
  margin: 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 2;
  color: #4b5563;
}
</style>
