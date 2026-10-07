import type { SchemaField } from '@modoor/hooks'
import {
  isLongTextField,
  isNumericField,
  referOptions,
  type ReferDict,
} from '@modoor/hooks'

export function isRelationField(f: SchemaField) {
  return String(f.ftype).toUpperCase() === 'RELATION'
}

export function isOptionalField(f: SchemaField) {
  return String(f.ftype).toUpperCase() === 'OPTIONAL'
}

export function isDateField(f: SchemaField) {
  return String(f.ftype).toUpperCase() === 'DATETIME'
}

export function isSerialField(f: SchemaField) {
  return String(f.ftype).toUpperCase() === 'SERIALNO' || f.field === 'uukey'
}

export function isUploadField(f: SchemaField) {
  return String(f.ftype).toUpperCase() === 'UPLOADS'
}

export function uploadAccept(f: SchemaField) {
  const accept = String(f.extra?.acceptType || '').trim()
  if (accept) return accept
  const dt = String(f.extra?.dataType || '').toUpperCase()
  if (dt === 'IMG_FILE') return 'image/*'
  return ''
}

export function isNumericFormField(f: SchemaField) {
  return isNumericField(f)
}

export function isTextareaField(f: SchemaField) {
  return isLongTextField(f) || f.field === 'remark' || f.field === 'note'
}

export function isFullRowField(f: SchemaField) {
  return isTextareaField(f)
}

/** Select 选项：优先 refers，回退 field.options；可按 parentField 过滤 */
export function fieldSelectOptions(
  f: SchemaField,
  refers?: ReferDict,
  parentValue?: string,
): { label: string; value: string }[] {
  const fromRefer = referOptions(f, refers)
  let opts: { label: string; value: string; parent?: string }[]
  if (fromRefer.length) {
    opts = fromRefer
  } else {
    const raw = (f.options || f.extra?.options || []) as {
      label?: string
      value?: string
      uukey?: string
      parent?: string
    }[]
    opts = raw
      .map((o) => {
        const value = String(o.uukey ?? o.value ?? '')
        const label = String(o.label || value)
        return { label, value, parent: String(o.parent || '') }
      })
      .filter((o) => o.value)
  }
  const pv = String(parentValue || '').trim()
  if (pv && opts.some((o) => o.parent)) {
    opts = opts.filter((o) => !o.parent || o.parent === pv)
  }
  return opts.map(({ label, value }) => ({ label, value }))
}
