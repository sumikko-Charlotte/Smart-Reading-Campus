/**
 * 全局字典：与后端 app/core/enums.py、app/core/permissions.py 一一对应。
 * ⚠️ 新增枚举值/权限点先改后端与规范文档，再同步这里，禁止只改一端。
 */

/** 权限点编码：业务代码里只用 PERM.XXX，不写裸字符串 */
export const PERM = {
  ACTIVITY_VIEW: 'activity:view',
  ACTIVITY_SIGNUP: 'activity:signup',
  ACTIVITY_CREATE: 'activity:create',
  ACTIVITY_MANAGE_ALL: 'activity:manage_all',
  ACTIVITY_REVIEW: 'activity:review',
  ACTIVITY_SUMMARY: 'activity:summary',
  DRIFT_VIEW: 'drift:view',
  DRIFT_PARTICIPATE: 'drift:participate',
  DRIFT_MANAGE: 'drift:manage',
  BOOK_MANAGE: 'book:manage',
  CERTIFICATE_VIEW: 'certificate:view',
  CERTIFICATE_ISSUE: 'certificate:issue',
  AI_RECOMMEND: 'ai:recommend',
  AI_CHAT: 'ai:chat',
  SYSTEM_USER: 'system:user',
  SYSTEM_PERMISSION: 'system:permission'
}

export const USER_ROLE = [
  { value: 'visitor', label: '访客', type: 'info' },
  { value: 'student', label: '学生', type: 'primary' },
  { value: 'admin', label: '普通管理员', type: 'warning' },
  { value: 'super_admin', label: '系统管理员', type: 'danger' }
]

export const ACTIVITY_STATUS = [
  { value: 'draft', label: '草稿', type: 'info' },
  { value: 'pending_review', label: '待审批', type: 'warning' },
  { value: 'rejected', label: '审批驳回', type: 'danger' },
  { value: 'published', label: '已发布', type: 'success' },
  { value: 'signup_closed', label: '报名截止', type: 'warning' },
  { value: 'ongoing', label: '进行中', type: 'primary' },
  { value: 'finished', label: '已结束', type: 'info' },
  { value: 'cancelled', label: '已取消', type: 'danger' }
]

/**
 * 运营类流转移（前端镜像，仅控制按钮可用性）。
 * 注意：draft→pending_review 走「提交审批」接口；pending_review→published/rejected 走「审批」接口，
 * 都不在这里，避免前端绕过审批直接发布。
 */
export const ACTIVITY_STATUS_FLOW = {
  draft: [],
  pending_review: [],
  rejected: [],
  published: ['signup_closed', 'cancelled'],
  signup_closed: ['ongoing', 'cancelled'],
  ongoing: ['finished'],
  finished: [],
  cancelled: []
}

export const ACTIVITY_LEVEL = [
  { value: 'none', label: '未定级', type: 'info' },
  { value: 'college', label: '院级', type: 'primary' },
  { value: 'school', label: '校级', type: 'danger' }
]

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
  { value: 'drift', label: '漂流图书' },
  { value: 'both', label: '馆藏及漂流' }
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

export const CERT_STATUS = [
  { value: 'issued', label: '有效', type: 'success' },
  { value: 'revoked', label: '已撤销', type: 'info' }
]

export const NOTIFICATION_TYPE = [
  { value: 'activity_summary', label: '活动回顾', type: 'success' },
  { value: 'activity_published', label: '活动发布', type: 'primary' },
  { value: 'activity_rejected', label: '活动驳回', type: 'danger' },
  { value: 'activity_cancelled', label: '活动取消', type: 'danger' },
  { value: 'activity_review', label: '待审批活动', type: 'warning' },
  { value: 'activity_status', label: '活动状态', type: 'info' },
  { value: 'certificate_issued', label: '证书颁发', type: 'warning' },
  { value: 'permission_request', label: '待审批权限', type: 'warning' },
  { value: 'permission_approved', label: '权限通过', type: 'success' },
  { value: 'permission_rejected', label: '权限驳回', type: 'danger' },
  { value: 'permission_changed', label: '权限调整', type: 'info' },
  { value: 'system', label: '系统消息', type: 'info' }
]

/** 通用字典查值：labelOf(ACTIVITY_STATUS, 'draft') → '草稿' */
export function labelOf(dict, value, fallback = '-') {
  return dict.find((i) => i.value === value)?.label ?? fallback
}

/** 通用字典查标签色：typeOf(ACTIVITY_STATUS, 'published') → 'success' */
export function typeOf(dict, value, fallback = 'info') {
  return dict.find((i) => i.value === value)?.type ?? fallback
}
