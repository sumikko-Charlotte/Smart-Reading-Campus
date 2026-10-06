/** 通用格式化工具 */

/** ISO 时间 → 2026-10-18 12:00（默认只到分钟） */
export function formatDateTime(value, withSeconds = false) {
  if (!value) return '-'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return String(value)
  const pad = (n) => String(n).padStart(2, '0')
  const base = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
  return withSeconds ? `${base}:${pad(d.getSeconds())}` : base
}

/** 时间区间展示 */
export function formatRange(start, end) {
  if (!start) return '-'
  return end ? `${formatDateTime(start)} ~ ${formatDateTime(end)}` : formatDateTime(start)
}

/** 是否已过某时间 */
export function isPast(value) {
  if (!value) return false
  return new Date(value).getTime() < Date.now()
}

/** 环境要求：Element Plus 日期选择器需要 Date 对象 */
export function toDate(value) {
  return value ? new Date(value) : null
}
