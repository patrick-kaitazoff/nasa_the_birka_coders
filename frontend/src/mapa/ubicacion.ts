/**
 * Dónde está la persona, para llevar el mapa ahí.
 *
 * Primero la ubicación del navegador (pide permiso; en una computadora sale del Wi-Fi y suele acertar
 * a cientos de metros; en el celular, del GPS). Si no la da, la de la conexión a internet
 * (get.geojs.io, sin cuenta), que es aproximada: suele marcar la ciudad del proveedor.
 */
export type Donde = { lat: number; lon: number; zoom: number; aviso?: string };

export async function dondeEstoy(): Promise<Donde> {
  const delNavegador = () =>
    new Promise<GeolocationPosition>((ok, mal) => {
      if (!navigator.geolocation) return mal(new Error("sin geolocalización"));
      navigator.geolocation.getCurrentPosition(ok, mal, { timeout: 9000, maximumAge: 600000 });
    });
  try {
    const p = await delNavegador();
    const lejos = p.coords.accuracy > 2000;
    return {
      lat: p.coords.latitude, lon: p.coords.longitude, zoom: lejos ? 13 : 15,
      aviso: lejos ? "Te ubiqué de forma aproximada. Si tu campo no está a la vista, movete un poco por el mapa." : undefined,
    };
  } catch {
    /* sin permiso o sin señal: se prueba por la conexión */
  }
  try {
    const r = await fetch("https://get.geojs.io/v1/ip/geo.json");
    const js = await r.json();
    const lat = parseFloat(js.latitude), lon = parseFloat(js.longitude);
    if (Number.isNaN(lat) || Number.isNaN(lon)) throw new Error("sin datos");
    return {
      lat, lon, zoom: 11,
      aviso: `Te ubiqué por la conexión a internet${js.city ? `, cerca de ${js.city}` : ""}. Es aproximado (puede errar varios kilómetros): buscá tu campo desde ahí o escribí el pueblo más cercano.`,
    };
  } catch {
    throw new Error("No pude saber dónde estás. Tocá tu departamento en el mapa o escribí el pueblo más cercano.");
  }
}
