/** 登录态、当前用户与权限判断 */
import { defineStore } from 'pinia'
import * as userApi from '@/api/user'
import { getToken, setToken } from '@/api/request'

export const useUserStore = defineStore('user', {
  state: () => ({
    token: getToken(),
    profile: null
  }),
  getters: {
    isLoggedIn: (state) => Boolean(state.token),
    role: (state) => state.profile?.role ?? '',
    roleLabel: (state) => state.profile?.role_label ?? '',
    permissions: (state) => state.profile?.permissions ?? [],
    /** 管理员（普通 + 系统） */
    isStaff: (state) => ['admin', 'super_admin'].includes(state.profile?.role ?? ''),
    isSuperAdmin: (state) => (state.profile?.role ?? '') === 'super_admin',
    isVisitor: (state) => (state.profile?.role ?? '') === 'visitor'
  },
  actions: {
    /** 权限判断：can('activity:review') / can([a,b]) 需全部命中 */
    can(code) {
      const codes = Array.isArray(code) ? code : [code]
      const owned = this.profile?.permissions ?? []
      return codes.every((item) => owned.includes(item))
    },
    canAny(codes) {
      const owned = this.profile?.permissions ?? []
      return codes.some((item) => owned.includes(item))
    },
    async login(studentNo, password) {
      const data = await userApi.login(studentNo, password)
      this.token = data.token
      this.profile = data.user
      setToken(data.token)
      return data
    },
    /** 注册：role 只允许 student / admin，后端校验，注册成功直接进入登录态 */
    async register(payload) {
      const data = await userApi.register(payload)
      this.token = data.token
      this.profile = data.user
      setToken(data.token)
      return data
    },
    /** 访客：不注册、不登录，直接拿只读身份 */
    async guestLogin() {
      const data = await userApi.guestLogin()
      this.token = data.token
      this.profile = data.user
      setToken(data.token)
      return data
    },
    async fetchProfile() {
      if (!this.token) return null
      this.profile = await userApi.getProfile()
      return this.profile
    },
    logout() {
      this.token = ''
      this.profile = null
      setToken('')
    }
  }
})
