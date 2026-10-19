<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-brand">
        <span class="logo">智</span>
        <h1>智阅校园</h1>
        <p>基于生成式 AI 的高校双端协同阅读推广平台</p>
      </div>

      <!-- 三种进入方式：登录 / 注册 / 访客，不再让用户先选角色 -->
      <div class="entry-switch">
        <button class="entry-item active" type="button">登录</button>
        <button class="entry-item" type="button" @click="$router.push('/register')">注册</button>
        <button class="entry-item" type="button" :disabled="guestLoading" @click="onGuest">
          {{ guestLoading ? '进入中…' : '访客' }}
        </button>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @keyup.enter="onSubmit">
        <el-form-item label="学号 / 工号" prop="student_no">
          <el-input v-model="form.student_no" size="large" placeholder="请输入学号或工号" :prefix-icon="User" clearable />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" size="large" type="password" show-password placeholder="请输入密码" :prefix-icon="Lock" />
        </el-form-item>
        <el-button type="primary" size="large" class="login-btn" :loading="loading" @click="onSubmit">
          登录
        </el-button>
      </el-form>

      <div class="entry-foot">
        还没有账号？
        <el-link type="primary" :underline="false" @click="$router.push('/register')">立即注册</el-link>
        <el-divider direction="vertical" />
        <el-link :underline="false" @click="onGuest">以访客身份浏览</el-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Lock, User } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'

const router = useRouter()
const route = useRoute()
const store = useUserStore()

const formRef = ref()
const loading = ref(false)
const guestLoading = ref(false)
const form = reactive({ student_no: '', password: '' })

const rules = {
  student_no: [{ required: true, message: '请输入学号或工号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

async function onSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await store.login(form.student_no, form.password)
    ElMessage.success('登录成功')
    router.push(route.query.redirect || '/dashboard')
  } finally {
    loading.value = false
  }
}

async function onGuest() {
  guestLoading.value = true
  try {
    await store.guestLogin()
    ElMessage.info('已进入访客模式：可浏览内容，不能报名或申办')
    router.push('/dashboard')
  } finally {
    guestLoading.value = false
  }
}
</script>

<style scoped>
.login-page {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #eef2ff 0%, #f7f9ff 45%, #eaf4ff 100%);
}

.login-card {
  width: 440px;
  background: #fff;
  border-radius: 14px;
  padding: 32px 34px 22px;
  box-shadow: 0 12px 40px rgba(47, 84, 235, 0.12);
}

.login-brand {
  text-align: center;
  margin-bottom: 20px;
}

.logo {
  display: inline-flex;
  width: 48px;
  height: 48px;
  border-radius: 12px;
  background: var(--sr-primary);
  color: #fff;
  font-size: 24px;
  font-weight: 700;
  align-items: center;
  justify-content: center;
}

.login-brand h1 {
  font-size: 22px;
  margin: 12px 0 6px;
}

.login-brand p {
  color: #6b7280;
  font-size: 13px;
  margin: 0;
}

.entry-switch {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-bottom: 18px;
}

.entry-item {
  height: 38px;
  border-radius: 9px;
  border: 1px solid #e5e7eb;
  background: #f8fafc;
  color: #4b5563;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.18s;
}

.entry-item:hover:not(:disabled) {
  border-color: var(--sr-primary);
  color: var(--sr-primary);
}

.entry-item.active {
  background: rgba(47, 84, 235, 0.08);
  border-color: var(--sr-primary);
  color: var(--sr-primary);
  font-weight: 600;
}

.entry-item:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.login-btn {
  width: 100%;
  margin-top: 4px;
}

.entry-foot {
  margin-top: 14px;
  text-align: center;
  font-size: 13px;
  color: #6b7280;
}

</style>
