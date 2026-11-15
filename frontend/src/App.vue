<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
} from 'vue'
import {
  ArrowUp,
  ChevronDown,
  Files,
  LoaderCircle,
  Menu,
  MessageSquareText,
  Paperclip,
  Plus,
  RefreshCw,
  SlidersHorizontal,
  Sparkles,
  Store,
  X,
} from 'lucide-vue-next'
import AgentMarketplace from './components/AgentMarketplace.vue'
import AdminKnowledgeManager from './components/AdminKnowledgeManager.vue'
import AttachmentChip from './components/AttachmentChip.vue'
import AuthScreen from './components/AuthScreen.vue'
import ChatMessage from './components/ChatMessage.vue'
import ConversationSidebar from './components/ConversationSidebar.vue'
import MediaCrawlerConfigurator from './components/MediaCrawlerConfigurator.vue'
import PcBuilderConfigurator from './components/PcBuilderConfigurator.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import {
  createConversation,
  createAgent,
  consumeEventStream,
  applyAgent,
  deleteAgent,
  deleteAttachment,
  deleteConversation,
  ApiError,
  getConversation,
  getCurrentUser,
  getConversations,
  getConversationAttachments,
  getHealth,
  getRagStatus,
  getAgents,
  login,
  logout,
  register,
  sendMessage,
  uploadAttachment,
} from './api'
import type {
  AgentCreatePayload,
  AgentSummary,
  AttachmentSummary,
  AuthSubmission,
  ConversationSummary,
  Health,
  Message,
  ProviderId,
  RagKnowledgeStatus,
  RunOptions,
  RuntimeSettings,
  StreamEvent,
  UserInfo,
} from './types'

const SETTINGS_STORAGE_KEY = 'agent-chat-runtime-settings'

const providerOptions: Array<{ id: ProviderId; label: string }> = [
  { id: 'demo', label: '演示模式' },
  { id: 'openai', label: 'ChatGPT / OpenAI' },
  { id: 'deepseek', label: 'DeepSeek' },
  { id: 'custom', label: '自定义兼容服务' },
]

const providerLabels: Record<ProviderId, string> = {
  demo: '演示模式',
  openai: 'ChatGPT / OpenAI',
  deepseek: 'DeepSeek',
  custom: '自定义服务',
}

const providerPresets = {
  openai: {
    base_url: 'https://api.openai.com/v1',
    model: 'gpt-4o-mini',
  },
  deepseek: {
    base_url: 'https://api.deepseek.com/v1',
    model: 'deepseek-chat',
  },
  custom: {
    base_url: '',
    model: '',
  },
}

function createRuntimeSettings(): RuntimeSettings {
  return {
    provider: 'demo',
    profiles: {
      openai: {
        api_key: '',
        ...providerPresets.openai,
      },
      deepseek: {
        api_key: '',
        ...providerPresets.deepseek,
      },
      custom: {
        api_key: '',
        ...providerPresets.custom,
      },
    },
    web_search_enabled: false,
    tavily_api_key: '',
    tavily_api_url: 'https://api.tavily.com',
  }
}

const conversations = ref<ConversationSummary[]>([])
const agents = ref<AgentSummary[]>([])
const user = ref<UserInfo | null>(null)
const authLoading = ref(true)
const authBusy = ref(false)
const authError = ref('')
const currentId = ref<string | null>(null)
const currentTitle = ref('新会话')
const messages = ref<Message[]>([])
const health = ref<Health | null>(null)
const input = ref('')
const busy = ref(false)
const statusText = ref('就绪')
const pageError = ref('')
const sidebarOpen = ref(false)
const settingsOpen = ref(false)
const marketplaceOpen = ref(false)
const knowledgeOpen = ref(false)
const agentCreateOpen = ref(false)
const agentsLoading = ref(false)
const agentMutationBusy = ref(false)
const agentError = ref('')
const ragStatus = ref<RagKnowledgeStatus | null>(null)
const pendingAttachments = ref<AttachmentSummary[]>([])
const conversationAttachments = ref<AttachmentSummary[]>([])
const uploadBusy = ref(false)
const draggingFiles = ref(false)
const referenceOpen = ref(false)
const runtimeSettings = reactive<RuntimeSettings>(createRuntimeSettings())
const composer = ref<HTMLTextAreaElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const messageScroller = ref<HTMLElement | null>(null)
const stickToBottom = ref(true)
let activeStreamController: AbortController | null = null
let streamCompleted = false

function abortActiveStream() {
  activeStreamController?.abort()
  activeStreamController = null
}

function discardPendingFiles() {
  const unbound = pendingAttachments.value.filter(
    (attachment) => !attachment.referenced,
  )
  pendingAttachments.value = []
  for (const attachment of unbound) {
    void deleteAttachment(attachment.id).catch(() => undefined)
  }
}

