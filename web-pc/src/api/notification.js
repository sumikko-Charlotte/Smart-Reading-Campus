/** 站内消息：列表、未读数、已读 */
import request from './request'

export const listNotifications = (params) => request.get('/notifications', { params })
export const getUnreadCount = () => request.get('/notifications/unread-count')
export const markNotificationRead = (id) => request.post(`/notifications/${id}/read`)
export const markAllNotificationsRead = () => request.post('/notifications/read-all')
