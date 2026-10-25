import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        // Dev-time only: forwards /api/* to the FastAPI backend so the app
        // never needs CORS configured. Set VITE_API_TARGET in frontend/.env.local
        // to point at a remote backend (e.g. the EC2 instance).
        '/api': {
          target: env.VITE_API_TARGET || 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
  };
});
