import { createRouter, createWebHashHistory } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/store/user'
import { PERM } from '@/constants'

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/Login.vue'),
    meta: { title: '登录', public: true }
  },
  {
    path: '/register',
    name: 'register',
    component: () => import('@/views/Register.vue'),
    meta: { title: '注册', public: true }
  },
  {
    path: '/',
    component: () => import('@/layouts/BasicLayout.vue'),
    redirect: '/dashboard',
    children: [
      {
        path: 'profile',
        name: 'profile',
        component: () => import('@/views/Profile.vue'),
        meta: { title: '个人中心', hidden: true }
      },
      {
        path: 'dashboard',
        name: 'dashboard',
        component: () => import('@/views/Dashboard.vue'),
        meta: { title: '首页概览', icon: 'Odometer', menu: true, permission: PERM.ACTIVITY_VIEW }
      },
      {
        path: 'activities',
        name: 'activity-home',
        component: () => import('@/views/activity/ActivityFeed.vue'),
        meta: { title: '活动', icon: 'Calendar', menu: true, permission: PERM.ACTIVITY_VIEW }
      },
      {
        path: 'activities/create',
        name: 'activity-create',
        component: () => import('@/views/activity/ActivityForm.vue'),
        meta: { title: '申办活动', hidden: true, activeMenu: '/activities', permission: PERM.ACTIVITY_CREATE }
      },
      {
        path: 'activities/review',
        name: 'activity-review',
        component: () => import('@/views/activity/ActivityReview.vue'),
        meta: { title: '活动审批', icon: 'Stamp', menu: true, permission: PERM.ACTIVITY_REVIEW }
      },
      {
        path: 'activities/:id',
        name: 'activity-detail',
        component: () => import('@/views/activity/ActivityDetail.vue'),
        meta: { title: '活动详情', hidden: true, activeMenu: '/activities', permission: PERM.ACTIVITY_VIEW }
      },
      {
        path: 'activities/:id/edit',
        name: 'activity-edit',
        component: () => import('@/views/activity/ActivityForm.vue'),
        meta: { title: '编辑活动', hidden: true, activeMenu: '/activities', permission: PERM.ACTIVITY_CREATE }
      },
      {
        path: 'activities/:id/summary',
        name: 'activity-summary-edit',
        component: () => import('@/views/activity/SummaryEdit.vue'),
        meta: { title: '活动总结', hidden: true, activeMenu: '/activities', permission: PERM.ACTIVITY_CREATE }
      },
      {
        path: 'certificates',
        name: 'certificate-mine',
        component: () => import('@/views/certificate/CertificateMine.vue'),
        meta: { title: '我的证书', icon: 'Medal', menu: true, permission: PERM.CERTIFICATE_VIEW, roles: ['student'] }
      },
      {
        path: 'notifications',
        name: 'notifications',
        component: () => import('@/views/NotificationList.vue'),
        meta: { title: '消息推送', icon: 'Bell', menu: true, permission: PERM.ACTIVITY_VIEW }
      },
      {
        path: 'agents',
        name: 'agent-workbench',
        component: () => import('@/views/agent/AgentWorkbench.vue'),
        meta: { title: '智能体工作台', icon: 'Cpu', menu: true, permission: PERM.AI_RECOMMEND }
      },
      {
        path: 'ai/recommend',
        name: 'ai-recommend',
        component: () => import('@/views/ai/Recommend.vue'),
        meta: { title: 'AI 智能推荐', icon: 'MagicStick', menu: true, permission: PERM.AI_RECOMMEND }
      },
      {
        path: 'ai/assistant',
        name: 'ai-assistant',
        component: () => import('@/views/ai/Assistant.vue'),
        meta: { title: 'AI 阅读助手', icon: 'ChatDotRound', menu: true, permission: PERM.AI_CHAT }
      },
      {
        path: 'drift',
        name: 'drift',
        component: () => import('@/views/drift/DriftList.vue'),
        meta: { title: '图书漂流', icon: 'Van', menu: true, permission: PERM.DRIFT_VIEW }
      },
      {
        path: 'system/users',
        name: 'system-users',
        component: () => import('@/views/system/UserPermission.vue'),
        meta: { title: '用户与权限', icon: 'User', menu: true, permission: PERM.SYSTEM_PERMISSION }
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

  const needed = to.meta.permission
  if (needed && !store.can(needed)) {
    ElMessage.warning('当前账号没有该页面的访问权限')
    return { name: 'dashboard' }
  }
  const onlyRoles = to.meta.roles
  if (onlyRoles && !onlyRoles.includes(store.role)) {
    ElMessage.warning('当前账号无法访问该页面')
    return { name: 'dashboard' }
  }
  return true
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · 智阅校园` : '智阅校园 · PC 端平台'
})

export default router
