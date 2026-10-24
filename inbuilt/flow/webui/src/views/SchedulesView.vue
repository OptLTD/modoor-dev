<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listSchedules, upsertSchedule } from '../api/flow'

const items = ref<Array<Record<string, unknown>>>([])
const flowKey = ref('capacity.company_cert')
const cron = ref('0 9 * * 1-5')
const error = ref('')

async function reload() {
  const res = await listSchedules()
  items.value = res.items || []
}

async function add() {
  error.value = ''
  try {
    await upsertSchedule({ flow_key: flowKey.value, cron: cron.value, enabled: true })
    await reload()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

onMounted(reload)
</script>

<template>
  <section class="panel">
    <h1>定时触发</h1>
    <p class="muted">5 段 cron：分 时 日 月 周</p>
    <div class="form">
      <input v-model="flowKey" placeholder="flow key" />
      <input v-model="cron" placeholder="0 9 * * 1-5" />
      <button type="button" class="btn primary" @click="add">添加</button>
    </div>
    <p v-if="error" class="err">{{ error }}</p>
    <ul>
      <li v-for="s in items" :key="String(s.id)">
        {{ s.flow_key }} · <code>{{ s.cron }}</code> · {{ s.enabled ? 'on' : 'off' }}
        · next {{ s.next_run_at || '—' }}
      </li>
    </ul>
  </section>
</template>

<style scoped>
.panel { padding: 20px; }
.form { display: flex; gap: 8px; margin: 12px 0; }
.form input { flex: 1; padding: 8px; border-radius: 8px; border: 1px solid #ddd; }
.btn { padding: 6px 12px; border-radius: 8px; border: 1px solid #ccc; background: #fff; cursor: pointer; }
.btn.primary { background: #1c1914; color: #fff; border-color: transparent; }
.err { color: #b42318; }
.muted { color: #777; }
</style>
