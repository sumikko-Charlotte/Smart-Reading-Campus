<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">{{ isEdit ? '编辑活动' : '新建活动' }}</h2>
        <p class="page-desc">
          {{ isEdit ? '编辑后需手动流转状态，未发布的活动仅管理端可见' : '新建后默认为「草稿」，确认信息无误后再流转为「报名中」' }}
        </p>
      </div>
      <div>
        <el-button @click="$router.back()">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="onSubmit">{{ isEdit ? '保存修改' : '创建草稿' }}</el-button>
      </div>
    </div>

    <el-row :gutter="16">
      <el-col :md="16">
        <div class="card-block">
          <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
            <el-form-item label="活动标题" prop="title">
              <el-input v-model="form.title" maxlength="128" show-word-limit placeholder="如：「书海拾贝」秋季读书分享会" />
            </el-form-item>
            <el-form-item label="副标题">
              <el-input v-model="form.subtitle" maxlength="255" placeholder="一句话卖点，展示在列表与小程序卡片上" />
            </el-form-item>
            <el-form-item label="活动分类" prop="category">
              <el-select v-model="form.category" style="width: 220px">
                <el-option v-for="c in ACTIVITY_CATEGORY" :key="c.value" :label="c.label" :value="c.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="活动地点">
              <el-input v-model="form.location" placeholder="如：图书馆三层报告厅 / 线上" />
            </el-form-item>
            <el-form-item label="封面图地址">
              <el-input v-model="form.cover_url" placeholder="暂填 URL，第 2 轮接对象存储上传" />
            </el-form-item>
            <el-form-item label="活动简介">
              <el-input v-model="form.summary" type="textarea" :rows="3" maxlength="255" show-word-limit placeholder="列表页展示的简介" />
            </el-form-item>
            <el-form-item label="活动详情">
              <el-input v-model="form.content" type="textarea" :rows="6" placeholder="支持纯文本 / 简易 HTML，小程序端统一渲染" />
            </el-form-item>
          </el-form>
        </div>
      </el-col>

      <el-col :md="8">
        <div class="card-block">
          <h3 class="section-title">时间与名额</h3>
          <el-form :model="form" label-width="96px">
            <el-form-item label="报名开始">
              <el-date-picker v-model="form.signup_start_at" type="datetime" placeholder="选择时间" style="width: 100%" />
            </el-form-item>
            <el-form-item label="报名截止">
              <el-date-picker v-model="form.signup_end_at" type="datetime" placeholder="选择时间" style="width: 100%" />
            </el-form-item>
            <el-form-item label="活动开始" required>
              <el-date-picker v-model="form.start_at" type="datetime" placeholder="选择时间" style="width: 100%" />
            </el-form-item>
            <el-form-item label="活动结束">
              <el-date-picker v-model="form.end_at" type="datetime" placeholder="选择时间" style="width: 100%" />
            </el-form-item>
            <el-form-item label="名额上限">
              <el-input-number v-model="form.capacity" :min="0" :max="5000" style="width: 100%" />
            </el-form-item>
            <el-form-item label="不限名额">
              <el-switch :model-value="form.capacity === 0" @change="(v) => (form.capacity = v ? 0 : 50)" />
            </el-form-item>
            <el-form-item label="电子证书">
              <el-switch v-model="form.need_certificate" />
            </el-form-item>
            <el-form-item v-if="form.need_certificate" label="证书模板">
              <el-input v-model="form.certificate_template_id" placeholder="模板 ID（第 2 轮实现模板管理）" />
            </el-form-item>
          </el-form>
        </div>

        <div class="card-block mt-16">
          <div class="flex-between">
            <h3 class="section-title">AI 宣传推文</h3>
            <el-button size="small" :disabled="!isEdit" :loading="copyLoading" @click="onGenerateCopy">一键生成</el-button>
          </div>
          <el-alert
            v-if="!isEdit"
            type="info"
            :closable="false"
            show-icon
            title="先保存活动，再生成推文"
            description="推文生成后会自动回存到活动 ai_copy 字段（后端 POST /activities/{id}/ai-copy）。"
          />
          <el-input v-else v-model="form.ai_copy" type="textarea" :rows="10" placeholder="点击「一键生成」调用 AI 生成小红书/公众号风格推文" />
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { createActivity, generateActivityCopy, getActivity, updateActivity } from '@/api/activity'
import { ACTIVITY_CATEGORY } from '@/constants'

const route = useRoute()
const router = useRouter()

const formRef = ref()
const submitting = ref(false)
const copyLoading = ref(false)
const isEdit = computed(() => Boolean(route.params.id))

const form = reactive({
  title: '',
  subtitle: '',
  category: 'reading_share',
  location: '',
  cover_url: '',
  summary: '',
  content: '',
  signup_start_at: null,
  signup_end_at: null,
  start_at: null,
  end_at: null,
  capacity: 50,
  need_certificate: false,
  certificate_template_id: '',
  ai_copy: ''
})

const rules = {
  title: [{ required: true, message: '请输入活动标题', trigger: 'blur' }],
  category: [{ required: true, message: '请选择活动分类', trigger: 'change' }]
}

function toISO(v) {
  return v ? new Date(v).toISOString() : null
}

function buildPayload() {
  return {
    title: form.title,
    subtitle: form.subtitle,
    category: form.category,
    location: form.location,
    cover_url: form.cover_url,
    summary: form.summary,
    content: form.content,
    signup_start_at: toISO(form.signup_start_at),
    signup_end_at: toISO(form.signup_end_at),
    start_at: toISO(form.start_at) || new Date().toISOString(),
    end_at: toISO(form.end_at),
    capacity: form.capacity,
    need_certificate: form.need_certificate,
    certificate_template_id: form.certificate_template_id
  }
}

async function loadDetail() {
  if (!isEdit.value) return
  const data = await getActivity(route.params.id)
  Object.assign(form, {
    ...data,
    signup_start_at: data.signup_start_at ? new Date(data.signup_start_at) : null,
    signup_end_at: data.signup_end_at ? new Date(data.signup_end_at) : null,
    start_at: data.start_at ? new Date(data.start_at) : null,
    end_at: data.end_at ? new Date(data.end_at) : null
  })
}

async function onSubmit() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    if (isEdit.value) {
      await updateActivity(route.params.id, buildPayload())
      ElMessage.success('保存成功')
      router.push(`/activities/${route.params.id}`)
    } else {
      const data = await createActivity(buildPayload())
      ElMessage.success('创建成功（当前为草稿状态）')
      router.push(`/activities/${data.activity_id}`)
    }
  } finally {
    submitting.value = false
  }
}

async function onGenerateCopy() {
  copyLoading.value = true
  try {
    const data = await generateActivityCopy(route.params.id)
    form.ai_copy = data.ai_copy
    ElMessage.success('推文已生成并回存')
  } finally {
    copyLoading.value = false
  }
}

onMounted(loadDetail)
</script>

<style scoped>
.section-title {
  font-size: 15px;
  margin: 0 0 12px;
}
</style>
