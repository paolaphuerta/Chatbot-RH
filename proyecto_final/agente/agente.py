"""Agente inteligente de reclutamiento (arquitectura híbrida).

Ciclo del agente:  PERCIBIR → DELIBERAR → ACTUAR

- Percepción: el módulo NLP identifica la intención y el puesto del mensaje;
  el módulo de visión identifica el tipo de documento de un archivo.
- Capa reactiva: responde de inmediato las preguntas frecuentes (estímulo → respuesta).
- Capa deliberativa: tiene una META (que el candidato complete su postulación),
  mantiene CREENCIAS sobre el candidato (perfil, documentos, cita) y en cada
  turno genera un PLAN con los requisitos pendientes. La siguiente acción es
  atender el primer requisito del plan: preguntar un dato, validar un documento,
  volver a pedirlo, escalar el caso a recursos humanos o agendar la entrevista.
"""
import difflib
import re
import threading
import time
from dataclasses import asdict, dataclass, field

from .conocimiento import DIAS_HABILES
from .nlp import normalizar
from .vision import ArchivoInvalido

NOMBRE_DOC = {"ine": "INE", "licencia": "licencia de conducir",
              "comprobante": "comprobante de domicilio (recibo de luz o agua)"}
CORTO_DOC = {"ine": "INE", "licencia": "licencia", "comprobante": "comprobante de domicilio"}
MAX_INTENTOS = 3
SI = ["si", "claro", "sip", "simon", "correcto", "por supuesto", "ok", "va", "afirmativo"]
NO = ["no", "nop", "nel", "negativo"]
NUMEROS = {"cero": 0, "ninguno": 0, "nada": 0, "uno": 1, "un": 1, "dos": 2, "tres": 3, "cuatro": 4,
           "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10}


@dataclass
class Decision:
    """Resultado de un turno: qué percibió el agente, qué decidió y qué respondió."""
    respuesta: str
    capa: str                     # 'reactiva' o 'deliberativa'
    accion: str                   # nombre de la acción ejecutada
    percepcion: dict = field(default_factory=dict)
    objetivo: str = None          # requisito que el agente atiende ahora
    plan: list = field(default_factory=list)   # requisitos pendientes para cumplir la meta
    espera_documento: str = None  # 'ine', 'licencia' o 'comprobante' si el agente espera un archivo
    documentos: dict = field(default_factory=dict)

    def a_dict(self):
        return asdict(self)


def _contiene(texto, frase):
    return re.search(r"\b" + re.escape(frase) + r"\b", texto) is not None


def _si_no(texto):
    if any(_contiene(texto, n) for n in NO):
        return False
    if any(_contiene(texto, s) for s in SI):
        return True
    return None


def _numero(tokens):
    for t in tokens:
        if t.isdigit():
            return int(t)
    for t in tokens:
        if t in NUMEROS:
            return NUMEROS[t]
    return None


class AgenteReclutamiento:
    def __init__(self, conocimiento, nlp, vision, almacen):
        self.kb, self.nlp, self.vision, self.almacen = conocimiento, nlp, vision, almacen
        self.sesiones = {}
        self._candado = threading.Lock()

    # ======================= Creencias (estado de cada candidato) =======================
    @staticmethod
    def _estado_inicial():
        return {"modo": "conversacion", "puesto": None, "edad": None, "horario": None,
                "experiencia": None, "licencia": None, "docs": {}, "intentos": {},
                "dia": None, "hora": None, "nombre": None,
                "ultimo_puesto": None, "ofrecio_postular": None, "ultimo_uso": time.time()}

    def _estado(self, sesion):
        with self._candado:
            if len(self.sesiones) > 1000:                      # limpia sesiones viejas
                viejas = sorted(self.sesiones, key=lambda s: self.sesiones[s]["ultimo_uso"])[:200]
                for s in viejas:
                    self.sesiones.pop(s, None)
            est = self.sesiones.setdefault(sesion, self._estado_inicial())
            est["ultimo_uso"] = time.time()
            return est

    def reiniciar(self, sesion):
        with self._candado:
            self.sesiones.pop(sesion, None)

    # ======================= Planificación (capa deliberativa) =======================
    def plan(self, est):
        """Lista de requisitos pendientes para cumplir la meta: postulación completa y cita agendada."""
        if est["modo"] != "postulacion":
            return []
        p = self.kb.puestos.get(est["puesto"])
        pasos = ["puesto", "edad", "horario"]
        if p and p["experiencia"] > 0:
            pasos.append("experiencia")
        if p and p["requiere_licencia"]:
            pasos.append("licencia")
        pasos += ["doc_ine"] + (["doc_licencia"] if p and p["requiere_licencia"] else []) + ["doc_comprobante"]
        pasos += ["dia", "hora", "nombre"]
        cumplido = {
            "puesto": est["puesto"] is not None, "edad": est["edad"] is not None,
            "horario": est["horario"] is True, "experiencia": est["experiencia"] is not None,
            "licencia": est["licencia"] is True, "dia": est["dia"] is not None,
            "hora": est["hora"] is not None, "nombre": est["nombre"] is not None,
        }
        return [x for x in pasos if not (est["docs"].get(x[4:]) if x.startswith("doc_") else cumplido[x])]

    def _decision(self, est, respuesta, capa, accion, percepcion):
        plan = self.plan(est)
        objetivo = plan[0] if plan else None
        return Decision(
            respuesta=respuesta, capa=capa, accion=accion, percepcion=percepcion,
            objetivo=objetivo, plan=plan,
            espera_documento=objetivo[4:] if objetivo and objetivo.startswith("doc_") else None,
            documentos=dict(est["docs"]))

    # ======================= Percepción =======================
    def _identificar_puesto(self, tokens):
        for clave, sinonimos in self.kb.sinonimos.items():
            if any(t in sinonimos for t in tokens):
                return clave
        todos = {s: c for c, lista in self.kb.sinonimos.items() for s in lista}
        for t in tokens:                               # palabra mal escrita: «mesra», «cosinero»
            if len(t) >= 5:
                parecida = difflib.get_close_matches(t, list(todos), n=1, cutoff=0.85)
                if parecida:
                    return todos[parecida[0]]
        return None

    def _percibir_texto(self, mensaje):
        tokens = normalizar(mensaje).split()
        intencion, confianza = self.nlp.predecir(mensaje)
        return {"tipo": "texto", "tokens": tokens, "texto": " ".join(tokens),
                "intencion": intencion, "confianza": round(confianza, 2),
                "puesto": self._identificar_puesto(tokens)}

    # ======================= Turno de texto =======================
    def procesar_texto(self, sesion, mensaje):
        est = self._estado(sesion)
        per = self._percibir_texto(mensaje)
        resumen = {k: per[k] for k in ("tipo", "intencion", "confianza", "puesto")}

        if est["modo"] == "postulacion":
            if _contiene(per["texto"], "cancelar"):
                self.sesiones[sesion] = self._estado_inicial()
                return self._decision(self._estado(sesion), "Postulación cancelada. " + self._menu(),
                                      "deliberativa", "cancelar_postulacion", resumen)
            respuesta, accion = self._deliberar(est, per, mensaje)
            return self._decision(est, respuesta, "deliberativa", accion, resumen)

        respuesta, capa, accion = self._reaccionar(est, per)
        return self._decision(est, respuesta, capa, accion, resumen)

    # ---------- Capa reactiva ----------
    def _reaccionar(self, est, per):
        tokens, puesto, intencion = per["tokens"], per["puesto"], per["intencion"]

        ofrecio = est.pop("ofrecio_postular", None)
        if ofrecio and len(tokens) <= 2 and _si_no(per["texto"]):
            return self._iniciar_postulacion(est, ofrecio), "deliberativa", "iniciar_postulacion"

        if puesto:
            est["ultimo_puesto"] = puesto
            contenido = [t for t in tokens if t not in self.nlp.stopwords]
            if len(contenido) == 1:                       # solo escribió el puesto
                p = self.kb.puestos[puesto]
                est["ofrecio_postular"] = puesto
                return (f"{p['nombre']}: sueldo {p['sueldo']}, horario {' / '.join(p['horarios'])}, "
                        f"{self._texto_exp(p)}. ¿Quieres saber algo más o postularte?"), "reactiva", "ofrecer_postulacion"
        elif intencion in ("funciones", "sueldo", "horarios"):
            puesto = est["ultimo_puesto"]                 # seguimiento: «¿y cuánto pagan?»

        if intencion == "postularse":
            return self._iniciar_postulacion(est, puesto), "deliberativa", "iniciar_postulacion"
        return self._respuesta_faq(intencion, puesto), "reactiva", "responder_faq"

    # ---------- Capa deliberativa ----------
    def _iniciar_postulacion(self, est, puesto):
        est.update(self._estado_inicial())
        est["modo"] = "postulacion"
        if puesto:
            est["puesto"] = puesto
            return f"¡Qué gusto! Te haré unas preguntas rápidas para el puesto de {self.kb.puestos[puesto]['nombre']}.\n" \
                   + self._pregunta(est)
        return ("¡Qué gusto que quieras unirte! Te haré unas preguntas rápidas "
                "(escribe \"cancelar\" en cualquier momento).\n" + self._pregunta(est))

    def _deliberar(self, est, per, mensaje):
        """Atiende el primer requisito pendiente del plan y decide la siguiente acción."""
        objetivo = self.plan(est)[0]
        tokens, texto = per["tokens"], per["texto"]
        p = self.kb.puestos.get(est["puesto"])
        g = self.kb.general

        if objetivo.startswith("doc_"):
            return "Para continuar necesito el archivo. " + self._pregunta(est), "solicitar_documento"

        valor, aclaracion = None, None
        if objetivo == "puesto":
            valor = per["puesto"]
            aclaracion = "No reconocí el puesto."
        elif objetivo == "edad":
            n = _numero(tokens)
            valor = n if n is not None and 10 <= n <= 99 else None
            aclaracion = "Escribe tu edad con un número, por ejemplo: 25."
        elif objetivo in ("horario", "licencia"):
            valor = _si_no(texto)
            aclaracion = "Por favor responde sí o no."
        elif objetivo == "experiencia":
            valor = _numero(tokens)
            aclaracion = "Escribe tus años de experiencia con un número, por ejemplo: 2."
        elif objetivo == "dia":
            valor = next((d for d in DIAS_HABILES if _contiene(texto, d)), None)
            if valor is None and (_contiene(texto, "sabado") or _contiene(texto, "domingo")):
                aclaracion = f"Las entrevistas son solo de {self.kb.entrevista['dias']}."
            elif valor and not self._libres(valor):
                valor, aclaracion = None, f"El {valor} ya no tiene espacios."
            else:
                aclaracion = "No reconocí el día."
        elif objetivo == "hora":
            valor = self._extraer_hora(texto)
            if valor not in self.kb.espacios_del_dia():
                valor, aclaracion = None, "Elige uno de los horarios disponibles."
            elif valor in self.almacen.ocupados(est["dia"]):
                valor, aclaracion = None, "Ese horario ya está ocupado."
        elif objetivo == "nombre":
            nombre = " ".join(mensaje.split()).title()
            valor = nombre if 2 <= len(nombre) <= 60 else None
            aclaracion = "Por favor escribe tu nombre."

        # No entendió la respuesta: si era una pregunta frecuente, la responde y retoma el plan (híbrido)
        if valor is None:
            if per["intencion"] not in ("no_entendido", "fuera_de_tema", "saludo", "despedida") \
                    and per["confianza"] >= 0.55 and objetivo not in ("puesto", "nombre"):
                faq = self._respuesta_faq(per["intencion"], est["puesto"])
                return faq + "\n\nContinuemos con tu postulación: " + self._pregunta(est), "responder_faq_y_retomar"
            return aclaracion + " " + self._pregunta(est), "aclarar"

        # Registrar la creencia y validar los requisitos del puesto
        if objetivo == "puesto":
            est["puesto"] = valor
            p = self.kb.puestos[valor]
            return f"Perfecto, {p['nombre']}. " + self._pregunta(est), "registrar_dato"
        if objetivo == "edad":
            if valor < g["edad_minima"]:
                return self._rechazar(est, f"tener al menos {g['edad_minima']} años"), "rechazar_por_requisito"
            est["edad"] = valor
        if objetivo == "horario":
            if not valor:
                return self._rechazar(est, "disponibilidad para los horarios del puesto"), "rechazar_por_requisito"
            est["horario"] = True
        if objetivo == "experiencia":
            if valor < p["experiencia"]:
                return self._rechazar(est, self._texto_exp(p), sugerir=True), "rechazar_por_requisito"
            est["experiencia"] = valor
        if objetivo == "licencia":
            if not valor:
                return self._rechazar(est, "licencia de conducir vigente"), "rechazar_por_requisito"
            est["licencia"] = True
        if objetivo == "dia":
            est["dia"] = valor
        if objetivo == "hora":
            est["hora"] = valor
        if objetivo == "nombre":
            est["nombre"] = valor
            return self._agendar(est)

        siguiente = self.plan(est)[0]
        prefijo = ""
        if siguiente == "doc_ine":
            prefijo = (f"✅ ¡Tu perfil es compatible con el puesto de {p['nombre']}!\n"
                       "Antes de agendar tu entrevista necesito tus documentos.\n")
        return prefijo + self._pregunta(est), "registrar_dato"

    def _rechazar(self, est, motivo, sugerir=False):
        est["modo"] = "conversacion"
        t = f"Gracias por tus respuestas. Por ahora no cumples con un requisito: {motivo}."
        if sugerir:
            t += f"\nTe pueden interesar puestos que no piden experiencia: {', '.join(self.kb.puestos_sin_experiencia())}."
        return t + "\nSi tienes otra duda, con gusto te ayudo."

    def _agendar(self, est):
        p = self.kb.puestos[est["puesto"]]
        ok = [d for d, v in est["docs"].items() if v == "aceptado"]
        revision = [d for d, v in est["docs"].items() if v == "revision"]
        if not self.almacen.agendar(est["dia"], est["hora"], est["nombre"], p["nombre"],
                                    [CORTO_DOC[d] for d in ok], [CORTO_DOC[d] for d in revision]):
            est["hora"], est["nombre"] = None, None          # otro candidato tomó el espacio
            return "Lo siento, ese horario se acaba de ocupar. " + self._pregunta(est), "replanificar_cita"
        t = (f"📅 Listo, {est['nombre']}. Tu entrevista para {p['nombre']} quedó agendada:\n"
             f"  • Día: {est['dia']}\n  • Hora: {est['hora']}\n  • Lugar: {self.kb.entrevista['lugar']}\n"
             f"  • Documentos recibidos: {', '.join(CORTO_DOC[d] for d in ok) or 'ninguno'}")
        if revision:
            t += f"\n  • Recursos humanos revisará en la entrevista: {', '.join(CORTO_DOC[d] for d in revision)}"
        est["modo"] = "conversacion"
        return t + "\n¡Te esperamos!", "agendar_entrevista"

    # ======================= Turno con documento =======================
    def procesar_documento(self, sesion, contenido, nombre_archivo):
        est = self._estado(sesion)
        plan = self.plan(est)
        if not plan or not plan[0].startswith("doc_"):
            return self._decision(est, "Gracias. Los documentos se reciben al completar el prefiltro: "
                                       "escribe \"me interesa\" para empezar.", "reactiva",
                                  "documento_no_solicitado", {"tipo": "documento"})
        esperado = plan[0][4:]
        try:
            clase, conf, probs = self.vision.predecir(contenido, nombre_archivo)
        except ArchivoInvalido as e:
            return self._decision(est, f"⚠️ {e} " + self._pregunta(est), "deliberativa", "archivo_invalido",
                                  {"tipo": "documento", "error": str(e)})
        per = {"tipo": "documento", "clase": clase, "confianza": round(conf, 2), "probabilidades": probs,
               "esperado": esperado}

        if clase == esperado:
            est["docs"][esperado] = "aceptado"
            msg, accion = f"✅ Recibí tu {NOMBRE_DOC[esperado]}.", "aceptar_documento"
        else:
            est["intentos"][esperado] = est["intentos"].get(esperado, 0) + 1
            if clase == "dudoso":
                msg = ("❓ No pude identificar el documento con seguridad. Envía otra foto con buena luz, "
                       "sin reflejos y con el documento completo.")
            elif clase == "otro":
                msg = f"⚠️ Esta imagen no parece un documento. Necesito tu {NOMBRE_DOC[esperado]}."
            else:
                msg = f"⚠️ Esta imagen parece tu {NOMBRE_DOC[clase]}, pero en este paso necesito tu {NOMBRE_DOC[esperado]}."
            accion = "solicitar_reenvio"
            if est["intentos"][esperado] >= MAX_INTENTOS:
                est["docs"][esperado] = "revision"
                msg += f"\nNo te preocupes: recursos humanos revisará tu {NOMBRE_DOC[esperado]} en la entrevista."
                accion = "escalar_a_rh"
            else:
                return self._decision(est, msg, "deliberativa", accion, per)

        siguiente = self.plan(est)[0]
        if siguiente == "dia":
            msg += "\nYa tengo tus documentos. "
        else:
            msg += "\n"
        return self._decision(est, msg + self._pregunta(est), "deliberativa", accion, per)

    # ======================= Acciones de comunicación =======================
    def _pregunta(self, est):
        objetivo = self.plan(est)[0]
        p = self.kb.puestos.get(est["puesto"])
        e = self.kb.entrevista
        if objetivo == "puesto":
            return "¿Qué puesto te interesa?\n" + self._lista_puestos()
        if objetivo == "edad":
            return "¿Cuántos años tienes? (escribe un número)"
        if objetivo == "horario":
            return f"Los horarios de {p['nombre']} son: {' / '.join(p['horarios'])}. ¿Puedes cubrir alguno? (sí / no)"
        if objetivo == "experiencia":
            return f"¿Cuántos años de experiencia tienes como {p['nombre']}? (escribe un número)"
        if objetivo == "licencia":
            return "¿Cuentas con licencia de conducir vigente? (sí / no)"
        if objetivo.startswith("doc_"):
            return f"📎 Envía una foto o PDF de tu {NOMBRE_DOC[objetivo[4:]]}."
        if objetivo == "dia":
            return f"¿Qué día te queda mejor para tu entrevista {e['modalidad']} de {e['duracion']}? ({e['dias']})"
        if objetivo == "hora":
            return f"Horarios disponibles el {est['dia']}: {', '.join(self._libres(est['dia']))}. ¿Cuál prefieres?"
        return "¡Perfecto! Para registrar tu cita, ¿cuál es tu nombre?"

    def _libres(self, dia):
        ocupados = self.almacen.ocupados(dia)
        return [h for h in self.kb.espacios_del_dia() if h not in ocupados]

    @staticmethod
    def _extraer_hora(texto):
        m = re.search(r"\b(\d{1,2})(?:\s+(\d{2}))?\b", texto)
        if not m:
            return None
        h, mins = int(m.group(1)), int(m.group(2) or 0)
        if 1 <= h <= 7:                      # «a las 2» en horario de oficina = 14:00
            h += 12
        return f"{h}:{mins:02d}"

    @staticmethod
    def _texto_exp(p):
        if p["experiencia"] == 0:
            return "no se requiere experiencia"
        return f"se requiere mínimo {p['experiencia']} año{'s' if p['experiencia'] > 1 else ''} de experiencia"

    def _lista_puestos(self):
        return "\n".join(f"  • {p['nombre']}" for p in self.kb.puestos.values())

    def _menu(self):
        return ("Puedo ayudarte con: vacantes, funciones, sueldos, horarios, experiencia, prestaciones, "
                "propinas, documentos y entrevistas.\nSi quieres postularte, escribe \"me interesa\".")

    def _respuesta_faq(self, intencion, puesto):
        kb, g, e = self.kb, self.kb.general, self.kb.entrevista
        p = kb.puestos.get(puesto)
        if intencion == "saludo":
            return ("¡Hola! Soy el asistente virtual de reclutamiento de El Sauce. 😊 "
                    "Soy un programa automático; las decisiones finales las toma recursos humanos.\n" + self._menu())
        if intencion == "vacantes":
            return ("Estos son los puestos que estamos contratando:\n" + self._lista_puestos() +
                    "\n¿Te interesa alguno? Pregúntame por sus funciones, sueldo u horario.")
        if intencion == "funciones":
            return (f"El puesto de {p['nombre']} se encarga de {p['funciones']}" if p
                    else "¿De qué puesto quieres conocer las funciones?\n" + self._lista_puestos())
        if intencion == "sueldo":
            if p:
                return f"El sueldo de {p['nombre']} es de {p['sueldo']}{' más propinas' if p['propinas'] else ''}."
            return "Estos son los sueldos por puesto:\n" + "\n".join(
                f"  • {x['nombre']}: {x['sueldo']}" for x in kb.puestos.values())
        if intencion == "horarios":
            if p:
                return f"Horarios de {p['nombre']}: {' / '.join(p['horarios'])}. {g['turnos']}"
            return "Horarios por puesto:\n" + "\n".join(
                f"  • {x['nombre']}: {' / '.join(x['horarios'])}" for x in kb.puestos.values()) + "\n" + g["turnos"]
        if intencion == "flexibilidad":
            return g["flexibilidad"] + " Puedes comentarlo en tu entrevista."
        if intencion == "experiencia":
            if p:
                return f"Para {p['nombre']} {self._texto_exp(p)}."
            return ("Algunos puestos piden experiencia y otros no. Puedes entrar sin experiencia como: "
                    + ", ".join(kb.puestos_sin_experiencia()) + ".")
        if intencion == "prestaciones":
            return f"Ofrecemos:\n  • {g['descanso']}\n  • {g['comida']}\n  • Propinas (según el puesto)"
        if intencion == "propinas":
            if p:
                return f"El puesto de {p['nombre']} {'sí' if p['propinas'] else 'no'} recibe propinas."
            return "Sí se reparten propinas entre: " + ", ".join(
                x["nombre"] for x in kb.puestos.values() if x["propinas"]) + "."
        if intencion == "documentos":
            con_lic = [x["nombre"] for x in kb.puestos.values() if x["requiere_licencia"]]
            return (f"Los documentos obligatorios son: {g['documentos']}. Es deseable una {g['deseable']}. "
                    f"Para {', '.join(con_lic)} también se requiere licencia de conducir vigente. "
                    "Puedes enviarlos por aquí al completar el prefiltro (escribe \"me interesa\").")
        if intencion == "entrevista":
            return (f"Las entrevistas son {e['modalidad']}es en {e['lugar']}, de {e['dias']} de {e['horario']}, "
                    f"y duran {e['duracion']}. Para agendar primero completa el prefiltro (escribe \"me interesa\").")
        if intencion == "consulta_rh":
            return ("Esa información te la explica directamente el área de recursos humanos durante la entrevista. 🙂\n"
                    "¿Te puedo ayudar con algo más sobre las vacantes?")
        if intencion == "fuera_de_tema":
            return ("Este chat es solo para reclutamiento de personal de El Sauce. Para pedidos, reservaciones o "
                    "dudas del menú, comunícate directamente con el restaurante.\n" + self._menu())
        if intencion == "despedida":
            return "¡Gracias por tu interés en El Sauce! Mucho éxito. 👋"
        return "Perdón, no entendí tu mensaje. 🤔\n" + self._menu()
