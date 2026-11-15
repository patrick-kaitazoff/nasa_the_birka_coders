/** Gráficos SVG propios: livianos, con tooltip al pasar el mouse y tinta de texto (nunca del color de la serie). */
import { useState, type ReactNode } from "react";
import { useIdioma } from "../i18n/idioma";
import { traducir } from "../i18n/traducir";
import { useUS } from "../i18n/region";
import { medidas } from "../i18n/unidades";

const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const TINTA = "#1f2a24", TINTA2 = "#56615a", GRILLA = "#e9e3d6", EJE = "#cdc3b0";
const LLUVIA = "#2f6fae", ET0 = "#c27c0e";

function fmt(n: number, d = 0) {
  return n.toLocaleString("es-UY", { maximumFractionDigits: d, minimumFractionDigits: d });
}

interface Tip { x: number; y: number; contenido: ReactNode }

function Tooltip({ tip, ancho }: { tip: Tip | null; ancho: number }) {
  if (!tip) return null;
  const izq = tip.x > ancho * 0.6;
  return (
    <div style={{
      position: "absolute", left: izq ? undefined : tip.x + 12, right: izq ? ancho - tip.x + 12 : undefined, top: Math.max(0, tip.y - 10),
      background: "#fffdf8", border: "1px solid #cdc3b0", borderRadius: 8, padding: "6px 9px", fontSize: 12, boxShadow: "0 4px 14px rgba(0,0,0,.12)",
      pointerEvents: "none", whiteSpace: "nowrap", zIndex: 5, color: TINTA,
    }}>{tip.contenido}</div>
  );
}

function Leyenda({ items }: { items: Array<{ color: string; t: string; forma?: "barra" | "linea" | "punto" }> }) {
  return (
    <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 12, color: TINTA2, marginBottom: 6 }}>
      {items.map((i) => (
        <span key={i.t} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          {i.forma === "linea" ? <svg width="16" height="8"><path d="M0 4h16" stroke={i.color} strokeWidth="2" /></svg>
            : i.forma === "punto" ? <svg width="10" height="10"><circle cx="5" cy="5" r="4" fill={i.color} /></svg>
            : <span style={{ width: 10, height: 10, borderRadius: 2, background: i.color }} />}
          {i.t}
        </span>
      ))}
    </div>
  );
}

/** Lluvia (barras) y evapotranspiración (línea) por mes, misma escala en mm. */
export function GraficoLluviaET({ mensual: enMm }: { mensual: Array<{ mes: string; lluvia_mm: number; et0_mm: number; balance_mm: number }> }) {
  const [tip, setTip] = useState<Tip | null>(null);
  // en EE. UU. el gráfico entero va en pulgadas: valores, eje, leyenda y tooltip
  const u = medidas(useUS());
  const mensual = enMm.map((d) => ({ ...d, lluvia_mm: u.agua(d.lluvia_mm), et0_mm: u.agua(d.et0_mm), balance_mm: u.agua(d.balance_mm) }));
  const W = 480, H = 240, m = { t: 10, r: 8, b: 26, l: 36 };
  const mayor = Math.max(...mensual.flatMap((d) => [d.lluvia_mm, d.et0_mm]));
  const paso = u.uAgua === "in" ? (mayor > 8 ? 2 : 1) : 50;
  const max = Math.ceil(mayor / paso) * paso;
  const x = (i: number) => m.l + (i + 0.5) * ((W - m.l - m.r) / 12);
  const y = (v: number) => H - m.b - (v / max) * (H - m.t - m.b);
  const bw = (W - m.l - m.r) / 12 - 8;
  const ticks = Array.from({ length: max / paso + 1 }, (_, i) => i * paso);
  return (
    <div style={{ position: "relative" }}>
      <Leyenda items={[{ color: LLUVIA, t: `Lluvia media (${u.uAgua})` }, { color: ET0, t: `Agua que se evapora (ET0, ${u.uAgua})`, forma: "linea" }]} />
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Lluvia y evapotranspiración por mes" onMouseLeave={() => setTip(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={m.l} x2={W - m.r} y1={y(t)} y2={y(t)} stroke={GRILLA} />
            <text x={m.l - 6} y={y(t) + 4} fontSize="11.5" textAnchor="end" fill={TINTA2}>{t}</text>
          </g>
        ))}
        {mensual.map((d, i) => (
          <g key={d.mes}>
            <path d={`M${x(i) - bw / 2},${y(0)} V${y(d.lluvia_mm) + 4} q0,-4 4,-4 h${bw - 8} q4,0 4,4 V${y(0)} Z`} fill={LLUVIA} opacity={0.85} />
            <text x={x(i)} y={H - 8} fontSize="11.5" textAnchor="middle" fill={TINTA2}>{d.mes}</text>
            <rect x={x(i) - bw / 2 - 6} y={m.t} width={bw + 12} height={H - m.t - m.b} fill="transparent"
              onMouseMove={(e) => {
                const r = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                setTip({ x: e.clientX - r.left, y: e.clientY - r.top, contenido: <><b>{d.mes}</b><br />{`Lluvia ${fmt(d.lluvia_mm, u.decAgua)} ${u.uAgua} · ET0 ${fmt(d.et0_mm, u.decAgua)} ${u.uAgua}`}<br />{`Balance ${d.balance_mm > 0 ? "+" : ""}${fmt(d.balance_mm, u.decAgua)} ${u.uAgua}`}</> });
              }} />
          </g>
        ))}
        <path d={mensual.map((d, i) => `${i ? "L" : "M"}${x(i)},${y(d.et0_mm)}`).join(" ")} fill="none" stroke={ET0} strokeWidth="2" />
        {mensual.map((d, i) => <circle key={i} cx={x(i)} cy={y(d.et0_mm)} r="4" fill={ET0} stroke="#fffdf8" strokeWidth="2" pointerEvents="none" />)}
        <line x1={m.l} x2={W - m.r} y1={y(0)} y2={y(0)} stroke={EJE} />
      </svg>
      <Tooltip tip={tip} ancho={W} />
    </div>
  );
}