const suggestions = computed(() => {
  if (currentAgent.value?.key === 'customer-service') {
    return [
      { label: '查询订单进度', prompt: '我的订单一直没有发货，怎么处理？' },
      { label: '申请退款', prompt: '我想申请退款，需要准备哪些信息？' },
      { label: '修改收货地址', prompt: '订单还没发货，可以修改收货地址吗？' },
    ]
  }
  if (currentAgent.value?.key === 'automated-reports') {
    return [
      { label: '生成销售报表', prompt: '帮我生成一份本周销售分析报表' },
      { label: '分析转化率', prompt: '请设计一份转化率下降排查报表' },
      { label: '制作运营简报', prompt: '把本月运营数据整理成一份管理简报' },
    ]
  }
  return [
    {
      label: '查询当前时间',
      prompt: '现在几点了？',
    },
    {
      label: '执行数学计算',
      prompt: '计算 (128 + 72) * 3 / 5',
    },
    runtimeSettings.web_search_enabled
      ? {
          label: '联网搜索最新资讯',
          prompt: '搜索今天的 AI 行业重要新闻',
        }
      : {
          label: '了解 Agent 原理',
          prompt: 'LangChain Agent 是如何工作的？',
        },
  ]
})

const sendDisabled = computed(
  () =>
    busy.value ||
    uploadBusy.value ||
    (!input.value.trim() && pendingAttachments.value.length === 0),
)
const referenceableAttachments = computed(() =>
  conversationAttachments.value.filter(
    (attachment) =>
      !pendingAttachments.value.some((item) => item.id === attachment.id),
  ),
)
const ragSources = computed(() => ragStatus.value?.sources || [])
const currentSummary = computed(() =>
  conversations.value.find((item) => item.id === currentId.value),
)
const currentAgent = computed(() => currentSummary.value?.agent || null)
const ragRevisionNotice = computed(() => {
  if (currentAgent.value?.key !== 'rag-assistant' || !ragStatus.value) {
    return null
  }
  for (const message of [...messages.value].reverse()) {
    if (message.activity?.activityType !== 'rag-retrieval') continue
    const revision = Number(message.activity.content.revision || 0)
    if (revision > 0 && ragStatus.value.revision > revision) {
      return {
        previous: revision,
        current: ragStatus.value.revision,
      }
    }
    break
  }
  return null
})
const composerPlaceholder = computed(() =>
  currentAgent.value?.key === 'rag-assistant'
    ? '直接提问项目知识库'
    : '给 Agent 发送消息，或拖入文件',
)
const headerMeta = computed(() =>
  messages.value.length > 0 ? `${messages.value.length} 条消息` : '新会话',
)
const activeProfile = computed(() => {
  const provider =
    runtimeSettings.provider === 'demo'
      ? 'openai'
      : runtimeSettings.provider
  return runtimeSettings.profiles[provider]
})
const providerLabel = computed(
  () => providerLabels[runtimeSettings.provider],
)
const providerDetail = computed(() =>
  runtimeSettings.provider === 'demo'
    ? '无需 API Key'
    : activeProfile.value.model || '未配置模型',
)
const providerLive = computed(
  () =>
    runtimeSettings.provider !== 'demo' &&
    (!!activeProfile.value.api_key.trim() ||
      !!health.value?.server_credentials.includes(
        runtimeSettings.provider,
      )),
)

function persistRuntimeSettings() {
  try {
    window.sessionStorage.setItem(
      SETTINGS_STORAGE_KEY,
      JSON.stringify(runtimeSettings),
    )
  } catch {
    // The app still works when browser storage is unavailable.
  }
}

function hydrateRuntimeSettings(): boolean {
  try {
    const raw = window.sessionStorage.getItem(SETTINGS_STORAGE_KEY)
    if (!raw) return false
    const saved = JSON.parse(raw) as Partial<RuntimeSettings>
    const defaults = createRuntimeSettings()
    const provider = providerOptions.some(
      (item) => item.id === saved.provider,
    )
      ? (saved.provider as ProviderId)
      : 'demo'

    runtimeSettings.provider = provider
    for (const key of ['openai', 'deepseek', 'custom'] as const) {
      runtimeSettings.profiles[key] = {
        ...defaults.profiles[key],
        ...(saved.profiles?.[key] || {}),
      }
    }
    runtimeSettings.web_search_enabled =
      saved.web_search_enabled === true
    runtimeSettings.tavily_api_key =
      typeof saved.tavily_api_key === 'string'
        ? saved.tavily_api_key
        : ''
    runtimeSettings.tavily_api_url =
      typeof saved.tavily_api_url === 'string' &&
      saved.tavily_api_url.trim()
        ? saved.tavily_api_url
        : defaults.tavily_api_url
    return true
  } catch {
    return false
  }
}

function applyProviderPreset(providerId: ProviderId) {
  if (providerId === 'demo') return
  const profile = runtimeSettings.profiles[providerId]
  const preset = providerPresets[providerId]
  if (!profile.base_url.trim()) profile.base_url = preset.base_url
  if (!profile.model.trim()) profile.model = preset.model
}

function handleProviderChange() {
  applyProviderPreset(runtimeSettings.provider)
  persistRuntimeSettings()
  if (
    runtimeSettings.provider !== 'demo' &&
    !activeProfile.value.api_key.trim()
  ) {
    settingsOpen.value = true
  }
}

function saveSettings(settings: RuntimeSettings) {
  Object.assign(runtimeSettings, settings)
  persistRuntimeSettings()
  settingsOpen.value = false
  pageError.value = ''
}

function buildRunOptions(): RunOptions {
  const profile =
    runtimeSettings.provider === 'demo' ? null : activeProfile.value
  return {
    provider: runtimeSettings.provider,
    api_key: profile?.api_key.trim() || null,
    base_url: profile?.base_url.trim() || null,
    model: profile?.model.trim() || null,
    web_search_enabled: runtimeSettings.web_search_enabled,
    tavily_api_key: runtimeSettings.tavily_api_key.trim() || null,
    tavily_api_url: runtimeSettings.tavily_api_url.trim() || null,
  }
}

