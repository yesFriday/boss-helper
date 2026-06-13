export const CITY_GROUPS = [
  {
    label: '山东省',
    cities: ['济南', '青岛', '淄博', '潍坊', '烟台', '济宁', '临沂', '泰安', '威海', '东营', '滨州', '菏泽', '枣庄', '日照', '聊城', '德州'],
  },
  { label: '一线城市', cities: ['北京', '上海', '广州', '深圳'] },
  {
    label: '新一线',
    cities: ['成都', '杭州', '武汉', '南京', '重庆', '西安', '长沙', '天津', '苏州', '郑州', '东莞', '沈阳', '宁波', '昆明'],
  },
  {
    label: '其他省会',
    cities: ['合肥', '福州', '厦门', '南昌', '贵阳', '南宁', '太原', '石家庄', '哈尔滨', '长春', '兰州', '乌鲁木齐', '呼和浩特', '拉萨', '西宁', '银川', '海口', '三亚'],
  },
]

export const STATUS_MAP: Record<string, string> = {
  pending: '待投递',
  applied: '已投递',
  replied: 'HR已回复',
  skipped: '已跳过',
  failed: '失败',
  missing_url: '缺少链接',
}

export const STATUS_BADGE_CLASS: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  applied: 'bg-blue-100 text-blue-800',
  replied: 'bg-green-100 text-green-800',
  skipped: 'bg-gray-100 text-gray-600',
  failed: 'bg-red-100 text-red-800',
  missing_url: 'bg-orange-100 text-orange-800',
}

export const HR_ACTIVE_BADGE_CLASS: Record<string, string> = {
  在线: 'bg-emerald-100 text-emerald-800 border-emerald-300',
  '刚刚活跃': 'bg-teal-100 text-teal-800 border-teal-300',
  '今日活跃': 'bg-sky-100 text-sky-800 border-sky-300',
  '3日内活跃': 'bg-blue-100 text-blue-800 border-blue-300',
  '本周活跃': 'bg-indigo-100 text-indigo-800 border-indigo-300',
  '本月活跃': 'bg-violet-100 text-violet-800 border-violet-300',
  '半年前活跃': 'bg-gray-100 text-gray-500 border-gray-200',
  '一年前活跃': 'bg-gray-100 text-gray-400 border-gray-200',
}

export const AI_PLATFORMS: Record<string, { baseUrl: string; models: { v: string; t: string }[] }> = {
  deepseek: {
    baseUrl: 'https://api.deepseek.com/v1',
    models: [
      { v: 'deepseek-v4-pro', t: 'DeepSeek V4 Pro' },
      { v: 'deepseek-chat', t: 'DeepSeek Chat' },
      { v: 'deepseek-reasoner', t: 'DeepSeek Reasoner' },
    ],
  },
  openrouter: {
    baseUrl: 'https://openrouter.ai/api/v1',
    models: [
      { v: 'openrouter/auto', t: 'Auto' },
      { v: 'deepseek/deepseek-chat', t: 'DeepSeek Chat' },
      { v: 'deepseek/deepseek-r1', t: 'DeepSeek R1' },
      { v: 'anthropic/claude-sonnet-4', t: 'Claude Sonnet 4' },
      { v: 'google/gemini-2.5-flash', t: 'Gemini 2.5 Flash' },
    ],
  },
  mimo: {
    baseUrl: 'https://token-plan-sgp.xiaomimimo.com/v1',
    models: [{ v: 'mi-undefined', t: 'MiMo' }],
  },
  custom: { baseUrl: '', models: [] },
}
