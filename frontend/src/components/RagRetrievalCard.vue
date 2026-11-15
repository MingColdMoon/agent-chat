<script setup lang="ts">
import { computed } from 'vue'
import {
  ArrowDown,
  Database,
  FileText,
  Gauge,
  Layers3,
  Search,
} from 'lucide-vue-next'
import type { RagRetrievalResult } from '../types'

const props = defineProps<{
  retrieval: RagRetrievalResult
}>()

const selectedCount = computed(() => props.retrieval.items?.length || 0)
const candidateCount = computed(
  () => props.retrieval.candidate_count || 0,
)

function scoreWidth(score: number) {
  return `${Math.max(4, Math.min(100, Math.round(score * 100)))}%`
}
</script>

<template>
  <section class="rag-retrieval-card">
    <header class="rag-card-head">
      <span class="rag-card-mark" aria-hidden="true">
        <Database :size="18" />
      </span>
      <div class="rag-card-title">
        <span>RAG / PROJECT KNOWLEDGE</span>
        <h3>项目知识库检索与重排</h3>
      </div>
      <span class="rag-card-badge">
        <Gauge :size="12" />
        Rerank
      </span>
    </header>

    <div class="rag-card-query">
      <Search :size="14" />
      <span>{{ retrieval.query || '未提供检索问题' }}</span>
    </div>

    <div class="rag-pipeline">
      <span>
        <Layers3 :size="14" />
        候选召回
        <strong>{{ candidateCount }}</strong>
      </span>
      <ArrowDown :size="13" />
      <span>
        <Gauge :size="14" />
        Rerank 保留
        <strong>{{ selectedCount }}</strong>
      </span>
    </div>

    <div v-if="retrieval.error" class="rag-card-error">
      {{ retrieval.error }}
    </div>

    <div v-else-if="selectedCount" class="rag-result-list">
      <article
        v-for="item in retrieval.items"
        :key="`${item.document_id}-${item.chunk_index}`"
        class="rag-result-item"
      >
        <div class="rag-result-meta">
          <span>
            <FileText :size="13" />
            {{ item.title || item.filename }}
          </span>
          <small>v{{ item.version }} · 片段 {{ item.chunk_index + 1 }}</small>
          <strong>{{ item.rerank_score.toFixed(4) }}</strong>
        </div>
        <p>{{ item.preview }}</p>
        <div class="rag-score-track" aria-hidden="true">
          <span :style="{ width: scoreWidth(item.rerank_score) }"></span>
        </div>
      </article>
    </div>

    <div v-else class="rag-card-empty">
      当前会话知识库没有匹配片段
    </div>

    <footer class="rag-card-footer">
      <span>检索策略：{{ retrieval.rerank || 'lexical-coverage-v1' }}</span>
      <span>第二阶段：覆盖度 + 短语 + 文件名词权重</span>
    </footer>
  </section>
</template>
