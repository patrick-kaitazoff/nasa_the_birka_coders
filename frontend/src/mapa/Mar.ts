import L from "leaflet";

/**
 * Mar parejo de cerca. La foto de Esri, desde el
 * zoom 12, arma el Río de la Plata y el Atlántico con cuadrados de distinto tono y manchas marrones pegadas
 * a la costa. Encima se pinta el mar (línea de costa de OpenStreetMap, guardada en el backend por
 * scripts/actualizar_mar.py) con el azul del agua profunda de la misma foto. Solo sobre el satélite común.
 */
const DESDE_ZOOM = 11.5;
const AZUL = "#092732"; // el agua profunda de la foto de Esri

export function capaMar(mapa: L.Map) {
  if (!mapa.getPane("mar")) {
    const p = mapa.createPane("mar");
    p.style.zIndex = "250"; // arriba de la foto (200), abajo de departamentos, rutas y campo (400)
    p.style.pointerEvents = "none";
  }
  const capa = L.geoJSON(undefined, {
    pane: "mar", interactive: false,
    renderer: L.svg({ pane: "mar", padding: 1 }),
    style: { stroke: true, color: AZUL, weight: 1, fillColor: AZUL, fillOpacity: 1 },
  } as L.GeoJSONOptions);
  let pedida = false;
  let activa = false;
  const actualizar = () => {
    const ver = activa && mapa.getZoom() >= DESDE_ZOOM;
    if (ver && !pedida) {
      pedida = true;
      fetch("/api/mar").then((r) => r.json()).then((d) => capa.addData(d.mar)).catch(() => { pedida = false; });
    }
    if (ver && !mapa.hasLayer(capa)) capa.addTo(mapa);
    else if (!ver && mapa.hasLayer(capa)) capa.remove();
  };
  mapa.on("zoomend moveend", actualizar); // (moveend también: si la primera vez no llegó, se reintenta)
  return { mostrar(si: boolean) { activa = si; actualizar(); } };
}
