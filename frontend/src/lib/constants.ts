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
  pending: 'bg-amber-50 text-amber-700 ring-amber-200',
  applied: 'bg-blue-50 text-blue-700 ring-blue-200',
  replied: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  skipped: 'bg-slate-100 text-slate-500 ring-slate-200',
  failed: 'bg-red-50 text-red-700 ring-red-200',
  missing_url: 'bg-orange-50 text-orange-700 ring-orange-200',
}

export const HR_ACTIVE_BADGE_CLASS: Record<string, string> = {
  在线: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  '刚刚活跃': 'bg-emerald-50 text-emerald-600 border-emerald-200',
  '今日活跃': 'bg-blue-50 text-blue-700 border-blue-200',
  '3日内活跃': 'bg-blue-50 text-blue-600 border-blue-200',
  '本周活跃': 'bg-indigo-50 text-indigo-700 border-indigo-200',
  '本月活跃': 'bg-violet-50 text-violet-700 border-violet-200',
  '半年前活跃': 'bg-slate-100 text-slate-500 border-slate-200',
  '一年前活跃': 'bg-slate-100 text-slate-400 border-slate-200',
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
