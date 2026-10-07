import { defineComponent, h, markRaw, type Component } from 'vue'
import type { RecordEntityConfig } from '@modoor/hooks'
import RecordEntity from './RecordEntity.vue'

/** Wrap RecordEntity+config as a drawer body component for registerRecordView. */
export function defineRecordEntityView(config: RecordEntityConfig): Component {
  return markRaw(
    defineComponent({
      name: 'RecordEntityView',
      props: {
        model: { type: String, required: true },
        uukey: { type: String, default: '' },
        lookup: { type: Object, default: undefined },
        title: { type: String, default: '' },
      },
      emits: ['close', 'action'],
      setup(props, { emit }) {
        return () =>
          h(RecordEntity, {
            model: props.model,
            uukey: props.uukey || undefined,
            lookup: props.lookup as Record<string, unknown> | undefined,
            title: props.title || undefined,
            config,
            onClose: () => emit('close'),
            onAction: (payload: unknown) => emit('action', payload),
          })
      },
    }),
  )
}
