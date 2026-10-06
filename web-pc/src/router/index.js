import { createRouter, createWebHashHistory } from 'vue-router'
import { useUserStore } from '@/store/user'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录', public: true }
  },
  {
    path: '/',
    component: () => import('@/layouts/BasicLayout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '首页概览', icon: 'Odometer' }
      },
      {
        path: 'activities',
        name: 'activity-list',
        component: () => import('@/views/activity/ActivityList.vue'),
        meta: { title: '活动管理', icon: 'Calendar', roles: ['librarian', 'admin'] }
      },
      {
        path: 'activities/create',
        name: 'activity-create',
        component: () => import('@/views/activity/ActivityForm.vue'),
        meta: { title: '新建活动', hidden: true, activeMenu: '/activities', roles: ['librarian', 'admin'] }
      },
      {
        path: 'activities/:id',
        name: 'activity-detail',
        component: () => import('@/views/activity/ActivityDetail.vue'),
        meta: { title: '活动详情', hidden: true, activeMenu: '/activities' }
      },
      {
        path: 'activities/:id/edit',
        name: 'activity-edit',
        component: () => import('@/views/activity/ActivityForm.vue'),
        meta: { title: '编辑活动', hidden: true, activeMenu: '/activities', roles: ['librarian', 'admin'] }
      },
      {
        path: 'ai/recommend',
        name: 'ai-recommend',
        component: () => import('@/views/ai/Recommend.vue'),
        meta: { title: 'AI 智能推荐', icon: 'MagicStick' }
      },
      {
        path: 'ai/assistant',
        name: 'ai-assistant',
        component: () => import('@/views/ai/Assistant.vue'),
        meta: { title: 'AI 阅读助手', icon: 'ChatDotRound' }
      },
      {
        path: 'drift',
        name: 'drift',
        component: () => import('@/views/drift/DriftList.vue'),
        meta: { title: '图书漂流', icon: 'Van' }
      }
    ]
  },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFound.vue'), meta: { public: true } }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

router.beforeEach(async (to) => {
  const store = useUserStore()
  if (to.meta.public) return true
  if (!store.isLoggedIn) return { name: 'login', query: { redirect: to.fullPath } }

  if (!store.profile) {
    try {
      await store.fetchProfile()
    } catch {
      store.logout()
      return { name: 'login' }
    }
  }

  const roles = to.meta.roles
  if (roles?.length && !roles.includes(store.role)) return { name: 'dashboard' }
  return true
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · 智阅校园` : '智阅校园 · PC 端管理平台'
})

export default router
