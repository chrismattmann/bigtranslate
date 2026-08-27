import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: '/gloss/',
  publicDir: 'public',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false
  },
  server: {
    proxy: {
      '/gloss-services': {
        target: 'http://localhost:8080',
        changeOrigin: true
      }
    }
  }
})