/** Frecuencia de tormentas de 50 mm o más por mes (barritas). */
export function GraficoTormentasMes({ por_mes }: { por_mes: number[] }) {
  const [tip, setTip] = useState<Tip | null>(null);
  const W = 480, H = 160, m = { t: 14, r: 8, b: 24, l: 32 };
  const maxVal = Math.max(...por_mes, 0.4);
  const max = Math.ceil(maxVal * 2) / 2;
  const x = (i: number) => m.l + (i + 0.5) * ((W - m.l - m.r) / 12);
  const y = (v: number) => H - m.b - (v / max) * (H - m.t - m.b);
  const bw = (W - m.l - m.r) / 12 - 8;
  const ticks = [0, max / 2, max];
  return (
    <div style={{ position: "relative" }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Lluvias de 50 mm o más por mes" onMouseLeave={() => setTip(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={m.l} x2={W - m.r} y1={y(t)} y2={y(t)} stroke={GRILLA} />
            <text x={m.l - 6} y={y(t) + 4} fontSize="11" textAnchor="end" fill={TINTA2}>{fmt(t, 1)}</text>
          </g>
        ))}
        {por_mes.map((v, i) => (
          <g key={i}>
            <rect
              x={x(i) - bw / 2}
              y={y(v)}
              width={bw}
              height={Math.max(2, y(0) - y(v))}
              rx={3}
              fill={LLUVIA}
              opacity={0.85}
            />
            <text x={x(i)} y={H - 7} fontSize="11" textAnchor="middle" fill={TINTA2}>{MESES[i]}</text>
            <rect
              x={x(i) - bw / 2 - 4}
              y={m.t}
              width={bw + 8}
              height={H - m.t - m.b}
              fill="transparent"
              onMouseMove={(e) => {
                const r = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                setTip({
                  x: e.clientX - r.left,
                  y: e.clientY - r.top,
                  contenido: <><b>{MESES[i]}</b><br />{`${fmt(v, 2)} lluvias ≥ 50 mm por año`}</>,
                });
              }}
            />
          </g>
        ))}
        <line x1={m.l} x2={W - m.r} y1={y(0)} y2={y(0)} stroke={EJE} />
      </svg>
      <Tooltip tip={tip} ancho={W} />
    </div>
  );
}

export interface MetricaAntesAhora {
  antes: number;
  ahora: number;
  k_antes?: number;
  n_antes?: number;
  k_ahora?: number;
  n_ahora?: number;
  cambio_claro?: boolean;
}

export interface FilaCultivoAntesAhora {
  cod: string;
  nombre: string;
  enPlan?: boolean;
  seca?: MetricaAntesAhora;
  calor?: MetricaAntesAhora;
}

