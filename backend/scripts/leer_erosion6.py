"""Lee las tablas del programa Erosión 6.0 del MGAP (archivos .ERD) y las pasa a JSON.

Los .ERD son listas de objetos de .NET guardadas con BinaryFormatter (formato MS-NRBF). Este lector
las recorre sin ejecutar el programa ni cargar sus DLL.

Cómo conseguir los .ERD (no se suben al repo):
  1. Bajar https://descargas.mgap.gub.uy/DGRN/CONEAT/Erosion%20para%20Windows.rar (1,2 MB), que se
     publica en https://www.gub.uy/ministerio-ganaderia-agricultura-pesca/politicas-y-gestion/programa-erosion-60-usle-rusle
  2. Sacar solo los datos, en una carpeta fuera del repo, con el tar de Windows:
     tar -xf erosion.rar -C <carpeta> "Erosion para Windows/DATA"

Uso: python leer_erosion6.py "<carpeta>/Erosion para Windows/DATA/RPS.ERD" > rps.json
Tablas: RPS (relaciones de pérdida de suelo por cultivo, manejo, rendimiento y período), CULTIVOS,
MANEJOS, RENDIMIENTOS, ERP (efecto residual de pasturas), FACTORESC (C ya calculados), LOCALIDADES
(R y reparto mensual viejo), SUELOS y SUELOS40K (K y tolerancia)."""
import json
import struct
import sys


class Ref:
    def __init__(self, i):
        self.i = i


class Lector:
    def __init__(self, b):
        self.b, self.p = b, 0
        self.objs, self.clases = {}, {}

    def u8(self):
        v = self.b[self.p]; self.p += 1; return v

    def i32(self):
        v = struct.unpack_from("<i", self.b, self.p)[0]; self.p += 4; return v

    def lps(self):
        n, s = 0, 0
        while True:
            c = self.u8(); n |= (c & 0x7F) << s; s += 7
            if not c & 0x80:
                break
        v = self.b[self.p:self.p + n].decode("utf-8", "replace"); self.p += n; return v

    def prim(self, t):
        f = {1: "<?", 2: "<B", 6: "<d", 7: "<h", 8: "<i", 9: "<q", 10: "<b", 11: "<f",
             12: "<q", 13: "<q", 14: "<H", 15: "<I", 16: "<Q"}
        if t in f:
            v = struct.unpack_from(f[t], self.b, self.p)[0]
            self.p += struct.calcsize(f[t]); return v
        if t in (5, 18):
            return self.lps()
        if t == 3:
            c = self.u8(); n = 1 if c < 0x80 else 2 if c < 0xE0 else 3 if c < 0xF0 else 4
            v = self.b[self.p - 1:self.p - 1 + n].decode("utf-8", "replace"); self.p += n - 1; return v
        raise ValueError(f"primitivo {t}")

    def info_clase(self):
        oid, nombre, n = self.i32(), self.lps(), None
        n = self.i32()
        return oid, nombre, [self.lps() for _ in range(n)]

    def tipos(self, n):
        bt = [self.u8() for _ in range(n)]
        extra = []
        for t in bt:
            if t in (0, 7):
                extra.append(self.u8())
            elif t == 3:
                extra.append(self.lps())
            elif t == 4:
                extra.append((self.lps(), self.i32()))
            else:
                extra.append(None)
        return list(zip(bt, extra))

    def valores(self, oid, nombre, miembros, tipos):
        d = {"__clase": nombre}
        self.objs[oid] = d
        for m, (bt, ex) in zip(miembros, tipos):
            d[m] = self.prim(ex) if bt == 0 else self.registro()
        return d

    def registro(self):
        r = self.u8()
        if r == 0:
            self.p += 16; return None
        if r == 1:
            oid, mid = self.i32(), self.i32()
            nombre, miembros, tipos = self.clases[mid]
            self.clases[oid] = self.clases[mid]
            return self.valores(oid, nombre, miembros, tipos)
        if r in (4, 5):
            oid, nombre, miembros = self.info_clase()
            tipos = self.tipos(len(miembros))
            if r == 5:
                self.i32()
            self.clases[oid] = (nombre, miembros, tipos)
            return self.valores(oid, nombre, miembros, tipos)
        if r == 6:
            oid = self.i32(); s = self.lps(); self.objs[oid] = s; return s
        if r == 8:
            return self.prim(self.u8())
        if r == 9:
            return Ref(self.i32())
        if r == 10:
            return None
        if r == 12:
            self.i32(); self.lps(); return self.registro()
        if r in (13, 14):
            n = self.u8() if r == 13 else self.i32()
            return ("NULOS", n)
        if r == 15:
            oid, n, t = self.i32(), self.i32(), None
            t = self.u8(); arr = [self.prim(t) for _ in range(n)]
            self.objs[oid] = arr; return arr
        if r in (16, 17):
            oid, n = self.i32(), self.i32()
            arr = []
            while len(arr) < n:
                v = self.registro()
                if isinstance(v, tuple) and v and v[0] == "NULOS":
                    arr.extend([None] * v[1])
                else:
                    arr.append(v)
            self.objs[oid] = arr; return arr
        if r == 11:
            return "FIN"
        raise ValueError(f"registro {r} en {self.p - 1}")

    def todo(self):
        raiz = None
        while self.p < len(self.b):
            v = self.registro()
            if v == "FIN":
                break
            if raiz is None and v is not None:
                raiz = v
        return raiz

    def resolver(self, v, vistos=()):
        if isinstance(v, Ref):
            return self.resolver(self.objs.get(v.i), vistos)
        if isinstance(v, dict):
            if id(v) in vistos:
                return "<ciclo>"
            return {k: self.resolver(x, vistos + (id(v),)) for k, x in v.items()}
        if isinstance(v, list):
            return [self.resolver(x, vistos) for x in v]
        return v


def leer(ruta):
    with open(ruta, "rb") as f:
        lec = Lector(f.read())
    raiz = lec.resolver(lec.todo())
    if isinstance(raiz, dict) and "_items" in raiz:
        return raiz["_items"][: raiz["_size"]]
    return raiz


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(leer(sys.argv[1]), ensure_ascii=False, indent=1))
