<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  ArrowLeft,
  ArrowRight,
  Bot,
  BriefcaseBusiness,
  ChartNoAxesCombined,
  Check,
  Cpu,
  FileText,
  Headset,
  LoaderCircle,
  Plus,
  Radar,
  Search,
  Sparkles,
  Trash2,
  X,
} from 'lucide-vue-next'
import type {
  AgentCreatePayload,
  AgentSummary,
} from '../types'

const props = defineProps<{
  agents: AgentSummary[]
  loading: boolean
  mutationBusy: boolean
  error: string
  currentConversationId: string | null
  currentAgentId: string | null
  createOpen: boolean
}>()

const emit = defineEmits<{
  back: []
  create: [payload: AgentCreatePayload]
  openCreate: []
  closeCreate: []
  start: [agent: AgentSummary]
  apply: [agent: AgentSummary]
  delete: [agent: AgentSummary]
}>()

const form = reactive<AgentCreatePayload>({
  name: '',
  description: '',
  category: '自定义',
  icon: 'sparkles',
  instructions: '',
})
const formError = ref('')
const searchQuery = ref('')
const activeFilter = ref<'all' | 'builtin' | 'custom'>('all')

const iconMap = {
  bot: Bot,
  headset: Headset,
  chart: ChartNoAxesCombined,
  sparkles: Sparkles,
  document: FileText,
  business: BriefcaseBusiness,
  cpu: Cpu,
  radar: Radar,
}

const iconOptions = [
  { value: 'sparkles', label: '灵感' },
  { value: 'bot', label: '通用' },
  { value: 'headset', label: '客服' },
  { value: 'chart', label: '分析' },
  { value: 'document', label: '文档' },
  { value: 'business', label: '业务' },
]

const marketplaceFilters = [
  { id: 'all', label: '全部' },
  { id: 'builtin', label: '内置' },
  { id: 'custom', label: '我的' },
] as const

const builtinAgents = computed(() =>
  props.agents.filter((agent) => agent.is_builtin),
)

const customAgents = computed(() =>
  props.agents.filter((agent) => !agent.is_builtin),
)

const normalizedQuery = computed(() => searchQuery.value.trim().toLowerCase())

function matchesSearch(agent: AgentSummary) {
  if (!normalizedQuery.value) return true
  const searchable = [
    agent.name,
    agent.description,
    agent.category,
    agent.key || '',
  ]
    .join(' ')
    .toLowerCase()
  return searchable.includes(normalizedQuery.value)
}

const visibleBuiltinAgents = computed(() => {
  if (activeFilter.value === 'custom') return []
  return builtinAgents.value.filter(matchesSearch)
})

const visibleCustomAgents = computed(() => {
  if (activeFilter.value === 'builtin') return []
  return customAgents.value.filter(matchesSearch)
})

const visibleAgentCount = computed(
  () => visibleBuiltinAgents.value.length + visibleCustomAgents.value.length,
)

function agentIcon(agent: AgentSummary) {
  return iconMap[agent.icon as keyof typeof iconMap] || Bot
}

function resetForm() {
  form.name = ''
  form.description = ''
  form.category = '自定义'
  form.icon = 'sparkles'
  form.instructions = ''
  formError.value = ''
}

function submitAgent() {
  formError.value = ''
  if (form.name.trim().length < 2) {
    formError.value = '智能体名称至少需要 2 个字符'
    return
  }
  if (form.description.trim().length < 4) {
    formError.value = '请填写更清晰的智能体简介'
    return
  }
  if (form.instructions.trim().length < 10) {
    formError.value = '系统指令至少需要 10 个字符'
    return
  }
  emit('create', {
    name: form.name.trim(),
    description: form.description.trim(),
    category: form.category.trim() || '自定义',
    icon: form.icon,
    instructions: form.instructions.trim(),
  })
}

watch(
  () => props.createOpen,
  (open) => {
    if (open) resetForm()
  },
)
</script>

