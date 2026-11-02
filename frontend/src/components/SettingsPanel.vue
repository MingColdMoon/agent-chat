<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  Check,
  ChevronDown,
  Eye,
  EyeOff,
  Globe2,
  KeyRound,
  RotateCcw,
  X,
} from 'lucide-vue-next'
import type {
  ApiProviderId,
  ProviderId,
  RuntimeSettings,
} from '../types'

const props = defineProps<{
  open: boolean
  runtime: RuntimeSettings
}>()

const emit = defineEmits<{
  close: []
  save: [runtime: RuntimeSettings]
}>()

const providerOptions: Array<{ id: ProviderId; label: string }> = [
  { id: 'demo', label: '演示模式' },
  { id: 'openai', label: 'ChatGPT / OpenAI' },
  { id: 'deepseek', label: 'DeepSeek' },
  { id: 'custom', label: '自定义兼容服务' },
]

const providerPresets: Record<
  ApiProviderId,
  { base_url: string; model: string }
> = {
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

const draft = ref<RuntimeSettings>(cloneSettings(props.runtime))
const showServiceKey = ref(false)
const showTavilyKey = ref(false)

const selectedProfile = computed(() => {
  const provider =
    draft.value.provider === 'demo' ? 'openai' : draft.value.provider
  return draft.value.profiles[provider]
})

const hasWebSearch = computed(
  () => draft.value.web_search_enabled && !!draft.value.tavily_api_key,
)

function cloneSettings(settings: RuntimeSettings): RuntimeSettings {
  return {
    provider: settings.provider,
    profiles: {
      openai: { ...settings.profiles.openai },
      deepseek: { ...settings.profiles.deepseek },
      custom: { ...settings.profiles.custom },
    },
    web_search_enabled: settings.web_search_enabled,
    tavily_api_key: settings.tavily_api_key,
    tavily_api_url: settings.tavily_api_url,
  }
}

function applyProviderPreset() {
  if (draft.value.provider === 'demo') return
  const provider = draft.value.provider as ApiProviderId
  const profile = draft.value.profiles[provider]
  const preset = providerPresets[provider]
  if (!profile.base_url) profile.base_url = preset.base_url
  if (!profile.model) profile.model = preset.model
}

function resetCurrentProvider() {
  if (draft.value.provider === 'demo') return
  const provider = draft.value.provider as ApiProviderId
  draft.value.profiles[provider] = {
    api_key: '',
    ...providerPresets[provider],
  }
}

function saveSettings() {
  emit('save', cloneSettings(draft.value))
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      draft.value = cloneSettings(props.runtime)
      showServiceKey.value = false
      showTavilyKey.value = false
    }
  },
)
</script>

<template>
  <Transition name="settings-fade">
    <div v-if="open" class="settings-layer">
      <button
        class="settings-backdrop"
        type="button"
        aria-label="关闭设置"
        @click="emit('close')"
      ></button>

      <aside class="settings-panel" role="dialog" aria-label="模型与联网设置">
        <header class="settings-header">
          <div>
            <h2>模型与联网</h2>
            <span>当前服务商与 API 接入配置</span>
          </div>
          <button
            class="icon-button"
            type="button"
            title="关闭设置"
            aria-label="关闭设置"
            @click="emit('close')"
          >
            <X :size="18" />
          </button>
        </header>

        <form class="settings-form" @submit.prevent="saveSettings">
          <div class="settings-body">
            <section class="settings-section">
              <div class="section-heading">
                <KeyRound :size="16" />
                <span>模型服务</span>
              </div>

              <label class="field">
                <span>服务商</span>
                <span class="select-wrap">
                  <select v-model="draft.provider" @change="applyProviderPreset">
                    <option
                      v-for="provider in providerOptions"
                      :key="provider.id"
                      :value="provider.id"
                    >
                      {{ provider.label }}
                    </option>
                  </select>
                  <ChevronDown :size="15" />
                </span>
              </label>

              <div v-if="draft.provider === 'demo'" class="provider-note">
                内置演示 Agent 可直接使用，无需填写模型 API。
              </div>

              <template v-else>
                <label class="field">
                  <span>API Key</span>
                  <span class="secret-field">
                    <input
                      v-model="selectedProfile.api_key"
                      :type="showServiceKey ? 'text' : 'password'"
                      autocomplete="off"
                      spellcheck="false"
                      placeholder="sk-..."
                    />
                    <button
                      type="button"
                      :title="showServiceKey ? '隐藏 API Key' : '显示 API Key'"
                      :aria-label="
                        showServiceKey ? '隐藏 API Key' : '显示 API Key'
                      "
                      @click="showServiceKey = !showServiceKey"
                    >
                      <EyeOff v-if="showServiceKey" :size="16" />
                      <Eye v-else :size="16" />
                    </button>
                  </span>
                </label>

                <label class="field">
                  <span>API 地址</span>
                  <input
                    v-model="selectedProfile.base_url"
                    type="text"
                    autocomplete="off"
                    spellcheck="false"
                    placeholder="https://api.example.com/v1"
                  />
                </label>

                <label class="field">
                  <span>模型名称</span>
                  <input
                    v-model="selectedProfile.model"
                    type="text"
                    autocomplete="off"
                    spellcheck="false"
                    placeholder="gpt-4o-mini"
                  />
                </label>

                <button
                  class="reset-provider"
                  type="button"
                  @click="resetCurrentProvider"
                >
                  <RotateCcw :size="14" />
                  恢复当前服务商默认值
                </button>
              </template>

              <p class="security-note">
                API Key 仅保存在当前浏览器标签页，并随请求发送到本地后端。
              </p>
            </section>

            <section class="settings-section">
              <div class="section-heading">
                <Globe2 :size="16" />
                <span>联网搜索</span>
              </div>

              <div class="switch-row">
                <div>
                  <strong>Tavily 联网搜索</strong>
                  <span>{{ hasWebSearch ? '已启用' : '未启用' }}</span>
                </div>
                <button
                  class="switch-button"
                  :class="{ on: draft.web_search_enabled }"
                  type="button"
                  role="switch"
                  :aria-checked="draft.web_search_enabled"
                  @click="
                    draft.web_search_enabled = !draft.web_search_enabled
                  "
                >
                  <span></span>
                </button>
              </div>

              <template v-if="draft.web_search_enabled">
                <label class="field">
                  <span>Tavily API Key</span>
                  <span class="secret-field">
                    <input
                      v-model="draft.tavily_api_key"
                      :type="showTavilyKey ? 'text' : 'password'"
                      autocomplete="off"
                      spellcheck="false"
                      placeholder="tvly-..."
                    />
                    <button
                      type="button"
                      :title="showTavilyKey ? '隐藏 API Key' : '显示 API Key'"
                      :aria-label="
                        showTavilyKey ? '隐藏 API Key' : '显示 API Key'
                      "
                      @click="showTavilyKey = !showTavilyKey"
                    >
                      <EyeOff v-if="showTavilyKey" :size="16" />
                      <Eye v-else :size="16" />
                    </button>
                  </span>
                </label>

                <label class="field">
                  <span>Tavily API 地址</span>
                  <input
                    v-model="draft.tavily_api_url"
                    type="text"
                    autocomplete="off"
                    spellcheck="false"
                    placeholder="https://api.tavily.com"
                  />
                </label>
              </template>
            </section>
          </div>

          <footer class="settings-footer">
            <button class="primary-button" type="submit">
              <Check :size="16" />
              应用设置
            </button>
          </footer>
        </form>
      </aside>
    </div>
  </Transition>
</template>

