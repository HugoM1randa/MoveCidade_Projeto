/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

const API = process.env.MOVECIDADE_API ?? 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icone.svg'],
      manifest: {
        name: 'MoveCidade — ônibus de Matão',
        short_name: 'MoveCidade',
        description: 'Linhas, pontos e previsão de chegada dos ônibus de Matão/SP.',
        lang: 'pt-BR',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        background_color: '#F6F7F9',
        theme_color: '#0F4C5C',
        icons: [
          { src: '/icone-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icone-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icone-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//],
        runtimeCaching: [
          {
            // dados do app: rede primeiro; sem conexão, usa a última resposta guardada
            urlPattern: ({ url }) => url.pathname.startsWith('/api/') && !url.pathname.startsWith('/api/gestor'),
            handler: 'NetworkFirst',
            method: 'GET',
            options: { cacheName: 'api', networkTimeoutSeconds: 4, expiration: { maxEntries: 200 } },
          },
          {
            urlPattern: ({ url }) => url.hostname === 'tile.openstreetmap.org',
            handler: 'CacheFirst',
            options: { cacheName: 'mapa', expiration: { maxEntries: 600, maxAgeSeconds: 60 * 60 * 24 * 30 } },
          },
        ],
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: { '/api': { target: API, changeOrigin: true } },
  },
  preview: {
    port: 4173,
    proxy: { '/api': { target: API, changeOrigin: true } },
  },
  build: { chunkSizeWarningLimit: 700 },
  test: {
    include: ['src/**/*.test.ts'],
  },
});
