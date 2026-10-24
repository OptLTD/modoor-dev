import type { RouteRecordRaw } from 'vue-router'
import ModuleShell from './ModuleShell.vue'
import WorkspaceView from './WorkspaceView.vue'

/** skill：根路径直接 sidebar + detail workspace。 */
export const skillRoute: RouteRecordRaw = {
  path: '/mod/skill',
  component: ModuleShell,
  meta: { module: 'skill' },
  children: [
    { path: '', name: 'skill.catalog', component: WorkspaceView },
    { path: ':id', name: 'skill.detail', component: WorkspaceView },
  ],
}
