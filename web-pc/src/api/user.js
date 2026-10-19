/** 用户、权限与鉴权接口 */
import request from './request'

export const login = (student_no, password) => request.post('/auth/login', { student_no, password })
export const register = (data) => request.post('/auth/register', data)
export const guestLogin = () => request.post('/auth/guest')
export const getProfile = () => request.get('/users/me')
export const updateProfile = (data) => request.patch('/users/me', data)
export const changePassword = (data) => request.patch('/users/me/password', data)
export const listUsers = (params) => request.get('/users', { params })
export const createUser = (data) => request.post('/users', data)
export const updateUser = (id, data) => request.patch(`/users/${id}`, data)
export const health = () => request.get('/health')

// ---- 权限分配（系统管理员） ----
export const getPermissionCatalog = () => request.get('/permissions/catalog')
export const getUserPermissions = (id) => request.get(`/users/${id}/permissions`)
export const updateUserPermissions = (id, data) => request.patch(`/users/${id}/permissions`, data)
export const updateUserRole = (id, data) => request.patch(`/users/${id}/role`, data)
export const listPermissionLogs = (params) => request.get('/permission-logs', { params })

// ---- 权限申请 ----
export const createPermissionRequest = (data) => request.post('/permission-requests', data)
export const listMyPermissionRequests = (params) => request.get('/permission-requests/mine', { params })
export const cancelPermissionRequest = (id) => request.post(`/permission-requests/${id}/cancel`)
export const listPermissionRequests = (params) => request.get('/permission-requests', { params })
export const reviewPermissionRequest = (id, data) => request.post(`/permission-requests/${id}/review`, data)
export const permissionRequestSummary = () => request.get('/permission-requests/summary')
