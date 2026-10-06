/**
 * axios 统一封装：对齐后端 {code, message, data, trace_id} 响应体。
 * 业务层拿到的是 data 本体，不需要再层层 .data.data。
 */
import axios from 'axios'
import { ElMessage } from 'element-plus'

const TOKEN_KEY = 'smart_reading_token'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 20000
})

service.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

service.interceptors.response.use(
  (response) => {
    const body = response.data
    // 非标准响应（如 SSE、文件流）直接透传
    if (body === null || typeof body !== 'object' || !('code' in body)) return body

    if (body.code === 0) return body.data

    if (body.code === 1002) {
      setToken('')
      ElMessage.error('登录已失效，请重新登录')
      if (!location.hash.includes('/login')) location.hash = '#/login'
      return Promise.reject(body)
    }

    ElMessage.error(body.message || '请求失败')
    return Promise.reject(body)
  },
  (error) => {
    const status = error.response?.status
    const msg = error.response?.data?.message || error.message || '网络异常'
    ElMessage.error(status === 404 ? '接口不存在，请确认后端已启动' : msg)
    return Promise.reject(error)
  }
)

export default service
