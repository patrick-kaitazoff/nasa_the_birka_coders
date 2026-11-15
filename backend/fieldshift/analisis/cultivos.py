"""Base de cultivos para Uruguay: calendario, coeficientes de cultivo y ventanas críticas.

Fuentes y estado:
- Kc y largos de etapa: FAO-56 (Allen et al. 1998), tabla 11 y 12, ajustados a fechas típicas
  de siembra en Uruguay. De memoria, a validar con INIA.
- Fechas de siembra y ventanas críticas (floración / llenado): calendario típico de Uruguay,
  a validar con un agrónomo o con material de INIA.
- Cobertura y rastrojo por etapa: aproximación propia para estimar el factor C de la USLE mes a
  mes. Reemplazar por la tabla C del "Manual de medidas exigibles" del MGAP (ago-2025) cuando
  se lea.

Todo esto NO es dato de la NASA: es el conocimiento agronómico que se cruza con el clima.

Hemisferio norte: `CULTIVOS` devuelve cada cultivo con el calendario del norte cuando
el análisis corre para un campo al norte del ecuador (`HEMISFERIO`, lo fija `plan.analizar_campo_pasos`). Ver `NORTE`.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass, field, replace


@dataclass(frozen=True)
class Ventana:
    """Período sensible, en días desde la siembra."""

    desde: int
    hasta: int
    que: str  # texto corto: "floración", "llenado de grano"...


@dataclass(frozen=True)
class Cultivo:
    codigo: str
    nombre: str
    temporada: str  # "verano" | "invierno" | "perenne" | "barbecho"
    siembra: tuple[int, int]  # (mes, día)
    etapas: tuple[int, int, int, int]  # ini, desarrollo, media, final (días) — FAO-56
    kc: tuple[float, float, float]  # ini, media, final
    rastrojo: float  # cobertura que deja el rastrojo tras la cosecha (0-1)
    color: str
    icono: str
    ventana_agua: Ventana | None = None
    ventana_helada: Ventana | None = None
    ventana_calor: Ventana | None = None
    umbral_calor: float = 35.0
    ky: float = 1.0  # respuesta del rendimiento al déficit (FAO-33), aproximada
    ingreso_relativo: float = 0.0  # 0-1, índice relativo si el productor no da márgenes
    forraje: float = 0.0  # 0-1, cuánto aporta al ganado
    fija_n: bool = False
    ph_minimo: float | None = None
    tolera_anegamiento: bool = False
    notas: str = ""
    perenne_anios: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def ciclo(self) -> int:
        return sum(self.etapas)


C = Cultivo

CULTIVOS: dict[str, Cultivo] = {
    c.codigo: c
    for c in [
        C("soja", "Soja de primera", "verano", (11, 15), (20, 30, 60, 25), (0.40, 1.15, 0.50), 0.30,
          "#4E7F2A", "soja",
          ventana_agua=Ventana(70, 110, "floración y llenado (R3-R6)"),
          ventana_calor=Ventana(55, 95, "floración"), umbral_calor=35.0,
          ky=0.85, ingreso_relativo=0.85, fija_n=True,
          notas="Deja poco rastrojo: el suelo queda expuesto en otoño si no sigue un cultivo."),
        C("soja2", "Soja de segunda", "verano", (12, 15), (15, 25, 50, 20), (0.40, 1.10, 0.50), 0.30,
          "#7FA845", "soja",
          ventana_agua=Ventana(55, 90, "floración y llenado (R3-R6)"),
          ventana_calor=Ventana(40, 75, "floración"),
          ky=0.85, ingreso_relativo=0.65, fija_n=True,
          notas="Sembrada sobre rastrojo de invierno; ciclo más corto y más riesgo de seca en marzo."),
        C("maiz", "Maíz de primera", "verano", (10, 1), (30, 40, 50, 30), (0.30, 1.20, 0.35), 0.80,
          "#E07B1A", "maiz",
          ventana_agua=Ventana(60, 95, "floración (panojamiento-cuaje)"),
          ventana_calor=Ventana(60, 95, "floración"), umbral_calor=35.0,
          ky=1.25, ingreso_relativo=0.80,
          notas="Mucho rastrojo: protege el suelo y suma carbono. Muy sensible a seca en floración."),
        C("maiz2", "Maíz de segunda", "verano", (12, 15), (20, 35, 40, 30), (0.30, 1.15, 0.35), 0.75,
          "#EFA45A", "maiz",
          ventana_agua=Ventana(55, 85, "floración"),
          ventana_helada=Ventana(100, 125, "llenado final"),
          ky=1.25, ingreso_relativo=0.60),
        C("sorgo", "Sorgo granífero", "verano", (11, 15), (20, 35, 40, 30), (0.30, 1.00, 0.55), 0.70,
          "#B5651D", "sorgo",
          ventana_agua=Ventana(60, 90, "floración"), ventana_calor=Ventana(60, 90, "floración"),
          umbral_calor=38.0, ky=0.90, ingreso_relativo=0.45, forraje=0.4,
          notas="Más tolerante a seca y calor que el maíz; rastrojo abundante."),
        C("girasol", "Girasol", "verano", (10, 1), (25, 35, 45, 25), (0.35, 1.00, 0.35), 0.25,
          "#D99A00", "girasol",
          ventana_agua=Ventana(60, 90, "floración"), ventana_calor=Ventana(60, 90, "floración"),
          ky=0.95, ingreso_relativo=0.55,
          notas="Raíz profunda; deja poco rastrojo."),
        C("trigo", "Trigo", "invierno", (6, 10), (30, 60, 50, 30), (0.40, 1.15, 0.30), 0.70,
          "#B08A1E", "trigo",
          ventana_agua=Ventana(110, 140, "espigazón y floración"),
          ventana_helada=Ventana(110, 135, "espigazón y floración"),
          ventana_calor=Ventana(135, 160, "llenado de grano"), umbral_calor=32.0,
          ky=1.05, ingreso_relativo=0.55,
          notas="Helada en floración (oct) y calor en llenado (nov) son sus riesgos climáticos."),
        C("cebada", "Cebada", "invierno", (6, 20), (25, 55, 45, 30), (0.40, 1.15, 0.30), 0.65,
          "#CDB46A", "cebada",
          ventana_agua=Ventana(95, 125, "espigazón y floración"),
          ventana_helada=Ventana(95, 125, "espigazón y floración"),
          ventana_calor=Ventana(125, 150, "llenado de grano"), umbral_calor=32.0,
          ky=1.0, ingreso_relativo=0.55),
        C("colza", "Colza / canola", "invierno", (5, 1), (25, 60, 50, 35), (0.35, 1.10, 0.35), 0.40,
          "#C9B400", "colza",
          ventana_agua=Ventana(90, 130, "floración y formación de silicuas"),
          ventana_helada=Ventana(90, 125, "floración"),
          ky=1.0, ingreso_relativo=0.60,
          notas="Libera el campo temprano (oct-nov) y permite soja de segunda en fecha."),
        C("cobertura", "Cultivo de cobertura (avena negra / raigrás / vicia)", "invierno", (4, 1),
          (25, 50, 80, 25), (0.30, 0.90, 0.80), 0.85,
          "#2E9C8F", "cobertura",
          ky=0.0, ingreso_relativo=-0.10, forraje=0.2,
          notas="No se cosecha: protege el suelo en otoño-invierno y aporta carbono. Consume agua del "
                "perfil antes del cultivo de verano: terminarlo a tiempo en años secos."),
        C("verdeo", "Verdeo de invierno (avena / raigrás para pastoreo)", "invierno", (3, 20),
          (25, 50, 80, 30), (0.30, 0.95, 0.80), 0.55,
          "#58B368", "verdeo",
          ky=0.0, ingreso_relativo=0.25, forraje=0.9, tolera_anegamiento=True,
          notas="Forraje de invierno para el ganado; el pisoteo con suelo húmedo puede compactar."),
        C("sorgo_forrajero", "Sorgo forrajero / pastoreo", "verano", (11, 1), (20, 35, 60, 25),
          (0.30, 1.00, 0.70), 0.50,
          "#B97A4F", "sorgo",
          ventana_agua=Ventana(40, 90, "crecimiento activo"),
          ky=0.8, ingreso_relativo=0.30, forraje=0.9),
        C("pradera", "Pradera (festuca + trébol blanco + lotus)", "perenne", (4, 15),
          (60, 90, 365, 0), (0.50, 0.90, 0.90), 0.95,
          "#1F5E3A", "pradera",
          ventana_agua=Ventana(240, 330, "rebrote de primavera-verano"),
          ky=0.0, ingreso_relativo=0.45, forraje=1.0, fija_n=True, tolera_anegamiento=True,
          perenne_anios=4,
          notas="Cubre el suelo todo el año y recupera carbono (La Estanzuela: con pasturas el suelo "
                "se mantiene cerca de 2,5 % de carbono contra 1,5 % en agricultura continua)."),
        C("alfalfa", "Alfalfa", "perenne", (4, 1), (60, 90, 365, 0), (0.40, 0.95, 0.90), 0.95,
          "#8E4FA0", "alfalfa",
          ventana_agua=Ventana(240, 330, "cortes de verano"),
          ky=0.0, ingreso_relativo=0.55, forraje=1.0, fija_n=True, ph_minimo=6.0, perenne_anios=4,
          notas="Pide pH ≥ 6 y buen drenaje; no tolera anegamiento."),
        C("campo_natural", "Campo natural", "perenne", (4, 15), (0, 0, 365, 0), (0.75, 0.75, 0.75), 0.95,
          "#8D9B5A", "campo",
          ventana_agua=Ventana(240, 330, "crecimiento de verano"),
          ky=0.0, ingreso_relativo=0.30, forraje=0.8, tolera_anegamiento=True),
        C("barbecho", "Barbecho (suelo sin cultivo)", "barbecho", (1, 1), (0, 0, 0, 0), (0.30, 0.30, 0.30), 0.0,
          "#9A8C7A", "barbecho",
          notas="Sin cultivo: el suelo queda con el rastrojo anterior, que se degrada mes a mes."),
    ]
}


# --------------------------------------------------------------------------------------------
# Hemisferio norte (EE. UU.)
# --------------------------------------------------------------------------------------------

HEMISFERIO: contextvars.ContextVar[str] = contextvars.ContextVar("hemisferio", default="sur")

# Fechas típicas del centro de EE. UU. (Corn Belt y planicies), de memoria a partir de USDA-NASS «Usual Planting and
# Harvesting Dates for U.S. Field Crops» (Agricultural Handbook 628, 2010): a validar con ese documento o con la
# extensión de cada estado. Los cultivos que no están acá corren su fecha seis meses (las perennes, el verdeo, el
# sorgo forrajero): sus ventanas cuentan días desde la siembra y caen en la misma estación que en Uruguay.
# Los de invierno sí cambian: en EE. UU. el trigo y la cebada son de invierno con reposo bajo la nieve (se siembran
# en octubre y se cosechan en junio o julio), un ciclo mucho más largo que el uruguayo (FAO-56, tabla 11, trigo de
# invierno con suelo helado). La espigazón del trigo de invierno cae en mayo (Kansas a principios, Iowa a fines).
# El ingreso relativo también cambia: en el Corn Belt el maíz rinde mucho más que en Uruguay (~11 t/ha) y el trigo
# con soja de segunda rinde menos porque la temporada es corta; índice propio, a reemplazar por márgenes del productor
# o por los precios de USDA (Market News / QuickStats).
NORTE: dict[str, dict] = {
    "soja": {"siembra": (5, 15), "ingreso_relativo": 0.85},
    "soja2": {"siembra": (6, 28), "nombre": "Soja de segunda (después del trigo)", "ingreso_relativo": 0.50,
              "ventana_helada": Ventana(95, 110, "llenado final (heladas tempranas de otoño)")},
    "maiz": {"siembra": (4, 30), "ingreso_relativo": 0.95},
    "maiz2": {"siembra": (6, 20)},
    "sorgo": {"siembra": (5, 25)},
    "girasol": {"siembra": (5, 25)},
    "trigo": {"siembra": (10, 1), "etapas": (150, 45, 50, 25), "kc": (0.40, 1.15, 0.30),
              "nombre": "Trigo de invierno", "ingreso_relativo": 0.45,
              "ventana_agua": Ventana(220, 250, "espigazón y floración"),
              "ventana_helada": Ventana(220, 240, "espigazón y floración (heladas tardías)"),
              "ventana_calor": Ventana(245, 268, "llenado de grano"),
              "notas": "Se siembra en otoño, pasa el invierno en reposo y se cosecha a fines de junio: cubre el "
                       "suelo en los meses de deshielo y lluvias de primavera."},
    "cebada": {"siembra": (10, 1), "etapas": (150, 45, 45, 25), "kc": (0.40, 1.15, 0.30),
               "nombre": "Cebada de invierno", "ingreso_relativo": 0.40,
               "ventana_agua": Ventana(215, 245, "espigazón y floración"),
               "ventana_helada": Ventana(215, 235, "espigazón y floración (heladas tardías)"),
               "ventana_calor": Ventana(240, 265, "llenado de grano")},
    "colza": {"siembra": (9, 15), "etapas": (160, 50, 50, 30), "nombre": "Colza / canola de invierno",
              "ingreso_relativo": 0.45,
              "ventana_agua": Ventana(215, 245, "floración y formación de silicuas"),
              "ventana_helada": Ventana(200, 230, "floración"),
              "notas": "Libera el campo a fines de junio y permite soja de segunda."},
    "cobertura": {"siembra": (10, 10), "etapas": (30, 60, 80, 25),
                  "nombre": "Cultivo de cobertura (centeno / vicia)",
                  "notas": "No se cosecha: el centeno se siembra tras la cosecha, aguanta el invierno y se termina en "
                           "abril, antes del maíz o la soja. Protege el suelo del deshielo y las lluvias de primavera."},
}


def _al_norte(c: Cultivo) -> Cultivo:
    if c.codigo in NORTE:
        return replace(c, **NORTE[c.codigo])
    mes, dia = c.siembra
    return replace(c, siembra=((mes + 5) % 12 + 1, dia))


class _Catalogo(dict):
    """El dict de cultivos, que devuelve la versión del hemisferio del análisis en curso."""

    def _h(self, c: Cultivo) -> Cultivo:
        return _CULTIVOS_NORTE[c.codigo] if HEMISFERIO.get() == "norte" else c

    def __getitem__(self, k: str) -> Cultivo:
        return self._h(super().__getitem__(k))

    def get(self, k, default=None):
        return self[k] if k in self else default

    def values(self):
        return [self._h(c) for c in super().values()]

    def items(self):
        return [(k, self._h(c)) for k, c in super().items()]


_CULTIVOS_NORTE: dict[str, Cultivo] = {k: _al_norte(c) for k, c in CULTIVOS.items()}
CULTIVOS = _Catalogo(CULTIVOS)


def inicio_anio_agricola() -> int:
    """Mes en que arranca el año de la rotación (la siembra de otoño): marzo en el sur, septiembre en el norte."""
    return 9 if HEMISFERIO.get() == "norte" else 3


def cultivo(codigo: str) -> Cultivo:
    return CULTIVOS[codigo]


# Qué le aporta cada tipo de cultivo al suelo, para explicarlo al productor (lo pide el desafío:
# "cómo contribuyen las fijadoras de nitrógeno, las coberturas, las de raíz profunda y las tolerantes
# a la seca"). Agronomía general, a validar con un agrónomo o con INIA.
APORTES: dict[str, dict[str, str]] = {
    "fija_n": {
        "nombre": "Fija nitrógeno",
        "explicacion": "Las leguminosas (soja, trébol, lotus, alfalfa) toman nitrógeno del aire con las "
                       "bacterias de sus raíces. En la soja de grano casi todo se va con la cosecha; las pasturas "
                       "de trébol, lotus y alfalfa dejan mucho más en el suelo para el cultivo que sigue.",
    },
    "cubre": {
        "nombre": "Cubre el suelo en invierno",
        "explicacion": "Ocupa los meses en que el campo quedaría desnudo: protege el suelo de la lluvia que "
                       "erosiona, frena malezas y suma raíces y rastrojo, que con los años se vuelven materia "
                       "orgánica.",
    },
    "raiz_profunda": {
        "nombre": "Raíz profunda",
        "explicacion": "Llega a capas que los otros cultivos no alcanzan: abre caminos para que el agua "
                       "infiltre, ayuda a romper capas compactadas y sube nutrientes de abajo.",
    },
    "tolera_seca": {
        "nombre": "Aguanta la seca",
        "explicacion": "Pierde menos rinde cuando falta agua, o la busca más hondo: reparte el riesgo de los "
                       "años secos.",
    },
    "recupera": {
        "nombre": "Recupera el suelo",
        "explicacion": "Varios años de pastura sin laboreo: las raíces permanentes recuperan materia orgánica y "
                       "estructura. Es la base del sistema agrícola-pastoril de La Estanzuela.",
    },
}
_RAIZ_PROFUNDA = {"girasol", "colza", "alfalfa", "sorgo", "sorgo_forrajero"}
_TOLERA_SECA = {"sorgo", "sorgo_forrajero", "girasol"}
_CUBRE = {"cobertura", "verdeo"}
_RECUPERA = {"pradera", "alfalfa", "campo_natural"}


def aportes(c: Cultivo) -> list[str]:
    """Códigos de APORTES que tiene el cultivo, en el orden de APORTES."""
    tiene = {
        "fija_n": c.fija_n,
        "cubre": c.codigo in _CUBRE,
        "raiz_profunda": c.codigo in _RAIZ_PROFUNDA,
        "tolera_seca": c.codigo in _TOLERA_SECA,
        "recupera": c.codigo in _RECUPERA,
    }
    return [k for k in APORTES if tiene[k]]


def catalogo_publico() -> list[dict]:
    """Lo que el frontend necesita para dibujar (nombre, color, icono, temporada)."""
    return [
        {
            "codigo": c.codigo,
            "nombre": c.nombre,
            "temporada": c.temporada,
            "color": c.color,
            "icono": c.icono,
            "siembra": f"{c.siembra[1]:02d}/{c.siembra[0]:02d}",
            "ciclo_dias": c.ciclo,
            "forraje": c.forraje,
            "notas": c.notas,
            "aportes": aportes(c),
        }
        for c in CULTIVOS.values()
    ]