function validateRuntimeSettings(): string | null {
  if (runtimeSettings.provider !== 'demo') {
    if (
      !activeProfile.value.api_key.trim() &&
      !health.value?.server_credentials.includes(runtimeSettings.provider)
    ) {
      return `请填写 ${providerLabel.value} 的 API Key`
    }
    if (!activeProfile.value.base_url.trim()) {
      return `请填写 ${providerLabel.value} 的 API 地址`
    }
    if (!activeProfile.value.model.trim()) {
      return `请填写 ${providerLabel.value} 的模型名称`
    }
  }
  if (
    runtimeSettings.web_search_enabled &&
    !runtimeSettings.tavily_api_key.trim() &&
    !health.value?.tavily_configured
  ) {
    return '请填写 Tavily API Key'
  }
  if (
    runtimeSettings.web_search_enabled &&
    !runtimeSettings.tavily_api_url.trim()
  ) {
    return '请填写 Tavily API 地址'
  }
  return null
}

function setStatusFromEvent(event: StreamEvent) {
  if (event.type === 'assistant.status') {
    if (event.status === 'thinking') statusText.value = '正在思考'
    if (event.status === 'continuing') statusText.value = '正在整理工具结果'
    if (event.status === 'answering') statusText.value = '正在回答'
  }
  if (event.type === 'tool.started') statusText.value = '正在调用工具'
}

function scrollToBottom(force = false) {
  void nextTick(() => {
    requestAnimationFrame(() => {
      const element = messageScroller.value
      if (!element || (!force && !stickToBottom.value)) return
      element.scrollTop = element.scrollHeight
    })
  })
}

function updateScrollStickiness() {
  const element = messageScroller.value
  if (!element) return
  const distance =
    element.scrollHeight - element.scrollTop - element.clientHeight
  stickToBottom.value = distance < 72
}

async function loadWorkspace() {
  const [healthResult, conversationList, agentList, ragStatusResult] =
    await Promise.all([
      getHealth(),
      getConversations(),
      getAgents(),
      getRagStatus().catch(() => null),
    ])
  health.value = healthResult
  ragStatus.value = ragStatusResult
  const hadSavedSettings = window.sessionStorage.getItem(
    SETTINGS_STORAGE_KEY,
  )
  if (!hadSavedSettings && healthResult.server_credentials[0]) {
    runtimeSettings.provider = healthResult.server_credentials[0]
    persistRuntimeSettings()
  }
  conversations.value = conversationList
  agents.value = agentList
  messages.value = []
  currentId.value = null
  currentTitle.value = '新会话'
  if (conversationList[0]) {
    await selectConversation(conversationList[0].id)
  }
}

async function restoreSession() {
  authLoading.value = true
  authError.value = ''
  try {
    const response = await getCurrentUser()
    await loadWorkspace()
    user.value = response.user
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      user.value = null
      return
    }
    authError.value =
      error instanceof Error ? error.message : '无法连接后端服务'
  } finally {
    authLoading.value = false
  }
}

async function handleAuthenticate(submission: AuthSubmission) {
  if (authBusy.value) return
  authBusy.value = true
  authError.value = ''
  try {
    const response =
      submission.mode === 'login'
        ? await login(submission.username, submission.password)
        : await register(submission.username, submission.password)
    await loadWorkspace()
    user.value = response.user
  } catch (error) {
    authError.value =
      error instanceof Error ? error.message : '登录失败，请重试'
  } finally {
    authBusy.value = false
  }
}

async function handleLogout() {
  abortActiveStream()
  discardPendingFiles()
  try {
    await logout()
  } finally {
    user.value = null
    conversations.value = []
    agents.value = []
    messages.value = []
    conversationAttachments.value = []
    referenceOpen.value = false
    draggingFiles.value = false
    currentId.value = null
    currentTitle.value = '新会话'
    pageError.value = ''
    authError.value = ''
    sidebarOpen.value = false
    settingsOpen.value = false
    marketplaceOpen.value = false
    knowledgeOpen.value = false
    agentCreateOpen.value = false
    ragStatus.value = null
    window.sessionStorage.removeItem(SETTINGS_STORAGE_KEY)
    Object.assign(runtimeSettings, createRuntimeSettings())
  }
}

function expireSession(message = '登录已过期，请重新登录') {
  abortActiveStream()
  user.value = null
  authError.value = message
}

async function loadConversationList() {
  conversations.value = await getConversations()
  const selected = conversations.value.find(
    (item) => item.id === currentId.value,
  )
  if (selected) currentTitle.value = selected.title
}

async function loadConversationAttachments(conversationId: string) {
  conversationAttachments.value = await getConversationAttachments(
    conversationId,
  )
}

async function selectConversation(id: string) {
  if (busy.value || uploadBusy.value || id === currentId.value) {
    sidebarOpen.value = false
    return
  }
  try {
    const [conversation, attachments, currentRagStatus] = await Promise.all([
      getConversation(id),
      getConversationAttachments(id),
      getRagStatus().catch(() => null),
    ])
    abortActiveStream()
    discardPendingFiles()
    currentId.value = conversation.id
    currentTitle.value = conversation.title
    messages.value = conversation.messages
    conversationAttachments.value = attachments
    if (currentRagStatus) ragStatus.value = currentRagStatus
    referenceOpen.value = false
    marketplaceOpen.value = false
    knowledgeOpen.value = false
    stickToBottom.value = true
    pageError.value = ''
    sidebarOpen.value = false
    if (conversation.messages.length) {
      scrollToBottom(true)
    } else {
      void nextTick(() => {
        if (messageScroller.value) messageScroller.value.scrollTop = 0
      })
    }
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : '加载会话失败'
  }
}

