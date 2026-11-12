<script setup lang="ts">
import { computed } from 'vue'
import {
  FileCode2,
  FileImage,
  FileText,
  FileType2,
  Paperclip,
  X,
} from 'lucide-vue-next'
import { attachmentKind, formatFileSize } from '../file-utils'
import type { AttachmentSummary } from '../types'

const props = withDefaults(
  defineProps<{
    attachment: AttachmentSummary
    removable?: boolean
    compact?: boolean
  }>(),
  {
    removable: false,
    compact: false,
  },
)

const emit = defineEmits<{
  select: [attachment: AttachmentSummary]
  remove: [attachment: AttachmentSummary]
}>()

const icon = computed(() => {
  const kind = attachmentKind(props.attachment)
  if (kind === 'image') return FileImage
  if (kind === 'code') return FileCode2
  if (kind === 'document') return FileText
  if (kind === 'pdf') return FileType2
  return Paperclip
})
</script>

<template>
  <span class="attachment-chip" :class="{ compact }">
    <button
      class="attachment-chip-main"
      type="button"
      :title="attachment.filename"
      @click="emit('select', attachment)"
    >
      <component :is="icon" :size="compact ? 13 : 15" />
      <span>{{ attachment.filename }}</span>
      <small v-if="!compact">{{ formatFileSize(attachment.size_bytes) }}</small>
    </button>
    <button
      v-if="removable"
      class="attachment-chip-remove"
      type="button"
      :title="`移除 ${attachment.filename}`"
      :aria-label="`移除 ${attachment.filename}`"
      @click.stop="emit('remove', attachment)"
    >
      <X :size="12" />
    </button>
  </span>
</template>

<style scoped>
.attachment-chip {
  display: inline-flex;
  max-width: 100%;
  min-width: 0;
  align-items: center;
  overflow: hidden;
  border: 1px solid var(--line-strong);
  border-radius: 999px;
  background: #151517;
  color: var(--ink-soft);
}

.attachment-chip-main {
  display: flex;
  min-width: 0;
  height: 30px;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
}

.attachment-chip-main:hover {
  color: var(--ink);
}

.attachment-chip-main span {
  max-width: 220px;
  overflow: hidden;
  font-size: 9px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.attachment-chip-main small {
  color: var(--ink-faint);
  font-family: var(--mono);
  font-size: 7px;
  white-space: nowrap;
}

.attachment-chip-remove {
  display: grid;
  width: 26px;
  height: 30px;
  flex: 0 0 auto;
  place-items: center;
  border: 0;
  border-left: 1px solid var(--line);
  background: transparent;
  color: var(--ink-faint);
  cursor: pointer;
}

.attachment-chip-remove:hover {
  background: #271517;
  color: #ff8d89;
}

.attachment-chip.compact .attachment-chip-main {
  height: 25px;
  padding: 0 8px;
}

.attachment-chip.compact .attachment-chip-main span {
  max-width: 160px;
}
</style>
