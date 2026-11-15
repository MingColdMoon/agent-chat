<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  Archive,
  ArrowLeft,
  BookOpen,
  Database,
  FileText,
  LoaderCircle,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  UploadCloud,
  X,
} from 'lucide-vue-next'
import {
  archiveKnowledgeDocument,
  createKnowledgeDocument,
  getAdminKnowledge,
  updateKnowledgeDocument,
} from '../api'
import { formatFileSize } from '../file-utils'
import type { KnowledgeDocumentSummary } from '../types'

const emit = defineEmits<{
  back: []
  changed: []
}>()

const documents = ref<KnowledgeDocumentSummary[]>([])
const revision = ref(0)
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const query = ref('')
const statusFilter = ref<'all' | 'active' | 'archived'>('all')
const editorOpen = ref(false)
const editing = ref<KnowledgeDocumentSummary | null>(null)
const title = ref('')
const selectedFile = ref<File | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const statusFilters = [
  { id: 'all', label: '全部' },
  { id: 'active', label: '有效' },
  { id: 'archived', label: '已归档' },
] as const

const filteredDocuments = computed(() => {
  const normalized = query.value.trim().toLowerCase()
  return documents.value.filter((document) => {
    if (
      statusFilter.value !== 'all' &&
      document.status !== statusFilter.value
    ) {
      return false
    }
    if (!normalized) return true
    return `${document.title} ${document.filename}`
      .toLowerCase()
      .includes(normalized)
  })
})

const activeCount = computed(
  () => documents.value.filter((item) => item.status === 'active').length,
)
const archivedCount = computed(
  () => documents.value.filter((item) => item.status === 'archived').length,
)
const totalChunks = computed(() =>
  documents.value
    .filter((item) => item.status === 'active')
    .reduce((sum, item) => sum + item.chunk_count, 0),
)

async function loadDocuments() {
  loading.value = true
  error.value = ''
  try {
    const result = await getAdminKnowledge()
    documents.value = result.documents
    revision.value = result.revision
  } catch (caught) {
    error.value =
      caught instanceof Error ? caught.message : '加载知识库失败'
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  title.value = ''
  selectedFile.value = null
  error.value = ''
  editorOpen.value = true
}

function openEdit(document: KnowledgeDocumentSummary) {
  editing.value = document
  title.value = document.title
  selectedFile.value = null
  error.value = ''
  editorOpen.value = true
}

function closeEditor() {
  if (busy.value) return
  editorOpen.value = false
  selectedFile.value = null
}

function chooseFile(event: Event) {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] || null
  if (selectedFile.value && !title.value) {
    title.value = selectedFile.value.name.replace(/\.[^.]+$/, '')
  }
}

async function submitDocument() {
  if (busy.value) return
  if (!editing.value && !selectedFile.value) {
    error.value = '请选择知识文件'
    return
  }
  if (!title.value.trim()) {
    error.value = '请填写知识标题'
    return
  }
  busy.value = true
  error.value = ''
  try {
    if (editing.value) {
      await updateKnowledgeDocument(
        editing.value.id,
        title.value.trim(),
        selectedFile.value,
      )
    } else if (selectedFile.value) {
      await createKnowledgeDocument(
        title.value.trim(),
        selectedFile.value,
      )
    }
    editorOpen.value = false
    await loadDocuments()
    emit('changed')
  } catch (caught) {
    error.value =
      caught instanceof Error ? caught.message : '保存知识文件失败'
  } finally {
    busy.value = false
  }
}