async function refreshAgents() {
  agentsLoading.value = true
  agentError.value = ''
  try {
    agents.value = await getAgents()
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      expireSession()
      return
    }
    agentError.value =
      error instanceof Error ? error.message : '加载智能体失败'
  } finally {
    agentsLoading.value = false
  }
}

function openMarketplace() {
  if (busy.value || uploadBusy.value) return
  marketplaceOpen.value = true
  knowledgeOpen.value = false
  settingsOpen.value = false
  sidebarOpen.value = false
  agentError.value = ''
  void refreshAgents()
}

async function refreshRagStatus() {
  try {
    ragStatus.value = await getRagStatus()
  } catch {
    // Keep the previous status; the management page reports its own errors.
  }
}

function openKnowledgeManager() {
  if (
    user.value?.role !== 'admin' ||
    busy.value ||
    uploadBusy.value
  ) {
    return
  }
  knowledgeOpen.value = true
  marketplaceOpen.value = false
  settingsOpen.value = false
  sidebarOpen.value = false
  pageError.value = ''
}

function openAgentCreator() {
  agentError.value = ''
  agentCreateOpen.value = true
}

async function handleCreateAgent(payload: AgentCreatePayload) {
  if (agentMutationBusy.value) return
  agentMutationBusy.value = true
  agentError.value = ''
  try {
    const created = await createAgent(payload)
    agents.value = await getAgents()
    agentCreateOpen.value = false
    agentError.value = ''
    statusText.value = `已创建 ${created.name}`
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      expireSession()
      return
    }
    agentError.value =
      error instanceof Error ? error.message : '创建智能体失败'
  } finally {
    agentMutationBusy.value = false
  }
}

async function startAgentConversation(agent: AgentSummary) {
  if (busy.value || agentMutationBusy.value) return
  agentMutationBusy.value = true
  agentError.value = ''
  try {
    const conversation = await createConversation(agent.id)
    marketplaceOpen.value = false
    await loadConversationList()
    await selectConversation(conversation.id)
    statusText.value = `已进入 ${agent.name}`
    void nextTick(() => composer.value?.focus())
  } catch (error) {
    agentError.value =
      error instanceof Error ? error.message : '创建智能体会话失败'
  } finally {
    agentMutationBusy.value = false
  }
}

async function applyAgentToCurrent(agent: AgentSummary) {
  if (!currentId.value || agentMutationBusy.value) return
  agentMutationBusy.value = true
  agentError.value = ''
  try {
    if (agent.key === 'rag-assistant') {
      discardPendingFiles()
      referenceOpen.value = false
    }
    const conversation = await applyAgent(currentId.value, agent.id)
    messages.value = conversation.messages
    currentTitle.value = conversation.title
    await loadConversationList()
    marketplaceOpen.value = false
    stickToBottom.value = true
    scrollToBottom(true)
    statusText.value = `已应用 ${agent.name}`
  } catch (error) {
    agentError.value =
      error instanceof Error ? error.message : '应用智能体失败'
  } finally {
    agentMutationBusy.value = false
  }
}

async function removeAgent(agent: AgentSummary) {
  if (
    agent.is_builtin ||
    agentMutationBusy.value ||
    !window.confirm(`删除智能体“${agent.name}”？`)
  ) {
    return
  }
  agentMutationBusy.value = true
  agentError.value = ''
  try {
    await deleteAgent(agent.id)
    agents.value = await getAgents()
    if (currentAgent.value?.id === agent.id) {
      await refreshCurrentConversation()
    }
  } catch (error) {
    agentError.value =
      error instanceof Error ? error.message : '删除智能体失败'
  } finally {
    agentMutationBusy.value = false
  }
}

function startNewChat() {
  if (busy.value || uploadBusy.value) return
  abortActiveStream()
  currentId.value = null
  currentTitle.value = '新会话'
  messages.value = []
  discardPendingFiles()
  conversationAttachments.value = []
  referenceOpen.value = false
  draggingFiles.value = false
  marketplaceOpen.value = false
  knowledgeOpen.value = false
  stickToBottom.value = true
  pageError.value = ''
  sidebarOpen.value = false
  statusText.value = '就绪'
  void nextTick(() => composer.value?.focus())
}

async function removeConversation(id: string) {
  if (
    busy.value ||
    uploadBusy.value ||
    !window.confirm('删除这个会话？')
  ) {
    return
  }
  try {
    await deleteConversation(id)
    if (id === currentId.value) {
      startNewChat()
      if (conversations.value.length > 0) {
        const next = conversations.value.find((item) => item.id !== id)
        if (next) await selectConversation(next.id)
      }
    }
    await loadConversationList()
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : '删除会话失败'
  }
}

async function ensureConversation(): Promise<string> {
  if (currentId.value) return currentId.value
  const conversation = await createConversation()
  currentId.value = conversation.id
  currentTitle.value = conversation.title
  conversationAttachments.value = []
  referenceOpen.value = false
  conversations.value.unshift({
    id: conversation.id,
    title: conversation.title,
    created_at: conversation.created_at,
    updated_at: conversation.updated_at,
    message_count: 0,
    agent: conversation.agent,
  })
  return conversation.id
}

