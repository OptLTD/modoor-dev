<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { decideTask, listTasks, type FlowTask } from '../api/flow'

const items = ref<FlowTask[]>([])
const error = ref('')
const comment = ref<Record<string, string>>({})

async function reload() {
  error.value = ''
  try {
    const res = await listTasks('pending')
    items.value = res.items || []
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

async function onDecide(id: string, decision: string) {
  try {
    await decideTask(id, decision, comment.value[id] || '')
    await reload()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

onMounted(reload)
</script>

<template>
  <section class="panel">
    <header class="head">
      <h1>审批中心</h1>
      <button type="button" class="btn" @click="reload">刷新</button>
    </header>
    <p v-if="error" class="err">{{ error }}</p>
    <p v-if="!items.length && !error" class="muted">暂无待办</p>
    <article v-for="t in items" :key="t.id" class="card">
      <div class="row">
        <strong>{{ t.title || t.id }}</strong>
        <span class="pill">L{{ t.level }}</span>
      </div>
      <p class="muted">实例 {{ t.instance_id }}</p>
      <input v-model="comment[t.id]" class="input" placeholder="意见（可选）" />
      <div class="actions">
        <button type="button" class="btn" @click="onDecide(t.id, 'reject')">驳回</button>
        <button type="button" class="btn primary" @click="onDecide(t.id, 'approve')">通过</button>
      </div>
    </article>
  </section>
</template>

<style scoped>
.panel { padding: 20px; }
.head { display: flex; justify-content: space-between; align-items: center; }
.card { border: 1px solid var(--line, #e5e5e5); border-radius: 10px; padding: 12px; margin: 10px 0; }
.row { display: flex; gap: 8px; align-items: center; }
.pill { font-size: 12px; background: #f3f3f3; padding: 2px 8px; border-radius: 999px; }
.input { width: 100%; margin: 8px 0; padding: 8px; border-radius: 8px; border: 1px solid #ddd; }
.actions { display: flex; gap: 8px; justify-content: flex-end; }
.btn { padding: 6px 12px; border-radius: 8px; border: 1px solid #ccc; background: #fff; cursor: pointer; }
.btn.primary { background: #1c1914; color: #fff; border-color: transparent; }
.err { color: #b42318; }
.muted { color: #777; }
</style>
