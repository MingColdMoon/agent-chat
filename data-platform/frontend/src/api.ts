export interface User { id: string; username: string; created_at: string }
export interface Column { source?: string; name: string; type: string; included?: boolean }
export interface Dataset { id: string; name: string; table_name: string; columns: Column[]; created_at: string }
export interface SourceTable { name: string; columns: Column[]; row_count: number }
export interface Preview { filename: string; columns: Column[]; rows: Record<string, unknown>[]; row_count: number }
export interface SourcePreview { columns: Column[]; rows: Record<string, unknown>[]; source_rows: Record<string, unknown>[]; total: number }
export interface ChatLine { role: 'user' | 'assistant'; content: string }

const TOKEN_KEY = 'agent-chat-access-token'

export function getToken() { return sessionStorage.getItem(TOKEN_KEY) }

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers)
  const token = getToken()
  if (token) headers.set('Authorization', 'Bearer ' + token)
  if (!(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch(path, { ...options, headers })
  if (!response.ok) {
    let message = '请求失败 (' + response.status + ')'
    try { message = (await response.json()).detail || message } catch { /* keep status message */ }
    if (response.status === 401) sessionStorage.removeItem(TOKEN_KEY)
    throw new Error(message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export async function authenticate(mode: 'login' | 'register', username: string, password: string) {
  const result = await request<{ access_token: string; user: User }>('/api/auth/' + mode, {
    method: 'POST', body: JSON.stringify({ username, password }),
  })
  sessionStorage.setItem(TOKEN_KEY, result.access_token)
  return result.user
}

export const getMe = () => request<{ user: User }>('/api/auth/me')
export const logout = () => request<void>('/api/auth/logout', { method: 'POST' }).finally(() => sessionStorage.removeItem(TOKEN_KEY))
export const getDatasets = async () => (await request<{ datasets: Dataset[] }>('/api/datasets')).datasets
export const getSourceTables = async () => (await request<{ tables: SourceTable[] }>('/api/source-tables')).tables
export const getSourceRows = (name: string) => request<SourcePreview>('/api/source-tables/' + encodeURIComponent(name) + '/rows')
export const getDatasetRows = (id: string, page = 1, pageSize = 20, search = '') => {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize), search })
  return request<{ rows: (Record<string, unknown> & { __row_id: number })[]; total: number; columns: Column[]; page: number; page_size: number }>('/api/datasets/' + id + '/rows?' + params)
}
export const createDatasetRow = (id: string, row: Record<string, unknown>) => request<{ row_id: number; message: string }>('/api/datasets/' + id + '/rows', { method: 'POST', body: JSON.stringify(row) })
export const updateDatasetRow = (id: string, rowId: number, row: Record<string, unknown>) => request<{ message: string }>('/api/datasets/' + id + '/rows/' + rowId, { method: 'PUT', body: JSON.stringify(row) })
export const deleteDatasetRow = (id: string, rowId: number) => request<void>('/api/datasets/' + id + '/rows/' + rowId, { method: 'DELETE' })
export const getChat = async (id: string) => (await request<{ messages: ChatLine[] }>('/api/datasets/' + id + '/chat')).messages
export const deleteDataset = (id: string) => request<void>('/api/datasets/' + id, { method: 'DELETE' })
export const exportDataset = (id: string) => request<{ filename: string; columns: Column[]; rows: Record<string, unknown>[] }>('/api/datasets/' + id + '/export')

export async function previewFile(file: File) {
  const form = new FormData()
  form.append('file', file)
  return request<Preview>('/api/import/preview', { method: 'POST', body: form })
}

export function importDataset(payload: { table_name: string; display_name: string; columns: Column[]; rows: Record<string, unknown>[] }) {
  return request<{ dataset: Dataset; imported_rows: number }>('/api/import', { method: 'POST', body: JSON.stringify(payload) })
}

export function importSource(tableName: string, payload: { table_name: string; display_name: string; columns: Column[]; rows: Record<string, unknown>[] }) {
  return request<{ dataset: Dataset; imported_rows: number }>('/api/import/source/' + encodeURIComponent(tableName), { method: 'POST', body: JSON.stringify(payload) })
}

export function sendAnalysis(id: string, content: string, model: { provider: string; api_key: string; base_url: string; model: string }) {
  return request<{ answer: string; provider: string; stats: Record<string, Record<string, number | null>> }>('/api/datasets/' + id + '/chat', {
    method: 'POST', body: JSON.stringify({ content, ...model }),
  })
}
