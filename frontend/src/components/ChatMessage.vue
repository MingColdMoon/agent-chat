<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  AlertCircle,
  Bot,
  Check,
  CheckCircle2,
  Copy,
  Globe2,
  LoaderCircle,
  UserRound,
  Wrench,
} from 'lucide-vue-next'
import MarkdownIt from 'markdown-it'
import type { Message, ToolTrace } from '../types'
import type { PcBuildPlan } from '../types'
import PcBuildCard from './PcBuildCard.vue'

const props = defineProps<{
  message: Message
}>()

const copied = ref(false)
const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

const defaultLinkOpen =
  markdown.renderer.rules.link_open ||
  ((tokens, index, options, _env, self) =>
    self.renderToken(tokens, index, options))

markdown.renderer.rules.link_open = (tokens, index, options, env, self) => {
  tokens[index]?.attrSet('target', '_blank')
  tokens[index]?.attrSet('rel', 'noopener noreferrer')
  return defaultLinkOpen(tokens, index, options, env, self)
}

const renderedContent = computed(() => markdown.render(props.message.content))

const toolLabels: Record<string, string> = {
  get_current_time: '查询当前时间',
  calculator: '数学计算',
  web_search: '联网搜索',
}

function toolLabel(tool: ToolTrace): string {
  return toolLabels[tool.name] || tool.name
}

function formatValue(value: unknown): string {
  if (typeof value === 'string') return value
  return JSON.stringify(value ?? {}, null, 2)
}

async function copyMessage() {
  if (!props.message.content) return
  await navigator.clipboard.writeText(props.message.content)
  copied.value = true
  window.setTimeout(() => {
    copied.value = false
  }, 1400)
}
</script>

<template>
  <article class="message" :class="message.role">
    <div class="message-head">
      <span class="message-avatar" aria-hidden="true">
        <UserRound v-if="message.role === 'user'" :size="15" />
        <Bot v-else :size="16" />
      </span>
      <span class="message-author">
        {{ message.role === 'user' ? '你' : 'Agent' }}
      </span>
      <span
        v-if="message.role === 'assistant' && message.model"
        class="message-model"
      >
        {{ message.model }}
      </span>
      <span class="message-time">
        {{
          new Intl.DateTimeFormat('zh-CN', {
            hour: '2-digit',
            minute: '2-digit',
          }).format(new Date(message.created_at))
        }}
      </span>
    </div>

    <div v-if="message.tools.length" class="tool-stack">
      <details
        v-for="tool in message.tools"
        :key="tool.id"
        class="tool-call"
        :class="tool.state"
      >
        <summary>
          <Globe2 v-if="tool.name === 'web_search'" :size="14" />
          <Wrench v-else :size="14" />
          <span class="tool-name">{{ toolLabel(tool) }}</span>
          <span class="tool-state">
            <LoaderCircle
              v-if="tool.state === 'running'"
              class="spin"
              :size="14"
            />
            <CheckCircle2
              v-else-if="tool.state === 'complete'"
              :size="14"
            />
            <AlertCircle v-else :size="14" />
            {{
              tool.state === 'running'
                ? '运行中'
                : tool.state === 'complete'
                  ? '完成'
                  : '失败'
            }}
          </span>
        </summary>
        <div class="tool-detail">
          <div>
            <span class="tool-label">输入</span>
            <pre>{{ formatValue(tool.input) }}</pre>
          </div>
          <div v-if="tool.output !== undefined">
            <span class="tool-label">结果</span>
            <pre>{{ formatValue(tool.output) }}</pre>
          </div>
        </div>
      </details>
    </div>

    <div
      v-if="message.content"
      class="message-content markdown-body"
      v-html="renderedContent"
    ></div>
    <div
      v-else-if="message.streaming"
      class="thinking-dots"
      aria-label="正在生成回答"
    >
      <span></span><span></span><span></span>
    </div>

    <div v-if="message.error" class="message-error">
      <AlertCircle :size="15" />
      <span>{{ message.error }}</span>
    </div>

    <PcBuildCard
      v-if="message.activity?.activityType === 'pc-build-plan'"
      :plan="message.activity.content as unknown as PcBuildPlan"
    />

    <button
      v-if="message.role === 'assistant' && message.content"
      class="copy-button"
      type="button"
      :title="copied ? '已复制' : '复制回答'"
      :aria-label="copied ? '已复制' : '复制回答'"
      @click="copyMessage"
    >
      <Check v-if="copied" :size="15" />
      <Copy v-else :size="15" />
    </button>
  </article>
</template>

