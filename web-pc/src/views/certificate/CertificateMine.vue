<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h2 class="page-title">我的证书</h2>
        <p class="page-desc">完成活动签到与签退后自动发放，可下载 PDF。</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" @click="fetchList">刷新</el-button>
    </div>

    <div v-loading="loading" class="cert-grid">
      <el-empty v-if="!list.length && !loading" description="暂无证书，完成活动签到与签退后会自动发放" />

      <el-card v-for="cert in list" :key="cert.certificate_id" class="cert-card" shadow="hover">
        <div class="cert-head">
          <div class="cert-medal">
            <el-icon :size="26"><Medal /></el-icon>
          </div>
          <div class="cert-meta">
            <div class="cert-name">
              {{ cert.certificate_name }}
              <el-tag :type="typeOf(ACTIVITY_LEVEL, cert.activity_level)" size="small" effect="plain">
                {{ labelOf(ACTIVITY_LEVEL, cert.activity_level) }}
              </el-tag>
            </div>
            <div class="text-muted cert-activity">{{ cert.activity_title }}</div>
          </div>
        </div>

        <el-divider />
        <div class="cert-info">
          <div><span class="label">证书编号</span>{{ cert.serial_no }}</div>
          <div><span class="label">颁发时间</span>{{ formatDateTime(cert.issued_at) }}</div>
          <div><span class="label">盖章单位</span>{{ cert.seal_name }}</div>
          <div><span class="label">验真码</span><code>{{ cert.verify_code }}</code></div>
        </div>

        <div class="cert-actions">
          <el-button type="primary" size="small" :icon="Download" @click="onDownload(cert)">下载 PDF</el-button>
          <el-button size="small" :icon="CircleCheck" @click="onVerify(cert)">验真</el-button>
        </div>
      </el-card>
    </div>

    <el-dialog v-model="verifyVisible" title="证书验真结果" width="420px">
      <el-result
        :icon="verifyResult?.valid ? 'success' : 'warning'"
        :title="verifyResult?.valid ? '证书有效' : '未查询到证书'"
        :sub-title="verifyResult?.message"
      >
        <template #extra>
          <div v-if="verifyResult?.valid" class="verify-detail">
            <div>持有人：{{ verifyResult.holder_name }}</div>
            <div>活动：{{ verifyResult.activity_title }}（{{ verifyResult.activity_level }}）</div>
            <div>编号：{{ verifyResult.serial_no }}</div>
          </div>
        </template>
      </el-result>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { CircleCheck, Download, Medal, Refresh } from '@element-plus/icons-vue'
import { downloadCertificatePdf, listMyCertificates, verifyCertificate } from '@/api/certificate'
import { ACTIVITY_LEVEL, labelOf, typeOf } from '@/constants'
import { formatDateTime } from '@/utils/format'

const loading = ref(false)
const list = ref([])
const verifyVisible = ref(false)
const verifyResult = ref(null)

async function fetchList() {
  loading.value = true
  try {
    const data = await listMyCertificates({ page: 1, page_size: 50 })
    list.value = data.list
  } finally {
    loading.value = false
  }
}

async function onDownload(cert) {
  try {
    await downloadCertificatePdf(cert)
    ElMessage.success('已开始下载')
  } catch {
    /* 下载失败提示由拦截器给出 */
  }
}

async function onVerify(cert) {
  verifyResult.value = await verifyCertificate(cert.verify_code)
  verifyVisible.value = true
}

onMounted(fetchList)
</script>

<style scoped>
.cert-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 16px;
  min-height: 200px;
}

.cert-head {
  display: flex;
  gap: 12px;
}

.cert-medal {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  background: #fef3c7;
  color: #b45309;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
}

.cert-name {
  font-size: 16px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.cert-activity {
  margin-top: 4px;
}

.cert-info {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 16px;
  font-size: 13px;
}

.cert-info .label {
  color: #6b7280;
  margin-right: 8px;
}

.cert-actions {
  margin-top: 14px;
  display: flex;
  gap: 8px;
}

.verify-detail {
  text-align: left;
  font-size: 13px;
  line-height: 1.9;
  color: #4b5563;
}
</style>
