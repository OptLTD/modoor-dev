import type { RouteRecordRaw } from 'vue-router'
import ModuleShell from './ModuleShell.vue'
import { SchemaView } from '@modoor/views/SchemaView'

/** sale：标准 SchemaView（单页签 = 当前页）. */
export const saleRoute: RouteRecordRaw = {
  path: '/mod/sale',
  component: ModuleShell,
  meta: { module: 'sale' },
  children: [
    {
      path: '',
      name: 'sale.orders',
      component: SchemaView,
      props: {
        title: '销售订单',
        tabs: [{ model: 'sale.order', label: '销售订单' }],
      },
    },
  ],
}
