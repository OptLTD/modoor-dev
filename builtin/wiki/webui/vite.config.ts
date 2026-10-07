import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import { createRequire } from 'node:module'

const root = path.dirname(fileURLToPath(import.meta.url))
const repo = path.resolve(root, '../../..')
const require = createRequire(import.meta.url)
const apiProxy = process.env.MODOOR_API_PROXY || 'http://127.0.0.1:8765'
const publicHost = process.env.MODOOR_PUBLIC_HOST || '127.0.0.1'
const publicPort = Number(process.env.MODOOR_PUBLIC_PORT || 8765)

/** @modoor/hooks i18n uses vue refs; resolve vue from a sibling Vue module. */
function resolveVue(): string {
  try {
    return path.dirname(require.resolve('vue/package.json'))
  } catch {
    return path.resolve(repo, 'builtin/doc/webui/node_modules/vue')
  }
}

export default defineConfig({
  base: '/mod/wiki/',
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(root, 'src'),
      '@modoor/hooks': path.resolve(repo, 'shared/hooks/src'),
      '@modoor/hooks/i18n': path.resolve(repo, 'shared/hooks/src/i18n.ts'),
      vue: resolveVue(),
    },
  },
  optimizeDeps: {
    include: ['vue'],
  },
  server: {
    port: 5176,
    host: true,
    strictPort: true,
    origin: `http://${publicHost}:${publicPort}`,
    hmr: {
      protocol: 'ws',
      host: publicHost,
      clientPort: publicPort,
    },
    proxy: {
      '/api': { target: apiProxy, changeOrigin: true },
      '/logo.png': { target: apiProxy, changeOrigin: true },
    },
  },
  preview: {
    port: 5176,
    host: true,
    strictPort: true,
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
