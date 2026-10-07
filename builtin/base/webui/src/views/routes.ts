import type { RouteRecordRaw } from 'vue-router'
import ModuleShell from './ModuleShell.vue'
import UsersView from './UsersView.vue'
import RolesView from './RolesView.vue'
import ModulesView from './ModulesView.vue'

/** base：整模块挂到 /mod/base，内部切 users/roles/modules。 */
export const baseRoute: RouteRecordRaw = {
  path: '/mod/base',
  component: ModuleShell,
  meta: { module: 'base' },
  redirect: '/mod/base/users',
  children: [
    { path: 'users', name: 'base.users', component: UsersView },
    { path: 'roles', name: 'base.roles', component: RolesView },
    { path: 'modules', name: 'base.modules', component: ModulesView },
  ],
}