function DumbbellMetrica({
  m,
  tipo,
  nombreCultivo,
  periodoAntes,
  periodoAhora,
  onHover,
}: {
  m?: MetricaAntesAhora;
  tipo: "Seca" | "Calor";
  nombreCultivo: string;
  periodoAntes: string;
  periodoAhora: string;
  onHover: (tip: Tip | null) => void;
}) {
  if (!m || m.antes == null || m.ahora == null) {
    return <span className="sin-dato" style={{ fontSize: 12, color: "#8a968f" }}>sin dato</span>;
  }
  const esClaro = m.cambio_claro ?? (Math.abs(m.ahora - m.antes) >= 0.2);
  const peor = m.ahora > m.antes;
  const dAntes = Math.round(m.antes * 10);
  const dAhora = Math.round(m.ahora * 10);

  const W = 96, H = 20;
  const x = (v: number) => 8 + Math.max(0, Math.min(1, v)) * (W - 16);
  const xA = x(m.antes), xB = x(m.ahora);

  const colorLinea = esClaro ? (peor ? "#e3a99d" : "#a9cdb6") : "#d6ded9";
  const colorAhora = esClaro ? (peor ? "#b3412e" : "#2b6a4f") : "#9aa59e";
  const colorAntes = "#9aa59e";

  const textoAños = m.k_antes != null && m.n_antes != null && m.k_ahora != null && m.n_ahora != null
    ? `${m.k_antes} de ${m.n_antes} años (${periodoAntes}) → ${m.k_ahora} de ${m.n_ahora} años (${periodoAhora})`
    : `${dAntes} de cada 10 años (${periodoAntes}) → ${dAhora} de cada 10 años (${periodoAhora})`;

  const textoDetalle = esClaro
    ? (peor ? `subió de ${dAntes} a ${dAhora} de cada 10` : `bajó de ${dAntes} a ${dAhora} de cada 10`)
    : "sin cambio claro";

  const handlePointer = (e: React.MouseEvent<HTMLDivElement> | React.TouchEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const clientX = "touches" in e ? e.touches[0].clientX : e.clientX;
    const clientY = "touches" in e ? e.touches[0].clientY : e.clientY;
    onHover({
      x: clientX - rect.left,
      y: clientY - rect.top,
      contenido: (
        <div>
          <b>{nombreCultivo} · {tipo === "Seca" ? "Seca en floración" : "Calor extremo"}</b>
          <div style={{ marginTop: 2 }}>{textoAños}</div>
          <div style={{ marginTop: 2, fontWeight: 650, color: colorAhora }}>
            {textoDetalle}
          </div>
        </div>
      ),
    });
  };

  return (
    <div
      className="dumbbell-celda"
      onMouseMove={handlePointer}
      onTouchStart={handlePointer}
      title={`${nombreCultivo} · ${tipo}: ${textoAños} · ${textoDetalle}`}
    >
      <svg width={W} height={H} className="dumbbell-svg" aria-hidden="true">
        <line x1={8} x2={W - 8} y1={H / 2} y2={H / 2} stroke="#eee8dd" strokeWidth="3" strokeLinecap="round" />
        <line x1={xA} x2={xB} y1={H / 2} y2={H / 2} stroke={colorLinea} strokeWidth="3.5" strokeLinecap="round" />
        <circle cx={xA} cy={H / 2} r="4.5" fill={colorAntes} stroke="#fffdf8" strokeWidth="1.5" />
        <circle cx={xB} cy={H / 2} r="4.5" fill={colorAhora} stroke="#fffdf8" strokeWidth="1.5" />
      </svg>
      <span className={`dumbbell-rotulo ${esClaro ? (peor ? "peor" : "mejor") : "sin-cambio"}`}>
        {esClaro ? `${dAntes} → ${dAhora}` : "sin cambio claro"}
      </span>
    </div>
  );
}

