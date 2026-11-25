"""Evaluación de la aplicación integrada a través de la API REST.

1. Métricas del chatbot: intención detectada en conversación, éxito de tareas (postulaciones de
   principio a fin), turnos por tarea, validación de documentos y tiempos de respuesta.
2. Prueba de carga: tiempo de respuesta y errores con distintos niveles de usuarios simultáneos.

Uso (por ejemplo en Colab, contra la URL de Cloudflare Tunnel o http://localhost:5000):
    from pruebas.evaluacion import Cliente, metricas_chatbot, prueba_carga
    cli = Cliente("https://xxxx.trycloudflare.com")
    res = metricas_chatbot(cli, DOCUMENTOS)
"""
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd


class Cliente:
    """Envía peticiones a la API y mide el tiempo de cada una (lado del usuario)."""

    def __init__(self, url=None, app=None):
        self.url = (url or "").rstrip("/")
        self.prueba = app.test_client() if app is not None else None
        self.tiempos = []                      # (ruta, ms, estado)
        if self.prueba is None:
            import requests
            self.http = requests.Session()

    def _pedir(self, metodo, ruta, **kw):
        t0 = time.perf_counter()
        if self.prueba is not None:
            if "files" in kw:
                nombre, contenido, _ = kw.pop("files")["archivo"]
                import io
                kw["data"] = {**kw.get("data", {}), "archivo": (io.BytesIO(contenido), nombre)}
                kw["content_type"] = "multipart/form-data"
            r = self.prueba.open(ruta, method=metodo, **kw)
            estado, datos = r.status_code, r.get_json()
        else:
            r = self.http.request(metodo, self.url + ruta, timeout=60, **kw)
            estado, datos = r.status_code, r.json()
        self.tiempos.append((ruta, (time.perf_counter() - t0) * 1000, estado))
        return estado, datos

    def mensaje(self, sesion, texto):
        return self._pedir("POST", "/api/agente/mensaje", json={"sesion": sesion, "mensaje": texto})[1]

    def documento(self, sesion, ruta_archivo):
        with open(ruta_archivo, "rb") as f:
            contenido = f.read()
        nombre = ruta_archivo.split("/")[-1]
        return self._pedir("POST", "/api/agente/documento", data={"sesion": sesion},
                           files={"archivo": (nombre, contenido, "application/octet-stream")})[1]


# ============================ 1. Casos de prueba ============================
# Frases NUEVAS (no están en el conjunto de entrenamiento), escritas como en WhatsApp.
FRASES = [
    ("buenas tardes, una pregunta", "saludo"), ("holi buen dia", "saludo"), ("que onda buenas", "saludo"),
    ("que trabajos hay disponibles", "vacantes"), ("estan contratando gente?", "vacantes"),
    ("hay chamba para mi?", "vacantes"),
    ("que hace la lavaloza", "funciones"), ("en que consiste ser runner", "funciones"),
    ("cuales son las actividades del repartidor", "funciones"),
    ("cuanto ganaria de cocinero", "sueldo"), ("de cuanto es la paga del vendedor", "sueldo"),
    ("cuanto pagan x semana", "sueldo"),
    ("a que hora entran", "horarios"), ("cual es el horario de la mesera", "horarios"),
    ("que turno maneja el runner", "horarios"),
    ("puedo cambiar de turno despues?", "flexibilidad"), ("me pueden acomodar el horario porque estudio", "flexibilidad"),
    ("hay chance de medio tiempo", "flexibilidad"),
    ("piden experiencia para ayudante?", "experiencia"), ("nunca he trabajado en cocina, me aceptan", "experiencia"),
    ("es mi primer empleo", "experiencia"),
    ("dan de comer ahi?", "prestaciones"), ("cuantos dias descanso", "prestaciones"),
    ("que beneficios tienen", "prestaciones"),
    ("hay propina para cocina?", "propinas"), ("se reparten las propinas?", "propinas"),
    ("el runner lleva propina", "propinas"),
    ("que papeles ocupo", "documentos"), ("necesito comprobante de domicilio?", "documentos"),
    ("que requisitos piden", "documentos"),
    ("donde quedan ustedes", "entrevista"), ("cuando puedo ir a la entrevista", "entrevista"),
    ("en que direccion es", "entrevista"),
    ("me interesa la chamba", "postularse"), ("quiero aplicar para mesera", "postularse"),
    ("como le hago para entrar a trabajar", "postularse"),
    ("muchas gracias por la info", "despedida"), ("ok gracias, bye", "despedida"), ("hasta luego", "despedida"),
    ("dan imss?", "consulta_rh"), ("pagan aguinaldo", "consulta_rh"), ("firmo contrato?", "consulta_rh"),
    ("quiero ordenar comida", "fuera_de_tema"), ("tienen menu vegetariano", "fuera_de_tema"),
    ("a que hora cierran el restaurante", "fuera_de_tema"),
]

