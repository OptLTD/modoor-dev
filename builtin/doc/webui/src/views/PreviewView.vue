<template>
  <section class="detail">
    <PreviewPane v-if="asset" :asset="asset" class="detail-preview" @updated="asset = $event" />
    <p v-else-if="error" class="error">{{ error }}</p>
    <p v-else class="muted loading">{{ t('doc.loading') }}</p>
  </section>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from '@modoor/hooks'
import { getAsset, type DocAsset } from '../api/doc'
import PreviewPane from '../components/PreviewPane.vue'

const { t } = useI18n()
const route = useRoute()
const asset = ref<DocAsset | null>(null)
const error = ref('')
let timer: ReturnType<typeof setInterval> | null = null

function assetId() {
  return decodeURIComponent(String(route.params.id || ''))
}

async function load() {
  const id = assetId()
  error.value = ''
  try {
    const res = await getAsset(id)
    if (assetId() !== id) return
    asset.value = res.asset
  } catch (e) {
    if (assetId() !== id) return
    error.value = e instanceof Error ? e.message : String(e)
    asset.value = null
  }
}

watch(
  () => route.params.id,
  () => {
    asset.value = null
    void load()
  },
)
onMounted(() => {
  void load()
  timer = setInterval(() => {
    const status = asset.value?.text_status
    if (status === 'pending' || status === 'running') void load()
  }, 1500)
})
onUnmounted(() => {
  if (timer != null) clearInterval(timer)
})
</script>

<style scoped>
.detail {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.detail-preview {
  flex: 1;
  min-height: 0;
  min-width: 0;
}

.loading,
.error {
  padding: 24px 8px;
}
</style>
