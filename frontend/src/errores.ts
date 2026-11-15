/**
 * Errores en palabras de la persona. El navegador y las librerías hablan en inglés ("Failed to fetch",
 * "NetworkError", "Unexpected token") y el servidor a veces adjunta el detalle técnico después de ": ".
 * Nada de eso le sirve al productor: acá se traduce y se recorta.
 */
export function enPalabras(e: unknown, que?: string): string {
  const crudo = (e as any)?.message ?? String(e ?? "");
  const pre = que ? `${que}: ` : "";
  if (/failed to fetch|network\s*error|load failed|network request failed|err_connection|err_internet|net::err|connection refused/i.test(crudo)) {
    return que
      ? `${que}: no me pude conectar. Revisá que haya internet y probá de nuevo en un momento.`
      : "No me pude conectar. Revisá que haya internet y probá de nuevo en un momento.";
  }
  if (/timeout|timed out|504|gateway/i.test(crudo)) {
    return que
      ? `${que}: el servidor tardó demasiado en responder. Probá de nuevo en un momento.`
      : "El servidor tardó demasiado en responder. Probá de nuevo en un momento.";
  }
  if (/^error interno/i.test(crudo)) {
    return que
      ? `${que}: algo falló de nuestro lado al preparar la respuesta. Probá de nuevo; si sigue pasando, avisanos.`
      : "Algo falló de nuestro lado al preparar la respuesta. Probá de nuevo; si sigue pasando, avisanos.";
  }
  if (/^error de la api/i.test(crudo)) {
    return que
      ? `${que}: la IA no está respondiendo ahora. Probá de nuevo en un rato o seguí con la entrevista guiada.`
      : "La IA no está respondiendo ahora. Probá de nuevo en un rato o seguí con la entrevista guiada.";
  }
  if (/^\d{3}$/.test(crudo.trim())) {
    const n = Number(crudo);
    return n >= 500
      ? (que ? `${que}: el servidor tuvo un problema. Probá de nuevo en un rato.` : "El servidor tuvo un problema. Probá de nuevo en un rato.")
      : (que ? `${que}: no se pudo completar el pedido.` : "No se pudo completar el pedido.");
  }
  if (/unexpected token|json|syntaxerror|undefined|null|typeerror|cannot read/i.test(crudo)) {
    return que
      ? `${que}: algo falló de nuestro lado. Probá de nuevo; si sigue pasando, avisanos.`
      : "Algo falló de nuestro lado. Probá de nuevo; si sigue pasando, avisanos.";
  }
  // mensajes propios del servidor: lo que va antes del detalle técnico
  const corto = crudo.split(/:\s/)[0].trim().replace(/\.$/, "");
  return corto ? `${pre}${minuscula(corto, !!que)}.` : `${pre}algo falló. Probá de nuevo.`;
}

function minuscula(s: string, tras: boolean) {
  // "No respondió..." → "no respondió..."; una sigla ("MGAP...") queda como está
  return tras && /^[A-ZÁÉÍÓÚÑ][a-záéíóúñ]/.test(s) ? s.charAt(0).toLowerCase() + s.slice(1) : s;
}
