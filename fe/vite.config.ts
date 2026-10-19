import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: FE chạy ở :5173, gọi /api/v1 và Vite chuyển tiếp sang BE (mặc định :8000).
// Đổi BE thật hay mock chỉ cần đặt VITE_PROXY_TARGET.
const target = process.env.VITE_PROXY_TARGET ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': { target, changeOrigin: true } } },
})
