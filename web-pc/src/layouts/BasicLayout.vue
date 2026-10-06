<template>
  <el-container class="layout">
    <el-aside width="220px" class="layout-aside">
      <div class="brand">
        <span class="brand-logo">智</span>
        <div class="brand-text">
          <strong>智阅校园</strong>
          <small>PC 端管理平台</small>
        </div>
      </div>

      <el-menu :default-active="activeMenu" router class="layout-menu">
        <el-menu-item v-for="item in visibleMenus" :key="item.path" :index="item.path">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.title }}</span>
        </el-menu-item>
      </el-menu>

      <div class="aside-foot">
        <el-tag size="small" type="success" effect="plain">第 1 轮 · 骨架版</el-tag>
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
          <el-tooltip content="接口连通性检查" placement="bottom">
            <el-tag :type="healthOk ? 'success' : 'danger'" effect="plain" size="small" class="health-tag">
              {{ healthOk ? '后端已连通' : '后端未连通' }}
            </el-tag>
          </el-tooltip>

          <el-dropdown @command="onCommand">
            <span class="user-info">
              <el-avatar :size="28" :src="store.profile?.avatar_url || ''">
                {{ store.profile?.name?.slice(0, 1) || 'U' }}
              </el-avatar>
              <span>{{ store.profile?.name || '未登录' }}</span>
              <el-tag size="small" effect="plain">{{ roleLabel }}</el-tag>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">个人信息</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <el-main class="layout-main">
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
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useUserStore } from '@/store/user'
import { health } from '@/api/user'
import { USER_ROLE, labelOf } from '@/constants'

const route = useRoute()
const router = useRouter()
const store = useUserStore()
const healthOk = ref(false)

const menus = [
  { path: '/dashboard', title: '首页概览', icon: 'Odometer' },
  { path: '/activities', title: '活动管理', icon: 'Calendar', roles: ['librarian', 'admin'] },
  { path: '/ai/recommend', title: 'AI 智能推荐', icon: 'MagicStick' },
  { path: '/ai/assistant', title: 'AI 阅读助手', icon: 'ChatDotRound' },
  { path: '/drift', title: '图书漂流', icon: 'Van' }
]

const visibleMenus = computed(() => menus.filter((m) => !m.roles || m.roles.includes(store.role)))
const activeMenu = computed(() => route.meta.activeMenu || route.path)
const roleLabel = computed(() => labelOf(USER_ROLE, store.role))

onMounted(async () => {
  try {
    await health()
    healthOk.value = true
  } catch {
    healthOk.value = false
  }
})

async function onCommand(command) {
  if (command === 'profile') {
    ElMessage.info('个人信息页在第 2 轮实现（本轮用户信息已可从 /users/me 获取）')
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
</style>
