/** 活动总结与站内推送接口 */
import request from './request'

export const getActivitySummary = (activityId) => request.get(`/activities/${activityId}/summary`)
export const saveActivitySummary = (activityId, data) => request.post(`/activities/${activityId}/summary`, data)
export const publishSummary = (summaryId, targetRoles) =>
  request.post(`/summaries/${summaryId}/publish`, { target_roles: targetRoles })
export const listNotifications = (params) => request.get('/notifications', { params })
