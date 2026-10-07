import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import { docRoute } from './views/routes'
import DocNav from './views/DocNav.vue'
import { shellLoginUrl } from '@modoor/hooks'
import { registerSysTrayWidget } from '@modoor/views/ShellFrame'
import './i18n'
import '@modoor/widget/styles.css'

registerSysTrayWidget('doc', DocNav)

const router = createRouter({
  history: createWebHistory(),
  routes: [
    docRoute,
    { path: '/', redirect: '/mod/doc' },
  ],
})

router.beforeEach(async (to) => {
  if (to.meta.public) return true
  try {
    const res = await fetch('/api/auth/profile', { credentials: 'include' })
    if (res.status === 401) {
      location.href = shellLoginUrl(location.href)
      return false
    }
  } catch {
    location.href = shellLoginUrl(location.href)
    return false
  }
  return true
})

createApp(App).use(router).mount('#app')
