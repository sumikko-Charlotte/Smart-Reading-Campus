<template>
  <el-container class="layout">
    <el-aside width="220px" class="layout-aside">
      <div class="brand">
        <span class="brand-logo">智</span>
        <div class="brand-text">
          <strong>智阅校园</strong>
          <small>PC 端平台</small>
        </div>
      </div>

      <el-menu :default-active="activeMenu" router class="layout-menu">
        <el-menu-item v-for="item in visibleMenus" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </el-menu-item>
      </el-menu>

      <div class="aside-foot">
        <el-tag size="small" effect="plain" :type="store.isVisitor ? 'info' : 'success'">
          {{ store.isVisitor ? '访客只读模式' : store.roleLabel }}
        </el-tag>
      </div>
    </el-aside>

    <el-container>
      <el-header class="layout-header">
        <div class="header-left">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item>智阅校园</el-breadcrumb-item>
            <el-breadcrumb-item>{{ route.meta.title || '首页' }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>

        <div class="header-right">
          <el-tooltip content="服务状态" placement="bottom">
            <el-tag :type="healthOk ? 'success' : 'danger'" effect="plain" size="small" class="health-tag">
              {{ healthOk ? '服务正常' : '服务异常' }}
            </el-tag>
          </el-tooltip>

          <el-tooltip :content="unread ? `${unread} 条未读消息` : '消息中心'" placement="bottom">
            <el-badge :value="unread" :hidden="!unread" :max="99" class="msg-badge">
              <el-button text :icon="Bell" @click="$router.push('/notifications')">消息</el-button>
            </el-badge>
          </el-tooltip>

          <el-dropdown @command="onCommand">
            <span class="user-info">
              <el-avatar :size="28" :src="store.profile?.avatar_url || ''">
                {{ store.profile?.name?.slice(0, 1) || 'U' }}
              </el-avatar>
              <span>{{ store.profile?.name || '未登录' }}</span>
              <el-tag size="small" effect="plain" :type="roleType">{{ store.roleLabel || '—' }}</el-tag>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">个人中心</el-dropdown-item>
                <el-dropdown-item command="permissions">我的权限（{{ permissionCount }} 项）</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="layout-main">
        <el-alert
          v-if="store.isVisitor"
          class="visitor-tip"
          type="info"
          :closable="false"
          show-icon
          title="访客模式：以浏览为主，可在个人中心申请更多权限。"
        />
        <router-view v-slot="{ Component }">
          <keep-alive :max="5">
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { Bell } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'
import { health } from '@/api/user'
import { PERM, USER_ROLE, typeOf } from '@/constants'

const route = useRoute()
const router = useRouter()
const store = useUserStore()
const healthOk = ref(false)
// 未读数统一放在 store，消息页标记已读后可以直接回写，不必等轮询
const unread = computed(() => store.unread)
let unreadTimer = null

const menus = [
  { path: '/dashboard', title: '首页概览', icon: 'Odometer', permission: PERM.ACTIVITY_VIEW },
  { path: '/activities', title: '活动', icon: 'Calendar', permission: PERM.ACTIVITY_VIEW },
  { path: '/activities/review', title: '活动审批', icon: 'Stamp', permission: PERM.ACTIVITY_REVIEW },
  { path: '/certificates', title: '我的证书', icon: 'Medal', permission: PERM.CERTIFICATE_VIEW, roles: ['student'] },
  { path: '/ai/recommend', title: 'AI 智能推荐', icon: 'MagicStick', permission: PERM.AI_RECOMMEND },
  { path: '/agents', title: '智能体工作台', icon: 'Cpu', permission: PERM.AI_RECOMMEND },
  { path: '/ai/assistant', title: 'AI 阅读助手', icon: 'ChatDotRound', permission: PERM.AI_CHAT },
  { path: '/drift', title: '图书漂流', icon: 'Van', permission: PERM.DRIFT_VIEW },
  { path: '/system/users', title: '用户与权限', icon: 'User', permission: PERM.SYSTEM_PERMISSION },
  { path: '/profile', title: '个人中心', icon: 'Avatar' }
]

const visibleMenus = computed(() =>
  menus.filter(
    (m) =>
      (!m.permission || store.can(m.permission)) &&
      (!m.roles || m.roles.includes(store.role))
  )
)
const activeMenu = computed(() => route.meta.activeMenu || route.path)
const roleType = computed(() => typeOf(USER_ROLE, store.role))
const permissionCount = computed(() => store.permissions.length)

/**
 * 红点刷新策略（三条路一起兜）：
 * 1. 每 10 秒轮询一次，覆盖「别人那边产生了给我的消息」；
 * 2. 切页时刷新一次，避免刚审批完还显示旧数字；
 * 3. 页面内操作后派发 notify:refresh 立即拉取，做到「点完就变」。
 * 标签页切回前台也补一次，笔记本合盖回来不会停在旧状态。
 */
function refreshUnread() {
  if (store.isLoggedIn && document.visibilityState !== 'hidden') store.refreshUnread()
}

function onVisibilityChange() {
  if (document.visibilityState === 'visible') refreshUnread()
}

onMounted(async () => {
  try {
    await health()
    healthOk.value = true
  } catch {
    healthOk.value = false
  }
  await store.refreshUnread()
  unreadTimer = setInterval(refreshUnread, 10000)
  window.addEventListener('notify:refresh', refreshUnread)
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onUnmounted(() => {
  if (unreadTimer) clearInterval(unreadTimer)
  window.removeEventListener('notify:refresh', refreshUnread)
  document.removeEventListener('visibilitychange', onVisibilityChange)
})

watch(() => route.fullPath, refreshUnread)

async function onCommand(command) {
  if (command === 'profile') {
    router.push('/profile')
    return
  }
  if (command === 'permissions') {
    router.push({ path: '/profile', query: { tab: 'permissions' } })
    return
  }
  await ElMessageBox.confirm('确认退出登录吗？', '提示', { type: 'warning' })
  store.logout()
  router.push({ name: 'login' })
}
</script>

<style scoped>
.layout {
  height: 100%;
}

.layout-aside {
  background: #fff;
  border-right: 1px solid #e8ebf2;
  display: flex;
  flex-direction: column;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px;
  border-bottom: 1px solid #eef1f6;
}

.brand-logo {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: var(--sr-primary);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
}

.brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.3;
}

.brand-text small {
  color: #909399;
  font-size: 12px;
}

.layout-menu {
  border-right: none;
  flex: 1;
  overflow-y: auto;
}

.aside-foot {
  padding: 12px 16px;
}

.layout-header {
  background: #fff;
  border-bottom: 1px solid #e8ebf2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 14px;
}

.health-tag {
  cursor: default;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  outline: none;
}

.layout-main {
  padding: 0;
  overflow-y: auto;
}

.visitor-tip {
  margin: 16px 16px 0;
}
</style>
