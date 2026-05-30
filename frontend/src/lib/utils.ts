export function esc(s: string | null | undefined): string {
  if (!s) return ''
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

export function attr(s: string | null | undefined): string {
  if (!s) return ''
  return s.replace(/'/g, '&#39;')
}

export function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString('zh-CN')
}
