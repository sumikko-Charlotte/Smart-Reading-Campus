<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">个人中心</h2>
        <p class="page-desc">个人资料、权限与安全设置。</p>
      </div>
      <el-button :icon="Refresh" @click="loadAll">刷新</el-button>
    </div>

    <div class="profile-top">
      <el-avatar :size="56" :src="profile.avatar_url || ''">{{ profile.name?.slice(0, 1) || 'U' }}</el-avatar>
      <div class="profile-id">
        <div class="name-row">
          <strong>{{ profile.name || '—' }}</strong>
          <el-tag :type="typeOf(USER_ROLE, profile.role)" effect="plain" size="small">{{ profile.role_label }}</el-tag>
        </div>
        <div class="text-muted">
          {{ profile.student_no }} · {{ profile.college || '未填写学院/部门' }} · 注册于 {{ formatDateTime(profile.created_at) }}
        </div>
      </div>
      <div class="profile-stats">
        <div class="stat-item">
          <strong>{{ summary.permissions?.length || 0 }}</strong>
          <span>当前有效权限</span>
        </div>
        <div class="stat-item">
          <strong>{{ summary.granted_permissions?.length || 0 }}</strong>
          <span>额外授予</span>
        </div>
        <div class="stat-item">
          <strong>{{ pendingCount }}</strong>
          <span>审批中申请</span>
        </div>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="profile-tabs">
      <!-- 1. 个人资料 -->
      <el-tab-pane label="个人资料" name="info">
        <div class="card-block">
          <el-alert
            v-if="isVisitor"
            class="mb-12"
            type="info"
            :closable="false"
            show-icon
            title="访客是公共只读账号，资料不可修改；如需报名、申办或使用更多功能，请在「我的权限」中提交申请。"
          />
          <el-form ref="infoRef" :model="info" label-width="90px" class="info-form" :disabled="isVisitor">
            <div class="form-grid">
              <el-form-item label="姓名" prop="name" :rules="[{ required: true, message: '请输入姓名', trigger: 'blur' }]">
                <el-input v-model="info.name" placeholder="真实姓名" />
              </el-form-item>
              <el-form-item label="学号/工号">
                <el-input :model-value="profile.student_no" disabled />
              </el-form-item>
            </div>
            <div class="form-grid">
              <el-form-item :label="isStaff ? '所属部门' : '学院'">
                <el-input v-model="info.college" :placeholder="isStaff ? '如图书馆' : '如计算机学院'" />
              </el-form-item>
              <el-form-item label="专业" v-if="!isStaff">
                <el-input v-model="info.major" placeholder="如计算机科学与技术" />
              </el-form-item>
            </div>
            <div class="form-grid" v-if="!isStaff">
              <el-form-item label="年级">
                <el-input v-model="info.grade" placeholder="如 2023" />
              </el-form-item>
              <el-form-item label="班级">
                <el-input v-model="info.class_no" placeholder="如 2023211301" />
              </el-form-item>
            </div>
            <div class="form-grid">
              <el-form-item label="手机号">
                <el-input v-model="info.phone" placeholder="仅本人与系统管理员可见完整号码" />
              </el-form-item>
              <el-form-item label="邮箱">
                <el-input v-model="info.email" placeholder="name@example.edu.cn" />
              </el-form-item>
            </div>
            <el-form-item v-if="!isVisitor">
              <el-button type="primary" :loading="savingInfo" @click="onSaveInfo">保存资料</el-button>
            </el-form-item>
          </el-form>
        </div>
      </el-tab-pane>

      <!-- 2. 我的权限 -->
      <el-tab-pane label="我的权限" name="permissions">
        <div class="card-block">
          <div class="perm-toolbar">
            <div>
              <el-tag effect="plain" size="small">角色默认 {{ summary.default_permissions?.length || 0 }} 项</el-tag>
              <el-tag effect="plain" type="success" size="small" class="ml-6">额外授予 {{ summary.granted_permissions?.length || 0 }} 项</el-tag>
              <el-tag effect="plain" type="danger" size="small" class="ml-6">被收回 {{ summary.revoked_permissions?.length || 0 }} 项</el-tag>
            </div>
            <div>
              <el-button
                type="primary"
                :icon="Plus"
                :disabled="!canRequest || availableCodes.length === 0"
                @click="openRequest"
              >
                申请权限
              </el-button>
            </div>
          </div>

          <el-alert
            class="mb-12"
            type="info"
            :closable="false"
            show-icon
            title="有效权限 = 角色默认 − 被收回 + 额外授予。权限变更后立即生效，无需重新登录。"
          />

          <div v-for="group in catalog" :key="group.group" class="perm-group">
            <h4 class="group-title">{{ group.group }}</h4>
            <div class="perm-grid">
              <div
                v-for="item in group.items"
                :key="item.code"
                class="perm-item"
                :class="{ owned: isOwned(item.code), revoked: isRevoked(item.code) }"
              >
                <div class="perm-item-head">
                  <span class="perm-item-name">{{ item.name }}</span>
                  <el-tag size="small" effect="plain" :type="sourceType(item.code)">{{ sourceLabel(item.code) }}</el-tag>
                </div>
                <div class="text-muted perm-item-desc">{{ item.description }}</div>
                <div class="perm-code">{{ item.code }}</div>
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- 3. 我的申请 -->
      <el-tab-pane name="requests">
        <template #label>
          我的申请
          <el-badge v-if="pendingCount" :value="pendingCount" class="tab-badge" />
        </template>
        <div class="card-block">
          <div class="filter-bar">
            <el-form :inline="true" @submit.prevent>
              <el-form-item label="状态">
                <el-select v-model="requestStatus" placeholder="全部状态" clearable style="width: 150px" @change="fetchMine">
                  <el-option v-for="s in REQUEST_STATUS" :key="s.value" :label="s.label" :value="s.value" />
                </el-select>
              </el-form-item>
            </el-form>
            <el-button type="primary" :icon="Plus" @click="openRequest">发起申请</el-button>
          </div>

          <el-table v-loading="mineLoading" :data="mine" stripe border>
            <el-table-column label="申请权限" min-width="220">
              <template #default="{ row }">
                <el-tag v-for="code in row.permissions" :key="code" size="small" effect="plain" class="perm-tag">
                  {{ permName(code) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="reason" label="申请理由" min-width="200" show-overflow-tooltip />
            <el-table-column label="状态" width="100" align="center">
              <template #default="{ row }">
                <el-tag :type="statusType(row.status)" effect="plain" size="small">{{ row.status_label }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="提交时间" width="165">
              <template #default="{ row }">{{ formatDateTime(row.created_at, true) }}</template>
            </el-table-column>
            <el-table-column label="审批意见" min-width="180">
              <template #default="{ row }">
                <div v-if="row.reviewer_name" class="review-cell">
                  <span>{{ row.reviewer_name }}：{{ row.review_comment || '（未填写）' }}</span>
                  <span class="text-muted">{{ formatDateTime(row.reviewed_at, true) }}</span>
                </div>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="90" align="center">
              <template #default="{ row }">
                <el-button
                  v-if="row.status === 'pending'"
                  text
                  type="danger"
                  size="small"
                  @click="onCancel(row)"
                >撤回</el-button>
                <span v-else class="text-muted">—</span>
              </template>
            </el-table-column>
            <template #empty>
              <el-empty description="还没有提交过权限申请" />
            </template>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- 4. 账号安全（访客账号无密码，不展示） -->
      <el-tab-pane v-if="!isVisitor" label="账号安全" name="security">
        <div class="card-block security-block">
          <el-form ref="pwdRef" :model="pwd" label-width="100px" class="pwd-form">
            <el-form-item label="原密码" prop="old_password" :rules="[{ required: true, message: '请输入原密码', trigger: 'blur' }]">
              <el-input v-model="pwd.old_password" type="password" show-password placeholder="请输入原密码" />
            </el-form-item>
            <el-form-item label="新密码" prop="new_password" :rules="[{ required: true, min: 6, message: '新密码至少 6 位', trigger: 'blur' }]">
              <el-input v-model="pwd.new_password" type="password" show-password placeholder="至少 6 位" />
            </el-form-item>
            <el-form-item label="确认新密码" prop="confirm" :rules="[{ required: true, validator: confirmValidator, trigger: 'blur' }]">
              <el-input v-model="pwd.confirm" type="password" show-password placeholder="再输入一次" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" :loading="savingPwd" @click="onChangePassword">修改密码</el-button>
            </el-form-item>
          </el-form>
          <el-alert
            type="warning"
            :closable="false"
            show-icon
            title="修改后，该账号只能用新密码登录。"
          />
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 申请权限对话框 -->
    <el-dialog v-model="dialog.visible" title="申请权限" width="640px">
      <el-alert
        class="mb-12"
        type="info"
        :closable="false"
        show-icon
        title="勾选需要的权限并说明用途，提交后由系统管理员审批；通过后立即生效。"
      />

      <div v-for="group in catalog" :key="group.group" class="perm-group">
        <template v-if="group.items.some((i) => canApply(i.code))">
          <h4 class="group-title">{{ group.group }}</h4>
          <el-checkbox
            v-for="item in group.items.filter((i) => canApply(i.code))"
            :key="item.code"
            :model-value="dialog.checked.includes(item.code)"
            class="perm-checkbox"
            @change="(val) => toggleApply(item.code, val)"
          >
            <span class="perm-name">{{ item.name }}</span>
            <span class="text-muted perm-desc">{{ item.description }}</span>
          </el-checkbox>
        </template>
      </div>

      <div v-if="availableCodes.length === 0" class="text-muted">
        当前角色可申请的权限已全部拥有，无需申请。
      </div>

      <el-form label-width="70px" class="mt-12">
        <el-form-item label="申请理由">
          <el-input
            v-model="dialog.reason"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-word-limit
            placeholder="说明使用场景，例如：我是学生会成员，需要申办读书分享会并发布活动总结。"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="dialog.saving" @click="submitRequest">提交申请</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Refresh } from '@element-plus/icons-vue'
import {
  cancelPermissionRequest,
  changePassword,
  createPermissionRequest,
  getPermissionCatalog,
  getUserPermissions,
  listMyPermissionRequests,
  updateProfile
} from '@/api/user'
import { useUserStore } from '@/store/user'
import { USER_ROLE, typeOf } from '@/constants'
import { formatDateTime } from '@/utils/format'

const REQUEST_STATUS = [
  { value: 'pending', label: '待审批' },
  { value: 'approved', label: '已通过' },
  { value: 'rejected', label: '已驳回' },
  { value: 'cancelled', label: '已撤回' }
]

const store = useUserStore()
const route = useRoute()
const TAB_KEYS = ['info', 'permissions', 'requests', 'security']
const activeTab = ref(TAB_KEYS.includes(route.query.tab) ? route.query.tab : 'info')
const infoRef = ref()
const pwdRef = ref()
const savingInfo = ref(false)
const savingPwd = ref(false)
const mineLoading = ref(false)

const catalog = ref([])
const permMap = ref({})
const summary = ref({})
const mine = ref([])
const pendingCount = ref(0)
const requestStatus = ref('pending')

const profile = computed(() => store.profile || {})
const isStaff = computed(() => ['admin', 'super_admin'].includes(profile.value.role))
const isVisitor = computed(() => profile.value.role === 'visitor')
/** 除系统管理员外都能提交申请（访客也开放，审批后即刻获得对应能力） */
const canRequest = computed(() => profile.value.role !== 'super_admin')
const ownership = computed(() => new Set(summary.value.permissions || []))

const info = reactive({ name: '', college: '', major: '', grade: '', class_no: '', phone: '', email: '' })
const pwd = reactive({ old_password: '', new_password: '', confirm: '' })
const dialog = reactive({ visible: false, checked: [], reason: '', saving: false })

/** 可申请：未拥有 + 不是 system:permission（该权限仅系统管理员天然拥有） */
const availableCodes = computed(() =>
  catalog.value
    .flatMap((g) => g.items.map((i) => i.code))
    .filter((code) => !ownership.value.has(code) && code !== 'system:permission')
)

function permName(code) {
  return permMap.value[code] || code
}

function isOwned(code) {
  return ownership.value.has(code)
}

function isRevoked(code) {
  return (summary.value.revoked_permissions || []).includes(code)
}

function sourceLabel(code) {
  if (isRevoked(code)) return '已被收回'
  if (!isOwned(code)) return '未拥有'
  if ((summary.value.granted_permissions || []).includes(code)) return '额外授予'
  return '角色默认'
}

function sourceType(code) {
  if (isRevoked(code)) return 'danger'
  if (!isOwned(code)) return 'info'
  if ((summary.value.granted_permissions || []).includes(code)) return 'success'
  return 'primary'
}

function statusType(status) {
  return { pending: 'warning', approved: 'success', rejected: 'danger', cancelled: 'info' }[status] || 'info'
}

function canApply(code) {
  return !ownership.value.has(code) && code !== 'system:permission'
}

function toggleApply(code, val) {
  if (val) {
    if (!dialog.checked.includes(code)) dialog.checked.push(code)
  } else {
    dialog.checked = dialog.checked.filter((item) => item !== code)
  }
}

function fillInfo() {
  const p = profile.value
  Object.assign(info, {
    name: p.name || '',
    college: p.college || '',
    major: p.major || '',
    grade: p.grade || '',
    class_no: p.class_no || '',
    phone: p.phone || '',
    email: p.email || ''
  })
}

async function loadAll() {
  const [cat, sum, list, pending] = await Promise.all([
    getPermissionCatalog(),
    getUserPermissions(profile.value.user_id),
    listMyPermissionRequests({ page: 1, page_size: 50, status: requestStatus.value || undefined }),
    listMyPermissionRequests({ page: 1, page_size: 1, status: 'pending' })
  ])
  catalog.value = cat.groups
  permMap.value = Object.fromEntries(cat.groups.flatMap((g) => g.items.map((i) => [i.code, i.name])))
  summary.value = sum
  mine.value = list.list
  pendingCount.value = pending.total
  fillInfo()
  // 访客没有密码，深链到「账号安全」时落到「我的权限」
  if (isVisitor.value && activeTab.value === 'security') activeTab.value = 'permissions'
}

async function refreshPending() {
  const data = await listMyPermissionRequests({ page: 1, page_size: 1, status: 'pending' })
  pendingCount.value = data.total
}

async function fetchMine() {
  mineLoading.value = true
  try {
    const data = await listMyPermissionRequests({
      page: 1,
      page_size: 50,
      status: requestStatus.value || undefined
    })
    mine.value = data.list
  } finally {
    mineLoading.value = false
  }
}

async function onSaveInfo() {
  const valid = await infoRef.value.validate().catch(() => false)
  if (!valid) return
  savingInfo.value = true
  try {
    await updateProfile({ ...info })
    await store.fetchProfile()
    fillInfo()
    ElMessage.success('资料已保存')
  } finally {
    savingInfo.value = false
  }
}

function openRequest() {
  dialog.checked = []
  dialog.reason = ''
  dialog.visible = true
}

async function submitRequest() {
  if (!dialog.checked.length) {
    ElMessage.warning('请至少选择一个权限')
    return
  }
  if (dialog.reason.trim().length < 5) {
    ElMessage.warning('请填写至少 5 个字的申请理由')
    return
  }
  dialog.saving = true
  try {
    await createPermissionRequest({ permissions: dialog.checked, reason: dialog.reason.trim() })
    ElMessage.success('申请已提交，等待系统管理员审批')
    dialog.visible = false
    requestStatus.value = 'pending'
    await Promise.all([fetchMine(), refreshSummary()])
  } finally {
    dialog.saving = false
  }
}

async function refreshSummary() {
  summary.value = await getUserPermissions(profile.value.user_id)
  await refreshPending()
}

async function onCancel(row) {
  try {
    await ElMessageBox.confirm('确认撤回这条申请吗？', '提示', { type: 'warning' })
  } catch {
    return
  }
  await cancelPermissionRequest(row.request_id)
  ElMessage.success('已撤回')
  await Promise.all([fetchMine(), refreshSummary()])
}

function confirmValidator(_rule, value, callback) {
  if (!value) callback(new Error('请再次输入新密码'))
  else if (value !== pwd.new_password) callback(new Error('两次输入的新密码不一致'))
  else callback()
}

async function onChangePassword() {
  const valid = await pwdRef.value.validate().catch(() => false)
  if (!valid) return
  savingPwd.value = true
  try {
    await changePassword({ old_password: pwd.old_password, new_password: pwd.new_password })
    ElMessage.success('密码已修改，下次请用新密码登录')
    pwd.old_password = ''
    pwd.new_password = ''
    pwd.confirm = ''
    pwdRef.value.clearValidate()
  } finally {
    savingPwd.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.profile-top {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 18px 20px;
  margin: 16px 16px 0;
  background: #fff;
  border-radius: 10px;
  border: 1px solid #eef1f6;
}

.profile-id {
  flex: 1;
}

.name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 17px;
  margin-bottom: 4px;
}

.profile-stats {
  display: flex;
  gap: 28px;
  text-align: center;
}

.stat-item strong {
  display: block;
  font-size: 20px;
  color: var(--sr-primary);
}

.stat-item span {
  font-size: 12px;
  color: #909399;
}

.profile-tabs {
  margin: 12px 16px 16px;
  background: #fff;
  border-radius: 10px;
  padding: 4px 16px 16px;
  border: 1px solid #eef1f6;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 18px;
}

.info-form,
.pwd-form {
  max-width: 720px;
}

.security-block {
  max-width: 620px;
}

.perm-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.ml-6 {
  margin-left: 6px;
}

.mb-12 {
  margin-bottom: 12px;
}

.mt-12 {
  margin-top: 12px;
}

.perm-group {
  margin-bottom: 14px;
}

.group-title {
  margin: 10px 0 8px;
  font-size: 14px;
  color: #374151;
}

.perm-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px;
}

.perm-item {
  border: 1px solid #eef1f6;
  border-radius: 8px;
  padding: 10px 12px;
  background: #fafbfe;
}

.perm-item.owned {
  border-color: #c7d2fe;
  background: #f5f7ff;
}

.perm-item.revoked {
  border-color: #fecaca;
  background: #fff8f8;
}

.perm-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.perm-item-name {
  font-weight: 500;
}

.perm-item-desc {
  font-size: 12px;
  margin: 4px 0 2px;
  line-height: 1.5;
}

.perm-code {
  font-size: 11px;
  color: #b0b7c3;
  font-family: Consolas, monospace;
}

.perm-tag {
  margin: 0 4px 4px 0;
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

.review-cell {
  display: flex;
  flex-direction: column;
  font-size: 12px;
  line-height: 1.5;
}

.tab-badge {
  margin-left: 4px;
  transform: translateY(-2px);
}
</style>
