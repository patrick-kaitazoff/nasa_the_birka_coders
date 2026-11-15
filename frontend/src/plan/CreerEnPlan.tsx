import { useEffect } from "react";
import { useApp } from "../store";
import { irA } from "../analisis/Termino";

/** Una línea en el Plan que lleva a «¿Le podemos creer a la app?» en Datos. La historia se sigue pidiendo de fondo para tener el número. */
export function CreerEnPlan() {
  const { historia, historiaCargando, historiaError, cargarHistoria, campo, setPestania } = useApp();
  useEffect(() => {
    if (!historia && !historiaCargando && !historiaError && campo.secciones.length > 0) void cargarHistoria();
  }, [historia, historiaCargando, historiaError, campo.secciones.length, cargarHistoria]);
  const g = historia?.resumen_global;
  if (!g || !g.total_evaluadas) return null;
  return (
    <p className="creer-en-plan no-imprimir">
      <span>{`La app coincidió con lo que vio el satélite en ${g.aciertos_globales} de ${g.total_evaluadas} temporadas desde 2000.`}</span>{" "}
      <button type="button" className="enlace" onClick={() => { setPestania("analisis"); irA("datos-g-creer"); }}>Ver cómo</button>
    </p>
  );
}
