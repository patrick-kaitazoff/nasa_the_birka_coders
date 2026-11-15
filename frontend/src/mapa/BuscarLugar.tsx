import { useState } from "react";
import { useApp } from "../store";
import { Cargando } from "../comun/Cargando";
import type { LugarEncontrado } from "../tipos";

/**
 * Buscador del paso 1: un pueblo, un paraje, una calle o «ruta 5 km 200», con su
 * departamento. Lo resuelve el servidor (/api/buscar: IDE Uruguay y mojones del MTOP). Se usa en la tarjeta del
 * paso 1 y cuando se escribe un lugar en el chat antes de tener el contorno (store.buscarEnChat).
 */
export type ResultadoLugar = LugarEncontrado;

export async function buscarLugares(q: string): Promise<ResultadoLugar[]> {
  const r = await fetch(`/api/buscar?q=${encodeURIComponent(q)}`);
  if (!r.ok) throw new Error(`El buscador respondió ${r.status}.`);
  return ((await r.json()).resultados || []) as ResultadoLugar[];
}

/** «ruta 5 km 200», «R26 150», «interbalnearia km 60»: eso siempre es una búsqueda, no una pregunta. */
export const RE_RUTA_KM = /^\s*(?:ruta|rta\.?|r)\s*n?[º°o.]?\s*(?:\d{1,3}|ib)\s*[,;-]?\s*(?:(?:km|kil[oó]metro)s?\.?\s*)?\d{1,3}(?:[.,]\d+)?\s*$|^\s*(?:ruta\s*)?interbalnearia\b/i;

/** Si lo que se escribió en el chat parece un lugar (y no una pregunta o una charla). */
export function pareceLugar(t: string): boolean {
  const s = t.trim();
  if (RE_RUTA_KM.test(s)) return true;
  if (s.length < 3 || s.length > 70 || /[?¿!¡]/.test(s)) return false;
  if (s.split(/\s+/).length > 7) return false;
  const primera = s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").split(/[\s,]+/)[0];
  const charla = ["hola", "buenas", "buen", "gracias", "ok", "si", "no", "dale", "listo", "que", "como", "cuando", "cuanto", "cuanta",
    "donde", "por", "porque", "quiero", "tengo", "necesito", "ayuda", "ayudame", "explicame", "mi", "el", "la", "los", "las", "un", "una",
    "es", "esta", "estoy", "hay", "puedo", "podes", "sembre", "siembro", "cultivo", "analizar", "rehacer", "seguir", "continuar", "omitir"];
  return !charla.includes(primera);
}

/** Lleva el mapa al lugar, elige su departamento y le pone un alfiler con el nombre. */
export function irALugar(r: ResultadoLugar) {
  const st = useApp.getState();
  st.setExplorando(true);
  st.setPestania("mapa");
  st.setVistaMovil("trabajo");
  st.setCentrar(r.lat, r.lon, r.zoom || 14);
  // en EE. UU. el «departamento» es «condado, estado»: no hay caminos ni padrón que cargar
  if (r.departamento && st.paisMapa === "UY") window.dispatchEvent(new CustomEvent("fieldshift:departamento", { detail: r.departamento.toUpperCase() }));
  window.dispatchEvent(new CustomEvent("fieldshift:punto", { detail: r }));
}

export function ListaLugares({ lugares, elegido, alElegir }: { lugares: ResultadoLugar[]; elegido?: number | null; alElegir: (r: ResultadoLugar, i: number) => void }) {
  return (
    <div className="lugares-lista" role="list">
      {lugares.map((r, i) => (
        <button key={`${r.nombre}-${r.lat}`} role="listitem" className={`lugar-opcion ${elegido === i ? "on" : ""}`} onClick={() => alElegir(r, i)}>
          <b data-no-traducir>{r.nombre}</b>
          {r.departamento && <span className="lugar-opcion-depto" data-no-traducir>{r.departamento}</span>}
        </button>
      ))}
    </div>
  );
}

export function BuscarLugar({ pais = "UY" }: { pais?: "UY" | "US" }) {
  const [q, setQ] = useState("");
  const [buscando, setBuscando] = useState(false);
  const [lugares, setLugares] = useState<ResultadoLugar[] | null>(null);
  const [elegido, setElegido] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function buscar() {
    const t = q.trim();
    if (!t || buscando) return;
    setBuscando(true);
    setError(null);
    setElegido(null);
    try {
      const r = await buscarLugares(t);
      setLugares(r);
      if (!r.length) setError(RE_RUTA_KM.test(t) ? "No encontré ese kilómetro en esa ruta." : "No encontré ese lugar. Probá con el pueblo o paraje más cercano, o con la ruta y el kilómetro.");
      else if (r.length === 1) { setElegido(0); irALugar(r[0]); }
    } catch {
      setError("No pude buscar ahora. Probá de nuevo en un rato.");
    } finally {
      setBuscando(false);
    }
  }

  return (
    <div className="buscar-lugar">
      <form className="fila" onSubmit={(e) => { e.preventDefault(); void buscar(); }}>
        <input className="entrada" style={{ flex: "1 1 160px" }} value={q} onChange={(e) => setQ(e.target.value)}
          placeholder={pais === "US" ? "Pueblo o condado, ej. «Winterset, Iowa»" : "Pueblo, paraje, calle o «ruta 5 km 200»"} aria-label="Buscar dónde queda el campo" />
        <button className="btn primario chico" style={{ flex: "0 0 auto" }} type="submit" disabled={buscando || !q.trim()}>
          {buscando ? <Cargando que="buscando" claro etiqueta="Buscando" /> : "Buscar"}
        </button>
      </form>
      {lugares && lugares.length > 0 && (
        <ListaLugares lugares={lugares} elegido={elegido} alElegir={(r, i) => { setElegido(i); irALugar(r); }} />
      )}
      {error && <div className="alerta ambar" role="alert">{error}</div>}
    </div>
  );
}