# Escenarios de punta a punta. 'agendar' elige el primer día y hora disponibles y da un nombre.
ESCENARIOS = [
    ("Mesero completo", "agendada", ["me interesa", "mesera", "25", "si", "2", ("doc", "ine"), ("doc", "comprobante"), "agendar"]),
    ("Ayudante de cocina completo", "agendada", ["quiero aplicar de ayudante de cocina", "30", "si", "1", ("doc", "ine"), ("doc", "comprobante"), "agendar"]),
    ("Cocinero completo", "agendada", ["me interesa ser cocinero", "40", "si", "5", ("doc", "ine"), ("doc", "comprobante"), "agendar"]),
    ("Lavaloza sin experiencia", "agendada", ["me interesa", "lavaloza", "19", "si", ("doc", "ine"), ("doc", "comprobante"), "agendar"]),
    ("Repartidor con licencia", "agendada", ["quiero postularme de repartidor", "28", "si", "3", "si", ("doc", "ine"), ("doc", "licencia"), ("doc", "comprobante"), "agendar"]),
    ("Runner con duda a mitad", "agendada", ["me interesa ser runner", "22", "cuanto pagan?", "si", ("doc", "ine"), ("doc", "comprobante"), "agendar"]),
    ("Vendedor con documento equivocado", "agendada", ["me interesa ser vendedor", "35", "si", ("doc", "licencia"), ("doc", "ine"), ("doc", "comprobante"), "agendar"]),
    ("Faltas de ortografía", "agendada", ["me intereza", "mesra", "tengo 25 años", "simon", "3", ("doc", "ine"), ("doc", "comprobante"), "agendar"]),
    ("Desde tarjeta de puesto", "agendada", ["Ayudante de cocina", "ok", "27", "si", "2", ("doc", "ine"), ("doc", "comprobante"), "agendar"]),
    ("Imagen que no es documento", "agendada", ["me interesa ser lavaloza", "20", "si", ("doc", "otro"), ("doc", "ine"), ("doc", "comprobante"), "agendar"]),
    ("Menor de edad", "rechazada", ["me interesa ser runner", "16"]),
    ("Sin disponibilidad de horario", "rechazada", ["me interesa ser vendedor", "30", "no"]),
    ("Experiencia insuficiente", "rechazada", ["quiero aplicar de cocinero", "30", "si", "1"]),
    ("Repartidor sin licencia", "rechazada", ["me interesa ser repartidor", "30", "si", "4", "no"]),
    ("Cancelación a mitad", "cancelada", ["me interesa", "mesera", "25", "cancelar"]),
]
RESULTADO = {"agendar_entrevista": "agendada", "rechazar_por_requisito": "rechazada",
             "cancelar_postulacion": "cancelada"}


