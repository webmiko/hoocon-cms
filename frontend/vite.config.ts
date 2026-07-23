import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: [
        "favicon.svg",
        "logo.svg",
        "logo-on-dark.svg",
        "apple-touch-icon.png",
        "og-image.svg",
      ],
      manifest: {
        name: "Hoocon — электроприводы ОВК",
        short_name: "Hoocon",
        description:
          "B2B-каталог электроприводов Hoocon для ОВК: подбор, документы, запрос КП.",
        theme_color: "#dc1313",
        background_color: "#f3f4f7",
        display: "standalone",
        orientation: "portrait-primary",
        start_url: "/",
        scope: "/",
        lang: "ru",
        categories: ["business"],
        icons: [
          { src: "pwa-192.png", sizes: "192x192", type: "image/png" },
          { src: "pwa-512.png", sizes: "512x512", type: "image/png" },
          {
            src: "pwa-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,ico,woff2,jpg,jpeg,webp}"],
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//, /^\/admin\//, /^\/media\//],
      },
      devOptions: {
        enabled: true,
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/admin": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/media": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/robots.txt": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/sitemap.xml": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/llms.txt": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/llm.txt": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/llms-full.txt": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
