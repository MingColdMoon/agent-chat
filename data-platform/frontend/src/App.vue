<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import {
  ArrowDownToLine, ArrowRight, BarChart3, Check, ChevronDown, CircleHelp,
  Database, FileJson2, FileSpreadsheet, Layers3, LoaderCircle, LogOut,
  MessageSquareText, Plus, RefreshCw, Search, Send, Settings2, ShieldCheck,
  Sparkles, Table2, Trash2, Upload, X,
} from 'lucide-vue-next'
import {
  authenticate, createDatasetRow, deleteDataset, deleteDatasetRow, exportDataset,
  getChat, getDatasetRows, getDatasets, getMe, getSourceRows, getSourceTables,
  getToken, importDataset, importSource, logout, previewFile, sendAnalysis,
  updateDatasetRow,
} from './api'
import type { ChatLine, Column, Dataset, Preview, SourceTable, User } from './api'

type View = 'overview' | 'ingest' | 'analysis'
const user = ref<User | null>(null)
const booting = ref(true)
const authMode = ref<'login' | 'register'>('login')
const authBusy = ref(false)
const authError = ref('')
const username = ref('')
const password = ref('')
const view = ref<View>('overview')
const datasets = ref<Dataset[]>([])
const sourceTables = ref<SourceTable[]>([])
const activeDataset = ref<Dataset | null>(null)
const dataRows = ref<(Record<string, unknown> & { __row_id: number })[]>([])
const dataTotal = ref(0)
const rowPage = ref(1)
const rowPageSize = ref(20)
const rowSearch = ref('')
const rowEditorOpen = ref(false)
const editingRowId = ref<number | null>(null)
const rowDraft = ref<Record<string, unknown>>({})
const rowBusy = ref(false)
const loading = ref(false)
const busy = ref(false)
const pageError = ref('')
const success = ref('')
const query = ref('')
const importMode = ref<'file' | 'source'>('file')
const fileInput = ref<HTMLInputElement | null>(null)
const preview = ref<Preview | null>(null)
const selectedSource = ref<SourceTable | null>(null)
const importName = ref('')
const importTable = ref('dp_imported_data')
const importBusy = ref(false)
const previewRows = ref<Record<string, unknown>[]>([])
const chatMessages = ref<ChatLine[]>([])
const chatStream = ref<HTMLElement | null>(null)
const chatInput = ref('')
const provider = ref(sessionStorage.getItem('dp-provider') || 'demo')
const apiKey = ref(sessionStorage.getItem('dp-api-key') || '')
const baseUrl = ref(sessionStorage.getItem('dp-base-url') || 'https://api.openai.com/v1')
const model = ref(sessionStorage.getItem('dp-model') || 'gpt-4o-mini')
const settingsOpen = ref(false)
const navItems = [
  { id: 'overview' as View, label: '数据总览', icon: Layers3 },
  { id: 'ingest' as View, label: '数据接入', icon: ArrowDownToLine },
  { id: 'analysis' as View, label: '数据分析', icon: MessageSquareText },
]
const activeTitle = computed(() => ({ overview: '数据总览', ingest: '数据接入', analysis: '数据分析' })[view.value])
const filteredDatasets = computed(() => datasets.value.filter((item) => (item.name + item.table_name).toLowerCase().includes(query.value.trim().toLowerCase())))
const rowColumns = computed(() => activeDataset.value?.columns || [])
const totalSourceRows = computed(() => sourceTables.value.reduce((sum, table) => sum + table.row_count, 0))
const currentTime = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' }).format(new Date())

async function refreshData() {
  loading.value = true
  pageError.value = ''
  try {
    const [nextDatasets, nextTables] = await Promise.all([getDatasets(), getSourceTables()])
    datasets.value = nextDatasets
    sourceTables.value = nextTables
    if (activeDataset.value) {
      const updated = nextDatasets.find((item) => item.id === activeDataset.value?.id)
      activeDataset.value = updated || null
      if (updated) await loadDataset(updated)
    }
  } catch (error) { pageError.value = error instanceof Error ? error.message : '数据加载失败' }
  finally { loading.value = false }
}

async function loadDataset(dataset: Dataset) {
  activeDataset.value = dataset
  pageError.value = ''
  try {
    const [table, messages] = await Promise.all([
      getDatasetRows(dataset.id, rowPage.value, rowPageSize.value, rowSearch.value),
      getChat(dataset.id),
    ])
    dataRows.value = table.rows
    dataTotal.value = table.total
    chatMessages.value = messages
  } catch (error) { pageError.value = error instanceof Error ? error.message : '数据加载失败' }
}

async function submitAuth() {
  authBusy.value = true
  authError.value = ''
  try {
    user.value = await authenticate(authMode.value, username.value, password.value)
    await refreshData()
    if (pageError.value) { authError.value = pageError.value; pageError.value = '' }
  } catch (error) { authError.value = error instanceof Error ? error.message : '登录失败' }
  finally { authBusy.value = false }
}

