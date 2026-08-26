import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Tauri 构建时(tauri build 的 beforeBuildCommand)会注入 TAURI_ENV_* 环境变量
const isTauriBuild = !!process.env.TAURI_ENV_PLATFORM

export default defineConfig(({ command }) => ({
  plugins: [react()],
  // Tauri:产物打进应用包,用根路径;后端托管:输出到 static/dist,带 /static/dist/ 前缀
  base: isTauriBuild ? '/' : command === 'build' ? '/static/dist/' : '/',
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8010',
      '/ws': {
        target: 'ws://127.0.0.1:8010',
        ws: true,
      },
    },
  },
  build: {
    outDir: isTauriBuild ? 'dist' : '../static/dist',
    emptyOutDir: true,
  },
}))