def metricas_chatbot(cli, documentos):
    """documentos: {'ine': ruta, 'licencia': ruta, 'comprobante': ruta, 'otro': ruta}"""
    # --- Intenciones dentro de la conversación ---
    filas = []
    for frase, esperada in FRASES:
        d = cli.mensaje("eval-" + uuid.uuid4().hex[:8], frase)
        filas.append({"frase": frase, "esperada": esperada, "detectada": d["percepcion"]["intencion"],
                      "confianza": d["percepcion"]["confianza"], "accion": d["accion"]})
    intenciones = pd.DataFrame(filas)
    intenciones["correcta"] = intenciones["esperada"] == intenciones["detectada"]

    # --- Tareas de punta a punta ---
    tareas, docs = [], []
    for nombre, esperado, pasos in ESCENARIOS:
        sesion, turnos, d, resultado = "eval-" + uuid.uuid4().hex[:8], 0, None, "incompleta"
        for paso in pasos:
            if isinstance(paso, tuple):                         # enviar documento (hasta 3 intentos)
                for _ in range(3):
                    d = cli.documento(sesion, documentos[paso[1]])
                    turnos += 1
                    per = d["percepcion"]
                    docs.append({"escenario": nombre, "enviado": paso[1], "esperado": per.get("esperado"),
                                 "detectado": per.get("clase"), "confianza": per.get("confianza"),
                                 "accion": d["accion"]})
                    if d["accion"] in ("aceptar_documento", "escalar_a_rh") or paso[1] != per.get("esperado"):
                        break
            elif paso == "agendar":
                for texto in (lambda: d["opciones"][0], lambda: d["opciones"][0], lambda: f"Prueba {nombre}"):
                    if d.get("cita"):
                        break
                    d = cli.mensaje(sesion, texto())
                    turnos += 1
            else:
                d = cli.mensaje(sesion, paso)
                turnos += 1
            if d["accion"] in RESULTADO:
                resultado = RESULTADO[d["accion"]]
        tareas.append({"escenario": nombre, "esperado": esperado, "resultado": resultado,
                       "exito": resultado == esperado, "turnos": turnos})
    tareas, docs = pd.DataFrame(tareas), pd.DataFrame(docs)

    # --- Tiempos de respuesta medidos por el cliente ---
    t = pd.DataFrame(cli.tiempos, columns=["ruta", "ms", "estado"])
    tiempos = t.groupby("ruta")["ms"].agg(peticiones="count", promedio="mean",
                                          p50=lambda x: np.percentile(x, 50), p95=lambda x: np.percentile(x, 95)).round(1)

    agendadas = tareas[tareas["resultado"] == "agendada"]
    primeros = docs.drop_duplicates(["escenario", "enviado", "esperado"]) if len(docs) else docs
    validos = primeros[primeros["enviado"] == primeros["esperado"]] if len(docs) else docs
    resumen = {
        "Precisión de intención en conversación": f"{intenciones['correcta'].mean():.1%} ({intenciones['correcta'].sum()}/{len(intenciones)})",
        "Confianza promedio del NLP": f"{intenciones['confianza'].mean():.2f}",
        "Tasa de éxito de tareas": f"{tareas['exito'].mean():.1%} ({tareas['exito'].sum()}/{len(tareas)})",
        "Turnos promedio por postulación agendada": f"{agendadas['turnos'].mean():.1f}" if len(agendadas) else "—",
        "Documentos aceptados al primer intento": (f"{(validos['accion'] == 'aceptar_documento').mean():.1%}"
                                                   if len(validos) else "—"),
        "Documentos escalados a RH": int((docs["accion"] == "escalar_a_rh").sum()) if len(docs) else 0,
        "Peticiones con error (5xx)": int((t["estado"] >= 500).sum()),
        "Tiempo de respuesta promedio (ms)": f"{t['ms'].mean():.0f}",
    }
    return {"resumen": pd.Series(resumen, name="Valor"), "intenciones": intenciones, "tareas": tareas,
            "documentos": docs, "tiempos": tiempos}


# ============================ 2. Prueba de carga ============================
def prueba_carga(url, niveles=(1, 5, 10, 20), peticiones=40, ruta_imagen=None):
    """Envía 'peticiones' por nivel de concurrencia y mide latencia y errores."""
    import requests
    resultados = []
    frases = [f for f, _ in FRASES]

    def texto(i):
        t0 = time.perf_counter()
        try:
            r = requests.post(url + "/api/agente/mensaje", timeout=60,
                              json={"sesion": f"carga-{uuid.uuid4().hex[:8]}", "mensaje": frases[i % len(frases)]})
            ok = r.status_code < 400
        except requests.RequestException:
            ok = False
        return (time.perf_counter() - t0) * 1000, ok

    def imagen(_):
        t0 = time.perf_counter()
        try:
            with open(ruta_imagen, "rb") as f:
                r = requests.post(url + "/api/documento", timeout=60, files={"archivo": (ruta_imagen.split("/")[-1], f)})
            ok = r.status_code < 400
        except requests.RequestException:
            ok = False
        return (time.perf_counter() - t0) * 1000, ok

    servicios = [("Texto (/api/agente/mensaje)", texto)]
    if ruta_imagen:
        servicios.append(("Imagen (/api/documento)", imagen))
    for nombre, funcion in servicios:
        for n in niveles:
            t0 = time.perf_counter()
            with ThreadPoolExecutor(max_workers=n) as ex:
                res = list(ex.map(funcion, range(peticiones)))
            total = time.perf_counter() - t0
            lat = np.array([r[0] for r in res])
            resultados.append({"servicio": nombre, "usuarios_simultaneos": n, "peticiones": peticiones,
                               "errores": sum(not r[1] for r in res),
                               "peticiones_por_segundo": round(peticiones / total, 1),
                               "latencia_p50_ms": round(np.percentile(lat, 50)),
                               "latencia_p95_ms": round(np.percentile(lat, 95)),
                               "latencia_max_ms": round(lat.max())})
    return pd.DataFrame(resultados)
