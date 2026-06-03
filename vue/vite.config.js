import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 标准做法：构建产物输出到本目录下的 dist/，由 Flask 直接 serve。
// dist/ 已加入 .gitignore，开发者克隆代码后需先 `npm install && npm run build`。
export default defineConfig({
    plugins: [vue()],
    base: './',
    build: {
        outDir: 'dist',
        emptyOutDir: true,
    },
    server: {
        port: 5173,
        proxy: { '/api': 'http://127.0.0.1:8765' },
    },
})