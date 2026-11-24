"""API REST (Flask) del asistente de reclutamiento.

Expone los servicios de inferencia y el agente:

    GET  /api/salud               Estado del servicio y de los modelos
    POST /api/intencion           Clasifica la intención de un texto            {"mensaje": "..."}
    POST /api/documento           Clasifica un archivo (multipart: archivo)
    POST /api/agente/mensaje      Turno de conversación con el agente          {"sesion": "...", "mensaje": "..."}
    POST /api/agente/documento    El candidato envía un documento al agente    (multipart: sesion, archivo)
    POST /api/agente/reiniciar    Reinicia la conversación                     {"sesion": "..."}
    GET  /api/agenda              Entrevistas agendadas (recursos humanos)
    GET  /api/metricas            Métricas de operación (monitoreo)

Ejecución local:   python -m api.servidor          (puerto 5000)
"""
import logging
import os
import sys
import time
from collections import Counter
from functools import wraps

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agente import construir_agente  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("api_reclutamiento")


class ErrorSolicitud(Exception):
    def __init__(self, mensaje, estado=400):
        super().__init__(mensaje)
        self.mensaje, self.estado = mensaje, estado


def crear_app(agente=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024           # 12 MB por petición
    inicio = time.time()
    agente = agente or construir_agente()
    almacen = agente.almacen
    contadores = {"intenciones": Counter(), "documentos": Counter(), "acciones": Counter()}

    # ---------------- Monitoreo: tiempo de respuesta y estado de cada petición ----------------
    @app.before_request
    def _antes():
        g.t0 = time.perf_counter()

    @app.after_request
    def _despues(resp):
        if request.path.startswith("/api/") and request.path not in ("/api/metricas", "/api/salud"):
            ms = (time.perf_counter() - g.t0) * 1000
            detalle = getattr(g, "detalle", "")
            almacen.registrar_evento(request.path, resp.status_code, ms, detalle)
            log.info("%s %s -> %s (%.0f ms) %s", request.method, request.path, resp.status_code, ms, detalle)
        return resp

    # ---------------- Manejo de errores: siempre se responde JSON con un mensaje claro ----------------
    @app.errorhandler(ErrorSolicitud)
    def _error_solicitud(e):
        g.detalle = e.mensaje
        return jsonify({"ok": False, "error": e.mensaje}), e.estado

    @app.errorhandler(413)
    def _muy_grande(_):
        g.detalle = "archivo demasiado grande"
        return jsonify({"ok": False, "error": "El archivo es demasiado grande (máximo 10 MB)."}), 413

    @app.errorhandler(404)
    def _no_existe(_):
        return jsonify({"ok": False, "error": "Ruta no encontrada."}), 404

    @app.errorhandler(Exception)
    def _error_interno(e):
        if isinstance(e, HTTPException):                    # 405, 400, etc.
            return jsonify({"ok": False, "error": e.description}), e.code
        log.exception("Error interno")
        g.detalle = f"error interno: {type(e).__name__}"
        return jsonify({"ok": False, "error": "Ocurrió un error interno. Intenta de nuevo en un momento."}), 500

    def _json(*campos):
        datos = request.get_json(silent=True)
        if not isinstance(datos, dict):
            raise ErrorSolicitud("Se esperaba un cuerpo JSON.")
        faltan = [c for c in campos if not str(datos.get(c, "")).strip()]
        if faltan:
            raise ErrorSolicitud(f"Falta el campo: {', '.join(faltan)}.")
        return datos

    def _archivo():
        f = request.files.get("archivo")
        if f is None or not f.filename:
            raise ErrorSolicitud("No se recibió ningún archivo.")
        contenido = f.read()
        if not contenido:
            raise ErrorSolicitud("El archivo está vacío.")
        return contenido, f.filename

    def _registrar(decision):
        contadores["acciones"][decision.accion] += 1
        per = decision.percepcion
        if per.get("intencion"):
            contadores["intenciones"][per["intencion"]] += 1
        if per.get("clase"):
            contadores["documentos"][per["clase"]] += 1
        g.detalle = f"{decision.capa}:{decision.accion}"

    # ---------------- Rutas ----------------
    @app.get("/api/salud")
    def salud():
        return jsonify({"ok": True, "estado": "en línea", "segundos_activo": int(time.time() - inicio),
                        "modelo_texto": {"frases_entrenamiento": agente.nlp.num_frases,
                                         "intenciones": len(agente.nlp.intenciones)},
                        "modelo_vision": {"motor": agente.vision.motor, "clases": agente.vision.clases},
                        "puestos": len(agente.kb.puestos)})

    @app.post("/api/intencion")
    def intencion():
        mensaje = _json("mensaje")["mensaje"]
        if len(mensaje) > 500:
            raise ErrorSolicitud("El mensaje es demasiado largo (máximo 500 caracteres).")
        intencion, confianza = agente.nlp.predecir(mensaje)
        g.detalle = intencion
        return jsonify({"ok": True, "intencion": intencion, "confianza": round(confianza, 3),
                        "texto_preprocesado": agente.nlp.preprocesar(mensaje)})

    @app.post("/api/documento")
    def documento():
        contenido, nombre = _archivo()
        try:
            clase, conf, probs = agente.vision.predecir(contenido, nombre)
        except ValueError as e:
            raise ErrorSolicitud(str(e), 422)
        g.detalle = clase
        return jsonify({"ok": True, "clase": clase, "confianza": round(conf, 3), "probabilidades": probs})

    @app.post("/api/agente/mensaje")
    def agente_mensaje():
        datos = _json("sesion", "mensaje")
        if len(datos["mensaje"]) > 500:
            raise ErrorSolicitud("El mensaje es demasiado largo (máximo 500 caracteres).")
        d = agente.procesar_texto(str(datos["sesion"]), datos["mensaje"])
        _registrar(d)
        return jsonify({"ok": True, **d.a_dict()})

    @app.post("/api/agente/documento")
    def agente_documento():
        sesion = request.form.get("sesion", "").strip()
        if not sesion:
            raise ErrorSolicitud("Falta el campo: sesion.")
        contenido, nombre = _archivo()
        d = agente.procesar_documento(sesion, contenido, nombre)   # el archivo no se guarda
        _registrar(d)
        return jsonify({"ok": True, **d.a_dict()})

    @app.post("/api/agente/reiniciar")
    def agente_reiniciar():
        agente.reiniciar(str(_json("sesion")["sesion"]))
        return jsonify({"ok": True})

    @app.get("/api/agenda")
    def agenda():
        return jsonify({"ok": True, "citas": almacen.citas()})

    @app.get("/api/metricas")
    def metricas():
        eventos = almacen.eventos()
        lat = [e["latencia_ms"] for e in eventos]
        errores = [e for e in eventos if e["estado"] >= 400]
        por_ruta = {}
        for e in eventos:
            r = por_ruta.setdefault(e["ruta"], {"peticiones": 0, "latencia_total": 0.0, "errores": 0})
            r["peticiones"] += 1
            r["latencia_total"] += e["latencia_ms"]
            r["errores"] += e["estado"] >= 400
        return jsonify({
            "ok": True,
            "segundos_activo": int(time.time() - inicio),
            "peticiones": len(eventos),
            "errores": len(errores),
            "tasa_error": round(len(errores) / len(eventos), 3) if eventos else 0,
            "latencia_promedio_ms": round(sum(lat) / len(lat), 1) if lat else 0,
            "latencia_p95_ms": round(sorted(lat)[int(len(lat) * 0.95) - 1], 1) if len(lat) >= 20 else None,
            "por_ruta": {k: {"peticiones": v["peticiones"], "errores": v["errores"],
                             "latencia_promedio_ms": round(v["latencia_total"] / v["peticiones"], 1)}
                         for k, v in por_ruta.items()},
            "intenciones": dict(contadores["intenciones"]),
            "documentos": dict(contadores["documentos"]),
            "acciones": dict(contadores["acciones"]),
            "ultimos_errores": errores[:10],
            "sesiones_activas": len(agente.sesiones),
        })

    return app


if __name__ == "__main__":
    puerto = int(os.environ.get("PUERTO", 5000))
    crear_app().run(host="0.0.0.0", port=puerto)