function inferFromDb(type: string) {
  const lowered = type.toLowerCase()
  if (/bool/.test(lowered)) return 'boolean'
  if (/int/.test(lowered)) return 'integer'
  if (/numeric|decimal|real|double|float/.test(lowered)) return 'number'
  return 'text'
}

async function loadSource(table: SourceTable) {
  importMode.value = 'source'
  selectedSource.value = table
  pageError.value = ''
  try {
    const result = await getSourceRows(table.name)
    const columns = result.columns.map((column) => ({ source: column.name, name: column.name, type: inferFromDb(column.type), included: true }))
    previewRows.value = result.rows
    preview.value = { filename: table.name, columns, rows: result.rows, row_count: result.total }
    importName.value = table.name
    importTable.value = 'dp_' + table.name.replace(/[^A-Za-z0-9_]/g, '_')
  } catch (error) { pageError.value = error instanceof Error ? error.message : '读取数据表失败' }
}

function openFilePicker() { fileInput.value?.click() }
function setFilePreview(next: Preview, fileName: string) {
  preview.value = next
  previewRows.value = next.rows.map((row) => ({ ...row }))
  selectedSource.value = null
  importName.value = fileName.replace(/\.(csv|json)$/i, '')
  importTable.value = 'dp_' + importName.value.toLowerCase().replace(/[^a-z0-9_]/g, '_').replace(/^[^a-z_]+/, '')
  if (importTable.value === 'dp_') importTable.value = 'dp_imported_data'
  view.value = 'ingest'
}
async function onFileSelected(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  pageError.value = ''
  try { setFilePreview(await previewFile(file), file.name) }
  catch (error) { pageError.value = error instanceof Error ? error.message : '文件预览失败' }
  finally { (event.target as HTMLInputElement).value = '' }
}
async function onDropFile(event: DragEvent) {
  const file = event.dataTransfer?.files?.[0]
  if (!file) return
  pageError.value = ''
  try { setFilePreview(await previewFile(file), file.name) }
  catch (error) { pageError.value = error instanceof Error ? error.message : '文件预览失败' }
}
function updatePreviewCell(rowIndex: number, source: string, value: string) {
  if (previewRows.value[rowIndex]) previewRows.value[rowIndex][source] = value
}

async function doImport() {
  if (!preview.value || !importName.value.trim()) return
  importBusy.value = true
  pageError.value = ''
  success.value = ''
  try {
    const payload = { table_name: importTable.value.trim(), display_name: importName.value.trim(), columns: preview.value.columns, rows: previewRows.value }
    const result = selectedSource.value ? await importSource(selectedSource.value.name, payload) : await importDataset(payload)
    success.value = '已导入 ' + result.imported_rows.toLocaleString() + ' 条记录'
    preview.value = null
    previewRows.value = []
    selectedSource.value = null
    await refreshData()
    await loadDataset(result.dataset)
    view.value = 'analysis'
  } catch (error) { pageError.value = error instanceof Error ? error.message : '导入失败' }
  finally { importBusy.value = false }
}