/** Antes contra ahora por cultivo: una fila por cultivo con seca y calor juntos en dos columnas. */
export function GraficoAntesAhora({
  cultivos,
  filas,
  antes,
  ahora,
}: {
  cultivos?: FilaCultivoAntesAhora[];
  filas?: Array<{ t: string; antes: number; ahora: number }>;
  antes: string;
  ahora: string;
}) {
  const [tip, setTip] = useState<Tip | null>(null);
  // los rótulos de cada métrica en la tarjeta angosta salen de un atributo (CSS content), que el traductor de la
  // pantalla no ve: se traducen acá
  const idioma = useIdioma((x) => x.idioma);
  const rotulo = (t: string) => (idioma === "en" ? traducir(t) : t);

  const filasCultivos: FilaCultivoAntesAhora[] = cultivos || (filas ? filas.map((f) => ({
    cod: f.t,
    nombre: f.t,
    seca: { antes: f.antes, ahora: f.ahora },
  })) : []);

  return (
    <div className="contenedor-antes-ahora" onMouseLeave={() => setTip(null)}>
      <Leyenda
        items={[
          { color: "#9aa59e", t: antes, forma: "punto" },
          { color: "#b3412e", t: `${ahora} (cambio claro)`, forma: "punto" },
          { color: "#717d75", t: "sin cambio claro" },
        ]}
      />
      <div className="tabla-antes-ahora" role="table" aria-label="Tu clima ya cambió: antes y ahora por cultivo">
        <div className="fila-antes-ahora cabecera" role="row">
          <span className="col-cultivo" role="columnheader">Cultivo</span>
          <span className="col-metrica" role="columnheader">Seca en floración</span>
          <span className="col-metrica" role="columnheader">Calor extremo</span>
        </div>
        {filasCultivos.map((c) => (
          <div key={c.cod} className={`fila-antes-ahora ${c.enPlan ? "en-plan" : ""}`} role="row">
            <div className="col-cultivo" role="cell">
              <b>{c.nombre}</b>
              {c.enPlan && <em className="etq-en-plan">en tu plan</em>}
            </div>
            <div className="col-metrica" role="cell" data-label={rotulo("Seca en floración")}>
              <DumbbellMetrica
                m={c.seca}
                tipo="Seca"
                nombreCultivo={c.nombre}
                periodoAntes={antes}
                periodoAhora={ahora}
                onHover={setTip}
              />
            </div>
            <div className="col-metrica" role="cell" data-label={rotulo("Calor extremo")}>
              <DumbbellMetrica
                m={c.calor}
                tipo="Calor"
                nombreCultivo={c.nombre}
                periodoAntes={antes}
                periodoAhora={ahora}
                onHover={setTip}
              />
            </div>
          </div>
        ))}
      </div>
      <Tooltip tip={tip} ancho={500} />
    </div>
  );
}

/**
 * La ventana de peligro: arriba, cuánta lluvia erosiva cae cada mes (NASA POWER); abajo, una fila por
 * opción con la cobertura del suelo de cada mes. Recuadro rojo = suelo descubierto en un mes de lluvia fuerte.
 */
function dividirNombre(s: string): [string] | [string, string] {
  if (s.length <= 28) return [s];
  const idxParen = s.indexOf(" (");
  if (idxParen > 0) return [s.slice(0, idxParen), s.slice(idxParen + 1)];
  const idxDosPuntos = s.indexOf(": ");
  if (idxDosPuntos > 0 && idxDosPuntos <= 22) return [s.slice(0, idxDosPuntos + 1), s.slice(idxDosPuntos + 2)];
  if (s.includes(" → ")) {
    const arrows: number[] = [];
    let pos = 0;
    while (true) {
      const i = s.indexOf(" → ", pos);
      if (i === -1) break;
      arrows.push(i);
      pos = i + 3;
    }
    const mid = s.length / 2;
    const best = arrows.reduce((prev, curr) => (Math.abs(curr - mid) < Math.abs(prev - mid) ? curr : prev));
    return [s.slice(0, best), s.slice(best + 1)];
  }
  const mid = s.length / 2;
  const spaces: number[] = [];
  for (let i = 0; i < s.length; i++) if (s[i] === " ") spaces.push(i);
  if (spaces.length) {
    const best = spaces.reduce((prev, curr) => (Math.abs(curr - mid) < Math.abs(prev - mid) ? curr : prev));
    return [s.slice(0, best), s.slice(best + 1)];
  }
  return [s];
}