async function archiveDocument(document: KnowledgeDocumentSummary) {
  if (
    busy.value ||
    document.status !== 'active' ||
    !window.confirm(`归档知识文件“${document.title}”？`)
  ) {
    return
  }
  busy.value = true
  error.value = ''
  try {
    await archiveKnowledgeDocument(document.id)
    await loadDocuments()
    emit('changed')
  } catch (caught) {
    error.value =
      caught instanceof Error ? caught.message : '归档知识文件失败'
  } finally {
    busy.value = false
  }
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

onMounted(loadDocuments)
</script>

<template>
  <section class="knowledge-manager">
    <header class="knowledge-header">
      <button
        class="icon-button"
        type="button"
        title="返回对话"
        aria-label="返回对话"
        @click="emit('back')"
      >
        <ArrowLeft :size="18" />
      </button>
      <div class="knowledge-heading">
        <span>ADMIN / KNOWLEDGE</span>
        <h1>知识库管理</h1>
        <p>管理项目 RAG 使用的知识文件、版本与索引。</p>
      </div>
      <button class="knowledge-create" type="button" @click="openCreate">
        <Plus :size="16" />
        添加知识
      </button>
    </header>

    <div v-if="error" class="knowledge-error">{{ error }}</div>

    <div class="knowledge-stats">
      <div>
        <Database :size="17" />
        <span>有效文件</span>
        <strong>{{ activeCount }}</strong>
      </div>
      <div>
        <BookOpen :size="17" />
        <span>索引片段</span>
        <strong>{{ totalChunks }}</strong>
      </div>
      <div>
        <RefreshCw :size="17" />
        <span>知识版本</span>
        <strong>r{{ revision }}</strong>
      </div>
      <div>
        <Archive :size="17" />
        <span>已归档</span>
        <strong>{{ archivedCount }}</strong>
      </div>
    </div>

    <div class="knowledge-toolbar">
      <label>
        <Search :size="16" />
        <input
          v-model="query"
          type="search"
          placeholder="搜索标题或文件名"
        />
      </label>
      <div class="knowledge-filter">
        <button
          v-for="filter in statusFilters"
          :key="filter.id"
          type="button"
          :class="{ active: statusFilter === filter.id }"
          @click="statusFilter = filter.id"
        >
          {{ filter.label }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="knowledge-loading">
      <LoaderCircle class="spin" :size="19" />
      正在读取知识库
    </div>

    <div v-else-if="filteredDocuments.length" class="knowledge-list">
      <article
        v-for="document in filteredDocuments"
        :key="document.id"
        class="knowledge-row"
        :class="{ archived: document.status === 'archived' }"
      >
        <span class="knowledge-file-icon">
          <FileText :size="18" />
        </span>
        <div class="knowledge-file-copy">
          <div>
            <h3>{{ document.title }}</h3>
            <span class="knowledge-version">
              v{{ document.current_version }}
            </span>
            <span
              v-if="document.status === 'archived'"
              class="knowledge-archived"
            >
              已归档
            </span>
          </div>
          <p>{{ document.filename }}</p>
          <small>
            {{ document.chunk_count }} 个片段 ·
            {{ formatFileSize(document.size_bytes) }} ·
            {{ formatTime(document.updated_at) }} ·
            {{ document.created_by || 'system' }}
          </small>
        </div>
        <div v-if="document.status === 'active'" class="knowledge-actions">
          <button
            type="button"
            title="编辑或替换文件"
            aria-label="编辑或替换文件"
            :disabled="busy"
            @click="openEdit(document)"
          >
            <Pencil :size="15" />
          </button>
          <button
            type="button"
            title="归档知识文件"
            aria-label="归档知识文件"
            :disabled="busy"
            @click="archiveDocument(document)"
          >
            <Archive :size="15" />
          </button>
        </div>
      </article>
    </div>

    <div v-else class="knowledge-empty">
      <BookOpen :size="22" />
      <strong>没有匹配的知识文件</strong>
      <span>添加文件后，RAG 智能体会自动使用最新有效版本。</span>
    </div>

    <Transition name="settings-fade">
      <div v-if="editorOpen" class="knowledge-editor-layer">
        <button
          class="knowledge-editor-backdrop"
          type="button"
          aria-label="关闭知识编辑"
          @click="closeEditor"
        ></button>
        <form class="knowledge-editor" @submit.prevent="submitDocument">
          <header>
            <div>
              <span>KNOWLEDGE FILE</span>
              <h2>{{ editing ? '更新知识文件' : '添加知识文件' }}</h2>
            </div>
            <button
              class="icon-button"
              type="button"
              title="关闭"
              aria-label="关闭"
              @click="closeEditor"
            >
              <X :size="18" />
            </button>
          </header>

          <div class="knowledge-editor-body">
            <label class="field">
              <span>知识标题</span>
              <input
                v-model="title"
                type="text"
                maxlength="200"
                placeholder="例如：B站直播规范"
              />
            </label>

            <div class="field">
              <span>
                {{ editing ? '替换文件（可选）' : '知识文件' }}
              </span>
              <button
                class="knowledge-file-picker"
                type="button"
                @click="fileInput?.click()"
              >
                <UploadCloud :size="20" />
                <span>
                  <strong>
                    {{ selectedFile?.name || '选择 HTML、PDF、DOCX 或文本文件' }}
                  </strong>
                  <small>
                    {{
                      selectedFile
                        ? formatFileSize(selectedFile.size)
                        : '最大 15 MB'
                    }}
                  </small>
                </span>
              </button>
              <input
                ref="fileInput"
                class="knowledge-file-input"
                type="file"
                accept=".md,.markdown,.txt,.html,.htm,.pdf,.docx,.csv,.json,.yaml,.yml,.xml"
                @change="chooseFile"
              />
            </div>

            <p v-if="editing" class="knowledge-editor-note">
              上传新文件会创建 v{{ editing.current_version + 1 }}，旧版本仅用于历史追溯。
            </p>
            <p v-if="error" class="knowledge-editor-error">{{ error }}</p>
          </div>

          <footer>
            <button class="knowledge-save" type="submit" :disabled="busy">
              <LoaderCircle v-if="busy" class="spin" :size="16" />
              <UploadCloud v-else :size="16" />
              {{ busy ? '正在保存' : editing ? '保存新版本' : '添加知识' }}
            </button>
          </footer>
        </form>
      </div>
    </Transition>
  </section>
</template>

<style scoped>
.knowledge-manager {
  min-height: 100%;
  padding: 0 34px 56px;
}

.knowledge-header {
  position: sticky;
  z-index: 8;
  top: 0;
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  margin: 0 -34px 24px;
  padding: 25px 34px 22px;
  border-bottom: 1px solid var(--line);
  background: rgba(5, 5, 6, 0.92);
  backdrop-filter: blur(18px);
}

.knowledge-heading > span {
  color: var(--warm);
  font-family: var(--mono);
  font-size: 8px;
  font-weight: 700;
}

.knowledge-heading h1 {
  margin: 7px 0 0;
  font-size: clamp(31px, 3.2vw, 46px);
  line-height: 1.06;
}

.knowledge-heading p {
  margin: 8px 0 0;
  color: var(--ink-soft);
  font-size: 11px;
}

.knowledge-create,
.knowledge-save {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  border: 1px solid #f0eee6;
  border-radius: 999px;
  background: #f0eee6;
  color: #080809;
  cursor: pointer;
  font-size: 10px;
  font-weight: 650;
}

.knowledge-create {
  height: 40px;
  padding: 0 15px;
}

.knowledge-error {
  margin-bottom: 16px;
  padding: 10px 12px;
  border: 1px solid #4d2929;
  border-radius: var(--radius);
  background: #1a1011;
  color: #ff8f8b;
  font-size: 10px;
}

.knowledge-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: #0d0d0f;
}

.knowledge-stats > div {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 8px;
  padding: 13px;
  border-right: 1px solid var(--line);
}

.knowledge-stats > div:last-child {
  border-right: 0;
}

.knowledge-stats svg {
  color: var(--warm);
}

.knowledge-stats span {
  color: var(--ink-faint);
  font-size: 9px;
}

.knowledge-stats strong {
  color: var(--ink);
  font-family: var(--mono);
  font-size: 17px;
}

.knowledge-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 22px 0 14px;
}

