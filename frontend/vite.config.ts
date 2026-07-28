import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

import { asyncEntryCssPlugin } from "./vite.async-css.ts";
import { COLOR_BG, COLOR_BRAND } from "./src/styles/brandColors.ts";

/** Bump when replacing public/pwa-*.png so installed PWAs refetch icons. */
const PWA_ICON_REV = "20260725b";

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
        "pwa-192.png",
        "pwa-512.png",
        "pwa-512-maskable.png",
        "og-image.svg",
      ],
      manifest: {
        name: "Hoocon — электроприводы вентиляции и кондиционирования",
        short_name: "Hoocon",
        description:
          "B2B-каталог электроприводов Hoocon для ОВК: подбор, документы, запрос КП.",
        theme_color: COLOR_BRAND,
        background_color: COLOR_BG,
        display: "standalone",
        orientation: "portrait-primary",
        start_url: "/",
        scope: "/",
        lang: "ru",
        categories: ["business"],
        icons: [
          {
            src: `pwa-192.png?v=${PWA_ICON_REV}`,
            sizes: "192x192",
            type: "image/png",
            purpose: "any",
          },
          {
            src: `pwa-512.png?v=${PWA_ICON_REV}`,
            sizes: "512x512",
            type: "image/png",
            purpose: "any",
          },
          {
            src: `pwa-512-maskable.png?v=${PWA_ICON_REV}`,
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
    // After PWA HTML inject — last transformIndexHtml wins for stylesheet links.
    asyncEntryCssPlugin(),
  ],
  build: {
    cssCodeSplit: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("node_modules")) {
            return;
          }
          if (id.includes("dompurify")) {
            return "vendor-dompurify";
          }
          if (
            id.includes("react-dom") ||
            id.includes("/react/") ||
            id.includes("react-router") ||
            id.includes("react-helmet-async") ||
            id.includes("scheduler")
          ) {
            return "vendor-react";
          }
        },
      },
    },
  },
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
