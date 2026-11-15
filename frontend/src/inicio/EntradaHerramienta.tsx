import { useEffect, useLayoutEffect } from "react";
import { alMostrarse, reducirMovimiento, vieneDePortada } from "./llegada";
import { useApp } from "../store";
import { bajarDepartamentos } from "../mapa/MapaCampo";

/**
 * Entrada a la herramienta. Reemplaza a la bajada desde el espacio (la Tierra que bajaba hasta Uruguay) y,
 * antes, a la página «Planifiquemos qué sembrar…» con «Comenzar».
 *
 * Ahora: el navegador funde la portada con la herramienta, que pinta su esqueleto al instante (app.html); el mapa ya
 * está encuadrado en Uruguay con la foto satelital que bajó la portada, y el chat entra desde la derecha. Sin pantallas
 * de por medio, sin vuelos ni fotos del trigo.
 *
 * Usa el estado `bienvenida` del store solo para saber que el campo está vacío al abrir: se cierra enseguida.
 */
export function EntradaHerramienta() {
  const { bienvenida, setBienvenida } = useApp();

  useEffect(() => {
    void bajarDepartamentos();
  }, []);

  // antes de pintar, así no hay ni un cuadro de diferencia
  useLayoutEffect(() => {
    if (!bienvenida) return;
    const decidir = () => {
      if (!useApp.getState().bienvenida) return;
      setBienvenida(false);
      if (!vieneDePortada() || reducirMovimiento()) return;
      const chat = document.querySelector<HTMLElement>(".columna-chat");
      chat?.classList.add("chat-entra");
      window.setTimeout(() => chat?.classList.remove("chat-entra"), 1100);
    };
    // si la portada armó la página por adelantado, se decide cuando se muestra
    const quitar = alMostrarse(decidir);
    if (!(document as Document & { prerendering?: boolean }).prerendering) decidir();
    return quitar;
  }, [bienvenida, setBienvenida]);

  return null;
}
