import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.dirname(fileURLToPath(import.meta.url))
const repo = path.resolve(root, '../../..')
const apiProxy = process.env.MODOOR_API_PROXY || 'http://127.0.0.1:8765'
const publicHost = process.env.MODOOR_PUBLIC_HOST || '127.0.0.1'
const publicPort = Number(process.env.MODOOR_PUBLIC_PORT || 8765)

export default defineConfig({
  base: '/mod/flow/',
  plugins: [vue()],
  resolve: {
    alias: {
      '@modoor/hooks': path.resolve(repo, 'shared/hooks/src'),
      '@modoor/widget': path.resolve(repo, 'shared/widget/src'),
      '@modoor/views': path.resolve(repo, 'shared/views/src'),
      vue: path.resolve(root, 'node_modules/vue'),
      'vue-router': path.resolve(root, 'node_modules/vue-router'),
    },
  },
  server: {
    port: 5184,
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
    port: 5184,
    host: true,
    strictPort: true,
  },
  build: { outDir: 'dist', emptyOutDir: true },
  optimizeDeps: { exclude: ['@modoor/hooks', '@modoor/widget', '@modoor/views'] },
})
