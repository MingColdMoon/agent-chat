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
  Menu,
  MessageSquareText,
  SlidersHorizontal,
  Sparkles,
  Store,
  X,
} from 'lucide-vue-next'
import AgentMarketplace from './components/AgentMarketplace.vue'
import AuthScreen from './components/AuthScreen.vue'
import ChatMessage from './components/ChatMessage.vue'
import ConversationSidebar from './components/ConversationSidebar.vue'
import PcBuilderConfigurator from './components/PcBuilderConfigurator.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import {
  createConversation,
  createAgent,
  consumeEventStream,
  applyAgent,
  deleteAgent,
  deleteConversation,
  ApiError,
  getConversation,
  getCurrentUser,
  getConversations,
  getHealth,
  getAgents,
  login,
  logout,
  register,
  sendMessage,
} from './api'
import type {
  AgentCreatePayload,
  AgentSummary,
  AuthSubmission,
  ConversationSummary,
  Health,
  Message,
  ProviderId,
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
const agentCreateOpen = ref(false)
const agentsLoading = ref(false)
const agentMutationBusy = ref(false)
const agentError = ref('')
const runtimeSettings = reactive<RuntimeSettings>(createRuntimeSettings())
const composer = ref<HTMLTextAreaElement | null>(null)
const messageScroller = ref<HTMLElement | null>(null)
const stickToBottom = ref(true)
let activeStreamController: AbortController | null = null
let streamCompleted = false

function abortActiveStream() {
  activeStreamController?.abort()
  activeStreamController = null
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

const sendDisabled = computed(() => busy.value || !input.value.trim())
const currentSummary = computed(() =>
  conversations.value.find((item) => item.id === currentId.value),
)
const currentAgent = computed(() => currentSummary.value?.agent || null)
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
  const [healthResult, conversationList, agentList] = await Promise.all([
    getHealth(),
    getConversations(),
    getAgents(),
  ])
  health.value = healthResult
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
  try {
    await logout()
  } finally {
    user.value = null
    conversations.value = []
    agents.value = []
    messages.value = []
    currentId.value = null
    currentTitle.value = '新会话'
    pageError.value = ''
    authError.value = ''
    sidebarOpen.value = false
    settingsOpen.value = false
    marketplaceOpen.value = false
    agentCreateOpen.value = false
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

async function selectConversation(id: string) {
  if (busy.value || id === currentId.value) {
    sidebarOpen.value = false
    return
  }
  try {
    const conversation = await getConversation(id)
    abortActiveStream()
    currentId.value = conversation.id
    currentTitle.value = conversation.title
    messages.value = conversation.messages
    marketplaceOpen.value = false
    stickToBottom.value = true
    pageError.value = ''
    sidebarOpen.value = false
    scrollToBottom(true)
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
  if (busy.value) return
  marketplaceOpen.value = true
  settingsOpen.value = false
  sidebarOpen.value = false
  agentError.value = ''
  void refreshAgents()
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
  if (busy.value) return
  abortActiveStream()
  currentId.value = null
  currentTitle.value = '新会话'
  messages.value = []
  marketplaceOpen.value = false
  stickToBottom.value = true
  pageError.value = ''
  sidebarOpen.value = false
  statusText.value = '就绪'
  void nextTick(() => composer.value?.focus())
}

async function removeConversation(id: string) {
  if (busy.value || !window.confirm('删除这个会话？')) return
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
    const conversation = await getConversation(currentId.value)
    messages.value = conversation.messages
    currentTitle.value = conversation.title
    scrollToBottom()
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : '刷新会话失败'
  }
}

async function submitMessage() {
  const content = input.value.trim()
  if (!content || busy.value) return
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

  const optimisticId = `local-${crypto.randomUUID()}`
  messages.value.push({
    id: optimisticId,
    role: 'user',
    content,
    created_at: new Date().toISOString(),
    tools: [],
  })
  stickToBottom.value = true
  scrollToBottom(true)

  try {
    const conversationId = await ensureConversation()
    const result = await sendMessage(
      conversationId,
      content,
      buildRunOptions(),
    )
    const optimistic = messages.value.find((item) => item.id === optimisticId)
    if (optimistic) {
      Object.assign(optimistic, result.user_message, {
        provider: result.provider,
        model: result.model,
      })
    }
    void loadConversationList()
    attachStream(result.stream_url)
  } catch (error) {
    busy.value = false
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
      @new-chat="startNewChat"
      @select="selectConversation"
      @remove="removeConversation"
      @close="sidebarOpen = false"
      @logout="handleLogout"
      @marketplace="openMarketplace"
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
      :class="{ 'marketplace-mode': marketplaceOpen }"
    >
      <AgentMarketplace
        v-if="marketplaceOpen"
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
                : '今天想了解什么？'
            }}
          </h2>
          <PcBuilderConfigurator
            v-if="currentAgent?.key === 'pc-builder'"
            :disabled="busy"
            @submit="useSuggestion"
          />
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
          @submit.prevent="submitMessage"
        >
          <textarea
            ref="composer"
            v-model="input"
            rows="1"
            maxlength="20000"
            placeholder="给 Agent 发送消息"
            aria-label="消息内容"
            @input="resizeComposer"
            @keydown="handleComposerKeydown"
          ></textarea>
          <button
            class="send-button"
            type="submit"
            :disabled="sendDisabled"
            title="发送消息"
            aria-label="发送消息"
          >
            <ArrowUp :size="19" :stroke-width="2" />
          </button>
        </form>
        <div class="composer-status">
          <span
            class="status-light"
            :class="{ active: busy }"
            aria-hidden="true"
          ></span>
          <span>{{ statusText }}</span>
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