function assistantMessage(assistantId: string): Message | undefined {
  return messages.value.find((item) => item.id === assistantId)
}

function handleStreamEvent(
  event: StreamEvent,
  context: { assistantId: string | null },
) {
    setStatusFromEvent(event)

    if (event.type === 'run.started' && event.assistant_id) {
      context.assistantId = event.assistant_id
      if (!assistantMessage(event.assistant_id)) {
        messages.value.push({
          id: event.assistant_id,
          role: 'assistant',
          content: '',
          created_at: event.at,
          tools: [],
          attachments: [],
          streaming: true,
          provider: event.provider,
          model: event.model,
        })
      }
      statusText.value = '正在思考'
      scrollToBottom()
      return
    }

    if (!context.assistantId) return
    const message = assistantMessage(context.assistantId)
    if (!message) return

    if (event.type === 'assistant.delta' && event.delta) {
      message.content += event.delta
      message.streaming = true
      statusText.value = '正在回答'
      scrollToBottom()
      return
    }

    if (event.type === 'tool.started' && event.tool) {
      const existing = message.tools.find((item) => item.id === event.tool?.id)
      if (existing) Object.assign(existing, event.tool)
      else message.tools.push(event.tool)
      scrollToBottom()
      return
    }

    if (event.type === 'tool.finished' && event.tool) {
      const existing = message.tools.find((item) => item.id === event.tool?.id)
      if (existing) Object.assign(existing, event.tool)
      else message.tools.push(event.tool)
      scrollToBottom()
      return
    }

    if (event.type === 'assistant.final' && event.message) {
      message.content = event.message.content
      message.tools = event.message.tools
      message.activity = event.message.activity
      message.streaming = false
      scrollToBottom()
      return
    }

    if (
      event.type === 'ACTIVITY_SNAPSHOT' &&
      event.activityType &&
      event.content
    ) {
      message.activity = {
        activityType: event.activityType,
        content: event.content,
      }
      scrollToBottom()
      return
    }

    if (event.type === 'run.error') {
      message.error = event.error || 'Agent 运行失败'
      message.streaming = false
      statusText.value = '运行失败'
      return
    }

    if (event.type === 'done') {
      streamCompleted = true
      message.streaming = false
      busy.value = false
      statusText.value = '就绪'
      void refreshCurrentConversation()
    }
}

async function attachStream(streamUrl: string) {
  abortActiveStream()
  streamCompleted = false
  const context: { assistantId: string | null } = { assistantId: null }
  const controller = new AbortController()
  activeStreamController = controller

  try {
    await consumeEventStream(
      streamUrl,
      (event) => handleStreamEvent(event, context),
      () => {
        if (!streamCompleted) statusText.value = '正在重新连接'
      },
      controller.signal,
    )
  } catch (error) {
    if (controller.signal.aborted) return
    if (error instanceof ApiError && error.status === 401) {
      expireSession()
      return
    }
    busy.value = false
    statusText.value = '事件流中断'
    pageError.value =
      error instanceof Error ? error.message : '无法读取事件流'
  } finally {
    if (activeStreamController === controller) {
      activeStreamController = null
    }
  }
}

async function refreshCurrentConversation() {
  try {
    await loadConversationList()
    if (!currentId.value) return
    const [conversation, currentRagStatus] = await Promise.all([
      getConversation(currentId.value),
      getRagStatus().catch(() => null),
    ])
    messages.value = conversation.messages
    currentTitle.value = conversation.title
    if (currentRagStatus) ragStatus.value = currentRagStatus
    await loadConversationAttachments(currentId.value)
    scrollToBottom()
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : '刷新会话失败'
  }
}

function openFilePicker() {
  if (busy.value || uploadBusy.value) return
  fileInput.value?.click()
}

function insertFileMention(attachment: AttachmentSummary) {
  const mention = `@${attachment.filename}`
  if (input.value.includes(mention)) return
  input.value = `${input.value}${input.value.trim() ? ' ' : ''}${mention} `
  void nextTick(() => {
    resizeComposer()
    composer.value?.focus()
  })
}

function referenceAttachment(attachment: AttachmentSummary) {
  if (
    !pendingAttachments.value.some((item) => item.id === attachment.id)
  ) {
    pendingAttachments.value.push(attachment)
  }
  insertFileMention(attachment)
  referenceOpen.value = false
}

