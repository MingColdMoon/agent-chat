<script setup lang="ts">
import {
  Box,
  CircuitBoard,
  Cpu,
  Fan,
  HardDrive,
  MemoryStick,
  MonitorCog,
  Zap,
} from 'lucide-vue-next'
import type { PcBuildComponent, PcBuildPlan } from '../types'

defineProps<{
  plan: PcBuildPlan
}>()

const iconMap = {
  CPU: Cpu,
  显卡: MonitorCog,
  主板: CircuitBoard,
  内存: MemoryStick,
  固态硬盘: HardDrive,
  电源: Zap,
  散热器: Fan,
  机箱: Box,
}

function componentIcon(component: PcBuildComponent) {
  return iconMap[component.category as keyof typeof iconMap] || Cpu
}

function currency(value: number) {
  return `¥${value.toLocaleString('zh-CN')}`
}
</script>

<template>
  <section class="pc-build-card">
    <header class="pc-build-head">
      <div>
        <span class="pc-build-kicker">AG-UI ACTIVITY · PC BUILD</span>
        <h3>{{ plan.title }}</h3>
      </div>
      <div class="pc-build-total">
        <span>预估总价</span>
        <strong>{{ currency(plan.total_price) }}</strong>
      </div>
    </header>

    <div class="pc-build-summary">
      <span>预算 {{ currency(plan.budget) }}</span>
      <span>用途 {{ plan.use_case }}</span>
      <span v-if="plan.priorities.length">
        偏好 {{ plan.priorities.join(' / ') }}
      </span>
    </div>

    <div class="pc-component-list">
      <div
        v-for="component in plan.components"
        :key="component.category"
        class="pc-component"
      >
        <span class="pc-component-icon">
          <component :is="componentIcon(component)" :size="17" />
        </span>
        <div>
          <span>{{ component.category }}</span>
          <strong>{{ component.name }}</strong>
          <small>{{ component.reason }}</small>
        </div>
        <b>{{ currency(component.price) }}</b>
      </div>
    </div>

    <div class="pc-build-notes">
      <div>
        <strong>兼容性提醒</strong>
        <ul>
          <li v-for="note in plan.compatibility_notes" :key="note">
            {{ note }}
          </li>
        </ul>
      </div>
      <div>
        <strong>升级路径</strong>
        <p>{{ plan.upgrade_path }}</p>
      </div>
    </div>

    <footer class="pc-build-footer">{{ plan.price_basis }}</footer>
  </section>
</template>

