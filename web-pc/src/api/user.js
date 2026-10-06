/** 用户与鉴权接口 */
import request from './request'

export const login = (student_no, password) => request.post('/auth/login', { student_no, password })
export const getProfile = () => request.get('/users/me')
export const updateProfile = (data) => request.patch('/users/me', data)
export const listUsers = (params) => request.get('/users', { params })
export const createUser = (data) => request.post('/users', data)
export const updateUser = (id, data) => request.patch(`/users/${id}`, data)
export const health = () => request.get('/health')
