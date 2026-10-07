<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { FormMode, SchemaField } from '@modoor/hooks'
import { entityLabel, resolveModelTitle, useI18n } from '@modoor/hooks'
import SchemaForm from '@modoor/widget/SchemaForm'
import { useRecordDialog } from './useRecordDialog'

const props = defineProps<{
  open: boolean
  model: string
  using?: string
  fields?: SchemaField[]
  mode: FormMode
  row?: Record<string, unknown> | null
  defer?: boolean
  /** Optional modal title; defaults to 新建/修改 + entity name. */
  title?: string
}>()

const emit = defineEmits<{
  close: []
  saved: []
  apply: [Record<string, unknown>]
}>()

const { t } = useI18n()
const modelTitle = ref('')

watch(
  () => [props.open, props.model, props.title] as const,
  async ([open, model, title]) => {
    if (!open || title) {
      modelTitle.value = ''
      return
    }
    modelTitle.value = await resolveModelTitle(model)
  },
  { immediate: true },
)

const heading = computed(() => {
  if (props.title) return props.title
  const name = entityLabel(modelTitle.value)
  if (name) {
    return props.mode === 'create'
      ? t('widget.formCreateNamed', { name })
      : t('widget.formEditNamed', { name })
  }
  return props.mode === 'create' ? t('widget.formCreate') : t('widget.formEdit')
})

const { saving, error, form, formFields, repeatGroups, groupRows, canEdit, save, inputRefers } =
  useRecordDialog(props, emit)
</script>

<template>
  <div v-if="open" class="modal-mask" @click.self="emit('close')">
    <div class="modal form-modal" :class="{ wide: repeatGroups.length }">
      <header class="modal-head">
        <strong>{{ heading }}</strong>
        <button type="button" class="link" @click="emit('close')">{{ t('widget.close') }}</button>
      </header>

      <div class="form-modal-body">
        <p v-if="error" class="error">{{ error }}</p>
        <SchemaForm
          :fields="formFields"
          :form="form"
          :mode="mode"
          :refers="inputRefers"
          :can-edit="canEdit"
          :repeat-groups="repeatGroups"
          :group-rows="groupRows"
        />
      </div>

      <div class="modal-actions pad-actions">
        <button type="button" class="btn" @click="emit('close')">{{ t('widget.cancel') }}</button>
        <button type="button" class="btn primary" :disabled="saving" @click="save">
          {{ saving ? t('widget.saving') : defer ? t('widget.applyDefer') : t('widget.save') }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.form-modal {
  width: min(720px, 100%);
  display: flex;
  flex-direction: column;
  max-height: 85vh;
}
.form-modal.wide {
  width: min(960px, 100%);
}
.form-modal-body {
  padding: 16px 18px;
  overflow: auto;
  min-height: 0;
  flex: 1;
}
.pad-actions {
  padding: 12px 16px;
  border-top: 1px solid var(--line);
}
</style>
