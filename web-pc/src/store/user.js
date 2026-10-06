/** 登录态与当前用户信息 */
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
    /** 是否为管理端角色（图书馆老师 / 系统管理员） */
    isStaff: (state) => ['librarian', 'admin'].includes(state.profile?.role ?? '')
  },
  actions: {
    async login(studentNo, password) {
      const data = await userApi.login(studentNo, password)
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
