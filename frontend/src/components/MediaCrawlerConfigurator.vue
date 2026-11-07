<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import {
  BookOpen,
  CircleHelp,
  Database,
  Image,
  Link2,
  MessageCircle,
  MessagesSquare,
  Music2,
  Play,
  Search,
  ShieldCheck,
  Tv,
  UserRound,
  Video,
} from 'lucide-vue-next'
import type {
  MediaCrawlerPlatform,
  MediaCrawlerTaskType,
} from '../types'

const props = defineProps<{
  disabled: boolean
}>()

const emit = defineEmits<{
  submit: [prompt: string]
}>()

const config = reactive({
  platform: 'xhs' as MediaCrawlerPlatform,
  taskType: 'search' as MediaCrawlerTaskType,
  keywords: '',
  targets: '',
  maxItems: 15,
  maxComments: 10,
  comments: true,
  subComments: false,
  media: false,
  saveOption: 'jsonl',
  startPage: 1,
})
const showError = ref(false)

const error = computed(() => {
  if (config.taskType === 'search' && !config.keywords.trim()) {
    return '请输入搜索关键词'
  }
  if (config.taskType !== 'search' && !config.targets.trim()) {
    return config.taskType === 'detail'
      ? '请输入内容链接或 ID'
      : '请输入创作者主页或 ID'
  }
  return ''
})

const platforms = [
  { id: 'xhs', label: '小红书', icon: BookOpen },
  { id: 'dy', label: '抖音', icon: Music2 },
  { id: 'ks', label: '快手', icon: Video },
  { id: 'bili', label: 'B站', icon: Tv },
  { id: 'wb', label: '微博', icon: MessageCircle },
  { id: 'tieba', label: '贴吧', icon: MessagesSquare },
  { id: 'zhihu', label: '知乎', icon: CircleHelp },
] as const

const taskTypes = [
  { id: 'search', label: '关键词', icon: Search },
  { id: 'detail', label: '内容详情', icon: Link2 },
  { id: 'creator', label: '创作者', icon: UserRound },
] as const

const saveOptions = [
  { id: 'jsonl', label: 'JSONL' },
  { id: 'json', label: 'JSON' },
  { id: 'csv', label: 'CSV' },
  { id: 'excel', label: 'Excel' },
  { id: 'sqlite', label: 'SQLite' },
] as const

const targetPlaceholder = computed(() =>
  config.taskType === 'detail'
    ? '粘贴内容链接，多个用逗号分隔'
    : '粘贴创作者主页链接，多个用逗号分隔',
)

function toggleCommentMode() {
  if (!config.comments) config.subComments = false
}

function submit() {
  if (props.disabled) return
  if (error.value) {
    showError.value = true
    return
  }
  showError.value = false
  const targets = config.targets
    .split(/[,，\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
  const platform =
    platforms.find((item) => item.id === config.platform)?.label || '小红书'
  const mode =
    taskTypes.find((item) => item.id === config.taskType)?.label || '关键词'
  const lines = [
    '请执行 MediaCrawler 公开数据采集任务。',
    `平台：${platform}（${config.platform}）`,
    `任务：${mode}（${config.taskType}）`,
  ]
  if (config.taskType === 'search') {
    lines.push(`关键词：${config.keywords.trim()}`)
  } else {
    lines.push(`目标：${targets.join('，')}`)
  }
  lines.push(
    `内容上限：${config.maxItems}`,
    `单篇评论上限：${config.maxComments}`,
    `一级评论：${config.comments ? '开启' : '关闭'}`,
    `二级评论：${config.comments && config.subComments ? '开启' : '关闭'}`,
    `下载媒体：${config.media ? '开启' : '关闭'}`,
    `导出格式：${config.saveOption}`,
    `起始页：${config.startPage}`,
  )
  emit('submit', lines.join('\n'))
}
</script>

<template>
  <div class="crawler-configurator">
    <div class="crawler-config-head">
      <div>
        <span>MEDIACRAWLER WORKBENCH</span>
        <h3>配置公开数据采集任务</h3>
      </div>
      <span class="crawler-platform-count">7 个平台</span>
    </div>

    <div class="crawler-field">
      <span>平台</span>
      <div class="crawler-platform-grid">
        <button
          v-for="platform in platforms"
          :key="platform.id"
          type="button"
          :class="{ active: config.platform === platform.id }"
          @click="config.platform = platform.id"
        >
          <component :is="platform.icon" :size="15" />
          {{ platform.label }}
        </button>
      </div>
    </div>

    <div class="crawler-field">
      <span>任务类型</span>
      <div class="crawler-segmented">
        <button
          v-for="task in taskTypes"
          :key="task.id"
          type="button"
          :class="{ active: config.taskType === task.id }"
          @click="config.taskType = task.id"
        >
          <component :is="task.icon" :size="14" />
          {{ task.label }}
        </button>
      </div>
    </div>

    <label class="crawler-field">
      <span>
        {{ config.taskType === 'search' ? '搜索关键词' : '目标链接或 ID' }}
      </span>
      <input
        v-if="config.taskType === 'search'"
        v-model="config.keywords"
        type="text"
        maxlength="500"
        placeholder="例如：AI 效率工具, 编程副业"
        @input="showError = false"
      />
      <textarea
        v-else
        v-model="config.targets"
        rows="3"
        maxlength="2000"
        :placeholder="targetPlaceholder"
        @input="showError = false"
      ></textarea>
    </label>

    <div class="crawler-number-row">
      <label class="crawler-field">
        <span>内容上限</span>
        <input
          v-model.number="config.maxItems"
          type="number"
          min="1"
          max="100"
        />
      </label>
      <label class="crawler-field">
        <span>单篇评论上限</span>
        <input
          v-model.number="config.maxComments"
          type="number"
          min="0"
          max="100"
          :disabled="!config.comments"
        />
      </label>
      <label class="crawler-field">
        <span>导出格式</span>
        <select v-model="config.saveOption">
          <option
            v-for="option in saveOptions"
            :key="option.id"
            :value="option.id"
          >
            {{ option.label }}
          </option>
        </select>
      </label>
    </div>

    <div class="crawler-toggles">
      <button
        type="button"
        :class="{ active: config.comments }"
        @click="config.comments = !config.comments; toggleCommentMode()"
      >
        <MessageCircle :size="14" />
        一级评论
        <span class="crawler-switch"></span>
      </button>
      <button
        type="button"
        :disabled="!config.comments"
        :class="{ active: config.subComments }"
        @click="config.subComments = !config.subComments"
      >
        <MessagesSquare :size="14" />
        二级评论
        <span class="crawler-switch"></span>
      </button>
      <button
        type="button"
        :class="{ active: config.media }"
        @click="config.media = !config.media"
      >
        <Image :size="14" />
        下载媒体
        <span class="crawler-switch"></span>
      </button>
    </div>

    <div class="crawler-config-footer">
      <span class="crawler-boundary">
        <ShieldCheck :size="14" />
        仅限公开信息与个人研究
      </span>
      <button
        class="crawler-submit"
        type="button"
        :disabled="disabled"
        @click="submit"
      >
        <Play :size="15" />
        {{ disabled ? '正在提交' : '创建采集任务' }}
      </button>
    </div>

    <p v-if="showError && error" class="crawler-form-error">{{ error }}</p>
    <div class="crawler-save-hint">
      <Database :size="13" />
      <span>
        {{ saveOptions.find((item) => item.id === config.saveOption)?.label }}
        结果由 MediaCrawler 服务生成
      </span>
    </div>
  </div>
</template>
