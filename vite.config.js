import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
//http://localhost:5001
// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "https://vite.dev/config/",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, "")
      }
    }
  }
})
// import { defineConfig } from 'vite'
// import react from '@vitejs/plugin-react'
// //http://localhost:5001
// // https://vite.dev/config/
// export default defineConfig({
//   plugins: [react()],
//   server: {
//     allowedHosts: [
//       'd349-2405-201-401f-b05a-4d23-4799-5fc0-7b7b.ngrok-free.app'
//     ],
//     proxy: {
//       "/api": {
//         target: "https://vite.dev/config/",
//         changeOrigin: true,
//         rewrite: (path) => path.replace(/^\/api/, "")
//       }
//     }
//   }
// })