.knowledge-toolbar > label {
  display: grid;
  height: 42px;
  flex: 1;
  grid-template-columns: 20px minmax(0, 1fr);
  align-items: center;
  gap: 6px;
  padding: 0 12px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #101012;
  color: var(--ink-faint);
}

.knowledge-toolbar input {
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--ink);
  font-size: 10px;
}

.knowledge-filter {
  display: flex;
  gap: 4px;
  padding: 4px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #0e0e10;
}

.knowledge-filter button {
  min-height: 32px;
  padding: 0 12px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--ink-faint);
  cursor: pointer;
  font-size: 9px;
}

.knowledge-filter button.active {
  background: #f0eee6;
  color: #080809;
}

.knowledge-loading,
.knowledge-empty {
  display: grid;
  min-height: 260px;
  place-items: center;
  align-content: center;
  gap: 8px;
  border: 1px dashed var(--line-strong);
  border-radius: var(--radius);
  color: var(--ink-faint);
  font-size: 10px;
}

.knowledge-loading {
  grid-template-columns: auto auto;
}

.knowledge-empty strong {
  color: var(--ink);
  font-size: 12px;
}

.knowledge-list {
  display: grid;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: #0d0d0f;
  overflow: hidden;
}

.knowledge-row {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--line);
}

.knowledge-row:last-child {
  border-bottom: 0;
}

.knowledge-row.archived {
  opacity: 0.55;
}

.knowledge-file-icon {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border: 1px solid var(--line);
  border-radius: 50%;
  background: #171719;
  color: var(--warm);
}

.knowledge-file-copy {
  min-width: 0;
}

.knowledge-file-copy > div {
  display: flex;
  align-items: center;
  gap: 7px;
}

.knowledge-file-copy h3 {
  margin: 0;
  color: var(--ink);
  font-size: 11px;
  font-weight: 650;
}

