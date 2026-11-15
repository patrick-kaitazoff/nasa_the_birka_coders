import type { TemporadaHistUI } from "../api";

/**
 * Dos filas de franjas, una por temporada desde 2000: «Lo que se hizo» y «Con este plan».
 *
 * Las dos filas usan la MISMA medida: cómo estuvo el lote en el momento crítico del cultivo de esa temporada,
 * según el balance de agua FAO-56 con el clima diario de NASA POWER (eta_etc: agua que tuvo / agua que pedía).
 * Si no hubo cultivo de cosecha, se dice si el suelo estuvo cubierto (pastura, cobertura) o descubierto
 * (barbecho). Si no se sabe qué hubo, va en gris como «sin dato»: nunca otra medida (como la lluvia del año)
 * haciéndose pasar por esta.
 */

export type ClaveCategoria = "falta" | "justa" | "bien" | "cubierto" | "descubierto" | "sin_dato";

export const CATEGORIAS: Record<ClaveCategoria, { color: string; rotulo: string }> = {
  falta: { color: "#b3412e", rotulo: "Le faltó agua (menos de la mitad)" },
  justa: { color: "#e0a03a", rotulo: "Agua justa (de la mitad al 70 %)" },
  bien: { color: "#5c9e64", rotulo: "Con el agua que pedía (70 % o más)" },
  cubierto: { color: "#2f6646", rotulo: "Pastura o cobertura" },
  descubierto: { color: "#bba98a", rotulo: "Suelo descubierto" },
  sin_dato: { color: "#e3e7e4", rotulo: "Sin dato" },
};

const ORDEN: ClaveCategoria[] = ["falta", "justa", "bien", "cubierto", "descubierto", "sin_dato"];
const COBERTURA = new Set(["cobertura", "verdeo", "pradera", "campo_natural"]);

export function categoria(codigo: string | undefined, eta: number | null | undefined): ClaveCategoria {
  if (!codigo || codigo === "sin_datos") return "sin_dato";
  if (codigo === "barbecho") return "descubierto";
  if (eta != null) return eta < 0.5 ? "falta" : eta < 0.7 ? "justa" : "bien";
  return COBERTURA.has(codigo) ? "cubierto" : "sin_dato";
}

export const categoriaReal = (t: TemporadaHistUI) => categoria(t.cultivo_real.codigo, t.cultivo_real.eta_etc);
export const categoriaPlan = (t: TemporadaHistUI) => categoria(t.propuesta.codigo, t.propuesta.eta_etc);

function detalle(nombre: string, cat: ClaveCategoria, eta: number | null): string {
  if (cat === "sin_dato") return "sin dato";
  if (eta != null) return `${nombre}, ${Math.round(eta * 100)} % del agua que pedía`;
  return `${nombre}, ${CATEGORIAS[cat].rotulo.toLowerCase()}`;
}

export function DosFilas({
  temporadas,
  activa,
  onElegir,
  compacto = false,
}: {
  temporadas: TemporadaHistUI[];
  activa?: string;
  onElegir: (temporada: string) => void;
  compacto?: boolean;
}) {
  if (temporadas.length === 0) return null;
  // Solo «Lo que se hizo». La fila «Con este plan» se sacó: aplicaba el plan al pasado empezando por
  // cualquier cultivo de la rotación y se leía como un pronóstico
  const filas: Array<{ id: "real" | "plan"; rotulo: string; cat: (t: TemporadaHistUI) => ClaveCategoria }> = [
    { id: "real", rotulo: "Lo que se hizo", cat: categoriaReal },
  ];
  const usadas = new Set<ClaveCategoria>();
  temporadas.forEach((t) => {
    usadas.add(categoriaReal(t));
  });
  // marcas del eje: la primera temporada de cada lustro, en la posición que ocupa en la fila
  const marcas: Array<{ anio: number; pct: number }> = [];
  temporadas.forEach((t, i) => {
    const a = t.anio_agricola;
    if (a % 5 === 0 && !marcas.some((m) => m.anio === a)) marcas.push({ anio: a, pct: (100 * i) / temporadas.length });
  });

  return (
    <div className={`dos-filas ${compacto ? "compacto" : ""}`}>
      {filas.map((f) => (
        <div className="df-fila" key={f.id}>
          <span className="df-rotulo">{f.rotulo}</span>
          <div className="df-barra" role="group" aria-label={f.rotulo}>
            {temporadas.map((t) => {
              const c = f.cat(t);
              const nombre = f.id === "real" ? t.cultivo_real.nombre : t.propuesta.nombre;
              const eta = f.id === "real" ? t.cultivo_real.eta_etc : t.propuesta.eta_etc;
              const texto = `${t.temporada}: ${detalle(nombre, c, eta)}`;
              return (
                <button
                  key={t.temporada}
                  type="button"
                  className={`df-franja ${t.temporada === activa ? "activa" : ""} ${t.es_estrella ? "estrella" : ""}`}
                  style={{ background: CATEGORIAS[c].color }}
                  title={texto}
                  aria-label={texto}
                  onClick={() => onElegir(t.temporada)}
                />
              );
            })}
          </div>
        </div>
      ))}
      <div className="df-fila df-fila-eje" aria-hidden>
        <span className="df-rotulo" />
        <div className="df-eje">
          {marcas.map((m) => (
            <span key={m.anio} style={{ left: `${m.pct}%` }}>{m.anio}</span>
          ))}
        </div>
      </div>
      <div className="df-leyenda">
        {ORDEN.filter((k) => usadas.has(k)).map((k) => (
          <span key={k} className="leyenda-item">
            <i style={{ backgroundColor: CATEGORIAS[k].color }} /> {CATEGORIAS[k].rotulo}
          </span>
        ))}
        <span className="leyenda-item"><i className="df-leyenda-estrella" /> Seca 2022-23</span>
      </div>
    </div>
  );
}
