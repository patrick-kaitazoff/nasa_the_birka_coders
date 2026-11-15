import { fuenteLluvia } from "../comun/fuenteLluvia";
import { useApp } from "../store";
import { elegidaDe, evaluacionDe, riesgoPrincipal } from "./eleccion";

/** Al final del Plan: qué revisar con el agrónomo según lo que eligió el productor en cada lote, y de dónde sale cada
 * dato (lo que contó él, lo que midió la NASA, lo que dice el MGAP). La herramienta apoya; no decide. */
export function ParaElAgronomo() {
  const { analisis, plan } = useApp();
  if (!analisis || !plan) return null;
  const vistos = new Set<string>();
  const items: Array<[string, string]> = [];
  for (const s of analisis.secciones) {
    const ev = evaluacionDe(s, elegidaDe(plan, s));
    if (!ev) continue;
    const r = riesgoPrincipal(ev);
    if (r && !vistos.has(r)) { vistos.add(r); items.push([s.nombre, r]); }
  }
  const huecos = new Set<string>();
  for (const s of analisis.secciones) {
    const ev = evaluacionDe(s, elegidaDe(plan, s));
    ev?.explicacion?.huecos?.forEach((h) => huecos.add(h));
  }
  return (
    <div className="caja para-agronomo">
      <h3>Qué revisar con tu agrónomo</h3>
      <p className="bajada">Con lo que elegiste en cada lote. La herramienta te ayuda a comparar; la decisión es tuya y de tu agrónomo.</p>
      <ul>
        {items.slice(0, 6).map(([n, r]) => <li key={r}><b>{n}:</b> {r}</li>)}
        {[...huecos].slice(0, 2).map((h) => <li key={h}>{h}</li>)}
      </ul>
      <h3 style={{ marginTop: 14 }}>De dónde sale cada dato</h3>
      <div className="para-agronomo-fuentes">
        <div className="vos"><b>Lo contaste vos</b><span>Qué sembraste en cada lote, qué te anduvo y qué no, tus prioridades y cómo trabajás el campo.</span></div>
        <div className="nasa"><b>Lo midió la NASA</b>
          <span>{fuenteLluvia(analisis) === "GPM IMERG"
            ? "Lluvia desde 2000 (GPM IMERG, celda de unos 10 km), temperatura desde 1991 (POWER, celda de unos 50 km), verdor y suelo descubierto (MODIS, 250 m), pendiente (SRTM, 30 m) y humedad del suelo (SMAP, 9 km)."
            : "Lluvia y temperatura desde 1991 (POWER, celda de unos 50 km), verdor y suelo descubierto (MODIS, 250 m), pendiente (SRTM, 30 m) y humedad del suelo (SMAP, 9 km)."}</span>
          {analisis.clima?.aviso_completados && <span>{analisis.clima.aviso_completados}</span>}
        </div>
        <div className="mgap"><b>Lo dice el MGAP</b><span>Tipo de suelo (CONEAT), factor K, lo que aguanta cada suelo (tolerancia) y la lluvia erosiva oficial.</span></div>
      </div>
    </div>
  );
}
