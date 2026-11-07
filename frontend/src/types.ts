export type Role = 'user' | 'assistant'
export type ProviderId = 'demo' | 'openai' | 'deepseek' | 'custom'
export type ApiProviderId = Exclude<ProviderId, 'demo'>
export type AuthMode = 'login' | 'register'

export interface UserInfo {
  id: string
  username: string
  created_at: string
}

export interface AuthResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  expires_at: string
  user: UserInfo
}

export interface MeResponse {
  user: UserInfo
}

export interface AuthSubmission {
  mode: AuthMode
  username: string
  password: string
}

export interface ProviderProfile {
  api_key: string
  base_url: string
  model: string
}

export interface RuntimeSettings {
  provider: ProviderId
  profiles: Record<ApiProviderId, ProviderProfile>
  web_search_enabled: boolean
  tavily_api_key: string
  tavily_api_url: string
}

export interface RunOptions {
  provider: ProviderId
  api_key: string | null
  base_url: string | null
  model: string | null
  web_search_enabled: boolean
  tavily_api_key: string | null
  tavily_api_url: string | null
}

export interface ToolTrace {
  id: string
  name: string
  input: Record<string, unknown>
  state: 'running' | 'complete' | 'error'
  output?: unknown
}

export interface Message {
  id: string
  role: Role
  content: string
  created_at: string
  tools: ToolTrace[]
  error?: string
  streaming?: boolean
  provider?: string
  model?: string
  activity?: AgUiActivity | null
}

export interface AgentSummary {
  id: string
  name: string
  description: string
  category: string
  icon: string
  key: string | null
  is_builtin: boolean
  created_at: string
}

export interface AgentCreatePayload {
  name: string
  description: string
  category: string
  icon: string
  instructions: string
}

export interface PcBuildComponent {
  category: string
  name: string
  price: number
  reason: string
}

export interface PcBuildPlan {
  title: string
  use_case: string
  budget: number
  total_price: number
  budget_delta: number
  price_basis: string
  priorities: string[]
  components: PcBuildComponent[]
  compatibility_notes: string[]
  upgrade_path: string
}

export interface AgUiActivity {
  activityType: string
  content: Record<string, unknown>
}

export type MediaCrawlerPlatform =
  | 'xhs'
  | 'dy'
  | 'ks'
  | 'bili'
  | 'wb'
  | 'tieba'
  | 'zhihu'

export type MediaCrawlerTaskType = 'search' | 'detail' | 'creator'
export type MediaCrawlerStatus =
  | 'preview'
  | 'accepted'
  | 'busy'
  | 'unavailable'
  | 'error'
  | 'ok'
  | 'unknown'

export interface MediaCrawlerTaskSummary {
  query?: string
  targets?: string[]
  max_items?: number
  max_comments?: number
  comments?: boolean
  sub_comments?: boolean
  media?: boolean
  save_option?: string
}

export interface MediaCrawlerTaskRequest {
  platform?: string
  login_type?: string
  crawler_type?: string
  keywords?: string
  specified_ids?: string
  creator_ids?: string
  max_notes_count?: number
  max_comments_count?: number | null
  enable_comments?: boolean
  enable_sub_comments?: boolean
  enable_media?: boolean
  save_option?: string
}

export interface MediaCrawlerTaskResult {
  source: 'mediacrawler'
  status: MediaCrawlerStatus
  execution_ready?: boolean
  platform?: MediaCrawlerPlatform
  platform_label?: string
  crawler_type?: MediaCrawlerTaskType
  crawler_type_label?: string
  request?: MediaCrawlerTaskRequest
  summary?: MediaCrawlerTaskSummary
  warnings?: string[]
  message?: string
  detail?: string
  setup?: {
    api_url_env?: string
    token_env?: string
    service_command?: string
    upstream?: string
  }
}

export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
  messages: Message[]
  agent: AgentSummary | null
}

export interface ConversationSummary {
  id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
  agent: AgentSummary | null
}

export interface Health {
  ok: boolean
  mode: 'demo' | 'live'
  model: string
  tools: string[]
  providers: ProviderId[]
  server_credentials: ProviderId[]
  tavily_configured: boolean
  media_crawler_configured: boolean
}

export interface SendMessageResponse {
  run_id: string
  conversation_id: string
  user_message: Message
  stream_url: string
  provider: ProviderId
  model: string
}

export interface StreamEvent {
  id: number
  type: string
  at: string
  assistant_id?: string
  status?: 'thinking' | 'continuing' | 'answering'
  delta?: string
  tool?: ToolTrace
  message?: Message
  error?: string
  provider?: ProviderId
  model?: string
  agent?: AgentSummary | null
  messageId?: string
  activityType?: string
  content?: Record<string, unknown>
  snapshot?: Record<string, unknown>
}