async function uploadFiles(files: File[]) {
  if (currentAgent.value?.key === 'rag-assistant') {
    pageError.value = '项目知识库 RAG 直接读取 rag 目录，无需上传附件'
    return
  }
  if (!files.length || busy.value || uploadBusy.value) return
  const available = 5 - pendingAttachments.value.length
  if (available <= 0) {
    pageError.value = '每条消息最多引用 5 个文件'
    return
  }

  const selected = files.slice(0, available)
  if (files.length > available) {
    pageError.value = '每条消息最多引用 5 个文件，已忽略多余文件'
  }
  const oversized = selected.find(
    (file) => file.size > 15 * 1024 * 1024,
  )
  if (oversized) {
    pageError.value = `文件 ${oversized.name} 超过 15 MB`
    return
  }

  uploadBusy.value = true
  statusText.value = '正在上传文件'
  pageError.value = ''
  try {
    const conversationId = await ensureConversation()
    for (const file of selected) {
      try {
        const attachment = await uploadAttachment(conversationId, file)
        if (
          !pendingAttachments.value.some(
            (item) => item.id === attachment.id,
          )
        ) {
          pendingAttachments.value.push(attachment)
        }
        if (
          !conversationAttachments.value.some(
            (item) => item.id === attachment.id,
          )
        ) {
          conversationAttachments.value.push(attachment)
        }
      } catch (error) {
        pageError.value =
          error instanceof Error
            ? `${file.name}：${error.message}`
            : `${file.name} 上传失败`
      }
    }
    statusText.value = pendingAttachments.value.length
      ? `已引用 ${pendingAttachments.value.length} 个文件`
      : '就绪'
    void nextTick(() => composer.value?.focus())
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      expireSession()
      return
    }
    pageError.value =
      error instanceof Error ? error.message : '文件上传失败'
    statusText.value = '上传失败'
  } finally {
    uploadBusy.value = false
  }
}

async function handleFileInput(event: Event) {
  const inputElement = event.target as HTMLInputElement
  const files = Array.from(inputElement.files || [])
  inputElement.value = ''
  await uploadFiles(files)
}

async function handleFileDrop(event: DragEvent) {
  draggingFiles.value = false
  await uploadFiles(Array.from(event.dataTransfer?.files || []))
}

async function removePendingAttachment(attachment: AttachmentSummary) {
  pendingAttachments.value = pendingAttachments.value.filter(
    (item) => item.id !== attachment.id,
  )
  input.value = input.value.replace(`@${attachment.filename}`, '').trim()
  if (!attachment.referenced) {
    try {
      await deleteAttachment(attachment.id)
      conversationAttachments.value = conversationAttachments.value.filter(
        (item) => item.id !== attachment.id,
      )
    } catch (error) {
      pageError.value =
        error instanceof Error ? error.message : '移除附件失败'
    }
  }
  statusText.value = pendingAttachments.value.length
    ? `已引用 ${pendingAttachments.value.length} 个文件`
    : '就绪'
  resizeComposer()
}

async function submitMessage() {
  const content = input.value.trim()
  const submittedAttachments = [...pendingAttachments.value]
  const attachmentIds = submittedAttachments.map((item) => item.id)
  if (
    (!content && attachmentIds.length === 0) ||
    busy.value ||
    uploadBusy.value
  ) {
    return
  }
  const validationError = validateRuntimeSettings()
  if (validationError) {
    pageError.value = validationError
    settingsOpen.value = true
    return
  }

  busy.value = true
  pageError.value = ''
  statusText.value = '正在提交'
  input.value = ''
  resizeComposer()
  referenceOpen.value = false

  const optimisticId = `local-${crypto.randomUUID()}`
  messages.value.push({
    id: optimisticId,
    role: 'user',
    content,
    created_at: new Date().toISOString(),
    tools: [],
    attachments: submittedAttachments,
  })
  stickToBottom.value = true
  scrollToBottom(true)

  try {
    const conversationId = await ensureConversation()
    const result = await sendMessage(
      conversationId,
      content,
      buildRunOptions(),
      attachmentIds,
    )
    const optimistic = messages.value.find((item) => item.id === optimisticId)
    if (optimistic) {
      Object.assign(optimistic, result.user_message, {
        provider: result.provider,
        model: result.model,
      })
    }
    pendingAttachments.value = []
    void loadConversationList()
    void loadConversationAttachments(conversationId)
    attachStream(result.stream_url)
  } catch (error) {
    busy.value = false
    if (!input.value) input.value = content
    resizeComposer()
    if (error instanceof ApiError && error.status === 401) {
      expireSession()
      return
    }
    statusText.value = '发送失败'
    pageError.value = error instanceof Error ? error.message : '发送消息失败'
  }
}

function useSuggestion(prompt: string) {
  input.value = prompt
  resizeComposer()
  void nextTick(() => {
    composer.value?.focus()
    void submitMessage()
  })
}

function resizeComposer() {
  const element = composer.value
  if (!element) return
  element.style.height = 'auto'
  element.style.height = `${Math.min(element.scrollHeight, 168)}px`
}

function handleComposerKeydown(event: KeyboardEvent) {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    void submitMessage()
  }
}

onMounted(async () => {
  hydrateRuntimeSettings()
  await restoreSession()
  if (user.value) {
    void nextTick(() => composer.value?.focus())
  }
})

onBeforeUnmount(() => {
  abortActiveStream()
})
</script>

