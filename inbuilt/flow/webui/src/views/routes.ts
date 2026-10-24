import type { RouteRecordRaw } from 'vue-router'
import ModuleShell from './ModuleShell.vue'
import InboxView from './InboxView.vue'
import InstancesView from './InstancesView.vue'
import DefinitionsView from './DefinitionsView.vue'
import SchedulesView from './SchedulesView.vue'

export const flowRoute: RouteRecordRaw = {
  path: '/mod/flow',
  component: ModuleShell,
  meta: { module: 'flow' },
  redirect: '/mod/flow/inbox',
  children: [
    { path: 'inbox', name: 'flow.inbox', component: InboxView },
    { path: 'instances', name: 'flow.instances', component: InstancesView },
    { path: 'instances/:id', name: 'flow.instance', component: InstancesView },
    { path: 'definitions', name: 'flow.definitions', component: DefinitionsView },
    { path: 'schedules', name: 'flow.schedules', component: SchedulesView },
  ],
}
