import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// DevTrack AI frontend — proxies /api/v1 to backend during local dev.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api/v1': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  preview: {
    port: 5173,
  },
});
