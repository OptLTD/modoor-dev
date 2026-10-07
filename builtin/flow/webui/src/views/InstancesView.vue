<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getInstance, listInstances, type FlowInstance } from '../api/flow'

const route = useRoute()
const router = useRouter()
const items = ref<FlowInstance[]>([])
const detail = ref<{ instance: FlowInstance; logs: any[]; tasks: any[] } | null>(null)
const error = ref('')

const selectedId = computed(() => String(route.params.id || ''))

async function reload() {
  error.value = ''
  try {
    const res = await listInstances({
      definition_key: String(route.query.key || '') || undefined,
    })
    items.value = res.items || []
    if (selectedId.value) {
      detail.value = await getInstance(selectedId.value)
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

function open(id: string) {
  router.push({ name: 'flow.instance', params: { id } })
}

watch(selectedId, reload)
onMounted(reload)
</script>

<template>
  <section class="panel layout">
    <aside class="list">
      <header class="head">
        <h1>运行记录</h1>
        <button type="button" class="btn" @click="reload">刷新</button>
      </header>
      <p v-if="error" class="err">{{ error }}</p>
      <button
        v-for="it in items"
        :key="it.id"
        type="button"
        class="item"
        :class="{ on: it.id === selectedId }"
        @click="open(it.id)"
      >
        <strong>{{ it.definition_key }}</strong>
        <span class="muted">{{ it.status }} · {{ it.current_node }}</span>
      </button>
    </aside>
    <main class="detail" v-if="detail">
      <h2>{{ detail.instance.definition_key }}</h2>
      <p class="muted">{{ detail.instance.status }} @ {{ detail.instance.current_node }}</p>
      <h3>Context</h3>
      <pre>{{ JSON.stringify(detail.instance.context, null, 2) }}</pre>
      <h3>Logs</h3>
      <pre>{{ JSON.stringify(detail.logs, null, 2) }}</pre>
      <h3>Tasks</h3>
      <pre>{{ JSON.stringify(detail.tasks, null, 2) }}</pre>
    </main>
    <main v-else class="detail muted">选择一条运行记录</main>
  </section>
</template>

<style scoped>
.layout { display: grid; grid-template-columns: 280px 1fr; gap: 16px; padding: 20px; min-height: 70vh; }
.list { border-right: 1px solid #eee; padding-right: 12px; }
.head { display: flex; justify-content: space-between; align-items: center; }
.item { display: grid; width: 100%; text-align: left; gap: 4px; padding: 10px; border: 0; background: transparent; border-radius: 8px; cursor: pointer; }
.item.on { background: #f5f5f5; }
.detail pre { background: #fafafa; padding: 10px; border-radius: 8px; overflow: auto; font-size: 12px; }
.btn { padding: 6px 12px; border-radius: 8px; border: 1px solid #ccc; background: #fff; cursor: pointer; }
.err { color: #b42318; }
.muted { color: #777; font-size: 12px; }
</style>
