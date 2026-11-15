/** «¿Y si cambia el clima?»: deslizadores de lluvia y temperatura que recalculan, con los mismos 35 años
 * de NASA POWER, cuántos años de cada 10 le iría mal a cada cultivo. Lo propone el desafío ("scenario
 * sliders that adjust rainfall or temperature patterns"). El cálculo está en el backend
 * (clima.escenario): la app no inventa números. */

import { useEffect, useRef, useState } from "react";
import { api, type ResultadoEscenario } from "../api";
import { nombreCultivo, useApp } from "../store";
import { DiezCambio } from "./DiezAnios";
import { enPalabras } from "../errores";
import { useUS } from "../i18n/region";
import { medidas } from "../i18n/unidades";

const ATAJOS: Array<{ t: string; lluvia: number; temp: number }> = [
  { t: "Como fue", lluvia: 0, temp: 0 },
  { t: "20 % menos de lluvia", lluvia: -20, temp: 0 },
  { t: "1,5 °C más", lluvia: 0, temp: 1.5 },
  { t: "Las dos juntas", lluvia: -20, temp: 1.5 },
];

function signo(n: number, d = 0) {
  const t = Math.abs(n).toLocaleString("es-UY", { maximumFractionDigits: d, minimumFractionDigits: d });
  return n > 0 ? `+${t}` : n < 0 ? `−${t}` : t;
}

const mm = (n: number, d = 0) => n.toLocaleString("es-UY", { maximumFractionDigits: d, minimumFractionDigits: d });

export function Escenario({ cultivos }: { cultivos: string[] }) {
  const { analisis, catalogo } = useApp();
  const [lluvia, setLluvia] = useState(0);
  const [temp, setTemp] = useState(0);
  const [res, setRes] = useState<ResultadoEscenario | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pedido = useRef(0);
  // en EE. UU., pulgadas y °F (el deslizador sigue en °C por dentro: 0,5 °C son 0,9 °F)
  const u = medidas(useUS());

  const celda = analisis?.clima?.celda;
  const agua = analisis?.clima?.agua_util_mm;
  const lista = cultivos.join(",");

  useEffect(() => {
    if (!celda) return;
    const n = ++pedido.current;
    const espera = setTimeout(() => {
      setCargando(true);
      api.escenario({ lat: celda.lat, lon: celda.lon, agua_util_mm: agua ?? 120, lluvia_pct: lluvia, temp_c: temp, cultivos: lista.split(",") })
        .then((r) => { if (n === pedido.current) { setRes(r); setError(null); } })
        .catch((e: Error) => { if (n === pedido.current) setError(enPalabras(e)); })
        .finally(() => { if (n === pedido.current) setCargando(false); });
    }, 350);
    return () => clearTimeout(espera);
  }, [celda?.lat, celda?.lon, agua, lluvia, temp, lista]);

  if (!celda) return null;
  const sinCambio = lluvia === 0 && temp === 0;

  return (
    <div className="caja escenario">
      <h3>¿Y si cambia el clima?</h3>
      <p className="bajada">Mové la lluvia y la temperatura y mirá cuántos años de cada 10 le habría ido mal a cada cultivo en estos mismos {res?.periodo ? res.periodo.replace("-", " a ") : "35 años"}. No es un pronóstico: sirve para ver qué cultivo aguanta mejor un clima más seco o más caliente.</p>

      <div className="escenario-controles">
        <label className="campo">
          <span>Lluvia: <b>{signo(lluvia)} %</b></span>
          <input type="range" min={-40} max={30} step={5} value={lluvia} onChange={(e) => setLluvia(+e.target.value)} aria-label="Cambio de la lluvia, en por ciento" />
        </label>
        <label className="campo">
          <span>Temperatura: <b>{`${signo(u.difTemp(temp), 1)} ${u.uTemp}`}</b></span>
          <input type="range" min={-1} max={4} step={0.5} value={temp} onChange={(e) => setTemp(+e.target.value)} aria-label="Cambio de la temperatura, en grados" />
        </label>
        <div className="escenario-atajos">
          {ATAJOS.map((a) => (
            <button key={a.t} className={`chip ${a.lluvia === lluvia && a.temp === temp ? "on" : ""}`} onClick={() => { setLluvia(a.lluvia); setTemp(a.temp); }}>{a.t}</button>
          ))}
        </div>
      </div>

      {error && <div className="alerta ambar">{error}</div>}
      {res && (
        <>
          <p className="fuente" style={{ margin: "6px 0 0" }}>
            Lluvia por año: {mm(u.agua(res.lluvia_anual_mm.hoy), u.decAgua)} → <b>{`${mm(u.agua(res.lluvia_anual_mm.escenario), u.decAgua)} ${u.uAgua}`}</b> · lo que pide el aire (ET0): {mm(u.agua(res.et0_anual_mm.hoy), u.decAgua)} → <b>{`${mm(u.agua(res.et0_anual_mm.escenario), u.decAgua)} ${u.uAgua}`}</b>
            {cargando && " · recalculando…"}
          </p>
          <div className="riesgo-diez" role="table" aria-label="Años de cada 10 con problemas, hoy y con el cambio">
            <div className="fila cab" role="row"><span role="columnheader">Cultivo</span><span role="columnheader">Seca</span><span role="columnheader">Helada</span><span role="columnheader">Calor</span></div>
            {res.cultivos.map((f) => (
              <div className="fila" role="row" key={f.cultivo}>
                <span role="cell"><b>{nombreCultivo(catalogo, f.cultivo, true)}</b></span>
                <span role="cell" data-r="Seca"><DiezCambio hoy={f.hoy.prob_seca} esc={f.escenario.prob_seca} /></span>
                <span role="cell" data-r="Helada"><DiezCambio hoy={f.hoy.prob_helada_agro} esc={f.escenario.prob_helada_agro} /></span>
                <span role="cell" data-r="Calor"><DiezCambio hoy={f.hoy.prob_calor} esc={f.escenario.prob_calor} /></span>
              </div>
            ))}
          </div>
          {!sinCambio && <p className="fuente" style={{ marginTop: 6 }}>En naranja, los años malos que se sumarían; con borde, los que dejarían de serlo.</p>}
          <details className="tecnico">
            <summary>Cómo se calcula y sus límites</summary>
            <p style={{ margin: "0 0 6px", fontSize: 13, color: "var(--texto-2)" }}>{res.metodo}</p>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: "var(--texto-2)" }}>{res.limites.map((l) => <li key={l}>{l}</li>)}</ul>
          </details>
        </>
      )}
      {!res && !error && <p className="fuente">Calculando con el clima de la NASA…</p>}
    </div>
  );
}
