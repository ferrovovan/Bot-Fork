import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Lets `npm run client` (Vite only) reach the Python bridge of server.ts
    proxy: {
      '/api': 'http://localhost:3000',
    },
  },
});
