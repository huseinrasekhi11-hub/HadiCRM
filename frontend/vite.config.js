import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
//
// The dev server can proxy the API under `/api`, so the browser only ever
// talks to ONE origin. That matters now that the refresh token lives in a
// cookie: first-party (same-site) cookies work everywhere, including Safari
// and other browsers that block cross-site cookies — whereas a panel on
// https://panel.example.com calling https://api.example.com needs
// SameSite=None and is still refused by some browsers.
//
// Local:      VITE_API_BASE_URL=/api  →  vite proxies /api to the backend
// Production: either keep VITE_API_BASE_URL pointed at the API host (the
//             cookie then needs SameSite=None + HTTPS), or put a rewrite in
//             front of it (e.g. Vercel: { "source": "/api/:path*",
//             "destination": "https://<api-host>/:path*" }) and build with
//             VITE_API_BASE_URL=/api for first-party cookies.
const API_TARGET = process.env.VITE_API_PROXY_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    // Allow preview/sandbox hostnames (the dev server is reached through a
    // generated host, not just `localhost`).
    allowedHosts: true,
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
