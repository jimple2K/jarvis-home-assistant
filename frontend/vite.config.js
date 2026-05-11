import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api':    'http://localhost:5757',
      '/chat':   'http://localhost:5757',
      '/tts':    'http://localhost:5757',
      '/config': 'http://localhost:5757',
      '/ping':   'http://localhost:5757',
    },
  },
  build: {
    outDir: 'dist',
  },
});
