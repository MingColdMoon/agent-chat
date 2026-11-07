<script setup lang="ts">
import { computed } from 'vue'
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Database,
  FileJson,
  Link2,
  MessageCircle,
  Radio,
  Search,
  ServerOff,
  ShieldCheck,
} from 'lucide-vue-next'
import type { MediaCrawlerTaskResult } from '../types'

const props = defineProps<{
  task: MediaCrawlerTaskResult
}>()

const statusMeta = computed(() => {
  if (props.task.status === 'accepted') {
    return {
      label: '任务运行中',
      icon: CheckCircle2,
      tone: 'success',
    }
  }
  if (props.task.status === 'busy') {
    return { label: '服务繁忙', icon: Clock3, tone: 'warning' }
  }
  if (
    props.task.status === 'unavailable' ||
    props.task.status === 'error'
  ) {
    return { label: '服务未就绪', icon: ServerOff, tone: 'danger' }
  }
  return { label: '任务预览', icon: Radio, tone: 'preview' }
})

const subject = computed(() => {
  const summary = props.task.summary
  if (summary?.query) return summary.query
  const targets = summary?.targets || []
  return targets.length ? targets.slice(0, 1).join('') : '待补充'
})

const modeLabel = computed(() => {
  const mode = props.task.crawler_type || props.task.request?.crawler_type
  return (
    props.task.crawler_type_label ||
    {
      search: '关键词搜索',
      detail: '内容详情',
      creator: '创作者主页',
    }[mode || 'search']
  )
})
</script>

<template>
  <section class="crawler-task-card">
    <header class="crawler-task-head">
      <span class="crawler-task-mark" aria-hidden="true">
        <Radio :size="18" />
      </span>
      <div class="crawler-task-title">
        <span>MEDIACRAWLER</span>
        <h3>{{ task.platform_label || task.platform || '公开数据采集' }}</h3>
      </div>
      <span class="crawler-task-status" :class="statusMeta.tone">
        <component :is="statusMeta.icon" :size="13" />
        {{ statusMeta.label }}
      </span>
    </header>

    <div class="crawler-task-subject">
      <span>
        <Search v-if="task.crawler_type === 'search'" :size="14" />
        <Link2 v-else :size="14" />
        {{ modeLabel }}
      </span>
      <strong>{{ subject }}</strong>
    </div>

    <div class="crawler-task-facts">
      <div>
        <span>内容上限</span>
        <strong>{{ task.summary?.max_items ?? task.request?.max_notes_count ?? '—' }}</strong>
      </div>
      <div>
        <span>评论</span>
        <strong>
          {{
            task.summary?.comments ??
            task.request?.enable_comments
              ? '采集'
              : '关闭'
          }}
        </strong>
      </div>
      <div>
        <span>媒体</span>
        <strong>
          {{
            task.summary?.media ??
            task.request?.enable_media
              ? '下载'
              : '关闭'
          }}
        </strong>
      </div>
      <div>
        <span>输出</span>
        <strong>
          {{
            (task.summary?.save_option || task.request?.save_option || 'jsonl')
              .toUpperCase()
          }}
        </strong>
      </div>
    </div>

    <div v-if="task.message" class="crawler-task-message">
      <Database v-if="task.status === 'accepted'" :size="14" />
      <AlertTriangle v-else :size="14" />
      <span>{{ task.message }}</span>
    </div>

    <div v-if="task.warnings?.length" class="crawler-task-notes">
      <span><ShieldCheck :size="13" /> 使用边界</span>
      <ul>
        <li v-for="warning in task.warnings.slice(0, 3)" :key="warning">
          {{ warning }}
        </li>
      </ul>
    </div>

    <footer class="crawler-task-footer">
      <span>
        <MessageCircle v-if="task.summary?.comments" :size="12" />
        <FileJson v-else :size="12" />
        {{ task.execution_ready ? 'MediaCrawler API' : '任务预览模式' }}
      </span>
      <a
        v-if="task.setup?.upstream"
        :href="task.setup.upstream"
        target="_blank"
        rel="noopener noreferrer"
      >
        MediaCrawler
      </a>
    </footer>
  </section>
</template>
