<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

/**
 * Compact adaptation of LeiBox "Dot Grid Loader".
 * Source: https://leibox.pantoria.cn/docs/animations/ai-generating
 * The original loader is a 20 x 20, two-focus animation. This version keeps
 * that visual language while fitting inline agent feedback.
 */
const props = withDefaults(
  defineProps<{
    label?: string
  }>(),
  {
    label: 'Agent 正在工作',
  },
)

const size = 12
const spacing = 5
const dots = Array.from({ length: size * size }, (_, index) => ({
  id: index,
  x: (index % size - size / 2) * spacing + spacing / 2,
  y: (Math.floor(index / size) - size / 2) * spacing + spacing / 2,
  scale: 0.36,
  tone: 72,
}))

const dotState = ref(dots)
let frame = 0
let media: MediaQueryList | null = null

function animate(timestamp: number) {
  const time = timestamp * 0.00115
  const reduced = media?.matches === true
  const focusA = {
    x: Math.sin(time * 0.8) * 24,
    y: Math.cos(time * 1.05) * 20,
  }
  const focusB = {
    x: Math.sin(time * -1.15 + 2) * 20,
    y: Math.cos(time * 0.72 + 1.2) * 27,
  }

  dotState.value = dots.map((dot) => {
    if (reduced) return { ...dot, scale: 0.46, tone: 112 }
    let intensity = 0
    for (const focus of [focusA, focusB]) {
      const dx = focus.x - dot.x
      const dy = focus.y - dot.y
      const distance = Math.sqrt(dx * dx + dy * dy)
      if (distance < 43) {
        intensity += Math.pow(1 - distance / 43, 1.5)
      }
    }
    intensity = Math.min(1, intensity)
    return {
      ...dot,
      scale: 0.36 + intensity * 0.68,
      tone: Math.round(72 + intensity * 158),
    }
  })

  if (!reduced) frame = requestAnimationFrame(animate)
}

onMounted(() => {
  media = window.matchMedia('(prefers-reduced-motion: reduce)')
  frame = requestAnimationFrame(animate)
  media.addEventListener('change', restart)
})

function restart() {
  cancelAnimationFrame(frame)
  frame = requestAnimationFrame(animate)
}

onBeforeUnmount(() => {
  cancelAnimationFrame(frame)
  media?.removeEventListener('change', restart)
})
</script>

<template>
  <div class="leibox-dot-loader" role="status" :aria-label="props.label">
    <div class="leibox-dot-board" aria-hidden="true">
      <span
        v-for="dot in dotState"
        :key="dot.id"
        :style="{
          '--dot-scale': dot.scale,
          '--dot-tone': dot.tone,
        }"
      />
    </div>
    <span>{{ props.label }}</span>
  </div>
</template>

<style scoped>
.leibox-dot-loader {
  display: inline-grid;
  justify-items: start;
  gap: 8px;
  color: var(--ink-faint);
  font-size: 9px;
}

.leibox-dot-board {
  display: grid;
  width: calc(12 * 5px);
  height: calc(12 * 5px);
  grid-template-columns: repeat(12, 5px);
  grid-template-rows: repeat(12, 5px);
  place-items: center;
  overflow: hidden;
}

.leibox-dot-board span {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: rgb(var(--dot-tone) var(--dot-tone) var(--dot-tone));
  transform: scale(var(--dot-scale));
  will-change: transform, background-color;
}
</style>
