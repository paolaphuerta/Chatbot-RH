"""Base de conocimiento del restaurante y almacenamiento (agenda y candidatos).

La información de las vacantes se lee del Excel `datos/base_conocimiento.xlsx`,
así recursos humanos puede actualizar sueldos u horarios sin tocar el código.
La agenda y los candidatos se guardan en una base SQLite para que no se pierdan
entre conversaciones.
"""
import os
import re
import sqlite3
import threading
import unicodedata
from datetime import datetime

import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_EXCEL = os.path.join(RAIZ, "datos", "base_conocimiento.xlsx")
RUTA_BD = os.path.join(RAIZ, "datos", "reclutamiento.db")

DIAS_HABILES = ["lunes", "martes", "miercoles", "jueves", "viernes"]


def sin_acentos(texto):
    texto = unicodedata.normalize("NFD", str(texto).lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn").strip()


def _es_si(valor):
    return sin_acentos(valor) in ("si", "s", "yes", "true", "1")


class BaseConocimiento:
    """Puestos, políticas generales y datos de la entrevista."""

    def __init__(self, ruta=RUTA_EXCEL):
        puestos_df = pd.read_excel(ruta, sheet_name="Puestos").dropna(subset=["Puesto"])
        general_df = pd.read_excel(ruta, sheet_name="General")
        entrevista_df = pd.read_excel(ruta, sheet_name="Entrevista")

        self.puestos, self.sinonimos = {}, {}
        for _, fila in puestos_df.iterrows():
            palabras = [sin_acentos(p) for p in str(fila["Palabras clave"]).split(",") if p.strip()]
            clave = palabras[0] if palabras else sin_acentos(fila["Puesto"])
            exp = fila["Experiencia (años)"]
            self.puestos[clave] = {
                "nombre": str(fila["Puesto"]).strip(),
                "horarios": [h.strip() for h in str(fila["Horarios"]).split("|") if h.strip()],
                "sueldo": str(fila["Sueldo"]).strip(),
                "experiencia": int(exp) if pd.notna(exp) else 0,
                "propinas": _es_si(fila["Propinas"]),
                "requiere_licencia": _es_si(fila["Requiere licencia"]),
                "funciones": str(fila["Funciones"]).strip(),
            }
            self.sinonimos[clave] = palabras

        self.general = dict(zip(general_df["Concepto"].str.strip(), general_df["Valor"]))
        self.general["edad_minima"] = int(self.general.get("edad_minima", 18))
        self.entrevista = dict(zip(entrevista_df["Concepto"].str.strip(), entrevista_df["Valor"].astype(str)))

    # ---- utilidades de consulta ----
    def espacios_del_dia(self):
        """Horas de inicio posibles, según el horario y la duración del Excel."""
        inicio, fin = re.findall(r"\d{1,2}:\d{2}", self.entrevista["horario"])[:2]
        dur = int(re.search(r"\d+", self.entrevista["duracion"]).group())
        a_min = lambda h: int(h.split(":")[0]) * 60 + int(h.split(":")[1])
        return [f"{m // 60}:{m % 60:02d}" for m in range(a_min(inicio), a_min(fin) - dur + 1, dur)]

    def puestos_sin_experiencia(self):
        return [p["nombre"] for p in self.puestos.values() if p["experiencia"] == 0]


class Almacen:
    """Agenda de entrevistas, candidatos y bitácora de eventos (SQLite)."""

    def __init__(self, ruta=RUTA_BD):
        self.ruta = ruta
        self._candado = threading.Lock()
        with self._conexion() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS citas (
                dia TEXT, hora TEXT, nombre TEXT, puesto TEXT, documentos TEXT,
                por_revisar TEXT, creada TEXT, PRIMARY KEY (dia, hora))""")
            c.execute("""CREATE TABLE IF NOT EXISTS eventos (
                fecha TEXT, ruta TEXT, estado INTEGER, latencia_ms REAL, detalle TEXT)""")
            c.execute("""CREATE TABLE IF NOT EXISTS retroalimentacion (
                fecha TEXT, util INTEGER, capa TEXT, accion TEXT, intencion TEXT)""")

    def _conexion(self):
        return sqlite3.connect(self.ruta, timeout=10)

    # ---- agenda ----
    def ocupados(self, dia):
        with self._conexion() as c:
            return {r[0] for r in c.execute("SELECT hora FROM citas WHERE dia = ?", (dia,))}

    def agendar(self, dia, hora, nombre, puesto, documentos, por_revisar):
        """Registra la cita. Regresa False si el espacio ya se ocupó."""
        with self._candado, self._conexion() as c:
            try:
                c.execute("INSERT INTO citas VALUES (?,?,?,?,?,?,?)",
                          (dia, hora, nombre, puesto, ", ".join(documentos), ", ".join(por_revisar),
                           datetime.now().isoformat(timespec="seconds")))
                return True
            except sqlite3.IntegrityError:
                return False

    def citas(self):
        orden = {d: i for i, d in enumerate(DIAS_HABILES)}
        with self._conexion() as c:
            filas = c.execute("SELECT dia, hora, nombre, puesto, documentos, por_revisar FROM citas").fetchall()
        filas.sort(key=lambda f: (f[0], orden.get(f[0], 9), int(f[1].split(":")[0]) * 60 + int(f[1].split(":")[1])))
        return [dict(zip(["dia", "hora", "nombre", "puesto", "documentos", "por_revisar"], f)) for f in filas]

    # ---- bitácora (monitoreo) ----
    def registrar_evento(self, ruta, estado, latencia_ms, detalle=""):
        with self._candado, self._conexion() as c:
            c.execute("INSERT INTO eventos VALUES (?,?,?,?,?)",
                      (datetime.now().isoformat(timespec="seconds"), ruta, estado, round(latencia_ms, 1), detalle))

    # ---- retroalimentación de los candidatos (👍 / 👎) ----
    def registrar_retro(self, util, capa, accion, intencion):
        """Solo se guarda qué hizo el agente, no lo que escribió el candidato (privacidad)."""
        with self._candado, self._conexion() as c:
            c.execute("INSERT INTO retroalimentacion VALUES (?,?,?,?,?)",
                      (datetime.now().isoformat(timespec="seconds"), int(bool(util)), capa, accion, intencion))

    def retro(self):
        with self._conexion() as c:
            filas = c.execute("SELECT util, accion, intencion FROM retroalimentacion").fetchall()
        return [dict(zip(["util", "accion", "intencion"], f)) for f in filas]

    def eventos(self, limite=500):
        with self._conexion() as c:
            filas = c.execute("SELECT fecha, ruta, estado, latencia_ms, detalle FROM eventos "
                              "ORDER BY rowid DESC LIMIT ?", (limite,)).fetchall()
        return [dict(zip(["fecha", "ruta", "estado", "latencia_ms", "detalle"], f)) for f in filas]
