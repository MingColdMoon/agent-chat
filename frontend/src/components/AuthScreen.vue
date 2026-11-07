<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  AlertCircle,
  ArrowUpRight,
  ArrowRight,
  Eye,
  EyeOff,
  LoaderCircle,
  LockKeyhole,
  ShieldCheck,
  Sparkles,
  UserRound,
} from 'lucide-vue-next'
import type { AuthMode, AuthSubmission } from '../types'

const props = defineProps<{
  busy: boolean
  error: string
}>()

const emit = defineEmits<{
  submit: [submission: AuthSubmission]
}>()

const mode = ref<AuthMode>('login')
const username = ref('')
const password = ref('')
const showPassword = ref(false)
const localError = ref('')

const title = computed(() =>
  mode.value === 'login' ? '欢迎回来' : '创建账号',
)
const subtitle = computed(() =>
  mode.value === 'login'
    ? '登录后继续你的对话'
    : '新账号将拥有独立的会话空间',
)
const submitLabel = computed(() =>
  mode.value === 'login' ? '登录' : '注册并登录',
)
const displayError = computed(() => localError.value || props.error)

function switchMode(nextMode: AuthMode) {
  if (props.busy || mode.value === nextMode) return
  mode.value = nextMode
  localError.value = ''
}

function submit() {
  localError.value = ''
  const cleanUsername = username.value.trim()
  if (cleanUsername.length < 3) {
    localError.value = '用户名至少需要 3 个字符'
    return
  }
  if (password.value.length < 8) {
    localError.value = '密码至少需要 8 个字符'
    return
  }
  emit('submit', {
    mode: mode.value,
    username: cleanUsername,
    password: password.value,
  })
}
</script>

<template>
  <main class="auth-screen">
    <section class="auth-intro">
      <div class="auth-intro-top">
        <div class="auth-brand">
          <span class="brand-mark" aria-hidden="true">
            <Sparkles :size="20" :stroke-width="1.8" />
          </span>
          <div>
            <strong>Agent Chat</strong>
            <span>LangChain + Vue</span>
          </div>
        </div>
        <span class="auth-index">AGENT / 01</span>
      </div>
      <div class="auth-hero">
        <span>PRIVATE AGENT WORKSPACE</span>
        <h1>
          让想法交给<br />
          <span>真正会工作的</span><br />
          <span>智能体。</span>
        </h1>
        <p>
          对话、检索、数据采集与工具调用，在同一个安静、专注的工作空间完成。
        </p>
        <span class="auth-hero-link">
          Agent Marketplace
          <ArrowUpRight :size="17" />
        </span>
      </div>
      <div class="auth-signal" aria-hidden="true">
        <span></span>
        <span></span>
        <span></span>
        <span></span>
      </div>
    </section>

    <section class="auth-workspace">
      <form class="auth-form" @submit.prevent="submit">
        <div class="auth-heading">
          <span class="auth-eyebrow">ACCOUNT</span>
          <h1>{{ title }}</h1>
          <p>{{ subtitle }}</p>
        </div>

        <div class="auth-tabs" role="tablist" aria-label="账号操作">
          <button
            type="button"
            :class="{ active: mode === 'login' }"
            :aria-selected="mode === 'login'"
            @click="switchMode('login')"
          >
            登录
          </button>
          <button
            type="button"
            :class="{ active: mode === 'register' }"
            :aria-selected="mode === 'register'"
            @click="switchMode('register')"
          >
            注册
          </button>
        </div>

        <label class="auth-field">
          <span>用户名</span>
          <span class="auth-input">
            <UserRound :size="17" />
            <input
              v-model="username"
              type="text"
              autocomplete="username"
              maxlength="32"
              placeholder="your-name"
            />
          </span>
        </label>

        <label class="auth-field">
          <span>密码</span>
          <span class="auth-input">
            <LockKeyhole :size="17" />
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              :autocomplete="
                mode === 'login' ? 'current-password' : 'new-password'
              "
              maxlength="128"
              placeholder="至少 8 个字符"
            />
            <button
              class="password-toggle"
              type="button"
              :title="showPassword ? '隐藏密码' : '显示密码'"
              :aria-label="showPassword ? '隐藏密码' : '显示密码'"
              @click="showPassword = !showPassword"
            >
              <EyeOff v-if="showPassword" :size="16" />
              <Eye v-else :size="16" />
            </button>
          </span>
        </label>

        <div v-if="displayError" class="auth-error" role="alert">
          <AlertCircle :size="16" />
          <span>{{ displayError }}</span>
        </div>

        <button class="auth-submit" type="submit" :disabled="busy">
          <LoaderCircle v-if="busy" class="spin" :size="17" />
          <span>{{ busy ? '请稍候' : submitLabel }}</span>
          <ArrowRight v-if="!busy" :size="17" />
        </button>

        <footer class="auth-footer">
          <ShieldCheck :size="14" />
          <span>安全会话</span>
        </footer>
      </form>
    </section>
  </main>
</template>

