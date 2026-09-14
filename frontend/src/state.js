import { api, openQueueSocket } from './api.js'

const LS = {
  token: 'mm_ticket',
  lang: 'mm_lang',
  status: 'mm_last_status',
}

export function getLang() {
  return localStorage.getItem(LS.lang) || 'ml'
}

export function setLang(l) {
  localStorage.setItem(LS.lang, l)
}

export function saveTicket(token, phone) {
  localStorage.setItem(LS.token, JSON.stringify({ token, phone }))
}

export function getTicket() {
  try { return JSON.parse(localStorage.getItem(LS.token)) } catch { return null }
}

export function cacheStatus(status) {
  localStorage.setItem(LS.status, JSON.stringify({ status, at: new Date().toISOString() }))
}

export function getCachedStatus() {
  try { return JSON.parse(localStorage.getItem(LS.status)) } catch { return null }
}

export async function refreshStatus({ token, phone }) {
  const q = token ? `token=${encodeURIComponent(token)}` : `phone=${encodeURIComponent(phone)}`
  const s = await api.get(`/farmer/status?${q}`)
  cacheStatus(s)
  return { status: s, offline: false }
}

export async function refreshStatusOfflineAware(t) {
  try {
    return await refreshStatus(t)
  } catch {
    const cached = getCachedStatus()
    return { status: cached?.status || null, offline: true }
  }
}

let ws = null
export function connectQueue(mandiId, onEvent) {
  if (ws) ws.close()
  ws = openQueueSocket(mandiId, onEvent)
  return ws
}
