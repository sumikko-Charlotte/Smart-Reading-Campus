/** 活动管理接口（第二阶段：审批 + 定级） */
import request from './request'

export const listActivities = (params) => request.get('/activities', { params })
export const getActivityFeed = (params) => request.get('/activities/feed', { params })
export const checkinActivity = (id) => request.post(`/activities/${id}/checkin`, {})
export const checkoutActivity = (id) => request.post(`/activities/${id}/checkout`, {})
export const listManagedActivities = (params) => request.get('/activities/managed', { params })
export const getActivity = (id) => request.get(`/activities/${id}`)
export const createActivity = (data) => request.post('/activities', data)
export const updateActivity = (id, data) => request.patch(`/activities/${id}`, data)
export const deleteActivity = (id) => request.delete(`/activities/${id}`)

/** 提交审批（草稿/驳回 → 待审批） */
export const submitActivity = (id, remark = '') => request.post(`/activities/${id}/submit`, { remark })
/** 审批（通过需定级，驳回需填意见） */
export const reviewActivity = (id, data) => request.post(`/activities/${id}/review`, data)
/** 运营类流转：报名截止 / 进行中 / 结束 / 取消 */
export const changeActivityStatus = (id, target_status, reason = '') =>
  request.post(`/activities/${id}/status`, { target_status, reason })

export const signupActivity = (id) => request.post(`/activities/${id}/signups`, {})
export const listMyActivities = (params) => request.get('/activities/mine', { params })
export const listActivitySignups = (id, params) => request.get(`/activities/${id}/signups`, { params })
export const activityStats = () => request.get('/activities/stats')
export const generateActivityCopy = (id, style = 'xiaohongshu') =>
  request.post(`/activities/${id}/ai-copy`, null, { params: { style } })
