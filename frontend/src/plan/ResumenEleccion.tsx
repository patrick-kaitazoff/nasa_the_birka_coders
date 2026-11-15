import { useState } from "react";
import { useApp } from "../store";
import { DiezAnios } from "./DiezAnios";
import { fuenteLluvia } from "../comun/fuenteLluvia";
import { cuentas, elegidaDe, menosSecaDentroDelPlan, metaAgricola, sugeridaDe } from "./eleccion";

function fmt(n: number, d = 0) {
  return n.toLocaleString("es-UY", { maximumFractionDigits: d, minimumFractionDigits: d });
}

/** Arriba del Plan: la respuesta en una frase, los números de todo el campo con lo que eligió el productor (contra
 * lo de hoy y su objetivo agrícola) y botones para probar una combinación de un toque. Arranca en
 * la sugerida de cada lote (antes en lo de hoy: quien leía rápido veía la situación actual como si fuera el plan), y
 * la frase dice cómo está hoy y cómo queda con lo que se ve. (rama seca-adelante) va primero la seca en floración, que es lo que más preocupa al productor y
 * donde entran los datos de agua de la NASA; la erosión pasa a ser una condición: el Plan de Uso pasa o no pasa. */
export function ResumenEleccion() {
  const { analisis, plan, campo, elegirVarias } = useApp();
  const [ocupado, setOcupado] = useState(false);
  if (!analisis || !plan) return null;
  const secs = analisis.secciones;
  const hoy = cuentas(secs, (s) => (s.actual ? "actual" : sugeridaDe(plan, s)));
  const ya = cuentas(secs, (s) => elegidaDe(plan, s));
  const meta = metaAgricola(campo);
  const cambiados = secs.filter((s) => s.actual && elegidaDe(plan, s) !== "actual").length;
  const conActual = secs.filter((s) => s.actual).length;

  const presets: Array<{ k: string; t: string; eleccion: Record<string, string> }> = [
    { k: "hoy", t: "Lo de hoy", eleccion: Object.fromEntries(secs.map((s) => [s.id, s.actual ? "actual" : sugeridaDe(plan, s) || "actual"])) },
    { k: "sugerida", t: "La sugerida en cada lote", eleccion: Object.fromEntries(secs.map((s) => [s.id, sugeridaDe(plan, s) || "actual"])) },
    { k: "seca", t: "Menos seca en los cultivos, dentro del Plan de Uso", eleccion: Object.fromEntries(secs.map((s) => [s.id, menosSecaDentroDelPlan(s, sugeridaDe(plan, s)) || "actual"])) },
  ];
  const activo = (e: Record<string, string>) => secs.every((s) => (e[s.id] || sugeridaDe(plan, s)) === elegidaDe(plan, s));
  const iguales = (a: Record<string, string>, b: Record<string, string>) =>
    secs.every((s) => (a[s.id] || sugeridaDe(plan, s)) === (b[s.id] || sugeridaDe(plan, s)));
  // Si dos botones dan la misma elección en todos los lotes, quedaban los
  // dos marcados a la vez y parecía un error. Queda uno solo, con un texto que dice que también es el otro.
  const grupos: Array<{ ks: string[]; eleccion: Record<string, string> }> = [];
  for (const p of presets) {
    const g = grupos.find((x) => iguales(x.eleccion, p.eleccion));
    if (g) g.ks.push(p.k);
    else grupos.push({ ks: [p.k], eleccion: p.eleccion });
  }
  const textoGrupo = (ks: string[]): string => {
    const k = ks.join("+");
    if (k === "hoy+sugerida+seca") return "Lo de hoy, que ya es la sugerida y la de menos seca";
    if (k === "hoy+sugerida") return "Lo de hoy, que ya es la sugerida";
    if (k === "hoy+seca") return "Lo de hoy, que ya es la de menos seca";
    if (k === "sugerida+seca") return "La sugerida en cada lote, que también es la de menos seca";
    return presets.find((p) => p.k === ks[0])!.t;
  };

  async function probar(e: Record<string, string>) {
    if (ocupado) return;
    setOcupado(true);
    try { await elegirVarias(e); } finally { setOcupado(false); }
  }

  // la frase va en tres textos separados, así el traductor de la pantalla reconoce cada uno
  const secaHoy = Math.round(hoy.seca * 10);
  const frase1 = secaHoy >= 1
    ? `Hoy, tus cultivos llegan a la floración con menos de la mitad del agua que necesitan ${fmt(secaHoy)} de cada 10 años.`
    : "Hoy, tus cultivos casi nunca llegan a la floración sin el agua que necesitan.";
  const frase2 = hoy.haSobre > 0
    ? `Además, ${fmt(hoy.haSobre)} de ${fmt(hoy.total)} ha no cumplirían con el Plan de Uso.`
    : "Todo el campo cumple con el Plan de Uso.";
  const igualHoy = cambiados === 0;
  const enSugerida = activo(presets[1].eleccion);
  // cómo queda con lo que se está viendo: la sugerida (al abrir) o lo que eligió el productor
  const secaYa = fmt(ya.seca * 10, 1);
  const frase3 = igualHoy && !enSugerida
    ? "Estás viendo lo de hoy: tocá «La sugerida en cada lote» para ver qué cambia."
    : enSugerida
      ? (ya.haSobre > 0
        ? `Con la sugerida en cada lote: seca en floración ${secaYa} de cada 10 años, y ${fmt(ya.haSobre)} ha no pasan el Plan de Uso.`
        : `Con la sugerida en cada lote: seca en floración ${secaYa} de cada 10 años, y todo el campo cumple con el Plan de Uso.`)
      : (ya.haSobre > 0
        ? `Con lo que elegiste: seca en floración ${secaYa} de cada 10 años, y ${fmt(ya.haSobre)} ha no pasan el Plan de Uso.`
        : `Con lo que elegiste: seca en floración ${secaYa} de cada 10 años, y todo el campo cumple con el Plan de Uso.`);
  const frase4 = "Tocá un lote para ver las otras opciones, con su porqué, y elegí vos.";
  const claseSeca = ya.seca >= 0.3 ? "mal" : ya.seca <= 0.15 ? "bien" : "";

  return (
    <div className="eleccion">
      <p className="eleccion-frase"><span className="eleccion-frase-hoy">{frase1}</span> <span className="eleccion-frase-hoy">{frase2}</span></p>
      <p className="eleccion-frase eleccion-frase-con"><span>{frase3}</span> <span className="eleccion-frase-pie">{frase4}</span></p>
      <div className={`eleccion-kpis ${ya.ingresoUsd ? "" : "tres"}`}>
        <div className={`eleccion-kpi destacado ${claseSeca}`}>
          <div className="k">Años con seca en floración</div>
          <div className="v">{`${fmt(ya.seca * 10, 1)} de cada 10`}</div>
          <DiezAnios p={ya.seca} />
          {ya.perdidaSeco != null && (
            <div className="eleccion-kpi-caida">{`Un año seco pierde ${fmt(ya.perdidaSeco * 100)} % de lo que rendiría con agua`}</div>
          )}
          <div className="s">{igualHoy ? `lo de hoy · lluvia ${fuenteLluvia(analisis)}` : `hoy ${fmt(hoy.seca * 10, 1)} de cada 10${hoy.perdidaSeco != null ? ` · pierde ${fmt(hoy.perdidaSeco * 100)} %` : ""}`}</div>
        </div>
        {/* Sin el «Ingreso relativo», un número fijo por cultivo que no sale de precios
            ni rindes del campo y no se entendía. El margen en dólares queda solo si el productor cargó sus márgenes */}
        {ya.ingresoUsd && (
          <div className="eleccion-kpi">
            <div className="k">Margen medio</div>
            <div className="v">{`${fmt(ya.ingreso)} USD/ha`}</div>
            <div className="s">{`hoy ${fmt(hoy.ingreso)} USD/ha`}</div>
          </div>
        )}
        <div className={`eleccion-kpi ${meta != null && ya.agricola < meta / 2 ? "mal" : ""}`}>
          <div className="k">Agrícola</div>
          <div className="v">{`${fmt(ya.agricola)} %`}</div>
          <div className="eleccion-pista" aria-hidden>
            <div className="lleno" style={{ width: `${Math.min(100, ya.agricola)}%` }} />
            {meta != null && <div className="meta" style={{ left: `${Math.min(100, meta)}%` }} />}
          </div>
          <div className="s">{meta != null ? `tu objetivo: ${fmt(meta)} %` : "de la superficie, en promedio"}</div>
        </div>
        <div className={`eleccion-kpi ${ya.haSobre > 0 ? "mal" : "bien"}`}>
          <div className="k">Plan de Uso</div>
          <div className="v">{ya.haSobre > 0 ? "No cumple" : "Cumple"}</div>
          {ya.haSobre > 0 && <div className="s">{`en ${fmt(ya.haSobre)} de ${fmt(ya.total)} ha`}</div>}
          <div className="s">{`erosión media ${fmt(ya.erosion, 1)} t/ha/año`}</div>
        </div>
      </div>
      {plan.equilibrio?.nota && <p className="eleccion-nota">{plan.equilibrio.nota}</p>}
      {/* Si la lluvia trae meses seguidos casi sin agua (POWER en 2022/23), se dice acá, junto a la seca */}
      {(analisis?.clima?.avisos_lluvia as string[] | undefined)?.map((a) => <p key={a} className="eleccion-nota">{a}</p>)}
      <div className="eleccion-botones">
        <span className="eleccion-rotulo">Probar de un toque:</span>
        {grupos.map((g) => (
          <button key={g.ks.join("+")} type="button" className={`chip ${activo(g.eleccion) ? "on" : ""}`} disabled={ocupado} onClick={() => void probar(g.eleccion)}>{textoGrupo(g.ks)}</button>
        ))}
        <span className="eleccion-cambios">{igualHoy ? "Igual que hoy en todos los lotes" : `${cambiados} de ${conActual} lotes distintos de hoy`}</span>
      </div>
    </div>
  );
}