.knowledge-version,
.knowledge-archived {
  padding: 2px 5px;
  border: 1px solid var(--line);
  border-radius: 999px;
  color: var(--ink-faint);
  font-family: var(--mono);
  font-size: 7px;
}

.knowledge-archived {
  border-color: #4d2929;
  color: #ff8f8b;
}

.knowledge-file-copy p {
  margin: 3px 0 0;
  color: var(--ink-soft);
  font-size: 9px;
}

.knowledge-file-copy small {
  display: block;
  margin-top: 3px;
  color: var(--ink-faint);
  font-family: var(--mono);
  font-size: 7px;
}

.knowledge-actions {
  display: flex;
  gap: 5px;
}

.knowledge-actions button {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border: 1px solid var(--line);
  border-radius: 50%;
  background: #141416;
  color: var(--ink-soft);
  cursor: pointer;
}

.knowledge-actions button:hover {
  border-color: var(--line-strong);
  color: var(--ink);
}

.knowledge-editor-layer {
  position: fixed;
  z-index: 52;
  inset: 0;
}

.knowledge-editor-backdrop {
  position: absolute;
  inset: 0;
  width: 100%;
  border: 0;
  background: rgba(0, 0, 0, 0.64);
}

.knowledge-editor {
  position: absolute;
  top: 50%;
  left: 50%;
  display: grid;
  width: min(480px, calc(100vw - 28px));
  max-height: calc(100dvh - 40px);
  grid-template-rows: auto minmax(0, 1fr) auto;
  border: 1px solid var(--line-strong);
  border-radius: var(--radius);
  background: #0b0b0d;
  box-shadow: 0 30px 90px rgba(0, 0, 0, 0.55);
  overflow: hidden;
  transform: translate(-50%, -50%);
}

.knowledge-editor > header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--line);
}

.knowledge-editor header span {
  color: var(--warm);
  font-family: var(--mono);
  font-size: 7px;
}

.knowledge-editor h2 {
  margin: 3px 0 0;
  font-size: 16px;
}

.knowledge-editor-body {
  overflow-y: auto;
  padding: 4px 16px 20px;
}

.knowledge-file-picker {
  display: grid;
  min-height: 92px;
  grid-template-columns: 34px minmax(0, 1fr);
  align-items: center;
  gap: 10px;
  padding: 13px;
  border: 1px dashed var(--line-strong);
  border-radius: var(--radius);
  background: #111113;
  color: var(--ink-soft);
  cursor: pointer;
  text-align: left;
}

.knowledge-file-picker:hover {
  border-color: #6d6d76;
}

.knowledge-file-picker strong,
.knowledge-file-picker small {
  display: block;
}

.knowledge-file-picker strong {
  color: var(--ink);
  font-size: 10px;
}

.knowledge-file-picker small {
  margin-top: 4px;
  color: var(--ink-faint);
  font-size: 8px;
}

.knowledge-file-input {
  display: none;
}

.knowledge-editor-note {
  margin: 12px 0 0;
  color: var(--ink-faint);
  font-size: 9px;
  line-height: 1.6;
}

.knowledge-editor-error {
  margin: 12px 0 0;
  color: #ff8f8b;
  font-size: 9px;
}

.knowledge-editor > footer {
  padding: 12px 16px;
  border-top: 1px solid var(--line);
}

.knowledge-save {
  width: 100%;
  height: 40px;
}

.knowledge-create:hover,
.knowledge-save:hover:not(:disabled) {
  border-color: #fff;
  background: #fff;
}

@media (max-width: 720px) {
  .knowledge-manager {
    padding: 0 14px 36px;
  }

  .knowledge-header {
    grid-template-columns: 34px minmax(0, 1fr) 38px;
    margin-right: -14px;
    margin-left: -14px;
    padding: 14px;
  }

  .knowledge-heading h1 {
    font-size: 24px;
  }

  .knowledge-heading p {
    display: none;
  }

  .knowledge-create {
    width: 38px;
    height: 38px;
    padding: 0;
    font-size: 0;
  }

  .knowledge-stats {
    grid-template-columns: repeat(2, 1fr);
  }

  .knowledge-stats > div:nth-child(2) {
    border-right: 0;
  }

  .knowledge-stats > div:nth-child(-n + 2) {
    border-bottom: 1px solid var(--line);
  }

  .knowledge-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .knowledge-filter button {
    flex: 1;
  }

  .knowledge-row {
    grid-template-columns: 34px minmax(0, 1fr);
  }

  .knowledge-actions {
    grid-column: 2;
  }
}
</style>
