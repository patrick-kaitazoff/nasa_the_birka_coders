/** Cómo le va al agua en la floración, de cada 10 años: una barra entera partida en dos, en verde los años que los
 * cultivos llegan a la floración con agua y en ámbar los de seca (menos de la mitad del agua que piden). Eran diez cuadritos con los años de seca pintados: «2 de 10» pintados se leía como una mala
 * nota en todas las opciones. Ahora se ve cuánto de la barra
 * es bueno, con los dos números abajo. El dato es el mismo. */
export function DiezAnios({ p, titulo }: { p: number; titulo?: string }) {
  const seca = Math.max(0, Math.min(1, p)) * 10;
  const agua = 10 - seca;
  const n = (x: number) => x.toLocaleString("es-UY", { maximumFractionDigits: 1 });
  const etiqueta = titulo || `De cada 10 años, ${n(agua)} llegan a la floración con agua y ${n(seca)} con seca`;
  return (
    <div className="anios-agua" role="img" aria-label={etiqueta} title={etiqueta}>
      <div className="anios-agua-barra" aria-hidden>
        <span className="anios-agua-bien" style={{ flexGrow: agua }} />
        {seca > 0.05 && <span className="anios-agua-seca" style={{ flexGrow: seca }} />}
      </div>
      <div className="anios-agua-leyenda" aria-hidden>
        <span className="bien">{`${n(agua)} con agua`}</span>
        <span className="seca">{`${n(seca)} con seca`}</span>
      </div>
    </div>
  );
}
