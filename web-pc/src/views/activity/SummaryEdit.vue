<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">活动总结</h2>
        <p class="page-desc">
          {{ activity?.title || '加载中…' }} —— 活动结束后撰写图文回顾，发布后推送到所选角色的消息流。
        </p>
      </div>
      <el-button @click="$router.push('/activities')">返回</el-button>
    </div>

    <el-row :gutter="16">
      <el-col :md="16">
        <div class="card-block">
          <el-form label-width="86px">
            <el-form-item label="总结标题" required>
              <el-input v-model="form.title" maxlength="128" show-word-limit placeholder="如：21 天，我们一起读完了两本书" />
            </el-form-item>
            <el-form-item label="总结正文" required>
              <el-input
                v-model="form.content"
                type="textarea"
                :rows="14"
                placeholder="回顾活动亮点、参与数据、现场照片说明等；支持纯文本。"
              />
            </el-form-item>
            <el-form-item label="现场照片">
              <el-input
                v-model="imagesText"
                type="textarea"
                :rows="2"
                placeholder="每行一个图片 URL，最多 9 张（第 3 阶段接对象存储后改为直接上传）"
              />
            </el-form-item>
          </el-form>
          <div class="form-actions">
            <el-button :loading="saving" @click="onSaveDraft">{{ published ? '更新已发布内容' : '保存草稿' }}</el-button>
            <el-button
              v-if="!published"
              type="primary"
              :loading="publishing"
              @click="onPublish"
            >发布并推送</el-button>
            <el-tag v-else type="success" effect="plain">已发布 · {{ formatDateTime(summary?.published_at) }} · {{ summary?.view_count }} 次阅读</el-tag>
          </div>
        </div>
      </el-col>

      <el-col :md="8">
        <div class="card-block">
          <h3 class="section-title">推送范围</h3>
          <el-checkbox-group v-model="targetRoles" :disabled="published">
            <el-checkbox v-for="r in USER_ROLE" :key="r.value" :value="r.value">{{ r.label }}</el-checkbox>
          </el-checkbox-group>
          <el-alert
            class="mt-12"
            type="info"
            :closable="false"
            show-icon
            title="发布后写入各角色的消息流；访客在「活动回顾」页也能看到。"
          />
        </div>

        <div class="card-block mt-16">
          <h3 class="section-title">活动信息</h3>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="活动等级">
              <el-tag v-if="activity && activity.level !== 'none'" :type="typeOf(ACTIVITY_LEVEL, activity.level)" effect="plain">
                {{ labelOf(ACTIVITY_LEVEL, activity.level) }}
              </el-tag>
              <span v-else class="text-muted">未定级</span>
            </el-descriptions-item>
            <el-descriptions-item label="活动时间">{{ formatRange(activity?.start_at, activity?.end_at) }}</el-descriptions-item>
            <el-descriptions-item label="参与人数">{{ activity?.signup_count ?? 0 }} 报名 / {{ activity?.checkin_count ?? 0 }} 签到</el-descriptions-item>
            <el-descriptions-item label="主办方">{{ activity?.organizer_name || '—' }}</el-descriptions-item>
          </el-descriptions>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getActivity } from '@/api/activity'
import { getActivitySummary, publishSummary, saveActivitySummary } from '@/api/summary'
import { ACTIVITY_LEVEL, USER_ROLE, labelOf, typeOf } from '@/constants'
import { formatDateTime, formatRange } from '@/utils/format'

const route = useRoute()
const activity = ref(null)
const summary = ref(null)
const saving = ref(false)
const publishing = ref(false)
const targetRoles = ref(['student', 'visitor', 'admin', 'super_admin'])

const form = reactive({ title: '', content: '' })
const imagesText = ref('')

const images = computed(() =>
  imagesText.value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 9)
)

const published = computed(() => summary.value?.status === 'published')

async function load() {
  const activityId = route.params.id
  activity.value = await getActivity(activityId)
  try {
    summary.value = await getActivitySummary(activityId)
    form.title = summary.value.title
    form.content = summary.value.content
    imagesText.value = (summary.value.images || []).join('\n')
  } catch {
    summary.value = null
  }
}

async function onSaveDraft() {
  if (!form.title.trim() || !form.content.trim()) {
    ElMessage.warning('标题和正文不能为空')
    return
  }
  saving.value = true
  try {
    summary.value = await saveActivitySummary(route.params.id, {
      title: form.title,
      content: form.content,
      images: images.value
    })
    ElMessage.success(published.value ? '已更新发布内容' : '草稿已保存')
  } finally {
    saving.value = false
  }
}

async function onPublish() {
  await onSaveDraft()
  if (published.value !== true) return
  publishing.value = true
  try {
    const data = await publishSummary(summary.value.summary_id, targetRoles.value)
    summary.value = data.summary
    ElMessage.success(`已发布并推送给：${data.pushed_to.map((r) => labelOf(USER_ROLE, r)).join('、')}`)
  } finally {
    publishing.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.section-title {
  font-size: 15px;
  margin: 0 0 12px;
}

.form-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.mt-12 {
  margin-top: 12px;
}
</style>
