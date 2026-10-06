<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-brand">
        <span class="logo">智</span>
        <h1>智阅校园</h1>
        <p>基于生成式 AI 的高校双端协同阅读推广平台</p>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @keyup.enter="onSubmit">
        <el-form-item label="学号 / 工号" prop="student_no">
          <el-input v-model="form.student_no" size="large" placeholder="请输入学号或工号" :prefix-icon="User" clearable />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" size="large" type="password" show-password placeholder="演示密码 123456" :prefix-icon="Lock" />
        </el-form-item>
        <el-button type="primary" size="large" class="login-btn" :loading="loading" @click="onSubmit">
          登录 PC 端管理平台
        </el-button>
      </el-form>

      <el-divider>演示账号（密码 123456）</el-divider>
      <div class="demo-accounts">
        <el-tag v-for="acc in demoAccounts" :key="acc.no" class="demo-tag" @click="fill(acc.no)">
          {{ acc.no }} · {{ acc.label }}
        </el-tag>
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
const form = reactive({ student_no: 'T2009', password: '123456' })

const rules = {
  student_no: [{ required: true, message: '请输入学号或工号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

const demoAccounts = [
  { no: 'T2009', label: '图书馆老师' },
  { no: 'admin', label: '系统管理员' },
  { no: '2025211995', label: '学生（万贝）' }
]

function fill(no) {
  form.student_no = no
  form.password = '123456'
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
  width: 420px;
  background: #fff;
  border-radius: 14px;
  padding: 34px 34px 26px;
  box-shadow: 0 12px 40px rgba(47, 84, 235, 0.12);
}

.login-brand {
  text-align: center;
  margin-bottom: 22px;
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

.login-btn {
  width: 100%;
  margin-top: 4px;
}

.demo-accounts {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.demo-tag {
  cursor: pointer;
  width: 100%;
  text-align: center;
}
</style>
