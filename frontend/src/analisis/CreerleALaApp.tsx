import { useEffect } from "react";
import { useApp } from "../store";
import { Cargando } from "../comun/Cargando";
import { DosFilas, categoriaReal, type ClaveCategoria } from "../historia/Franjas";

/**
 * «¿Le podemos creer a la app?», en Datos.
 * Primero cuántas temporadas coincidió el balance de agua de la app con el verdor que vio el satélite, después las
 * franjas de lo que se hizo en cada lote desde 2000 y la seca de 2022/23. Sin la fila «Con este plan».
 */

const REAL_PASO: Record<ClaveCategoria, string> = {
  falta: "le faltó agua",
  justa: "llegó con el agua justa",
  bien: "tuvo el agua que pedía",
  cubierto: "tuvo el suelo cubierto",
  descubierto: "dejó el suelo descubierto",
  sin_dato: "",
};

export function CreerleALaApp() {
  const { historia, historiaCargando, historiaError, cargarHistoria, campo, seccionSel, setSeccionSel, abrirHistoria } = useApp();

  useEffect(() => {
    if (historiaCargando || campo.secciones.length === 0) return;
    if (!historia && !historiaError) void cargarHistoria();
  }, [historia, historiaCargando, historiaError, campo.secciones.length, cargarHistoria]);

  const secciones = historia?.secciones || [];
  const sec = secciones.find((s) => s.seccion_id === seccionSel) || secciones[0];
  const global = historia?.resumen_global;

  let cuerpo: React.ReactNode;
  if (historiaCargando) {
    cuerpo = <Cargando que="calculando" size={32} etiqueta="Trayendo la historia de tu campo desde 2000…" />;
  } else if (historiaError && !historia) {
    cuerpo = (
      <div className="fila" style={{ gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <span className="bajada" style={{ margin: 0 }}>No se pudo cargar la historia de tu campo.</span>
        <button className="btn chico" onClick={() => void cargarHistoria()}>Probar de nuevo</button>
      </div>
    );
  } else if (!sec) {
    cuerpo = <span className="bajada">Todavía no hay historia para este campo.</span>;
  } else {
    const temps = sec.temporadas;
    const haySat = Boolean(sec.hay_satelite) || temps.some((t) => t.satelite.ndvi_max !== null);
    const seca = temps.find((t) => t.temporada === "verano 2022/23");
    const anom = seca?.satelite.anomalia_ndvi_pct;
    const val = sec.validacion;
    const catR = seca ? categoriaReal(seca) : "sin_dato";
    cuerpo = (
      <>
        {secciones.length > 1 && (
          <div className="selector-seccion">
            {secciones.map((x) => (
              <button key={x.seccion_id} type="button" className={`chip ${x.seccion_id === sec.seccion_id ? "on" : ""}`} onClick={() => setSeccionSel(x.seccion_id)}>
                {x.nombre}
              </button>
            ))}
          </div>
        )}
        {haySat && val && val.total_evaluadas > 0 && (
          <p className="creer-lote">{`En ${sec.nombre}: coincidió en ${val.aciertos} de ${val.total_evaluadas} temporadas.`}</p>
        )}
        <DosFilas compacto temporadas={temps} onElegir={(t) => abrirHistoria({ seccion: sec.seccion_id, temporada: t })} />
        <div className="hp-frases">
          {seca && haySat && anom != null && (
            <p>{`En el verano 2022/23, la seca, el satélite vio el verdor de ${sec.nombre} un ${Math.abs(Math.round(anom))} % ${anom < 0 ? "por debajo" : "por encima"} de lo normal.`}</p>
          )}
          {seca && catR !== "sin_dato" && (
            <p>{`Lo que había ese verano (${seca.cultivo_real.nombre.toLowerCase()}) ${REAL_PASO[catR]}.`}</p>
          )}
          {!haySat && (
            <p className="hp-sin-satelite">Por ahora sin el satélite: «Lo que se hizo» solo tiene los años que cargaste.</p>
          )}
        </div>
        <button className="btn chico" onClick={() => abrirHistoria({ seccion: sec.seccion_id })}>Ver temporada por temporada</button>
      </>
    );
  }

  return (
    <div className="caja historia-en-plan" id="datos-creer">
      <h3>Lo que calcula la app contra lo que vio el satélite</h3>
      {global && global.total_evaluadas > 0 ? (
        <p className="creer-numero">{`En ${global.aciertos_globales} de ${global.total_evaluadas} temporadas desde 2000, lo que calcula la app (el balance de agua de cada cultivo con la lluvia y el clima de la NASA) coincidió con el verdor que vio el satélite MODIS.`}</p>
      ) : (
        <p className="bajada">Se compara, temporada por temporada desde 2000, lo que calcula la app con el verdor que vio el satélite.</p>
      )}
      <p className="bajada">Cada franja es una temporada del lote, en el momento crítico del cultivo.</p>
      {cuerpo}
    </div>
  );
}
