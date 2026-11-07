<script setup lang="ts">
import {
  Bot,
  LogOut,
  PanelLeftClose,
  Plus,
  Store,
  Trash2,
} from 'lucide-vue-next'
import type { ConversationSummary, UserInfo } from '../types'

defineProps<{
  conversations: ConversationSummary[]
  currentId: string | null
  open: boolean
  providerLabel: string
  providerDetail: string
  providerLive: boolean
  user: UserInfo | null
  marketplaceActive: boolean
}>()

const emit = defineEmits<{
  newChat: []
  select: [id: string]
  remove: [id: string]
  close: []
  logout: []
  marketplace: []
}>()

function relativeTime(value: string): string {
  const timestamp = new Date(value).getTime()
  const minutes = Math.max(0, Math.round((Date.now() - timestamp) / 60_000))
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} 小时前`
  return new Intl.DateTimeFormat('zh-CN', {
    month: 'short',
    day: 'numeric',
  }).format(timestamp)
}
</script>

<template>
  <aside class="sidebar" :class="{ open }">
    <div class="brand">
      <span class="brand-mark" aria-hidden="true">
        <Bot :size="19" :stroke-width="1.8" />
      </span>
      <div class="brand-copy">
        <strong>Agent Chat</strong>
        <span>LangChain + Vue</span>
      </div>
      <button
        class="icon-button sidebar-close"
        type="button"
        title="关闭会话列表"
        aria-label="关闭会话列表"
        @click="emit('close')"
      >
        <PanelLeftClose :size="18" />
      </button>
    </div>

    <div class="sidebar-section-label">工作区</div>

    <button class="new-chat" type="button" @click="emit('newChat')">
      <Plus :size="17" />
      <span>新会话</span>
    </button>

    <button
      class="marketplace-link"
      :class="{ active: marketplaceActive }"
      type="button"
      @click="emit('marketplace')"
    >
      <Store :size="17" />
      <span>智能体广场</span>
    </button>

    <div class="list-heading">
      <span>最近会话</span>
      <span>{{ conversations.length }}</span>
    </div>

    <nav class="conversation-list" aria-label="会话列表">
      <div
        v-for="conversation in conversations"
        :key="conversation.id"
        class="conversation-row"
        :class="{ active: conversation.id === currentId }"
      >
        <button
          class="conversation-main"
          type="button"
          @click="emit('select', conversation.id)"
        >
          <span class="conversation-title">{{ conversation.title }}</span>
          <span class="conversation-meta">
            <template v-if="conversation.agent">
              {{ conversation.agent.name }} ·
            </template>
            {{ conversation.message_count }} 条
            <span aria-hidden="true">·</span>
            {{ relativeTime(conversation.updated_at) }}
          </span>
        </button>
        <button
          class="conversation-delete"
          type="button"
          title="删除会话"
          aria-label="删除会话"
          @click="emit('remove', conversation.id)"
        >
          <Trash2 :size="14" />
        </button>
      </div>
    </nav>

    <div class="sidebar-footer">
      <span
        class="provider-dot"
        :class="{ live: providerLive }"
        aria-hidden="true"
      ></span>
      <div>
        <strong>{{ providerLabel }}</strong>
        <span>{{ providerDetail }}</span>
      </div>
    </div>

    <div v-if="user" class="account-footer">
      <span class="account-avatar" aria-hidden="true">
        {{ user.username.slice(0, 1).toUpperCase() }}
      </span>
      <div>
        <strong>{{ user.username }}</strong>
        <span>已登录</span>
      </div>
      <button
        class="account-logout"
        type="button"
        title="退出登录"
        aria-label="退出登录"
        @click="emit('logout')"
      >
        <LogOut :size="15" />
      </button>
    </div>
  </aside>
</template>

