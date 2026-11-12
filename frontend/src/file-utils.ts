import type { AttachmentSummary } from './types'

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function attachmentKind(
  attachment: Pick<AttachmentSummary, 'extension' | 'content_type'>,
): 'image' | 'pdf' | 'document' | 'code' | 'file' {
  if (attachment.content_type.startsWith('image/')) return 'image'
  if (attachment.extension === '.pdf') return 'pdf'
  if (['.doc', '.docx', '.md', '.markdown', '.txt', '.rtf'].includes(attachment.extension)) {
    return 'document'
  }
  if (
    [
      '.c',
      '.cpp',
      '.css',
      '.go',
      '.h',
      '.html',
      '.java',
      '.js',
      '.jsx',
      '.json',
      '.py',
      '.rs',
      '.sh',
      '.sql',
      '.ts',
      '.tsx',
      '.vue',
      '.xml',
      '.yaml',
      '.yml',
    ].includes(attachment.extension)
  ) {
    return 'code'
  }
  return 'file'
}
