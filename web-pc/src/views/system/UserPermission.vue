<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">用户与权限</h2>
        <p class="page-desc">
          三类角色（访客 / 学生 / 管理员），管理员分普通与系统两级；权限逐项分配、即时生效，全部变更留痕。
        </p>
      </div>
      <el-button :icon="Refresh" @click="refresh">刷新</el-button>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane label="用户权限" name="users">
        <div class="filter-bar">
          <el-form :inline="true" :model="query" @submit.prevent>
            <el-form-item label="关键词">
              <el-input v-model="query.keyword" placeholder="姓名 / 学号 / 学院" clearable style="width: 200px" @keyup.enter="onSearch" />
            </el-form-item>
            <el-form-item label="角色">
              <el-select v-model="query.role" placeholder="全部角色" clearable style="width: 150px">
                <el-option v-for="r in USER_ROLE" :key="r.value" :label="r.label" :value="r.value" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :icon="Search" @click="onSearch">查询</el-button>
            </el-form-item>
          </el-form>
        </div>

        <div class="card-block">
          <el-table v-loading="loading" :data="users" stripe border>
            <el-table-column label="用户" min-width="170">
              <template #default="{ row }">
                <div class="cell-title">{{ row.name }}</div>
                <div class="text-muted cell-sub">{{ row.student_no }} · {{ row.college || '—' }}</div>
              </template>
            </el-table-column>
            <el-table-column label="角色" width="200">
              <template #default="{ row }">
                <el-select
                  :model-value="row.role"
                  size="small"
                  :disabled="row.role === 'super_admin' || row.user_id === store.profile?.user_id"
                  @change="(role) => onRoleChange(row, role)"
                >
                  <el-option v-for="r in roleOptions" :key="r.value" :label="r.label" :value="r.value" />
                </el-select>
                <div v-if="row.role === 'super_admin'" class="text-muted cell-sub">系统管理员不可在此调整</div>
              </template>
            </el-table-column>
            <el-table-column label="有效权限" min-width="240">
              <template #default="{ row }">
                <div class="perm-tags">
                  <el-tag
                    v-for="code in row.permissions.slice(0, 6)"
                    :key="code"
                    size="small"
                    effect="plain"
                    class="perm-tag"
                  >{{ permName(code) }}</el-tag>
                  <el-tag v-if="row.permissions.length > 6" size="small" type="info" effect="plain">
                    +{{ row.permissions.length - 6 }}
                  </el-tag>
                </div>
                <div v-if="row.revoked_permissions?.length" class="text-muted cell-sub">
                  已收回 {{ row.revoked_permissions.length }} 项默认权限
                </div>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="90" align="center">
              <template #default="{ row }">
                <el-tag :type="row.status === 'active' ? 'success' : 'danger'" effect="plain" size="small">
                  {{ row.status === 'active' ? '正常' : '禁用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="130" fixed="right">
              <template #default="{ row }">
                <el-button
                  text
                  type="primary"
                  size="small"
                  :disabled="row.role === 'super_admin' || row.user_id === store.profile?.user_id"
                  @click="openPermEditor(row)"
                >分配权限</el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="pager">
            <el-pagination
              v-model:current-page="query.page"
              v-model:page-size="query.page_size"
              :total="total"
              layout="total, prev, pager, next"
              background
              @current-change="fetchUsers"
            />
          </div>
        </div>
      </el-tab-pane>

      <el-tab-pane label="变更日志" name="logs">
        <div class="card-block">
          <el-table v-loading="logsLoading" :data="logs" stripe border>
            <el-table-column label="时间" width="170">
              <template #default="{ row }">{{ formatDateTime(row.created_at, true) }}</template>
            </el-table-column>
            <el-table-column label="操作人" width="130" prop="operator_name" />
            <el-table-column label="对象" width="150">
              <template #default="{ row }">{{ row.target_user_name }}</template>
            </el-table-column>
            <el-table-column label="动作" width="110" align="center">
              <template #default="{ row }">
                <el-tag :type="row.action === 'grant' ? 'success' : row.action === 'revoke' ? 'danger' : 'warning'" effect="plain" size="small">
                  {{ { grant: '授予', revoke: '收回', role_change: '角色调整' }[row.action] || row.action }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="内容" min-width="180">
              <template #default="{ row }">
                {{ row.action === 'role_change' ? `角色：${row.before_value} → ${row.after_value}` : permName(row.permission) }}
              </template>
            </el-table-column>
            <el-table-column prop="remark" label="备注" min-width="160" show-overflow-tooltip />
            <template #empty>
              <el-empty description="暂无变更记录" />
            </template>
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 权限分配抽屉 -->
    <el-drawer v-model="drawer.visible" :title="`分配权限 · ${drawer.user?.name || ''}`" size="520px">
      <el-alert
        class="mb-12"
        type="info"
        :closable="false"
        show-icon
        title="勾选 = 允许；取消勾选默认权限 = 收回。保存后立即生效（下次请求即按新权限校验）。"
      />
      <div class="drawer-user">
        <el-tag :type="typeOf(USER_ROLE, drawer.summary?.role)" effect="plain">
          {{ drawer.summary?.role_label }}
        </el-tag>
        <span class="text-muted" style="margin-left: 8px">
          默认 {{ drawer.summary?.default_permissions?.length || 0 }} 项 · 额外授予 {{ drawer.summary?.granted_permissions?.length || 0 }} 项
        </span>
      </div>

      <div v-for="group in catalog" :key="group.group" class="perm-group">
        <h4 class="group-title">{{ group.group }}</h4>
        <el-checkbox
          v-for="item in group.items"
          :key="item.code"
          :model-value="checked.has(item.code)"
          :disabled="item.code === 'system:permission'"
          class="perm-checkbox"
          @change="(val) => toggle(item, val)"
        >
          <span class="perm-name">{{ item.name }}</span>
          <span class="text-muted perm-desc">{{ item.description }}</span>
          <el-tag v-if="isDefault(item.code)" size="small" effect="plain" type="info" class="perm-default">角色默认</el-tag>
          <el-tag v-else-if="isGranted(item.code)" size="small" effect="plain" type="success" class="perm-default">额外授予</el-tag>
        </el-checkbox>
      </div>

      <el-form label-width="70px" class="remark-form">
        <el-form-item label="变更原因">
          <el-input v-model="drawer.remark" placeholder="写入审计日志，如：学生会推荐 / 任期结束" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="drawer.visible = false">取消</el-button>
        <el-button type="primary" :loading="drawer.saving" @click="onSavePermissions">保存并生效</el-button>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Search } from '@element-plus/icons-vue'
import {
  getPermissionCatalog,
  getUserPermissions,
  listPermissionLogs,
  listUsers,
  updateUserPermissions,
  updateUserRole
} from '@/api/user'
import { useUserStore } from '@/store/user'
import { USER_ROLE, typeOf } from '@/constants'
import { formatDateTime } from '@/utils/format'

const store = useUserStore()
const activeTab = ref('users')
const loading = ref(false)
const logsLoading = ref(false)
const users = ref([])
const total = ref(0)
const logs = ref([])
const catalog = ref([])
const permMap = ref({})

const query = reactive({ page: 1, page_size: 10, keyword: '', role: '' })

const drawer = reactive({ visible: false, user: null, summary: null, remark: '', saving: false })

/** 当前抽屉里勾选的权限（有效权限镜像） */
const checked = reactive(new Set())

/** 系统管理员不能在页面里提级/降级任何人到 super_admin，也不能动自己 */
const roleOptions = computed(() => USER_ROLE.filter((r) => r.value !== 'super_admin'))

function permName(code) {
  return permMap.value[code] || code
}

function isDefault(code) {
  return drawer.summary?.default_permissions?.includes(code)
}

function isGranted(code) {
  return drawer.summary?.granted_permissions?.includes(code)
}

async function fetchUsers() {
  loading.value = true
  try {
    const data = await listUsers({ ...query, keyword: query.keyword || undefined, role: query.role || undefined })
    users.value = data.list
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function fetchLogs() {
  logsLoading.value = true
  try {
    const data = await listPermissionLogs({ page: 1, page_size: 20 })
    logs.value = data.list
  } finally {
    logsLoading.value = false
  }
}

function onSearch() {
  query.page = 1
  fetchUsers()
}

async function openPermEditor(row) {
  drawer.user = row
  drawer.summary = await getUserPermissions(row.user_id)
  drawer.remark = ''
  checked.clear()
  drawer.summary.permissions.forEach((code) => checked.add(code))
  drawer.visible = true
}

function toggle(item, val) {
  if (val) checked.add(item.code)
  else checked.delete(item.code)
}

async function onSavePermissions() {
  const effective = new Set(drawer.summary.permissions)
  const grant = [...checked].filter((code) => !effective.has(code))
  const revoke = [...effective].filter((code) => !checked.has(code))
  if (!grant.length && !revoke.length) {
    ElMessage.info('没有权限变化')
    return
  }
  drawer.saving = true
  try {
    await updateUserPermissions(drawer.user.user_id, { grant, revoke, remark: drawer.remark || 'PC 端分配' })
    ElMessage.success(`已更新：授予 ${grant.length} 项、收回 ${revoke.length} 项`)
    drawer.visible = false
    await Promise.all([fetchUsers(), fetchLogs()])
  } finally {
    drawer.saving = false
  }
}

async function onRoleChange(row, role) {
  try {
    await ElMessageBox.confirm(
      `将「${row.name}」的角色改为「${roleOptions.value.find((r) => r.value === role)?.label}」？\n调整后按新角色的默认权限执行（个人化权限清空）。`,
      '角色调整',
      { type: 'warning' }
    )
  } catch {
    return
  }
  await updateUserRole(row.user_id, { role, remark: 'PC 端调整' })
  ElMessage.success('角色已调整')
  fetchUsers()
  fetchLogs()
}

async function refresh() {
  await Promise.all([fetchUsers(), activeTab.value === 'logs' ? fetchLogs() : Promise.resolve()])
}

onMounted(async () => {
  const data = await getPermissionCatalog()
  catalog.value = data.groups
  permMap.value = Object.fromEntries(data.groups.flatMap((g) => g.items.map((i) => [i.code, i.name])))
  await refresh()
})
</script>

<style scoped>
.mb-12 {
  margin-bottom: 12px;
}

.cell-title {
  font-weight: 500;
}

.cell-sub {
  font-size: 12px;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}

.perm-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.perm-tag {
  font-size: 12px;
}

.drawer-user {
  margin-bottom: 12px;
}

.perm-group {
  margin-bottom: 12px;
}

.group-title {
  margin: 8px 0;
  color: #374151;
}

.perm-checkbox {
  display: flex;
  align-items: flex-start;
  margin: 6px 0;
}

.perm-name {
  font-weight: 500;
  margin-right: 8px;
}

.perm-desc {
  font-size: 12px;
}

.perm-default {
  margin-left: 8px;
}

.remark-form {
  margin-top: 16px;
}
</style>
