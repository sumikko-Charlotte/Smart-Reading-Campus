/**
 * 全局字典：与后端 app/core/enums.py 一一对应。
 * ⚠️ 新增枚举值先改《核心数据对象与统一字段规范.md》，再同步这里和后端，禁止只改一端。
 */

export const ACTIVITY_STATUS = [
  { value: 'draft', label: '草稿', type: 'info' },
  { value: 'published', label: '报名中', type: 'success' },
  { value: 'signup_closed', label: '报名截止', type: 'warning' },
  { value: 'ongoing', label: '进行中', type: 'primary' },
  { value: 'finished', label: '已结束', type: 'info' },
  { value: 'cancelled', label: '已取消', type: 'danger' }
]

// 状态机的前端镜像：仅用于按钮可用性提示，真正校验在后端
export const ACTIVITY_STATUS_FLOW = {
  draft: ['published', 'cancelled'],
  published: ['signup_closed', 'ongoing', 'cancelled'],
  signup_closed: ['ongoing', 'finished', 'cancelled'],
  ongoing: ['finished'],
  finished: [],
  cancelled: []
}

export const ACTIVITY_CATEGORY = [
  { value: 'reading_share', label: '读书分享会' },
  { value: 'lecture', label: '讲座/沙龙' },
  { value: 'exhibition', label: '书展/展览' },
  { value: 'reading_challenge', label: '阅读打卡/挑战' },
  { value: 'book_drift', label: '图书漂流活动' },
  { value: 'other', label: '其他' }
]

export const BOOK_SOURCE = [
  { value: 'library', label: '馆藏图书' },
  { value: 'drift', label: '漂流图书' }
]

export const DRIFT_STATUS = [
  { value: 'idle', label: '待领取', type: 'success' },
  { value: 'reserved', label: '已预定', type: 'warning' },
  { value: 'in_transit', label: '流转中', type: 'primary' },
  { value: 'claimed', label: '已领用', type: 'info' },
  { value: 'closed', label: '已下架', type: 'info' }
]

export const CONVERSATION_SCENE = [
  { value: 'book_analysis', label: '书目深度解读' },
  { value: 'recommend', label: '智能推荐' },
  { value: 'qa', label: '多轮伴读问答' },
  { value: 'copywriting', label: '文案生成' }
]

export const USER_ROLE = [
  { value: 'student', label: '学生' },
  { value: 'librarian', label: '图书馆老师' },
  { value: 'admin', label: '系统管理员' }
]

/** 通用字典查值：labelOf(ACTIVITY_STATUS, 'draft') → '草稿' */
export function labelOf(dict, value, fallback = '-') {
  return dict.find((i) => i.value === value)?.label ?? fallback
}

/** 通用字典查标签色：typeOf(ACTIVITY_STATUS, 'published') → 'success' */
export function typeOf(dict, value, fallback = 'info') {
  return dict.find((i) => i.value === value)?.type ?? fallback
}
