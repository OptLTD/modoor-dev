import { computed, reactive, ref, watch } from 'vue'
import {
  appToast,
  autofillRecord,
  buildDependsTriggers,
  fetchInputSchema,
  loadDropdownRefers,
  rowToUpsertPayload,
  shouldSyncAutofillColumn,
  upsertRecords,
  type SchemaField,
  type SchemaGroup,
} from '@modoor/hooks'
import {
  formVisibleFields,
  isEmptyValue,
  isFieldEditable,
  isMultiple,
  isOnlyDate,
  isOnlyMonth,
  isRequired,
  normalizeReferDict,
  type FormMode,
  type ReferDict,
} from '@modoor/hooks'
import {
  assignFieldPayload,
  dateTimeKindFromExtra,
  fieldKey,
  formFieldDefault,
  formatDateInputValue,
  formatDateTimeInputValue,
  formatMonthInputValue,
  injectRowIdentity,
  normalizeDateTimeStoreValue,
  rowUUKey,
  t,
} from '@modoor/hooks'
import {
  fieldSelectOptions,
  isDateField,
  isFullRowField,
  isNumericFormField,
  isOptionalField,
  isRelationField,
  isSerialField,
  isTextareaField,
} from '@modoor/widget/SchemaForm'

const FORM_AUTOFILL_DEBOUNCE_MS = 280

export type RecordDialogProps = {
  open: boolean
  model: string
  using?: string
  fields?: SchemaField[]
  mode: FormMode
  row?: Record<string, unknown> | null
  /** 为 true 时校验后只回传 payload，不写库 */
  defer?: boolean
  title?: string
}

export type RecordDialogEmit = {
  (e: 'close'): void
  (e: 'saved'): void
  (e: 'apply', payload: Record<string, unknown>): void
}

