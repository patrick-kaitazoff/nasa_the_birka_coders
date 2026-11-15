import { resolve } from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [
    react(),
    // en desarrollo, /app sirve la herramienta (app.html) y /b la portada B; en Vercel lo hace el backend. «/» es la portada A.
    {
      name: "app-sin-html",
      configureServer(server) {
        server.middlewares.use((req, res, next) => {
          // La portada B no se muestra más; /b lleva a la A (igual que en Vercel, fieldshift/api.py)
          if (/^\/b(\.html)?\/?(\?.*)?$/.test(req.url || "")) { res.statusCode = 302; res.setHeader("Location", "/"); res.end(); return; }
          const m = req.url?.match(/^\/(app|b)\/?(\?.*)?$/);
          if (m) req.url = `/${m[1]}.html${m[2] ?? ""}`;
          next();
        });
      },
    },
    // El código de /app iba con blocking="render" (el navegador no pintaba nada hasta tenerlo) para
    // que el fundido desde la portada no terminara en una página vacía. En una compu lenta eso dejaba el trigo de la
    // portada quieto, como trabado, hasta un par de segundos. Ahora app.html trae el esqueleto de la herramienta y se
    // pinta enseguida.
    // La portada baja de antemano, sin apuro, el código de la herramienta y el del trigo 3D. Así, al tocar
    // «Planificar mi campo» solo falta el HTML y la escena no se queda quieta esperando. Es para los navegadores que
    // no arman /app por adelantado con speculation rules (Brave, Firefox, Safari). Solo al compilar: los nombres de
    // los archivos llevan un hash que recién se conoce ahí.
    {
      name: "portada-adelanta-la-herramienta",
      apply: "build",
      transformIndexHtml: {
        order: "post",
        handler(html, ctx) {
          if (!/[\\/]index\.html$/.test(ctx.filename) || !ctx.bundle) return html;
          const bundle = ctx.bundle;
          const archivos = new Set<string>();
          const sumar = (nombre: string) => {
            const c = bundle[nombre];
            if (!c || c.type !== "chunk" || archivos.has(nombre)) return;
            archivos.add(nombre);
            c.imports.forEach(sumar);
            c.viteMetadata?.importedCss.forEach((css) => archivos.add(css));
          };
          for (const c of Object.values(bundle)) {
            if (c.type === "chunk" && (c.facadeModuleId?.endsWith("app.html") || /src[\\/]main\.tsx$/.test(c.facadeModuleId ?? ""))) sumar(c.fileName);
            if (c.type === "chunk" && /CampoTrigo\.ts$/.test(c.facadeModuleId ?? "")) sumar(c.fileName);
          }
          // el trigo 3D de la portada se carga aparte (para no frenar el texto) pero se pide ya, con prioridad alta:
          // modulepreload y no prefetch, que el navegador deja para cuando no tiene nada más que hacer
          const ya = new Set(archivos);
          archivos.clear();
          const trigo = Object.values(bundle).find((c) => c.type === "chunk" && /CampoTrigo\.ts$/.test(c.facadeModuleId ?? ""));
          if (trigo) sumar(trigo.fileName);
          // y el traductor con sus diccionarios: La portada abre en inglés y espera a tenerlo para
          // mostrar el texto (si no, se vería el castellano un instante)
          const traductor = Object.values(bundle).find((c) => c.type === "chunk" && c.fileName.includes("observador"));
          if (traductor) sumar(traductor.fileName);
          const urgentes = [...archivos].filter((f) => f.endsWith(".js") && !html.includes(`/${f}"`));
          const enlaces = [
            ...urgentes.map((f) => `<link rel="modulepreload" crossorigin href="/${f}" />`),
            ...[...ya]
              .filter((f) => !archivos.has(f) && !html.includes(`/${f}"`))
              .map((f) => `<link rel="prefetch" href="/${f}"${f.endsWith(".css") ? ' as="style"' : ' as="script" crossorigin'} />`),
          ].join("\n    ");
          return html.replace("</head>", `    ${enlaces}\n  </head>`);
        },
      },
    },
  ],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: true } },
  },
  build: {
    chunkSizeWarningLimit: 1600,
    rollupOptions: { input: { portada: resolve(__dirname, "index.html"), app: resolve(__dirname, "app.html"), b: resolve(__dirname, "b.html") } },
  },
});
