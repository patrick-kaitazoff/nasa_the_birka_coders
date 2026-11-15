import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { PortadaB } from "./PortadaB";
import "./portada-b.css";
import { iniciarTraduccion } from "../i18n/observador";

// Portada B, en /b. Los links con parámetros de la herramienta (campo de ejemplo, puente,
// pestaña, campo vacío) van a /app con lo mismo.
const q = new URLSearchParams(location.search);
if (["demo", "puente", "pestania", "vacio"].some((k) => q.has(k))) {
  location.replace("/app" + location.search + location.hash);
} else {
  iniciarTraduccion();
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <PortadaB />
    </StrictMode>,
  );
}