async function selectDataset(dataset: Dataset) { await loadDataset(dataset); view.value = 'analysis' }
async function saveDataset() {
  if (!activeDataset.value) return
  try {
    const result = await exportDataset(activeDataset.value.id)
    const blob = new Blob([JSON.stringify(result.rows, null, 2)], { type: 'application/json;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = result.filename
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) { pageError.value = error instanceof Error ? error.message : '导出失败' }
}
async function removeDataset() {
  if (!activeDataset.value || !window.confirm('删除此数据集及其数据表？此操作不可撤销。')) return
  try {
    await deleteDataset(activeDataset.value.id)
    activeDataset.value = null
    dataRows.value = []
    dataTotal.value = 0
    chatMessages.value = []
    await refreshData()
  } catch (error) { pageError.value = error instanceof Error ? error.message : '删除失败' }
}

function openNewRow() {
  editingRowId.value = null
  rowDraft.value = Object.fromEntries((activeDataset.value?.columns || []).map((column) => [column.name, '']))
  rowEditorOpen.value = true
}
function openEditRow(row: Record<string, unknown> & { __row_id: number }) {
  editingRowId.value = row.__row_id
  rowDraft.value = Object.fromEntries((activeDataset.value?.columns || []).map((column) => [column.name, row[column.name] ?? '']))
  rowEditorOpen.value = true
}
async function saveRow() {
  if (!activeDataset.value) return
  const isNew = editingRowId.value === null
  rowBusy.value = true
  pageError.value = ''
  try {
    if (isNew) {
      await createDatasetRow(activeDataset.value.id, rowDraft.value)
      rowSearch.value = ''
      const result = await getDatasetRows(activeDataset.value.id, 1, rowPageSize.value, '')
      rowPage.value = Math.max(1, Math.ceil(result.total / rowPageSize.value))
    }
    else await updateDatasetRow(activeDataset.value.id, editingRowId.value as number, rowDraft.value)
    rowEditorOpen.value = false
    await loadDataset(activeDataset.value)
    success.value = isNew ? '记录已新增' : '记录已更新'
  } catch (error) { pageError.value = error instanceof Error ? error.message : '保存记录失败' }
  finally { rowBusy.value = false }
}
async function removeRow(row: Record<string, unknown> & { __row_id: number }) {
  if (!activeDataset.value || !window.confirm('确定删除这条记录吗？此操作不可撤销。')) return
  try {
    await deleteDatasetRow(activeDataset.value.id, row.__row_id)
    if (dataRows.value.length === 1 && rowPage.value > 1) rowPage.value -= 1
    await loadDataset(activeDataset.value)
    success.value = '记录已删除'
  } catch (error) { pageError.value = error instanceof Error ? error.message : '删除记录失败' }
}
function searchRows() {
  rowPage.value = 1
  if (activeDataset.value) void loadDataset(activeDataset.value)
}
function changeRowPage(page: number) {
  const pageCount = Math.max(1, Math.ceil(dataTotal.value / rowPageSize.value))
  rowPage.value = Math.min(Math.max(1, page), pageCount)
  if (activeDataset.value) void loadDataset(activeDataset.value)
}

async function sendMessage() {
  const content = chatInput.value.trim()
  if (!content || !activeDataset.value || busy.value) return
  chatMessages.value.push({ role: 'user', content })
  chatInput.value = ''
  busy.value = true
  pageError.value = ''
  try {
    sessionStorage.setItem('dp-provider', provider.value)
    sessionStorage.setItem('dp-api-key', apiKey.value)
    sessionStorage.setItem('dp-base-url', baseUrl.value)
    sessionStorage.setItem('dp-model', model.value)
    const result = await sendAnalysis(activeDataset.value.id, content, { provider: provider.value, api_key: apiKey.value, base_url: baseUrl.value, model: model.value })
    chatMessages.value.push({ role: 'assistant', content: result.answer })
    await nextTick()
    chatStream.value?.scrollTo({ top: chatStream.value.scrollHeight, behavior: 'smooth' })
  } catch (error) { chatMessages.value.pop(); chatInput.value = content; pageError.value = error instanceof Error ? error.message : '分析请求失败' }
  finally { busy.value = false }
}

function startAnalysis() {
  if (datasets.value.length) void selectDataset(datasets.value[0])
  else view.value = 'ingest'
}
async function signOut() {
  try { await logout() } catch { /* local UI still clears */ }
  user.value = null
  datasets.value = []
  sourceTables.value = []
  activeDataset.value = null
  dataRows.value = []
  chatMessages.value = []
}
watch(provider, (value) => {
  if (value === 'openai') {
    if (!baseUrl.value || baseUrl.value === 'https://api.deepseek.com/v1') baseUrl.value = 'https://api.openai.com/v1'
    if (!model.value || model.value === 'deepseek-chat') model.value = 'gpt-4o-mini'
  }
  if (value === 'deepseek') { baseUrl.value = 'https://api.deepseek.com/v1'; model.value = 'deepseek-chat' }
})
onMounted(async () => {
  if (!getToken()) { booting.value = false; return }
  try { user.value = (await getMe()).user; await refreshData() }
  catch { sessionStorage.removeItem('agent-chat-access-token') }
  finally { booting.value = false }
})
</script>

<template>
  <div v-if="booting" class="boot-screen"><span class="boot-pulse"></span>正在连接数据工作区…</div>
  <main v-else-if="!user" class="auth-screen">
    <section class="auth-intro"><div class="auth-brand"><span class="brand-mark"><Layers3 :size="20" /></span><div><strong>数据中台</strong><span>DATA WORKSPACE</span></div></div><div class="auth-hero"><span>DATA PLATFORM</span><h1>让数据<br /><em>回答问题</em></h1><p>接入业务数据，整理字段，用一场对话发现数据中的线索。</p><div class="auth-signal"><i v-for="n in 7" :key="n"></i></div></div><div class="auth-footnote"><ShieldCheck :size="14" />共享 Agent Chat 账号与数据服务</div></section>
    <section class="auth-workspace"><form class="auth-form" @submit.prevent="submitAuth"><span class="section-kicker">WELCOME</span><h2>{{ authMode === 'login' ? '登录工作区' : '创建账号' }}</h2><p class="muted">{{ authMode === 'login' ? '使用 Agent Chat 账号继续' : '账号会写入共享用户库' }}</p><div class="auth-tabs"><button type="button" :class="{ active: authMode === 'login' }" @click="authMode = 'login'; authError = ''">登录</button><button type="button" :class="{ active: authMode === 'register' }" @click="authMode = 'register'; authError = ''">注册</button></div><div v-if="authError" class="notice error"><X :size="15" />{{ authError }}</div><label class="field-label">用户名<input v-model="username" autocomplete="username" minlength="3" maxlength="32" required /></label><label class="field-label">密码<input v-model="password" :autocomplete="authMode === 'login' ? 'current-password' : 'new-password'" minlength="8" maxlength="128" type="password" required /></label><button class="button primary full" :disabled="authBusy"><LoaderCircle v-if="authBusy" class="spin" :size="16" />{{ authBusy ? '正在连接' : authMode === 'login' ? '登录数据中台' : '创建账号并登录' }}</button><div class="auth-safe"><ShieldCheck :size="14" />登录服务复用 Agent Chat 的认证配置</div></form></section>
  </main>
  <div v-else class="app-shell">
    <aside class="sidebar"><div class="sidebar-brand"><span class="brand-mark"><Layers3 :size="19" /></span><div><strong>数据中台</strong><span>DATA WORKSPACE</span></div><button class="icon-button sidebar-refresh" title="刷新" @click="refreshData"><RefreshCw :size="15" /></button></div><div class="nav-label">工作空间</div><button v-for="item in navItems" :key="item.id" class="nav-item" :class="{ selected: view === item.id }" @click="view = item.id"><component :is="item.icon" :size="17" />{{ item.label }}<span v-if="item.id === 'analysis' && datasets.length" class="nav-count">{{ datasets.length }}</span></button><div class="sidebar-section"><span class="nav-label">我的数据集</span><button class="icon-button" title="接入数据" @click="view = 'ingest'"><Plus :size="15" /></button></div><div class="dataset-nav-list"><button v-for="dataset in datasets.slice(0, 8)" :key="dataset.id" class="dataset-nav" :class="{ active: activeDataset?.id === dataset.id && view === 'analysis' }" @click="selectDataset(dataset)"><Table2 :size="14" /><span>{{ dataset.name }}</span></button><div v-if="!datasets.length" class="nav-empty">导入后，数据集会显示在这里</div></div><div class="sidebar-bottom"><div class="storage-card"><div class="storage-title"><Database :size="14" />数据连接<span class="status-dot"></span></div><div>{{ sourceTables.length }} 张业务表可接入</div><div class="storage-meta">{{ totalSourceRows.toLocaleString() }} 条当前账号可见记录</div></div><div class="user-card"><span class="avatar">{{ user.username.slice(0, 1).toUpperCase() }}</span><div class="user-meta"><strong>{{ user.username }}</strong><span>数据工作区</span></div><button class="icon-button" title="退出登录" @click="signOut"><LogOut :size="15" /></button></div></div></aside>
    <section class="main-column">
      <header class="topbar"><div class="breadcrumbs"><span>数据工作区</span><span class="crumb-slash">/</span><strong>{{ activeTitle }}</strong><template v-if="activeDataset && view === 'analysis'"><span class="crumb-slash">/</span><span>{{ activeDataset.name }}</span></template></div><div class="topbar-actions"><span class="date-stamp">{{ currentTime }}</span><button class="icon-button settings-trigger" @click="settingsOpen = !settingsOpen"><Settings2 :size="16" /><span>模型设置</span></button><div class="model-chip"><span class="model-dot" :class="{ live: provider !== 'demo' && apiKey }"></span>{{ provider === 'demo' ? '演示模式' : provider === 'deepseek' ? 'DeepSeek' : 'OpenAI 兼容' }}</div></div></header>
      <div v-if="pageError" class="global-notice error"><X :size="16" /><span>{{ pageError }}</span><button class="icon-button" @click="pageError = ''"><X :size="14" /></button></div><div v-if="success" class="global-notice success"><Check :size="16" /><span>{{ success }}</span><button class="icon-button" @click="success = ''"><X :size="14" /></button></div>
      <div v-if="settingsOpen" class="settings-popover"><div class="settings-head"><div><strong>模型设置</strong><span>API Key 仅保存在当前标签页</span></div><button class="icon-button" @click="settingsOpen = false"><X :size="16" /></button></div><label class="field-label">服务商<select v-model="provider"><option value="demo">演示模式</option><option value="openai">OpenAI 兼容</option><option value="deepseek">DeepSeek</option></select></label><label v-if="provider !== 'demo'" class="field-label">API Key<input v-model="apiKey" type="password" autocomplete="off" placeholder="sk-…" /></label><div v-if="provider !== 'demo'" class="settings-grid"><label class="field-label">API 地址<input v-model="baseUrl" placeholder="https://api.openai.com/v1" /></label><label class="field-label">模型名称<input v-model="model" placeholder="gpt-4o-mini" /></label></div><div class="settings-note"><CircleHelp :size="14" />演示模式不调用模型，真实分析会使用当前数据集的字段、统计和样本。</div></div>

      <section v-if="view === 'overview'" class="page-content overview-page"><div class="page-heading"><div><div class="eyebrow">OVERVIEW / {{ new Date().getFullYear() }}</div><h1>数据总览<span class="heading-period">· {{ currentTime }}</span></h1><p>接入业务数据，让每个问题都能找到依据。</p></div><button class="button primary" @click="view = 'ingest'"><Plus :size="16" />接入数据</button></div><div class="metric-grid"><article class="metric-card"><div class="metric-top"><span>我的数据集</span><span class="metric-icon teal"><Layers3 :size="17" /></span></div><div class="metric-value">{{ String(datasets.length).padStart(2, '0') }}<span class="metric-suffix">个</span></div><div class="metric-foot"><span class="metric-dot teal-bg"></span>已导入工作区</div><div class="metric-spark spark-teal"><i v-for="n in [38,54,43,68,52,80,63,91,70,100]" :key="n" :style="{ height: n + '%' }"></i></div></article><article class="metric-card"><div class="metric-top"><span>源业务表</span><span class="metric-icon ochre"><Database :size="17" /></span></div><div class="metric-value">{{ String(sourceTables.length).padStart(2, '0') }}<span class="metric-suffix">张</span></div><div class="metric-foot"><span class="metric-dot ochre-bg"></span>来自共享 PostgreSQL</div><div class="metric-spark spark-ochre"><i v-for="n in [64,42,70,51,85,60,73,53,88,69]" :key="n" :style="{ height: n + '%' }"></i></div></article><article class="metric-card"><div class="metric-top"><span>可接入记录</span><span class="metric-icon blue"><BarChart3 :size="17" /></span></div><div class="metric-value">{{ totalSourceRows.toLocaleString() }}<span class="metric-suffix">条</span></div><div class="metric-foot"><span class="metric-dot blue-bg"></span>按当前账号权限统计</div><div class="metric-spark spark-blue"><i v-for="n in [34,57,48,62,46,77,65,83,72,94]" :key="n" :style="{ height: n + '%' }"></i></div></article></div><div class="overview-grid"><section class="panel datasets-panel"><div class="panel-heading"><div><span class="section-kicker">YOUR DATA</span><h2>最近的数据集</h2></div><button class="text-button" @click="view = 'analysis'">查看分析空间<ArrowRight :size="14" /></button></div><div v-if="datasets.length" class="dataset-list"><button v-for="(dataset, index) in datasets.slice(0, 6)" :key="dataset.id" class="dataset-row" @click="selectDataset(dataset)"><span class="dataset-index">{{ String(index + 1).padStart(2, '0') }}</span><span class="table-glyph"><Table2 :size="16" /></span><span class="dataset-main"><strong>{{ dataset.name }}</strong><small>{{ dataset.table_name }} · {{ dataset.columns.length }} 个字段</small></span><span class="dataset-source">数据集</span><ArrowRight class="row-arrow" :size="16" /></button></div><div v-else class="empty-state"><div class="empty-art"><div class="empty-grid"><i v-for="n in 9" :key="n"></i></div><span><Database :size="21" /></span></div><strong>先接入一份业务数据</strong><p>从共享业务表读取，或上传 CSV、JSON 文件。</p><button class="button secondary" @click="view = 'ingest'"><Plus :size="15" />开始接入</button></div></section><section class="panel source-panel"><div class="panel-heading"><div><span class="section-kicker">CONNECTED SOURCE</span><h2>业务数据表</h2></div><span class="live-badge"><i></i>已连接</span></div><div class="source-list"><button v-for="table in sourceTables.slice(0, 6)" :key="table.name" class="source-row" @click="view = 'ingest'; loadSource(table)"><span class="source-icon"><Table2 :size="15" /></span><span class="source-main"><strong>{{ table.name }}</strong><small>{{ table.columns.length }} 字段</small></span><span class="source-count">{{ table.row_count.toLocaleString() }}<small>行</small></span></button><div v-if="!sourceTables.length" class="source-loading">{{ loading ? '正在读取数据库…' : '暂无可接入的业务表' }}</div></div><button class="source-all" @click="view = 'ingest'">浏览全部数据源<ArrowRight :size="14" /></button></section></div><div class="quick-strip"><div class="quick-mark"><Sparkles :size="17" /></div><div><strong>下一步：问问你的数据</strong><span>在分析空间中选择数据集，开启一场基于数据的对话。</span></div><button class="button dark-button" @click="startAnalysis">进入数据分析<ArrowRight :size="15" /></button></div></section>

      <section v-else-if="view === 'ingest'" class="page-content ingest-page"><div class="page-heading"><div><div class="eyebrow">DATA INGESTION / 02</div><h1>数据接入<span class="heading-period">· 预览、整理、导入</span></h1><p>接入原项目业务表，或上传 CSV、JSON 文件。导入目标独立建表，不修改源表。</p></div></div><div class="ingest-layout"><div class="ingest-main"><div class="ingest-tabs"><button :class="{ active: importMode === 'file' }" @click="importMode = 'file'"><Upload :size="16" />文件导入</button><button :class="{ active: importMode === 'source' }" @click="importMode = 'source'"><Database :size="16" />数据库表</button><span class="ingest-tabs-hint">支持 CSV / JSON · 最多 20 MB</span></div><div v-if="importMode === 'file' && !preview" class="dropzone" @click="openFilePicker" @dragover.prevent @drop.prevent="onDropFile"><input ref="fileInput" type="file" accept=".csv,.json,text/csv,application/json" hidden @change="onFileSelected" /><div class="drop-icon"><Upload :size="21" /></div><strong>拖拽文件到这里，或 <em>浏览文件</em></strong><span>支持以第一行为表头的 CSV 和对象数组 JSON</span><div class="file-types"><span><FileSpreadsheet :size="14" />CSV</span><span><FileJson2 :size="14" />JSON</span></div></div><div v-if="importMode === 'source' && !preview" class="source-picker"><div class="source-picker-head"><div><strong>共享 PostgreSQL 数据表</strong><span>展示当前账号可访问的行数，最多预览 100 条，导入上限 5,000 条</span></div><button class="icon-button" title="刷新数据源" @click="getSourceTables().then((items) => sourceTables = items)"><RefreshCw :size="15" /></button></div><button v-for="table in sourceTables" :key="table.name" class="source-option" :class="{ selected: selectedSource?.name === table.name }" @click="loadSource(table)"><span class="source-icon"><Table2 :size="16" /></span><span class="source-main"><strong>{{ table.name }}</strong><small>{{ table.columns.length }} 个字段 · 共享业务表</small></span><span class="source-count">{{ table.row_count.toLocaleString() }}<small>行</small></span><ChevronDown :size="16" class="option-arrow" /></button><div v-if="!sourceTables.length" class="source-loading">{{ loading ? '正在连接共享数据库…' : '当前账号没有可接入的业务表' }}</div></div><div v-if="preview" class="preview-card"><div class="preview-toolbar"><div class="preview-file"><span class="file-badge"><FileSpreadsheet v-if="preview.filename.toLowerCase().endsWith('.csv')" :size="16" /><Database v-else :size="16" /></span><div><strong>{{ preview.filename }}</strong><span>{{ preview.row_count.toLocaleString() }} 条记录 · 前 100 条可编辑预览</span></div></div><button class="icon-button" title="移除预览" @click="preview = null; previewRows = []; selectedSource = null"><X :size="17" /></button></div><div class="import-settings"><label class="field-label">数据集名称<input v-model="importName" maxlength="120" /></label><label class="field-label">目标表名<input v-model="importTable" maxlength="60" placeholder="dp_sales" /></label></div><div class="column-editor"><div class="table-toolbar"><div><span class="section-kicker">FIELD MAPPING</span><strong>字段整理</strong><small>修改表头、字段名、类型，或取消不需导入的字段</small></div><span class="selected-count">{{ preview.columns.filter((column) => column.included).length }} / {{ preview.columns.length }} 字段</span></div><div class="table-scroll"><table class="mapping-table"><thead><tr><th>导入</th><th>原始字段</th><th>目标字段名</th><th>字段类型</th></tr></thead><tbody><tr v-for="column in preview.columns" :key="column.source"><td><input v-model="column.included" class="check-input" type="checkbox" /></td><td><span class="source-field">{{ column.source }}</span></td><td><input class="mapping-input" v-model="column.name" /></td><td><select v-model="column.type" class="type-select"><option value="text">文本</option><option value="integer">整数</option><option value="number">数值</option><option value="boolean">布尔</option></select></td></tr></tbody></table></div></div><div class="table-toolbar row-preview-title"><div><span class="section-kicker">ROW PREVIEW</span><strong>数据预览</strong><small>可直接修正预览行中的单元格内容</small></div><span class="preview-limit">{{ Math.min(previewRows.length, 100) }} / {{ preview.row_count }} 行</span></div><div class="table-scroll data-preview-scroll"><table class="data-preview-table"><thead><tr><th v-for="column in preview.columns.filter((item) => item.included)" :key="column.source">{{ column.name }}</th></tr></thead><tbody><tr v-for="(row, rowIndex) in previewRows.slice(0, 100)" :key="rowIndex"><td v-for="column in preview.columns.filter((item) => item.included)" :key="column.source"><input :value="String(row[column.source || column.name] ?? '')" @input="updatePreviewCell(rowIndex, column.source || column.name, ($event.target as HTMLInputElement).value)" /></td></tr></tbody></table></div><div class="import-footer"><span><ShieldCheck :size="15" />导入将创建新的 dp_ 表，不会覆盖源数据</span><button class="button primary" :disabled="importBusy" @click="doImport"><LoaderCircle v-if="importBusy" class="spin" :size="16" /><ArrowDownToLine v-else :size="16" />{{ importBusy ? '正在导入' : '确认并导入' }}</button></div></div></div><aside class="ingest-aside"><div class="aside-card source-note"><div class="aside-icon"><ShieldCheck :size="17" /></div><span class="section-kicker">SAFE BY DEFAULT</span><h3>源数据只读</h3><p>原始业务表只提供预览和导入。数据中台会将选中的行写入独立数据表，不改变源表结构或内容。</p><div class="aside-divider"></div><div class="source-stat"><span>可访问数据表</span><strong>{{ sourceTables.length }} <small>张</small></strong></div><div class="source-stat"><span>当前账号可见记录</span><strong>{{ totalSourceRows.toLocaleString() }} <small>条</small></strong></div></div><div class="aside-card format-note"><span class="section-kicker">IMPORT GUIDE</span><h3>文件导入说明</h3><div class="format-row"><FileSpreadsheet :size="15" /><div><strong>CSV</strong><span>第一行作为表头，文本编码为 UTF-8</span></div></div><div class="format-row"><FileJson2 :size="15" /><div><strong>JSON</strong><span>支持对象数组，或包含 data / rows 数组</span></div></div><div class="format-hint">建议导入前检查字段类型与字段名。单次最多导入 5,000 行。</div></div></aside></div></section>

      <section v-else class="analysis-page"><aside class="analysis-rail"><div class="rail-heading"><div><span class="section-kicker">DATASETS</span><h2>分析空间</h2></div><button class="icon-button" title="导入数据" @click="view = 'ingest'"><Plus :size="16" /></button></div><div class="rail-search"><Search :size="15" /><input v-model="query" placeholder="查找数据集" /></div><div class="rail-dataset-list"><button v-for="dataset in filteredDatasets" :key="dataset.id" class="rail-dataset" :class="{ active: activeDataset?.id === dataset.id }" @click="loadDataset(dataset)"><span class="rail-table-icon"><Table2 :size="15" /></span><span><strong>{{ dataset.name }}</strong><small>{{ dataset.columns.length }} 个字段 · {{ dataset.table_name }}</small></span><ArrowRight :size="14" class="rail-arrow" /></button><div v-if="!filteredDatasets.length" class="rail-empty"><Database :size="22" /><strong>{{ datasets.length ? '没有匹配的数据集' : '还没有数据集' }}</strong><span>先接入一份 CSV、JSON 或业务表</span><button class="button secondary small" @click="view = 'ingest'"><Plus :size="14" />接入数据</button></div></div></aside><div v-if="activeDataset" class="analysis-workspace"><div class="analysis-titlebar"><div><div class="eyebrow">ANALYSIS / DATASET</div><h1>{{ activeDataset.name }}<span class="table-tag"><Table2 :size="13" />{{ activeDataset.table_name }}</span></h1></div><div class="analysis-actions"><span class="row-count"><span class="status-dot"></span>{{ dataTotal.toLocaleString() }} 条记录</span><button class="button secondary compact" title="导出为 JSON" @click="saveDataset"><ArrowDownToLine :size="14" />导出</button><button class="icon-button danger-icon" title="删除数据集" @click="removeDataset"><Trash2 :size="15" /></button><button class="button secondary compact" @click="settingsOpen = !settingsOpen"><Settings2 :size="15" />模型</button></div></div><div class="analysis-body"><section class="data-inspector"><div class="inspector-head"><div><span class="section-kicker">TABLE PREVIEW</span><strong>数据预览</strong><small>显示第 {{ dataTotal ? ((rowPage - 1) * rowPageSize + 1) : 0 }}–{{ Math.min(rowPage * rowPageSize, dataTotal) }} 条，共 {{ dataTotal }} 条</small></div><button class="button primary compact" @click="openNewRow"><Plus :size="14" />新增记录</button></div><div class="data-toolbar"><label class="row-search"><Search :size="14" /><input v-model="rowSearch" placeholder="搜索当前数据集" @keydown.enter="searchRows" /><button v-if="rowSearch" class="icon-button" title="清空搜索" @click="rowSearch = ''; searchRows()"><X :size="13" /></button></label><button class="button secondary compact" @click="searchRows"><Search :size="13" />查询</button><select v-model.number="rowPageSize" class="page-size" aria-label="每页行数" @change="rowPage = 1; loadDataset(activeDataset)"><option :value="10">10 条/页</option><option :value="20">20 条/页</option><option :value="50">50 条/页</option></select></div><div class="schema-strip"><span v-for="column in activeDataset.columns" :key="column.name" class="schema-pill"><span class="type-dot" :class="column.type"></span>{{ column.name }}<small>{{ column.type }}</small></span></div><div class="table-scroll inspector-table"><table><thead><tr><th class="index-cell">#</th><th v-for="column in rowColumns" :key="column.name">{{ column.name }}<small>{{ column.type }}</small></th><th class="row-actions-head">操作</th></tr></thead><tbody><tr v-for="(row, index) in dataRows" :key="row.__row_id"><td class="index-cell">{{ String((rowPage - 1) * rowPageSize + index + 1).padStart(2, '0') }}</td><td v-for="column in rowColumns" :key="column.name" :title="String(row[column.name] ?? '')">{{ row[column.name] ?? '—' }}</td><td class="row-actions"><button class="icon-button" title="编辑记录" @click="openEditRow(row)"><Settings2 :size="14" /></button><button class="icon-button danger-icon" title="删除记录" @click="removeRow(row)"><Trash2 :size="14" /></button></td></tr><tr v-if="!dataRows.length"><td :colspan="rowColumns.length + 2" class="table-empty">{{ rowSearch ? '没有匹配的记录' : '数据表为空' }}</td></tr></tbody></table></div><div class="row-pagination"><span>共 {{ dataTotal }} 条记录 · 第 {{ rowPage }} / {{ Math.max(1, Math.ceil(dataTotal / rowPageSize)) }} 页</span><div><button class="button secondary compact" :disabled="rowPage <= 1" @click="changeRowPage(rowPage - 1)">上一页</button><button class="button secondary compact" :disabled="rowPage >= Math.ceil(dataTotal / rowPageSize)" @click="changeRowPage(rowPage + 1)">下一页</button></div></div></section><section class="chat-panel"><div class="chat-header"><div class="chat-title-icon"><Sparkles :size="17" /></div><div><strong>数据分析助手</strong><span><i></i>{{ provider === 'demo' ? '演示模式 · 使用真实数据统计' : 'AI 模型已连接' }}</span></div><button class="icon-button chat-menu" title="模型设置" @click="settingsOpen = !settingsOpen"><Settings2 :size="16" /></button></div><div class="chat-context"><div class="context-label"><Database :size="14" />当前数据上下文</div><div class="context-name">{{ activeDataset.name }}</div><div class="context-meta">{{ dataTotal.toLocaleString() }} 行 <span>·</span> {{ activeDataset.columns.length }} 个字段</div><div class="context-columns"><span v-for="column in activeDataset.columns.slice(0, 5)" :key="column.name">{{ column.name }}</span><span v-if="activeDataset.columns.length > 5">+{{ activeDataset.columns.length - 5 }}</span></div></div><div ref="chatStream" class="chat-stream"><div v-if="!chatMessages.length" class="chat-welcome"><div class="welcome-spark"><Sparkles :size="20" /></div><span class="section-kicker">ASK YOUR DATA</span><h3>你想了解什么？</h3><p>我已准备好分析 <strong>{{ activeDataset.name }}</strong>。试试下面的问题，或直接输入你关心的内容。</p><div class="prompt-suggestions"><button @click="chatInput = '总结这份数据的主要特征与数值分布'"><BarChart3 :size="14" />总结数据特征</button><button @click="chatInput = '检查数据中是否有缺失值或异常值'"><Search :size="14" />检查缺失与异常</button></div></div><article v-for="(message, index) in chatMessages" :key="index" class="chat-message" :class="message.role"><div class="message-avatar">{{ message.role === 'user' ? user.username.slice(0, 1).toUpperCase() : '✳' }}</div><div class="message-content"><span class="message-author">{{ message.role === 'user' ? '你' : '数据分析助手' }}</span><div class="message-bubble" :class="{ markdownish: message.role === 'assistant' }">{{ message.content }}</div></div></article><div v-if="busy" class="chat-message assistant"><div class="message-avatar">✳</div><div class="thinking"><i></i><i></i><i></i></div></div></div><div class="chat-composer"><textarea v-model="chatInput" rows="2" placeholder="提问关于当前数据集的问题…" @keydown.enter.exact.prevent="sendMessage"></textarea><div class="composer-footer"><span><Sparkles :size="13" />答案基于当前数据集内容生成</span><button class="send-button" :disabled="!chatInput.trim() || busy" title="发送消息" @click="sendMessage"><LoaderCircle v-if="busy" class="spin" :size="16" /><Send v-else :size="16" /></button></div></div></section></div></div><div v-else class="analysis-empty"><div class="empty-art large"><div class="empty-grid"><i v-for="n in 9" :key="n"></i></div><span><MessageSquareText :size="22" /></span></div><span class="section-kicker">ANALYSIS WORKSPACE</span><h2>让数据回答问题</h2><p>从左侧选择一个数据集，查看表格并开始分析对话。</p><button class="button primary" @click="view = 'ingest'"><Plus :size="16" />接入第一份数据</button></div></section>
      <div v-if="rowEditorOpen" class="modal-backdrop" @click.self="rowEditorOpen = false"><form class="row-editor-modal" @submit.prevent="saveRow"><div class="modal-heading"><div><span class="section-kicker">DATA RECORD</span><h2>{{ editingRowId === null ? '新增记录' : '编辑记录' }}</h2></div><button class="icon-button" type="button" @click="rowEditorOpen = false"><X :size="16" /></button></div><div class="row-editor-fields"><label v-for="column in activeDataset?.columns || []" :key="column.name" class="field-label">{{ column.name }}<textarea v-if="column.type === 'text' && String(rowDraft[column.name] || '').length > 80" :value="String(rowDraft[column.name] ?? '')" @input="rowDraft[column.name] = ($event.target as HTMLTextAreaElement).value" rows="4"></textarea><input v-else :value="String(rowDraft[column.name] ?? '')" @input="rowDraft[column.name] = ($event.target as HTMLInputElement).value" :type="column.type === 'integer' || column.type === 'number' ? 'number' : 'text'" :step="column.type === 'number' ? 'any' : undefined" /></label></div><div class="modal-footer"><button class="button secondary" type="button" @click="rowEditorOpen = false">取消</button><button class="button primary" type="submit" :disabled="rowBusy"><LoaderCircle v-if="rowBusy" class="spin" :size="14" />保存记录</button></div></form></div>
    </section>
  </div>
</template>
