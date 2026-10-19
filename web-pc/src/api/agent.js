/** 智能体接口：四个场景共用一个入口 */
import request from './request'

export const agentHealth = () => request.get('/agents/health')
export const agentTools = () => request.get('/agents/tools')
export const agentDataset = () => request.get('/agents/dataset')
export const listAgentRuns = (params) => request.get('/agents/runs', { params })
export const getAgentRun = (runId) => request.get(`/agents/runs/${runId}`)

/** 执行一次智能体任务，scene ∈ intake / match / outreach / companion */
export const runAgent = (scene, payload) => request.post(`/agents/${scene}/run`, payload, { timeout: 120000 })