<template>
  <div v-if="authLoading" class="boot-screen">
    <span class="brand-mark" aria-hidden="true">
      <span class="boot-pulse"></span>
    </span>
    <span>正在连接 Agent Chat</span>
  </div>

  <AuthScreen
    v-else-if="!user"
    :busy="authBusy"
    :error="authError"
    @submit="handleAuthenticate"
  />

  <div v-else class="app-shell">
    <ConversationSidebar
      :conversations="conversations"
      :current-id="currentId"
      :open="sidebarOpen"
      :provider-label="providerLabel"
      :provider-detail="providerDetail"
      :provider-live="providerLive"
      :user="user"
      :marketplace-active="marketplaceOpen"
      :knowledge-active="knowledgeOpen"
      :is-admin="user.role === 'admin'"
      @new-chat="startNewChat"
      @select="selectConversation"
      @remove="removeConversation"
      @close="sidebarOpen = false"
      @logout="handleLogout"
      @marketplace="openMarketplace"
      @knowledge="openKnowledgeManager"
    />

    <button
      v-if="sidebarOpen"
      class="sidebar-backdrop"
      type="button"
      aria-label="关闭会话列表"
      @click="sidebarOpen = false"
    ></button>

    <main
      class="main-panel"
      :class="{
        'marketplace-mode': marketplaceOpen,
        'knowledge-mode': knowledgeOpen,
      }"
    >
      <AdminKnowledgeManager
        v-if="knowledgeOpen"
        @back="knowledgeOpen = false"
        @changed="refreshRagStatus"
      />
      <AgentMarketplace
        v-else-if="marketplaceOpen"
        :agents="agents"
        :loading="agentsLoading"
        :mutation-busy="agentMutationBusy"
        :error="agentError"
        :current-conversation-id="currentId"
        :current-agent-id="currentAgent?.id || null"
        :create-open="agentCreateOpen"
        @back="marketplaceOpen = false"
        @create="handleCreateAgent"
        @open-create="openAgentCreator"
        @close-create="agentCreateOpen = false"
        @start="startAgentConversation"
        @apply="applyAgentToCurrent"
        @delete="removeAgent"
      />

      <template v-else>
        <div class="top-area">
        <header class="topbar">
          <button
            class="icon-button mobile-menu"
            type="button"
            title="打开会话列表"
            aria-label="打开会话列表"
            @click="sidebarOpen = true"
          >
            <Menu :size="19" />
          </button>
          <div class="topbar-title">
            <span class="topbar-kicker">
              {{ currentAgent ? 'AGENT SESSION' : 'WORKSPACE' }}
            </span>
            <h1>{{ currentSummary?.title || currentTitle }}</h1>
            <span>{{ headerMeta }}</span>
          </div>
          <div v-if="currentAgent" class="current-agent-badge">
            <Sparkles :size="13" />
            <span>{{ currentAgent.name }}</span>
          </div>
          <div class="provider-controls">
            <label class="provider-picker" title="选择模型服务商">
              <span
                class="provider-dot"
                :class="{ live: providerLive }"
                aria-hidden="true"
              ></span>
              <select
                v-model="runtimeSettings.provider"
                aria-label="模型服务商"
                :disabled="busy"
                @change="handleProviderChange"
              >
                <option
                  v-for="provider in providerOptions"
                  :key="provider.id"
                  :value="provider.id"
                >
                  {{ provider.label }}
                </option>
              </select>
              <ChevronDown :size="14" aria-hidden="true" />
            </label>
            <button
              class="icon-button settings-button"
              type="button"
              title="模型与联网设置"
              aria-label="模型与联网设置"
              @click="settingsOpen = true"
            >
              <SlidersHorizontal :size="18" />
              <span
                v-if="runtimeSettings.web_search_enabled"
                class="settings-indicator"
              ></span>
            </button>
          </div>
        </header>

        <div v-if="pageError" class="page-error" role="alert">
          <span>{{ pageError }}</span>
          <button
            type="button"
            title="关闭提示"
            aria-label="关闭提示"
            @click="pageError = ''"
          >
            <X :size="16" />
          </button>
        </div>

        <div v-if="ragRevisionNotice" class="knowledge-revision-notice">
          <RefreshCw :size="15" />
          <span>
            知识库已从 r{{ ragRevisionNotice.previous }} 更新到
            r{{ ragRevisionNotice.current }}。历史回答保持原样，继续提问将使用最新知识。
          </span>
        </div>
        </div>

        <section
        ref="messageScroller"
        class="message-scroller"
        aria-live="polite"
        @scroll.passive="updateScrollStickiness"
      >
        <div v-if="messages.length === 0" class="empty-state">
          <span class="empty-icon" aria-hidden="true">
            <MessageSquareText :size="24" :stroke-width="1.7" />
          </span>
          <h2>
            {{
              currentAgent?.key === 'pc-builder'
                ? '告诉我你的装机需求'
                : currentAgent?.key === 'media-crawler'
                  ? '配置一次公开数据采集'
                  : currentAgent?.key === 'rag-assistant'
                    ? '直接问项目知识库'
                : '今天想了解什么？'
            }}
          </h2>
          <PcBuilderConfigurator
            v-if="currentAgent?.key === 'pc-builder'"
            :disabled="busy"
            @submit="useSuggestion"
          />
          <MediaCrawlerConfigurator
            v-else-if="currentAgent?.key === 'media-crawler'"
            :disabled="busy"
            @submit="useSuggestion"
          />
          <div
            v-else-if="currentAgent?.key === 'rag-assistant'"
            class="rag-starter"
          >
            <div class="rag-starter-head">
              <span>PROJECT KNOWLEDGE</span>
              <strong>
                {{
                  ragStatus?.available
                    ? `${ragStatus.source_count} 个文件 · ${ragStatus.chunk_count} 个片段`
                    : '知识目录未就绪'
                }}
              </strong>
            </div>
            <div v-if="ragSources.length" class="rag-source-list">
              <button
                v-for="source in ragSources.slice(0, 4)"
                :key="source.id"
                type="button"
                @click="
                  useSuggestion(
                    `请基于项目知识库，总结《${source.title}》的核心内容。`,
                  )
                "
              >
                <span>
                  <strong>{{ source.title }}</strong>
                  <small>
                    v{{ source.version }} · {{ source.chunk_count }} 个索引片段
                  </small>
                </span>
                <ArrowUp :size="14" />
              </button>
            </div>
            <div v-else class="rag-source-empty">
              管理员尚未添加有效的知识文件
            </div>
            <div class="rag-starter-flow">
              <span><Files :size="14" /> 项目内置</span>
              <span><strong>24</strong> 候选召回</span>
              <span><strong>5</strong> Rerank</span>
            </div>
          </div>
          <div v-else class="suggestion-list">
            <button
              v-for="suggestion in suggestions"
              :key="suggestion.label"
              type="button"
              @click="useSuggestion(suggestion.prompt)"
            >
              <span>{{ suggestion.label }}</span>
              <ArrowUp :size="16" />
            </button>
          </div>
        </div>

        <div v-else class="message-list">
          <ChatMessage
            v-for="message in messages"
            :key="message.id"
            :message="message"
          />
        </div>
        </section>

        <footer class="composer-area">
        <form
          class="composer"
          :class="{ dragging: draggingFiles }"
          @submit.prevent="submitMessage"
          @dragover.prevent="
            draggingFiles = currentAgent?.key !== 'rag-assistant'
          "
          @dragleave.prevent="draggingFiles = false"
          @drop.prevent="handleFileDrop"
          @keydown.esc="referenceOpen = false"
        >
          <input
            ref="fileInput"
            class="composer-file-input"
            type="file"
            multiple
            accept=".txt,.md,.markdown,.csv,.json,.jsonl,.yaml,.yml,.xml,.html,.css,.js,.jsx,.ts,.tsx,.vue,.py,.java,.go,.rs,.c,.cpp,.h,.sql,.sh,.toml,.ini,.log,.tex,.pdf,.docx,.png,.jpg,.jpeg,.webp,.gif,.svg"
            @change="handleFileInput"
          />

          <div
            v-if="pendingAttachments.length"
            class="composer-attachments"
          >
            <AttachmentChip
              v-for="attachment in pendingAttachments"
              :key="attachment.id"
              :attachment="attachment"
              compact
              removable
              @select="insertFileMention"
              @remove="removePendingAttachment"
            />
            <span class="composer-attachment-count">
              {{ pendingAttachments.length }}/5
            </span>
          </div>

          <div
            class="composer-entry"
            :class="{ 'no-tools': currentAgent?.key === 'rag-assistant' }"
          >
            <div
              v-if="currentAgent?.key !== 'rag-assistant'"
              class="composer-tools"
            >
              <button
                class="composer-tool"
                type="button"
                title="上传文件"
                aria-label="上传文件"
                :disabled="busy || uploadBusy"
                @click="openFilePicker"
              >
                <LoaderCircle
                  v-if="uploadBusy"
                  class="spin"
                  :size="16"
                />
                <Paperclip v-else :size="16" />
              </button>
              <button
                class="composer-tool composer-reference"
                type="button"
                title="引用当前会话中的文件"
                aria-label="引用当前会话中的文件"
                :disabled="
                  busy ||
                  uploadBusy ||
                  referenceableAttachments.length === 0
                "
                @click="referenceOpen = !referenceOpen"
              >
                <Files :size="15" />
                <span>引用</span>
              </button>
            </div>

            <textarea
              ref="composer"
              v-model="input"
              rows="1"
              maxlength="20000"
              :placeholder="composerPlaceholder"
              aria-label="消息内容"
              @input="resizeComposer"
              @keydown="handleComposerKeydown"
            ></textarea>
            <button
              class="send-button"
              type="submit"
              :disabled="sendDisabled"
              :title="uploadBusy ? '正在上传文件' : '发送消息'"
              aria-label="发送消息"
            >
              <ArrowUp :size="19" :stroke-width="2" />
            </button>
          </div>

          <div v-if="draggingFiles" class="composer-drop-hint">
            <Paperclip :size="18" />
            松开以上传并引用文件
          </div>

          <Transition name="settings-fade">
            <div v-if="referenceOpen" class="file-reference-menu">
              <header>
                <span>引用当前会话文件</span>
                <button
                  type="button"
                  title="关闭文件引用"
                  aria-label="关闭文件引用"
                  @click="referenceOpen = false"
                >
                  <X :size="14" />
                </button>
              </header>
              <div class="file-reference-list">
                <button
                  v-for="attachment in referenceableAttachments"
                  :key="attachment.id"
                  type="button"
                  class="file-reference-item"
                  @click="referenceAttachment(attachment)"
                >
                  <span>
                    <strong>{{ attachment.filename }}</strong>
                    <small>
                      {{ attachment.excerpt || '文件已上传' }}
                    </small>
                  </span>
                  <Plus :size="15" />
                </button>
              </div>
            </div>
          </Transition>
        </form>
        <div class="composer-status">
          <span
            class="status-light"
            :class="{ active: busy }"
            aria-hidden="true"
          ></span>
          <span>{{ statusText }}</span>
          <span class="composer-context">
            {{ currentAgent?.name || 'Agent Chat' }} / {{ providerLabel }}
          </span>
        </div>
        </footer>
      </template>
    </main>

    <SettingsPanel
      :open="settingsOpen"
      :runtime="runtimeSettings"
      @close="settingsOpen = false"
      @save="saveSettings"
    />
  </div>
</template>

