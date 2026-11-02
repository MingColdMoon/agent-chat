import type {
  AgentCreatePayload,
  AgentSummary,
  AuthResponse,
  Conversation,
  ConversationSummary,
  Health,
  MeResponse,
  RunOptions,
  SendMessageResponse,
  StreamEvent,
} from './types'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const TOKEN_STORAGE_KEY = 'agent-chat-access-token'

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export function getAccessToken(): string | null {
  return window.sessionStorage.getItem(TOKEN_STORAGE_KEY)
}

function setAccessToken(token: string) {
  window.sessionStorage.setItem(TOKEN_STORAGE_KEY, token)
}

function clearAccessToken() {
  window.sessionStorage.removeItem(TOKEN_STORAGE_KEY)
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers)
  headers.set('Content-Type', 'application/json')
  const accessToken = getAccessToken()
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`)
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  })

  if (!response.ok) {
    let message = `请求失败 (${response.status})`
    try {
      const body = await response.json()
      message = body.detail || body.error || message
    } catch {
      // Keep the status-based message when the body is not JSON.
    }
    if (response.status === 401) clearAccessToken()
    throw new ApiError(message, response.status)
  }

  if (response.status === 204) {
    return undefined as T
  }
  return response.json() as Promise<T>
}

export function getHealth(): Promise<Health> {
  return request<Health>('/api/health')
}

export async function getAgents(): Promise<AgentSummary[]> {
  const result = await request<{ agents: AgentSummary[] }>('/api/agents')
  return result.agents
}

export async function createAgent(
  payload: AgentCreatePayload,
): Promise<AgentSummary> {
  const result = await request<{ agent: AgentSummary }>('/api/agents', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  return result.agent
}

export function deleteAgent(id: string): Promise<void> {
  return request<void>(`/api/agents/${id}`, { method: 'DELETE' })
}

export function getCurrentUser(): Promise<MeResponse> {
  return request<MeResponse>('/api/auth/me')
}

export async function login(
  username: string,
  password: string,
): Promise<AuthResponse> {
  const result = await request<AuthResponse>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
  setAccessToken(result.access_token)
  return result
}

export async function register(
  username: string,
  password: string,
): Promise<AuthResponse> {
  const result = await request<AuthResponse>('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
  setAccessToken(result.access_token)
  return result
}

export async function logout(): Promise<void> {
  try {
    await request<void>('/api/auth/logout', { method: 'POST' })
  } finally {
    clearAccessToken()
  }
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

export async function consumeEventStream(
  streamUrl: string,
  onEvent: (event: StreamEvent) => void,
  onReconnect: () => void,
  signal: AbortSignal,
) {
  let lastEventId = 0
  while (!signal.aborted) {
    try {
      const headers = new Headers({
        Accept: 'text/event-stream',
      })
      const accessToken = getAccessToken()
      if (accessToken) {
        headers.set('Authorization', `Bearer ${accessToken}`)
      }
      if (lastEventId) {
        headers.set('Last-Event-ID', String(lastEventId))
      }

      const response = await fetch(`${API_BASE}${streamUrl}`, {
        headers,
        signal,
      })
      if (!response.ok) {
        let message = `事件流连接失败 (${response.status})`
        try {
          const body = await response.json()
          message = body.detail || message
        } catch {
          // Keep the status-based message.
        }
        if (response.status === 401) clearAccessToken()
        throw new ApiError(message, response.status)
      }
      if (!response.body) {
        throw new ApiError('浏览器不支持流式响应', 500)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const blocks = buffer.split(/\r?\n\r?\n/)
        buffer = blocks.pop() || ''
        for (const block of blocks) {
          const data = block
            .split(/\r?\n/)
            .filter((line) => line.startsWith('data:'))
            .map((line) => line.slice(5).trimStart())
            .join('\n')
          if (!data) continue
          const event = JSON.parse(data) as StreamEvent
          if (Number.isFinite(event.id)) lastEventId = event.id
          onEvent(event)
          if (event.type === 'done') return
        }
      }
      throw new ApiError('事件流意外结束', 502)
    } catch (error) {
      if (signal.aborted) return
      if (error instanceof ApiError && error.status < 500) throw error
      onReconnect()
      await sleep(1200)
    }
  }
}

export async function getConversations(): Promise<ConversationSummary[]> {
  const result = await request<{ conversations: ConversationSummary[] }>(
    '/api/conversations',
  )
  return result.conversations
}

export async function getConversation(id: string): Promise<Conversation> {
  const result = await request<{ conversation: Conversation }>(
    `/api/conversations/${id}`,
  )
  return result.conversation
}

export async function createConversation(
  agentId?: string | null,
): Promise<Conversation> {
  const result = await request<{ conversation: Conversation }>(
    '/api/conversations',
    {
      method: 'POST',
      body: agentId ? JSON.stringify({ agent_id: agentId }) : undefined,
    },
  )
  return result.conversation
}

export async function applyAgent(
  conversationId: string,
  agentId: string,
): Promise<Conversation> {
  const result = await request<{ conversation: Conversation }>(
    `/api/conversations/${conversationId}/agent`,
    {
      method: 'PATCH',
      body: JSON.stringify({ agent_id: agentId }),
    },
  )
  return result.conversation
}

export function deleteConversation(id: string): Promise<void> {
  return request<void>(`/api/conversations/${id}`, { method: 'DELETE' })
}

export function sendMessage(
  conversationId: string,
  content: string,
  runtime: RunOptions,
): Promise<SendMessageResponse> {
  return request<SendMessageResponse>(
    `/api/conversations/${conversationId}/messages`,
    {
      method: 'POST',
      body: JSON.stringify({ content, runtime }),
    },
  )
}

