/** 电子证书接口 */
import request from './request'

export const listMyCertificates = (params) => request.get('/certificates/mine', { params })
export const verifyCertificate = (code) => request.get(`/certificates/verify/${code}`)

/** 下载 PDF：带 token 取 blob，避免直接开新窗口丢失 Authorization */
export async function downloadCertificatePdf(cert) {
  const blob = await request.get(`/certificates/${cert.certificate_id}/pdf`, { responseType: 'blob' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `证书_${cert.serial_no}.pdf`
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 2000)
}
