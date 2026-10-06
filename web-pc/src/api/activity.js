/** 活动管理接口 */
import request from './request'

export const listActivities = (params) => request.get('/activities', { params })
export const getActivity = (id) => request.get(`/activities/${id}`)
export const createActivity = (data) => request.post('/activities', data)
export const updateActivity = (id, data) => request.patch(`/activities/${id}`, data)
export const deleteActivity = (id) => request.delete(`/activities/${id}`)
export const changeActivityStatus = (id, target_status, reason = '') =>
  request.post(`/activities/${id}/status`, { target_status, reason })
export const activityStats = () => request.get('/activities/stats')
export const generateActivityCopy = (id, style = 'xiaohongshu') =>
  request.post(`/activities/${id}/ai-copy`, null, { params: { style } })