export function useRecordDialog(props: RecordDialogProps, emit: RecordDialogEmit) {
  const saving = ref(false)
  const error = ref('')
  const form = reactive<Record<string, string | string[]>>({})
  const inputFields = ref<SchemaField[] | null>(null)
  const inputGroups = ref<SchemaGroup[]>([])
  const inputValues = ref<Record<string, unknown> | null>(null)
  const inputRefers = ref<ReferDict>({})
  const groupRows = reactive<Record<string, Record<string, string>[]>>({})
  const groupOriginals = ref<Record<string, Record<string, unknown>[]>>({})

  const using = computed(() => props.using || 'default')

  const visibleFields = computed(() =>
    formVisibleFields(inputFields.value?.length ? inputFields.value : props.fields || []),
  )

  function groupRepeats(g: SchemaGroup) {
    const v = g.extra?.multiple
    return v === true || v === 1 || v === '1' || String(v).toLowerCase() === 'true'
  }

  const repeatGroups = computed(() =>
    inputGroups.value
      .filter(groupRepeats)
      .map((g) => ({
        uukey: g.uukey,
        title: g.title || g.uukey,
        fields: visibleFields.value.filter((f) => f.group === g.uukey),
      }))
      .filter((g) => g.fields.length),
  )

  const formFields = computed(() => {
    const repeated = new Set(repeatGroups.value.map((g) => g.uukey))
    return visibleFields.value.filter((f) => !repeated.has(f.group))
  })

  function canEdit(f: SchemaField) {
    return isFieldEditable(f, props.mode)
  }

  function optionsOf(f: SchemaField) {
    const parentField = String(f.extra?.parentField || '').trim()
    const parentValue = parentField ? String(form[parentField] ?? '') : ''
    return fieldSelectOptions(f, inputRefers.value, parentValue)
  }

  function resetForm() {
    error.value = ''
    const source =
      props.mode === 'modify'
        ? { ...(props.row || {}), ...(inputValues.value || {}) }
        : inputValues.value
    for (const f of formFields.value) {
      const fk = fieldKey(f)
      form[fk] = formFieldDefault(source, f)
    }
    if (props.mode === 'create' && props.row) {
      for (const f of formFields.value) {
        const fk = fieldKey(f)
        const raw = props.row[fk] ?? props.row[`basic.${f.field}`]
        if (raw != null && String(raw).trim()) {
          form[fk] = String(raw)
        }
      }
    }
    const alive = new Set(repeatGroups.value.map((g) => g.uukey))
    for (const key of Object.keys(groupRows)) {
      if (!alive.has(key)) delete groupRows[key]
    }
    for (const g of repeatGroups.value) {
      const raw = source?.[g.uukey]
      const list = Array.isArray(raw)
        ? raw.filter((item) => item && typeof item === 'object' && !Array.isArray(item))
        : []
      const items = list as Record<string, unknown>[]
      groupOriginals.value[g.uukey] = items.map((item) => ({ ...item }))
      groupRows[g.uukey] = items.map((item) => {
        const row: Record<string, string> = {}
        for (const f of g.fields) {
          const v = item[f.field] ?? item[fieldKey(f)]
          row[f.field] = cellText(f, v)
        }
        return row
      })
    }
  }

  function cellText(f: SchemaField, raw: unknown): string {
    if (raw == null || raw === '') return ''
    if (String(f.ftype).toUpperCase() === 'DATETIME' && !Array.isArray(raw)) {
      const kind = dateTimeKindFromExtra(f.extra)
      if (kind === 'ONLYMONTH') return formatMonthInputValue(raw)
      if (kind === 'ONLYDATE') return formatDateInputValue(raw)
      return formatDateTimeInputValue(raw)
    }
    return Array.isArray(raw) ? raw.map(String).join(',') : String(raw)
  }

  async function loadInputFields() {
    try {
      const scene = props.mode === 'create' ? 'INSERT' : 'DETAIL'
      const uukey = props.mode === 'modify' ? rowUUKey(props.row) : undefined
      const res = await fetchInputSchema(props.model, using.value, scene, uukey)
      inputFields.value = res.input?.fields || []
      inputGroups.value = res.input?.groups || []
      inputValues.value = res.input?.values ?? null
      inputRefers.value = await loadDropdownRefers(
        inputFields.value,
        normalizeReferDict(res.input?.refers),
      )
    } catch (e) {
      inputFields.value = props.fields?.length ? props.fields : null
      inputGroups.value = []
      inputValues.value = null
      inputRefers.value = {}
      if (!inputFields.value?.length) {
        error.value = e instanceof Error ? e.message : String(e)
      }
    }
  }

  function validate(): string | null {
    for (const f of formFields.value) {
      if (!isRequired(f)) continue
      if (isEmptyValue(form[fieldKey(f)])) {
        if (props.mode === 'create' && isSerialField(f)) continue
        return t('widget.fillRequired', { label: f.label || f.field })
      }
    }
    return null
  }

  function formRowStrings(): Record<string, string> {
    const row: Record<string, string> = {}
    for (const f of formFields.value) {
      const fk = fieldKey(f)
      const raw = form[fk]
      row[fk] = Array.isArray(raw) ? raw.join(',') : String(raw ?? '')
    }
    if (props.mode === 'modify') {
      const uk = rowUUKey(props.row)
      if (uk) row.uukey = uk
    }
    return row
  }

  let formWatchReady = false
  let autofillApplying = false
  let autofillTimer: ReturnType<typeof setTimeout> | null = null
  let pendingTrigger = ''

  async function runFormAutofill(triggerUukey: string) {
    const fields = formFields.value
    const payload = rowToUpsertPayload(formRowStrings(), fields)
    try {
      const resp = await autofillRecord(props.model, payload, using.value)
      const flat = resp.data || {}
      autofillApplying = true
      try {
        for (const f of fields) {
          if (!shouldSyncAutofillColumn(f, triggerUukey)) continue
          const uk = fieldKey(f)
          const raw = flat[uk] ?? flat[f.uukey]
          form[uk] = raw == null ? '' : String(raw)
        }
      } finally {
        queueMicrotask(() => {
          autofillApplying = false
        })
      }
    } catch {
      /* 公式重算失败不打断编辑 */
    }
  }

  async function save() {
    const msg = validate()
    if (msg) {
      error.value = msg
      return
    }
    saving.value = true
    error.value = ''
    try {
      const payload: Record<string, unknown> = {}
      for (const f of formFields.value) {
        const fk = fieldKey(f)
        const raw = form[fk] ?? (isMultiple(f) ? [] : '')
        if (!canEdit(f)) {
          if (props.mode === 'modify') assignFieldPayload(payload, f, raw)
          continue
        }
        assignFieldPayload(payload, f, raw)
      }
      if (props.mode === 'create') {
        // Merge presets / parent defaults (e.g. install → basic.tire) not shown on form
        for (const src of [inputValues.value, props.row]) {
          if (!src) continue
          for (const [k, v] of Object.entries(src)) {
            if (v == null || v === '') continue
            if (payload[k] == null || payload[k] === '') payload[k] = v
          }
        }
      }
      if (props.mode === 'modify') {
        injectRowIdentity(payload, props.row)
      }
      for (const g of repeatGroups.value) {
        const originals = groupOriginals.value[g.uukey] || []
        const rows = groupRows[g.uukey] || []
        payload[g.uukey] = rows
          .map((row, index) => {
            const item: Record<string, unknown> = { ...(originals[index] || {}) }
            let filled = Object.keys(originals[index] || {}).length > 0
            for (const f of g.fields) {
              let value = String(row[f.field] ?? '').trim()
              if (String(f.ftype).toUpperCase() === 'DATETIME' && value) {
                value = normalizeDateTimeStoreValue(value, dateTimeKindFromExtra(f.extra))
              }
              if (value) {
                item[f.field] = value
                filled = true
              } else {
                delete item[f.field]
              }
            }
            return filled ? item : null
          })
          .filter((item) => item != null)
      }

      if (props.defer) {
        emit('apply', payload)
        emit('close')
        return
      }

      await upsertRecords(props.model, [payload], using.value)
      emit('saved')
      emit('close')
    } catch (e: unknown) {
      appToast(e instanceof Error ? e.message : String(e), 'error')
    } finally {
      saving.value = false
    }
  }

  watch(
    () => [props.open, props.mode, props.model, props.using, rowUUKey(props.row)] as const,
    async ([open]) => {
      if (!open) {
        formWatchReady = false
        return
      }
      await loadInputFields()
      resetForm()
      formWatchReady = false
    },
    { immediate: true },
  )

  watch(
    () => ({ ...form }),
    (next, prev) => {
      if (!props.open || autofillApplying) return
      if (!formWatchReady) {
        formWatchReady = true
        return
      }
      const fields = formFields.value
      // 级联：父字段变更时清空依赖它的子 OPTIONAL
      for (const f of fields) {
        const pf = String(f.extra?.parentField || '').trim()
        if (!pf) continue
        const a = next?.[pf]
        const b = prev?.[pf]
        if (
          String(Array.isArray(a) ? a.join(',') : (a ?? '')) !==
          String(Array.isArray(b) ? b.join(',') : (b ?? ''))
        ) {
          const ck = fieldKey(f)
          if (!isEmptyValue(form[ck])) form[ck] = isMultiple(f) ? [] : ''
        }
      }
      const triggers = buildDependsTriggers(fields)
      let trigger = ''
      for (const f of fields) {
        const fk = fieldKey(f)
        const a = next?.[fk]
        const b = prev?.[fk]
        if (
          String(Array.isArray(a) ? a.join(',') : (a ?? '')) ===
          String(Array.isArray(b) ? b.join(',') : (b ?? ''))
        ) {
          continue
        }
        if (triggers.includes(fk)) {
          trigger = fk
          break
        }
      }
      if (!trigger) return
      pendingTrigger = trigger
      if (autofillTimer != null) clearTimeout(autofillTimer)
      autofillTimer = setTimeout(() => {
        autofillTimer = null
        void runFormAutofill(pendingTrigger)
      }, FORM_AUTOFILL_DEBOUNCE_MS)
    },
    { deep: true },
  )

  return {
    saving,
    error,
    form,
    formFields,
    repeatGroups,
    groupRows,
    canEdit,
    optionsOf,
    save,
    fieldKey,
    isRequired,
    isMultiple,
    isOnlyDate,
    isOnlyMonth,
    isRelation: isRelationField,
    isOptional: isOptionalField,
    isNumeric: isNumericFormField,
    isDate: isDateField,
    isSerial: isSerialField,
    isTextarea: isTextareaField,
    isFullRow: isFullRowField,
    inputRefers,
  }
}
