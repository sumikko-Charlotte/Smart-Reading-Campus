<template>
  <div class="register-page">
    <div class="register-card">
      <div class="register-head">
        <el-button text :icon="ArrowLeft" @click="$router.push('/login')">返回登录</el-button>
        <h1>注册账号</h1>
        <p>先选择身份，注册成功后自动登录</p>
      </div>

      <!-- 身份选择：只分学生 / 管理员，系统管理员不开放注册 -->
      <div class="role-cards">
        <div
          v-for="item in roleOptions"
          :key="item.value"
          class="role-card"
          :class="{ active: form.role === item.value }"
          @click="form.role = item.value"
        >
          <el-icon class="role-icon"><component :is="item.icon" /></el-icon>
          <strong>{{ item.label }}</strong>
          <span>{{ item.desc }}</span>
        </div>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" label-position="top">
        <div class="form-grid">
          <el-form-item label="学号 / 工号" prop="student_no">
            <el-input v-model="form.student_no" size="large" :placeholder="form.role === 'admin' ? '工号' : '学号'" clearable />
          </el-form-item>
          <el-form-item label="姓名" prop="name">
            <el-input v-model="form.name" size="large" placeholder="真实姓名" clearable />
          </el-form-item>
        </div>

        <el-form-item :label="form.role === 'admin' ? '所属部门' : '学院'">
          <el-input v-model="form.college" size="large" :placeholder="form.role === 'admin' ? '如图书馆' : '如计算机学院'" clearable />
        </el-form-item>

        <div v-if="form.role === 'student'" class="form-grid">
          <el-form-item label="专业">
            <el-input v-model="form.major" placeholder="如计算机科学与技术" clearable />
          </el-form-item>
          <el-form-item label="年级 / 班级">
            <div class="inline-inputs">
              <el-input v-model="form.grade" placeholder="2023" clearable />
              <el-input v-model="form.class_no" placeholder="班级" clearable />
            </div>
          </el-form-item>
        </div>

        <div class="form-grid">
          <el-form-item label="密码" prop="password">
            <el-input v-model="form.password" type="password" show-password placeholder="至少 6 位" />
          </el-form-item>
          <el-form-item label="确认密码" prop="confirm">
            <el-input v-model="form.confirm" type="password" show-password placeholder="再输入一次" />
          </el-form-item>
        </div>

        <el-alert
          v-if="form.role === 'admin'"
          class="role-tip"
          type="warning"
          :closable="false"
          show-icon
          title="管理员注册后默认具备活动审批、图书漂流运营等权限；如需逐项调整，请找系统管理员。"
        />

        <el-button type="primary" size="large" class="submit-btn" :loading="loading" @click="onSubmit">
          注册并登录
        </el-button>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Reading, Setting } from '@element-plus/icons-vue'
import { useUserStore } from '@/store/user'

const router = useRouter()
const store = useUserStore()

const formRef = ref()
const loading = ref(false)

const roleOptions = [
  { value: 'student', label: '学生', desc: '报名活动、图书漂流、电子证书、AI 伴读', icon: Reading },
  { value: 'admin', label: '管理员', desc: '活动审批、图书漂流运营、证书颁发', icon: Setting }
]

const form = reactive({
  role: 'student',
  student_no: '',
  name: '',
  college: '',
  major: '',
  grade: '',
  class_no: '',
  password: '',
  confirm: ''
})

const rules = {
  student_no: [{ required: true, message: '请输入学号或工号', trigger: 'blur' }],
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  password: [{ required: true, min: 6, message: '密码至少 6 位', trigger: 'blur' }],
  confirm: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_rule, value, callback) => {
        if (value !== form.password) callback(new Error('两次输入的密码不一致'))
        else callback()
      },
      trigger: 'blur'
    }
  ]
}

watch(
  () => form.role,
  () => formRef.value?.clearValidate()
)

async function onSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await store.register({
      role: form.role,
      student_no: form.student_no.trim(),
      name: form.name.trim(),
      college: form.college.trim(),
      major: form.major.trim(),
      grade: form.grade.trim(),
      class_no: form.class_no.trim(),
      password: form.password
    })
    ElMessage.success('注册成功，已自动登录')
    router.push('/dashboard')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.register-page {
  min-height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
  background: linear-gradient(135deg, #eef2ff 0%, #f7f9ff 45%, #eaf4ff 100%);
}

.register-card {
  width: 560px;
  background: #fff;
  border-radius: 14px;
  padding: 24px 32px 28px;
  box-shadow: 0 12px 40px rgba(47, 84, 235, 0.12);
}

.register-head {
  margin-bottom: 18px;
}

.register-head h1 {
  font-size: 22px;
  margin: 6px 0 4px;
}

.register-head p {
  margin: 0;
  color: #6b7280;
  font-size: 13px;
}

.role-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 18px;
}

.role-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  cursor: pointer;
  background: #fafbfe;
  transition: all 0.18s;
}

.role-card:hover {
  border-color: var(--sr-primary);
}

.role-card.active {
  border-color: var(--sr-primary);
  background: rgba(47, 84, 235, 0.06);
  box-shadow: 0 4px 14px rgba(47, 84, 235, 0.1);
}

.role-icon {
  font-size: 20px;
  color: var(--sr-primary);
}

.role-card span {
  font-size: 12px;
  color: #6b7280;
  line-height: 1.5;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 14px;
}

.inline-inputs {
  display: flex;
  gap: 8px;
}

.role-tip {
  margin-bottom: 14px;
}

.submit-btn {
  width: 100%;
}
</style>
