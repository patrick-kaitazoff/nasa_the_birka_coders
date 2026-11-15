import { crearSeccion, useApp } from "../store";
import { EstadoMarcado } from "./EstadoMarcado";
import { revisarDivisiones } from "./revision";
import { calcularZonaLibre, areaHa } from "./geo";
import { useIdioma } from "../i18n/idioma";
import { traducir } from "../i18n/traducir";

export const COLORES_SECCION = ["#4F9A6F", "#C9A227", "#2F6FAE", "#B5651D", "#8E5BA8", "#D0644F", "#3E8E8E", "#7A8F2C", "#A3476B", "#5B6C8F"];


export function PanelSecciones() {
  const { campo, setSecciones, actualizarSeccion, setModoMapa, modoMapa, seccionSel, setSeccionSel } = useApp();
  const idioma = useIdioma((s) => s.idioma);
  const secs = campo.secciones;
  const esGanadero = campo.sistema?.tipo === "ganadero";


  // «Proponer las partes con la imagen de la NASA» se sacó. El backend (/api/partes, analisis/partes.py) y api.proponerPartes siguen.

  function campoEntero() {
    if (!campo.contorno) return;
    // el dibujo de lotes arranca prendido en el paso 2: si quedaba prendido, el mapa avisaba además «El campo ya está
    // completamente cubierto por los lotes» en un cartel encima del chat
    setModoMapa("ver");
    setSecciones([crearSeccion(campo.contorno, "Campo entero")]);
    window.dispatchEvent(new Event("fieldshift:encuadrar"));
  }

  const total = secs.reduce((a, s) => a + (s.area_ha || 0), 0);
  const libre = campo.contorno ? calcularZonaLibre(campo.contorno, secs) : null;
  const sinLugar = !!(campo.contorno && secs.length > 0 && (!libre || areaHa(libre) < 0.1));
  const avisos = secs.length && modoMapa !== "secciones" ? revisarDivisiones(campo) : [];
  const fmtHa = (x: number) => x.toLocaleString("es-UY", { maximumFractionDigits: x < 10 ? 1 : 0 });

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {sinLugar ? (
        <div className="alerta verde" style={{ fontSize: 13, padding: "8px 12px", borderRadius: 8, margin: 0 }}>
          El campo quedó completamente cubierto por las divisiones.
        </div>
      ) : (
        <div className="chips">
          <button className={`chip ${modoMapa === "secciones" ? "on" : ""}`} onClick={() => setModoMapa(modoMapa === "secciones" ? "ver" : "secciones")}>
            {modoMapa === "secciones"
              ? (esGanadero ? "Dibujando potrero… (clic para terminar)" : "Dibujando lote… (clic para terminar)")
              : (esGanadero ? "Dibujar un potrero" : "Dibujar un lote")}
          </button>
          <button className={`chip ${modoMapa === "circulo" ? "on" : ""}`} onClick={() => setModoMapa(modoMapa === "circulo" ? "ver" : "circulo")}>
            {modoMapa === "circulo" ? "Dibujando pivot… (clic para terminar)" : "Dibujar un pivot"}
          </button>
          <button className="chip" onClick={campoEntero}>
            {esGanadero ? "Todo el campo es un solo potrero" : "Todo el campo es un solo lote"}
          </button>
        </div>
      )}
      {modoMapa === "secciones" && <EstadoMarcado que="seccion" />}
      {modoMapa === "circulo" && <EstadoMarcado que="seccion" circulo />}
      {secs.length > 0 && (
        <>
          <div className="lista-secciones">
            {secs.map((s, i) => {
              const valorInput = (idioma === "en" && (s.nombre.startsWith("Lote ") || s.nombre.startsWith("Potrero ") || s.nombre.startsWith("Parte ") || s.nombre === "Campo entero"))
                ? traducir(s.nombre)
                : s.nombre;
              return (
                <div key={s.id} className={`item-seccion ${seccionSel === s.id ? "sel" : ""}`} onClick={() => setSeccionSel(s.id)}>
                  <span className="muestra-color" style={{ background: COLORES_SECCION[i % COLORES_SECCION.length] }} />
                  <input
                    value={valorInput}
                    onChange={(e) => actualizarSeccion(s.id, { nombre: e.target.value })}
                    aria-label="Nombre de la sección"
                  />
                  <small style={{ color: "var(--texto-3)", display: "inline-flex", alignItems: "center", gap: 6, flexWrap: "wrap" }} title={s.notas || undefined}>
                    <span>{`${(s.area_ha || 0).toLocaleString("es-UY", { maximumFractionDigits: 1 })} ha`}</span>
                  </small>
                  <button className="btn texto chico peligro" title="Borrar" onClick={(e) => { e.stopPropagation(); setSecciones(secs.filter((x) => x.id !== s.id)); }}>×</button>
                </div>
              );
            })}
          </div>
          {secs.some((s) => s.notas?.startsWith("Se ve ")) && (
            <ul className="como-se-ve">{secs.filter((s) => s.notas?.startsWith("Se ve ")).map((s) => <li key={s.id}><b>{s.nombre}:</b> {s.notas!.slice(6)}</li>)}</ul>
          )}

          <div className="fila" style={{ alignItems: "center" }}>
            <small style={{ color: "var(--texto-3)", flex: "1 1 200px" }}>
              {secs.length} {secs.length === 1 ? "sección" : "secciones"} · {`${fmtHa(total)} ha para planificar`}
              {campo.area_ha && campo.area_ha - total >= 0.5
                ? ` de ${fmtHa(campo.area_ha)} ha del campo. Las ${fmtHa(campo.area_ha - total)} ha que quedan afuera (caminos, casco, monte, lo que no se trabaja) no entran en el plan.`
                : "."}
            </small>
          </div>
          {avisos.length > 0 && (
            <div className="revision">
              <b>Mirando tus divisiones</b>
              <ul>{avisos.map((x, i) => <li key={i} className={`rev-${x.tipo}`}>{x.seccion ? <><b>{x.seccion}</b> {x.texto}</> : x.texto}</li>)}</ul>
              <small>Son ideas para conversar con tu agrónomo: no hace falta cambiar nada para seguir.</small>
            </div>
          )}
        </>
      )}
    </div>
  );
}
