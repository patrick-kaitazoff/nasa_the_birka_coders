import { wilson } from "./incertidumbre";

/** 10 cuadros, uno por año: pintados los años con problema. Parte y todo (13-mostrar-los-datos.md). */
export function DiezAnios({ p, anios }: { p: number | null | undefined; anios?: number }) {
  if (p == null) return <span className="sin-dato">no aplica</span>;
  const n = Math.round(10 * p);
  const ic = wilson(p, anios);
  const lo = ic ? Math.round(10 * ic[0]) : null;
  const hi = ic ? Math.round(10 * ic[1]) : null;
  return (
    <span className="diez" title={`${n} de cada 10 años`}>
      <span className="cuadros" aria-hidden>{Array.from({ length: 10 }, (_, k) => <i key={k} className={k < n ? "si" : ic && k < hi! && k >= lo! ? "ic" : ""} />)}</span>
      <span className="num">{n}<small> de 10</small>{ic && lo !== hi && <small className="ic-txt">entre {lo} y {hi}</small>}</span>
    </span>
  );
}

/** Los mismos 10 cuadros con el cambio de un escenario: los años malos que se suman van en naranja y los
 * que dejarían de serlo quedan con borde. */
export function DiezCambio({ hoy, esc }: { hoy: number | null | undefined; esc: number | null | undefined }) {
  if (hoy == null || esc == null) return <span className="sin-dato">no aplica</span>;
  const a = Math.round(10 * hoy);
  const b = Math.round(10 * esc);
  const clase = (k: number) => (k < Math.min(a, b) ? "si" : k < b ? "mas" : k < a ? "menos" : "");
  return (
    <span className="diez" title={`Hoy ${a} de cada 10 años; con el cambio, ${b}`}>
      <span className="cuadros" aria-hidden>{Array.from({ length: 10 }, (_, k) => <i key={k} className={clase(k)} />)}</span>
      <span className="num">{a === b ? <>{b}<small> de 10</small></> : <>{a} → <span className={b > a ? "cambio-sube" : "cambio-baja"}>{b}</span><small> de 10</small></>}</span>
    </span>
  );
}
