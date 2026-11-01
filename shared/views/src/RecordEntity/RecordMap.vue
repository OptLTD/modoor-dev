<script setup lang="ts">
/**
 * Map tab body: renders the LOCATION value as a marker map.
 *
 * Coordinates come from the `display|lat,lng|address` wire format; the image
 * itself is proxied by `/api/map/static`, so provider keys stay on the server.
 */
import { computed, ref, watch } from 'vue'
import { parseLocationValue, staticMapUrl, useI18n } from '@modoor/hooks'

const props = withDefaults(defineProps<{ value?: string }>(), { value: '' })

const { t } = useI18n()
const failed = ref(false)

const location = computed(() => parseLocationValue(props.value))
const coords = computed(() => {
  const { lat, lng } = location.value
  return typeof lat === 'number' && typeof lng === 'number' ? { lat, lng } : null
})
const address = computed(
  () => location.value.address || location.value.display || '',
)
const src = computed(() =>
  coords.value
    ? staticMapUrl(coords.value.lat, coords.value.lng, {
        zoom: 16,
        width: 640,
        height: 360,
      })
    : '',
)

watch(src, () => {
  failed.value = false
})
</script>

<template>
  <div class="record-map">
    <p v-if="!coords" class="record-map-state">{{ t('widget.mapNoLocation') }}</p>
    <template v-else>
      <div class="record-map-frame">
        <img
          v-if="!failed"
          :src="src"
          :alt="address"
          loading="lazy"
          @error="failed = true"
        />
        <p v-else class="record-map-state">{{ t('widget.mapLoadFailed') }}</p>
      </div>
      <div class="record-map-meta">
        <span v-if="address" class="record-map-address" :title="address">
          {{ address }}
        </span>
        <span class="record-map-coords">
          {{ coords.lat.toFixed(6) }}, {{ coords.lng.toFixed(6) }}
        </span>
      </div>
    </template>
  </div>
</template>

<style scoped>
.record-map {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.record-map-frame {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  aspect-ratio: 16 / 9;
  overflow: hidden;
  border: 1px solid var(--line, #e2e6eb);
  border-radius: var(--radius-lg, 8px);
  background: color-mix(in srgb, var(--panel, #fff) 92%, var(--ink, #1c1914));
}
.record-map-frame img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.record-map-state {
  margin: 0;
  padding: 20px 16px;
  font-size: 0.82rem;
  line-height: 1.5;
  color: var(--muted, #6b6458);
  text-align: center;
}
.record-map-meta {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
}
.record-map-address {
  min-width: 0;
  overflow: hidden;
  font-size: 0.86rem;
  line-height: 1.5;
  color: var(--ink, #1c1914);
  text-overflow: ellipsis;
  white-space: nowrap;
}
.record-map-coords {
  flex-shrink: 0;
  font-size: 0.76rem;
  line-height: 1.5;
  color: var(--muted, #6b6458);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.record-map-coords-label {
  margin-right: 4px;
}
</style>
