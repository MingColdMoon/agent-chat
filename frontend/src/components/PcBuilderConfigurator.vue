<script setup lang="ts">
import { computed, reactive } from 'vue'
import {
  BrainCircuit,
  BriefcaseBusiness,
  Cable,
  Check,
  Gamepad2,
  Palette,
  Scale,
  Sparkles,
  Volume2,
} from 'lucide-vue-next'

const props = defineProps<{
  disabled: boolean
}>()

const emit = defineEmits<{
  submit: [prompt: string]
}>()

const config = reactive({
  budget: 8000,
  useCase: 'gaming',
  priorities: ['静音'] as string[],
})

const useCases = [
  { id: 'gaming', label: '游戏', icon: Gamepad2 },
  { id: 'productivity', label: '生产力', icon: BriefcaseBusiness },
  { id: 'ai', label: 'AI 开发', icon: BrainCircuit },
  { id: 'balanced', label: '均衡', icon: Scale },
]

const priorities = [
  { id: '静音', icon: Volume2 },
  { id: '外观', icon: Palette },
  { id: '扩展性', icon: Cable },
  { id: '性价比', icon: Sparkles },
]

const budgetLabel = computed(() =>
  `¥${config.budget.toLocaleString('zh-CN')}`,
)

function togglePriority(value: string) {
  config.priorities = config.priorities.includes(value)
    ? config.priorities.filter((item) => item !== value)
    : [...config.priorities, value]
}

function submit() {
  if (props.disabled) return
  const useCase =
    useCases.find((item) => item.id === config.useCase)?.label || '均衡'
  const wants = config.priorities.length
    ? config.priorities.join('、')
    : '性价比'
  emit(
    'submit',
    `预算：${config.budget} 元；用途：${useCase}；偏好：${wants}。请生成装机方案。`,
  )
}
</script>

<template>
  <div class="pc-configurator">
    <div class="pc-configurator-head">
      <div>
        <span>BUILD CONFIGURATOR</span>
        <h3>配置你的下一台电脑</h3>
      </div>
      <output>{{ budgetLabel }}</output>
    </div>

    <label class="budget-control">
      <span>预算</span>
      <input
        v-model.number="config.budget"
        type="range"
        min="4000"
        max="20000"
        step="500"
      />
      <div class="budget-scale">
        <span>¥4,000</span>
        <span>¥20,000</span>
      </div>
    </label>

    <div class="pc-config-row">
      <span>主要用途</span>
      <div class="pc-use-cases">
        <button
          v-for="item in useCases"
          :key="item.id"
          type="button"
          :class="{ active: config.useCase === item.id }"
          @click="config.useCase = item.id"
        >
          <component :is="item.icon" :size="16" />
          {{ item.label }}
        </button>
      </div>
    </div>

    <div class="pc-config-row">
      <span>额外偏好</span>
      <div class="pc-priorities">
        <button
          v-for="item in priorities"
          :key="item.id"
          type="button"
          :class="{ active: config.priorities.includes(item.id) }"
          @click="togglePriority(item.id)"
        >
          <component :is="item.icon" :size="14" />
          {{ item.id }}
          <Check v-if="config.priorities.includes(item.id)" :size="12" />
        </button>
      </div>
    </div>

    <button
      class="pc-build-submit"
      type="button"
      :disabled="disabled"
      @click="submit"
    >
      <Sparkles :size="16" />
      {{ disabled ? '正在生成方案' : '生成装机方案' }}
    </button>
  </div>
</template>

