/** 图书 / AI 能力 / 图书漂流接口 */
import request from './request'

// ---------- 图书 ----------
export const listBooks = (params) => request.get('/books', { params })
export const getBook = (id) => request.get(`/books/${id}`)
export const getBookByIsbn = (isbn) => request.get(`/books/isbn/${isbn}`)
export const createBook = (data) => request.post('/books', data)
export const updateBook = (id, data) => request.patch(`/books/${id}`, data)
export const buildBookAiSummary = (id, forceRefresh = false) =>
  request.post(`/books/${id}/ai-summary`, null, { params: { force_refresh: forceRefresh } })
export const recommendBooks = (data) => request.post('/books/recommend', data)

// ---------- AI 会话 ----------
export const chat = (data) => request.post('/ai/chat', data)
export const listConversations = (params) => request.get('/ai/conversations', { params })
export const getConversation = (id) => request.get(`/ai/conversations/${id}`)
export const deleteConversation = (id) => request.delete(`/ai/conversations/${id}`)
export const generateCopywriting = (data) => request.post('/ai/copywriting', data)

/**
 * SSE 流式对话：与后端 /api/v1/ai/chat?stream=true 的帧格式一致。
 * 后续可替换为 fetch + ReadableStream 以获得更好的中断控制。
 */
export function chatStream(data, { onDelta, onDone, onError } = {}) {
  const controller = new AbortController()
  const token = localStorage.getItem('smart_reading_token') || ''

  fetch(`${import.meta.env.VITE_API_BASE_URL || '/api/v1'}/ai/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify({ ...data, stream: true }),
    signal: controller.signal
  })
    .then(async (resp) => {
      if (!resp.ok || !resp.body) throw new Error(`流式请求失败：${resp.status}`)
      const reader = resp.body.getReader()
      const decoder = new TextDecoder('utf-8')
      let buffer = ''
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const frames = buffer.split('\n\n')
        buffer = frames.pop() ?? ''
        for (const frame of frames) {
          const line = frame.trim()
          if (!line.startsWith('data:')) continue
          const payloadText = line.slice(5).trim()
          if (payloadText === '[DONE]') return onDone?.()
          try {
            const payload = JSON.parse(payloadText)
            if (payload.finished) onDone?.(payload)
            else onDelta?.(payload.delta, payload)
          } catch (err) {
            // 忽略无法解析的单帧，避免整条流中断
          }
        }
      }
      onDone?.()
    })
    .catch((err) => {
      if (err.name !== 'AbortError') onError?.(err)
    })

  return controller
}

// ---------- 图书漂流 ----------
export const listDriftBooks = (params) => request.get('/drift/books', { params })
export const listDriftRecords = (params) => request.get('/drift/records', { params })
export const driftStats = () => request.get('/drift/stats')
export const putBookOnShelf = (data) => request.post('/drift/books', data)
export const claimDriftBook = (bookId) => request.post(`/drift/books/${bookId}/claim`)