export function VentanaPeligro({ reparto, filas, fuente = "NASA POWER" }: { reparto: number[]; filas: Array<{ t: string; cobertura: number[]; destacada?: boolean }>; fuente?: string }) {
  const [tip, setTip] = useState<Tip | null>(null);
  const W = 940, alto_barras = 70, fila = 36, m = { t: 6, r: 10, l: 285 };
  const H = m.t + alto_barras + 22 + filas.length * fila + 8;
  const cw = (W - m.l - m.r) / 12;
  const maxR = Math.max(...reparto);
  const color = (c: number) => {
    // secuencial de un solo tono: marrón tierra (descubierto) → verde (cubierto), por luminosidad
    const pasos = ["#efe2cc", "#dccfa0", "#b9c98f", "#86b07a", "#4f9a6f", "#2b6a4f"];
    return pasos[Math.min(pasos.length - 1, Math.floor(c * pasos.length))];
  };
  const media = 1 / 12;
  return (
    <div style={{ position: "relative" }}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Meses con suelo descubierto y lluvia erosiva" onMouseLeave={() => setTip(null)}>
        <text x={m.l - 12} y={m.t + 14} fontSize="11.5" textAnchor="end" fill={TINTA} fontWeight={600}>Lluvia fuerte de cada mes</text>
        <text x={m.l - 12} y={m.t + 30} fontSize="10.5" textAnchor="end" fill={TINTA2}>{`en % del año (${fuente})`}</text>
        {reparto.map((r, i) => {
          const h = (r / maxR) * (alto_barras - 8);
          const fuerte = r >= media;
          return (
            <g key={i}>
              <rect x={m.l + i * cw + 6} y={m.t + alto_barras - h} width={cw - 12} height={h} rx="3" fill={fuerte ? "#2f6fae" : "#a9c3df"} />
              <text x={m.l + i * cw + cw / 2} y={m.t + alto_barras - h - 3} fontSize="9.5" textAnchor="middle" fill={TINTA2}>{Math.round(r * 100)}</text>
            </g>
          );
        })}
        {MESES.map((mm, i) => <text key={mm} x={m.l + i * cw + cw / 2} y={m.t + alto_barras + 15} fontSize="11" textAnchor="middle" fill={TINTA2}>{mm}</text>)}
        {filas.map((f, j) => {
          const y0 = m.t + alto_barras + 22 + j * fila;
          const lineas = dividirNombre(f.t);
          const peso = f.destacada ? 700 : 500;
          return (
            <g key={f.t}>
              {lineas.length === 1 ? (
                <text x={m.l - 12} y={y0 + fila / 2 + 4} fontSize="12" textAnchor="end" fill={TINTA} fontWeight={peso}>
                  {lineas[0]}
                </text>
              ) : (
                <text x={m.l - 12} y={y0 + fila / 2 - 2} fontSize="11.5" textAnchor="end" fill={TINTA} fontWeight={peso}>
                  <tspan x={m.l - 12}>{lineas[0]}</tspan>
                  <tspan x={m.l - 12} dy="13.5" fontSize="11" fill={f.destacada ? TINTA : TINTA2}>
                    {lineas[1]}
                  </tspan>
                </text>
              )}
              {f.cobertura.map((c, i) => {
                const peligro = c < 0.5 && reparto[i] >= media;
                return (
                  <g key={i}>
                    <rect x={m.l + i * cw + 1} y={y0 + 3} width={cw - 2} height={fila - 6} rx="4" fill={color(c)} stroke={peligro ? "#b3412e" : "none"} strokeWidth={peligro ? 2.2 : 0}
                      onMouseMove={(e) => {
                        const r = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                        setTip({ x: e.clientX - r.left, y: e.clientY - r.top, contenido: <><b>{f.t}</b> · {MESES[i]}<br />Suelo cubierto {Math.round(c * 100)} %<br />Lluvia erosiva del mes: {Math.round(reparto[i] * 100)} % del año{peligro ? <><br /><b style={{ color: "#b3412e" }}>Suelo expuesto con lluvia fuerte</b></> : null}</> });
                      }} />
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
      <div style={{ display: "flex", gap: 12, alignItems: "center", fontSize: 11.5, color: TINTA2, flexWrap: "wrap" }}>
        <span>Suelo cubierto:</span>
        {[0, 0.2, 0.4, 0.6, 0.8, 1].map((c) => <span key={c} style={{ display: "inline-flex", gap: 4, alignItems: "center" }}><span style={{ width: 14, height: 10, borderRadius: 3, background: color(Math.min(c, 0.99)) }} />{Math.round(c * 100)} %</span>)}
        <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}><span style={{ width: 14, height: 10, borderRadius: 3, border: "2px solid #b3412e" }} />expuesto en mes de lluvia fuerte</span>
      </div>
      <Tooltip tip={tip} ancho={W} />
    </div>
  );
}

/** NDVI de MODIS y HLS en el tiempo, con las franjas de "descubierto" y "cultivo activo". */
export function GraficoNDVI({
  serie,
  serieHls,
  umbrales,
  corteAuto,
}: {
  serie: Array<{ anio: number; mes: number; ndvi: number }>;
  serieHls?: Array<{ anio: number; mes: number; ndvi: number }>;
  umbrales?: { descubierto: number; cultivo: number };
  corteAuto?: number | null;
}) {
  const [tip, setTip] = useState<Tip | null>(null);
  const puntosModis = (serie || []).filter((d) => d.ndvi != null);
  const puntosHls = (serieHls || []).filter((d) => d.ndvi != null);
  const todos = [...puntosModis, ...puntosHls];
  if (!todos.length) return <div className="fuente">Sin datos de NDVI.</div>;

  const W = 460, H = 200, m = { t: 10, r: 8, b: 24, l: 32 };
  const t0 = Math.min(...todos.map((s) => s.anio * 12 + s.mes));
  const t1 = Math.max(...todos.map((s) => s.anio * 12 + s.mes));
  const x = (d: { anio: number; mes: number }) => m.l + ((d.anio * 12 + d.mes - t0) / Math.max(1, t1 - t0)) * (W - m.l - m.r);
  const y = (v: number) => H - m.b - (Math.max(0, Math.min(1, v)) / 0.9) * (H - m.t - m.b);
  const u = umbrales || { descubierto: 0.3, cultivo: 0.55 };
  const anios = Array.from(new Set(todos.map((s) => s.anio))).sort((a, b) => a - b);

  const mapaModis = new Map(puntosModis.map((s) => [`${s.anio}-${s.mes}`, s.ndvi]));
  const mapaHls = new Map(puntosHls.map((h) => [`${h.anio}-${h.mes}`, h.ndvi]));
  const mesesUnicos = Array.from(
    new Map(todos.map((d) => [`${d.anio}-${d.mes}`, { anio: d.anio, mes: d.mes }])).values()
  ).sort((a, b) => a.anio * 12 + a.mes - (b.anio * 12 + b.mes));
  const tieneHls = puntosHls.length > 0;

  return (
    <div style={{ position: "relative" }}>
      {tieneHls && (
        <Leyenda
          items={[
            { color: "#2b6a4f", t: "MODIS (250 m, punto)", forma: "linea" },
            { color: "#2f6fae", t: "HLS (30 m, polígono)", forma: "linea" },
          ]}
        />
      )}
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="NDVI mensual" onMouseLeave={() => setTip(null)}>
        <rect x={m.l} y={y(u.descubierto)} width={W - m.l - m.r} height={y(0) - y(u.descubierto)} fill="#f3e6d0" />
        <rect x={m.l} y={y(0.9)} width={W - m.l - m.r} height={y(u.cultivo) - y(0.9)} fill="#e6f1e8" />
        <text x={W - m.r - 4} y={y(u.descubierto) + 12} fontSize="10.5" textAnchor="end" fill="#8a6a3d">suelo descubierto o rastrojo</text>
        <text x={W - m.r - 4} y={y(0.9) + 12} fontSize="10.5" textAnchor="end" fill="#2b6a4f">cultivo o pastura activa</text>
        {[0, 0.3, 0.6, 0.9].map((t) => <text key={t} x={m.l - 5} y={y(t) + 4} fontSize="10.5" textAnchor="end" fill={TINTA2}>{t.toFixed(1).replace(".", ",")}</text>)}
        {anios.map((a) => {
          const xx = x({ anio: a, mes: 1 });
          return xx >= m.l ? <g key={a}><line x1={xx} x2={xx} y1={m.t} y2={H - m.b} stroke={GRILLA} /><text x={xx + 3} y={H - 8} fontSize="11" fill={TINTA2}>{a}</text></g> : null;
        })}
        {corteAuto != null && (
          <g>
            <line x1={m.l} x2={W - m.r} y1={y(corteAuto)} y2={y(corteAuto)} stroke="#7a4fb3" strokeWidth="1.5" strokeDasharray="5 4" />
            <text x={m.l + 4} y={y(corteAuto) - 4} fontSize="10.5" fill="#5b3a8a">corte automático {corteAuto.toFixed(2).replace(".", ",")}</text>
          </g>
        )}
        {puntosHls.length > 0 && (
          <path d={puntosHls.map((d, i) => `${i ? "L" : "M"}${x(d)},${y(d.ndvi)}`).join(" ")} fill="none" stroke="#2f6fae" strokeWidth="2" strokeDasharray="4 2" />
        )}
        {puntosModis.length > 0 && (
          <path d={puntosModis.map((d, i) => `${i ? "L" : "M"}${x(d)},${y(d.ndvi)}`).join(" ")} fill="none" stroke="#2b6a4f" strokeWidth="2" />
        )}
        {mesesUnicos.map((d) => {
          const mVal = mapaModis.get(`${d.anio}-${d.mes}`);
          const hVal = mapaHls.get(`${d.anio}-${d.mes}`);
          const yRef = y(mVal ?? hVal ?? 0.5);
          return (
            <circle
              key={`${d.anio}-${d.mes}`}
              cx={x(d)}
              cy={yRef}
              r="7"
              fill="transparent"
              onMouseMove={(e) => {
                const r = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                setTip({
                  x: e.clientX - r.left,
                  y: e.clientY - r.top,
                  contenido: (
                    <>
                      <b>{MESES[d.mes - 1]} {d.anio}</b>
                      {mVal != null && (
                        <div>MODIS (250 m): <b>{mVal.toFixed(2).replace(".", ",")}</b></div>
                      )}
                      {hVal != null && (
                        <div>HLS (30 m): <b>{hVal.toFixed(2).replace(".", ",")}</b></div>
                      )}
                    </>
                  ),
                });
              }}
            />
          );
        })}
      </svg>
      <Tooltip tip={tip} ancho={W} />
    </div>
  );
}

/** Erosión contra tolerancia: barra con la marca de T (bullet chart). */
type RangoBarra = { p10: number; p90: number; prob_supera_t: number };

/** Hasta dónde llega la barra de erosión para que entren el valor, el rango y la marca de la tolerancia. */
export function escalaErosion(a: number, t: number, rango?: RangoBarra | null): number {
  return Math.max(t * 1.8, a * 1.15, rango ? rango.p90 * 1.08 : 0, 1);
}

/** `escala`: el máximo común cuando hay varias barras una al lado de la otra (las opciones de un lote en Comparar).
 * Sin eso, cada barra usaba el suyo y en La Loma 3,2 y 58,9 t/ha/año llenaban casi igual. */
export function BarraErosion({ a, t, rango, escala }: { a: number; t: number; rango?: RangoBarra | null; escala?: number }) {
  const max = Math.max(escala ?? 0, escalaErosion(a, t, rango));
  const pct = (v: number) => `${Math.min(100, Math.max(0, (v / max) * 100))}%`;
  const cumple = a <= t;
  return (
    <div className="barra-erosion">
      <div className="barra-erosion-cab">
        {/* número y unidad en un solo texto: así se convierten juntos en EE. UU. */}
        <span className="barra-erosion-val">{`Erosión ${fmt(a, 1)} t/ha/año`}</span>
        <span className="barra-erosion-tol">{`tolerancia ${fmt(t, 0)} t/ha`}</span>
      </div>
      <div className="barra-erosion-pista">
        <div
          className={`barra-erosion-fill ${cumple ? "bien" : "mal"}`}
          style={{ width: pct(a) }}
        />
        {rango && (
          <>
            <div
              className={`barra-erosion-rango ${cumple ? "bien" : "mal"}`}
              style={{
                left: pct(rango.p10),
                width: `calc(${pct(rango.p90)} - ${pct(rango.p10)})`,
              }}
              title="Entre dónde cae la erosión 8 de cada 10 veces, moviendo los datos dudosos"
            />
            <div
              className="barra-erosion-whisker"
              style={{
                left: pct(rango.p10),
                width: `calc(${pct(rango.p90)} - ${pct(rango.p10)})`,
              }}
            />
          </>
        )}
        <div
          className="barra-erosion-tol-pin"
          style={{ left: pct(t) }}
          title="Tolerancia del suelo"
        />
      </div>
      {rango && (
        <div className="barra-erosion-sub">
          {/* un solo texto, para que el traductor de la pantalla reconozca la frase entera */}
          {`Entre ${fmt(rango.p10, 1)} y ${fmt(rango.p90, 1)} t/ha/año · supera la tolerancia en ${Math.round(rango.prob_supera_t * 100)} % de los casos`}
        </div>
      )}
    </div>
  );
}

/** Humedad del suelo: anomalía mensual de SMAP y GLDAS contra la del balance de la app (cuánto se aparta cada mes de
 * lo normal para ese mes, en desvíos). Arriba de la línea del medio, más húmedo que lo normal. */
export function GraficoHumedad({ mensual }: { mensual: Array<{ mes: string; smap_anomalia: number; app_anomalia: number; gldas_anomalia?: number | null }> }) {
  const [tip, setTip] = useState<Tip | null>(null);
  if (!mensual?.length) return null;
  const W = 480, H = 210, m = { t: 12, r: 8, b: 24, l: 30 };
  const todosValores = mensual.flatMap((d) => [
    Math.abs(d.smap_anomalia),
    Math.abs(d.app_anomalia),
    ...(d.gldas_anomalia != null ? [Math.abs(d.gldas_anomalia)] : []),
  ]);
  const lim = Math.max(2, Math.ceil(Math.max(...todosValores)));
  const x = (i: number) => m.l + (i / Math.max(1, mensual.length - 1)) * (W - m.l - m.r);
  const y = (v: number) => m.t + ((lim - Math.max(-lim, Math.min(lim, v))) / (2 * lim)) * (H - m.t - m.b);
  const linea = (k: "smap_anomalia" | "app_anomalia" | "gldas_anomalia") =>
    mensual
      .filter((d) => d[k] != null)
      .map((d, i) => `${i ? "L" : "M"}${x(mensual.indexOf(d))},${y(d[k] as number)}`)
      .join(" ");

  const SMAP = "#2f6fae", APP = "#c27c0e", GLDAS = "#6b46c1";
  const hayGldas = mensual.some((d) => d.gldas_anomalia != null);

  return (
    <div style={{ position: "relative", maxWidth: 620 }}>
      <Leyenda
        items={[
          { color: SMAP, t: "SMAP (satélite + modelo, 0-100 cm)", forma: "linea" },
          { color: APP, t: "Balance de la app (lluvia y ET0 de POWER)", forma: "linea" },
          ...(hayGldas ? [{ color: GLDAS, t: "GLDAS (modelo Noah, 0-100 cm, 2000-hoy)", forma: "linea" as const }] : []),
        ]}
      />
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Humedad del suelo: SMAP y GLDAS contra el balance de la app" onMouseLeave={() => setTip(null)}>
        <rect x={m.l} y={m.t} width={W - m.l - m.r} height={y(0) - m.t} fill="#eaf1f7" />
        <rect x={m.l} y={y(0)} width={W - m.l - m.r} height={H - m.b - y(0)} fill="#f6ecdc" />
        <text x={W - m.r - 4} y={m.t + 12} fontSize="10.5" textAnchor="end" fill="#2f5f8a">más húmedo que lo normal</text>
        <text x={W - m.r - 4} y={H - m.b - 5} fontSize="10.5" textAnchor="end" fill="#8a6a3d">más seco que lo normal</text>
        <line x1={m.l} x2={W - m.r} y1={y(0)} y2={y(0)} stroke={EJE} />
        {mensual.map((d, i) => d.mes.endsWith("-01") ? (
          <g key={d.mes}><line x1={x(i)} x2={x(i)} y1={m.t} y2={H - m.b} stroke={GRILLA} /><text x={x(i) + 3} y={H - 8} fontSize="11" fill={TINTA2}>{d.mes.slice(0, 4)}</text></g>
        ) : null)}
        {hayGldas && <path d={linea("gldas_anomalia")} fill="none" stroke={GLDAS} strokeWidth="2" strokeDasharray="4 3" />}
        <path d={linea("app_anomalia")} fill="none" stroke={APP} strokeWidth="2" />
        <path d={linea("smap_anomalia")} fill="none" stroke={SMAP} strokeWidth="2" />
        {mensual.map((d, i) => (
          <rect key={d.mes} x={x(i) - 5} y={m.t} width={10} height={H - m.t - m.b} fill="transparent"
            onMouseMove={(e) => {
              const r = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
              const [a, mm] = d.mes.split("-");
              setTip({
                x: e.clientX - r.left,
                y: e.clientY - r.top,
                contenido: (
                  <>
                    <b>{MESES[+mm - 1]} {a}</b><br />
                    SMAP: <b>{fmt(d.smap_anomalia, 1)}</b> · app: <b>{fmt(d.app_anomalia, 1)}</b>
                    {d.gldas_anomalia != null ? <> · GLDAS: <b>{fmt(d.gldas_anomalia, 1)}</b></> : null} desvíos
                  </>
                ),
              });
            }} />
        ))}
      </svg>
      <Tooltip tip={tip} ancho={W} />
    </div>
  );
}