<template>
  <section class="marketplace">
    <header class="marketplace-header">
      <button
        class="icon-button"
        type="button"
        title="返回对话"
        aria-label="返回对话"
        @click="emit('back')"
      >
        <ArrowLeft :size="18" />
      </button>
      <div class="marketplace-heading">
        <span class="marketplace-kicker">LEIBOX / AGENT INDEX</span>
        <h1>智能体，按用途挑选</h1>
        <p>从预置角色开始，或创建只属于你的工作方式。</p>
      </div>
      <button
        class="create-agent-button"
        type="button"
        @click="emit('openCreate')"
      >
        <Plus :size="17" />
        创建智能体
      </button>
    </header>

    <div class="marketplace-toolbar">
      <label class="marketplace-search">
        <Search :size="17" />
        <input
          v-model="searchQuery"
          type="search"
          placeholder="搜索智能体、用途或分类"
        />
        <span>{{ visibleAgentCount }}</span>
      </label>
      <div class="marketplace-filters" role="group" aria-label="智能体筛选">
        <button
          v-for="filter in marketplaceFilters"
          :key="filter.id"
          type="button"
          :class="{ active: activeFilter === filter.id }"
          @click="activeFilter = filter.id"
        >
          {{ filter.label }}
        </button>
      </div>
    </div>

    <div v-if="error" class="marketplace-error">{{ error }}</div>

    <div v-if="loading" class="marketplace-loading">
      <LoaderCircle class="spin" :size="20" />
      <span>正在加载智能体</span>
    </div>

    <template v-else>
      <div
        v-if="activeFilter !== 'custom'"
        class="marketplace-section-heading"
      >
        <div>
          <span>系统预置</span>
          <h2>即开即用</h2>
        </div>
        <span>{{ visibleBuiltinAgents.length }} 个内置角色</span>
      </div>

      <div v-if="visibleBuiltinAgents.length" class="agent-grid">
        <article
          v-for="(agent, index) in visibleBuiltinAgents"
          :key="agent.id"
          class="agent-card"
          :class="{ selected: agent.id === currentAgentId }"
        >
          <div class="agent-card-top">
            <span class="agent-icon" :class="`icon-${agent.icon}`">
              <component :is="agentIcon(agent)" :size="22" />
            </span>
            <span class="agent-badge">内置</span>
            <span class="agent-card-index">
              {{ String(index + 1).padStart(2, '0') }}
            </span>
          </div>
          <div class="agent-card-copy">
            <span class="agent-category">{{ agent.category }}</span>
            <h3>{{ agent.name }}</h3>
            <p>{{ agent.description }}</p>
          </div>
          <div class="agent-actions">
            <button
              class="agent-primary-action"
              type="button"
              @click="emit('start', agent)"
            >
              开始对话
              <ArrowRight :size="15" />
            </button>
            <button
              v-if="currentConversationId"
              class="agent-secondary-action"
              type="button"
              :disabled="mutationBusy"
              @click="emit('apply', agent)"
            >
              应用到当前
            </button>
          </div>
        </article>
      </div>

      <div
        v-if="activeFilter !== 'builtin'"
        class="marketplace-section-heading custom-heading"
      >
        <div>
          <span>个人空间</span>
          <h2>我的智能体</h2>
        </div>
        <span>{{ visibleCustomAgents.length }} 个自定义角色</span>
      </div>

      <div v-if="visibleCustomAgents.length" class="agent-grid">
        <article
          v-for="(agent, index) in visibleCustomAgents"
          :key="agent.id"
          class="agent-card custom"
          :class="{ selected: agent.id === currentAgentId }"
        >
          <div class="agent-card-top">
            <span class="agent-icon" :class="`icon-${agent.icon}`">
              <component :is="agentIcon(agent)" :size="22" />
            </span>
            <button
              class="agent-delete"
              type="button"
              title="删除智能体"
              aria-label="删除智能体"
              @click="emit('delete', agent)"
            >
              <Trash2 :size="15" />
            </button>
            <span class="agent-card-index">
              {{ String(index + 1).padStart(2, '0') }}
            </span>
          </div>
          <div class="agent-card-copy">
            <span class="agent-category">{{ agent.category }}</span>
            <h3>{{ agent.name }}</h3>
            <p>{{ agent.description }}</p>
          </div>
          <div class="agent-actions">
            <button
              class="agent-primary-action"
              type="button"
              @click="emit('start', agent)"
            >
              开始对话
              <ArrowRight :size="15" />
            </button>
            <button
              v-if="currentConversationId"
              class="agent-secondary-action"
              type="button"
              :disabled="mutationBusy"
              @click="emit('apply', agent)"
            >
              应用到当前
            </button>
          </div>
        </article>
      </div>

      <button
        v-else-if="activeFilter !== 'builtin' && !normalizedQuery"
        class="empty-custom-agent"
        type="button"
        @click="emit('openCreate')"
      >
        <span class="empty-custom-icon">
          <Plus :size="20" />
        </span>
        <span>
          <strong>创建第一个自定义智能体</strong>
          <small>用专属系统指令固定角色、语气和工作流程</small>
        </span>
        <ArrowRight :size="17" />
      </button>

      <div
        v-if="!loading && visibleAgentCount === 0"
        class="marketplace-empty"
      >
        <Search :size="22" />
        <strong>没有匹配的智能体</strong>
        <span>换一个关键词，或切换到“全部”。</span>
      </div>
    </template>
  </section>

  <Transition name="settings-fade">
    <div v-if="createOpen" class="settings-layer">
      <button
        class="settings-backdrop"
        type="button"
        aria-label="关闭创建智能体"
        @click="emit('closeCreate')"
      ></button>
      <aside class="agent-create-panel" role="dialog" aria-label="创建智能体">
        <header class="settings-header">
          <div>
            <h2>创建智能体</h2>
            <span>定义专属角色和回答方式</span>
          </div>
          <button
            class="icon-button"
            type="button"
            title="关闭"
            aria-label="关闭创建智能体"
            @click="emit('closeCreate')"
          >
            <X :size="18" />
          </button>
        </header>

        <form class="agent-create-form" @submit.prevent="submitAgent">
          <div class="agent-create-body">
            <label class="field">
              <span>智能体名称</span>
              <input
                v-model="form.name"
                type="text"
                maxlength="80"
                placeholder="例如：产品文案助手"
              />
            </label>

            <label class="field">
              <span>分类</span>
              <input
                v-model="form.category"
                type="text"
                maxlength="40"
                placeholder="内容创作"
              />
            </label>

            <div class="field">
              <span>图标</span>
              <div class="agent-icon-options">
                <button
                  v-for="option in iconOptions"
                  :key="option.value"
                  type="button"
                  :class="{ active: form.icon === option.value }"
                  :title="option.label"
                  :aria-label="option.label"
                  @click="form.icon = option.value"
                >
                  <component
                    :is="iconMap[option.value as keyof typeof iconMap]"
                    :size="18"
                  />
                  <Check v-if="form.icon === option.value" :size="11" />
                </button>
              </div>
            </div>

            <label class="field">
              <span>简介</span>
              <textarea
                v-model="form.description"
                rows="3"
                maxlength="300"
                placeholder="说明这个智能体擅长解决什么问题"
              ></textarea>
            </label>

            <label class="field">
              <span>系统指令</span>
              <textarea
                v-model="form.instructions"
                rows="8"
                maxlength="8000"
                placeholder="定义角色、目标、语气、工作步骤和输出格式"
              ></textarea>
            </label>

            <div v-if="formError || error" class="auth-error">
              {{ formError || error }}
            </div>
          </div>
          <footer class="settings-footer">
            <button
              class="primary-button"
              type="submit"
              :disabled="mutationBusy"
            >
              <LoaderCircle v-if="mutationBusy" class="spin" :size="16" />
              <Sparkles v-else :size="16" />
              {{ mutationBusy ? '正在创建' : '创建智能体' }}
            </button>
          </footer>
        </form>
      </aside>
    </div>
  </Transition>
</template>

