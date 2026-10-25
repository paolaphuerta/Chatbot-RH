# ============================================================
# Chatbot de Recursos Humanos - Restaurante El Sauce
# Proyecto Fase 1 (MBIA2602): chatbot basado en reglas
# Python 3.10+ y NLTK
# ============================================================

import re
import unicodedata

import nltk
import pandas as pd
from nltk.tokenize import wordpunct_tokenize


# ------------------------------------------------------------
# 1. BASE DE CONOCIMIENTO
#    Toda la información del restaurante se lee desde el archivo
#    base_conocimiento.xlsx. Para cambiar sueldos, horarios o
#    puestos se edita el Excel, no el código.
# ------------------------------------------------------------

ARCHIVO_BASE = "base_conocimiento.xlsx"


def _sin_acentos(texto):
    texto = unicodedata.normalize("NFD", str(texto).lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn").strip()


def _es_si(valor):
    return _sin_acentos(valor) in ("si", "s", "yes", "true", "1")


def cargar_base(ruta=ARCHIVO_BASE):
    """Lee las hojas Puestos, General y Entrevista del Excel."""
    puestos_df = pd.read_excel(ruta, sheet_name="Puestos").dropna(subset=["Puesto"])
    general_df = pd.read_excel(ruta, sheet_name="General")
    entrevista_df = pd.read_excel(ruta, sheet_name="Entrevista")

    puestos, sinonimos = {}, {}
    for _, fila in puestos_df.iterrows():
        palabras = [_sin_acentos(p) for p in str(fila["Palabras clave"]).split(",") if p.strip()]
        clave = palabras[0] if palabras else _sin_acentos(fila["Puesto"])
        puestos[clave] = {
            "nombre": str(fila["Puesto"]).strip(),
            "horarios": [h.strip() for h in str(fila["Horarios"]).split("|") if h.strip()],
            "sueldo": str(fila["Sueldo"]).strip(),
            "experiencia": int(fila["Experiencia (años)"]) if pd.notna(fila["Experiencia (años)"]) else 0,
            "propinas": _es_si(fila["Propinas"]),
            "requiere_licencia": _es_si(fila["Requiere licencia"]),
            "funciones": str(fila["Funciones"]).strip(),
        }
        sinonimos[clave] = palabras

    general = dict(zip(general_df["Concepto"].str.strip(), general_df["Valor"]))
    general["edad_minima"] = int(general.get("edad_minima", 18))
    entrevista = dict(zip(entrevista_df["Concepto"].str.strip(), entrevista_df["Valor"].astype(str)))
    return puestos, sinonimos, general, entrevista


PUESTOS, SINONIMOS_PUESTO, GENERAL, ENTREVISTA = cargar_base()
print(f"Base de conocimiento cargada: {len(PUESTOS)} puestos.")


# ------------------------------------------------------------
# 2. PREPROCESAMIENTO
#    Minúsculas, quitar acentos y tokenizar con NLTK.
# ------------------------------------------------------------

def normalizar(texto):
    texto = texto.lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")  # quita acentos
    return texto


def preprocesar(mensaje):
    """Devuelve la lista de palabras (tokens) y el texto limpio."""
    texto = normalizar(mensaje)
    tokens = [t for t in wordpunct_tokenize(texto) if t.isalnum()]
    return tokens, " ".join(tokens)


# ------------------------------------------------------------
# 3. REGLAS DE INTENCIÓN (palabras clave)
#    El orden importa: se revisan de arriba hacia abajo.
# ------------------------------------------------------------

INTENCIONES = [
    ("postularse",   ["postular", "postularme", "postulo", "postulacion", "aplicar", "aplico",
                      "me interesa", "quiero trabajar",
                      "quiero entrar", "quiero el puesto", "como aplico", "registrarme"]),
    ("flexibilidad", ["elegir mi horario", "elegir horario", "escoger", "cambiar de turno",
                      "cambiar mi horario", "acomodar", "flexible", "flexibilidad"]),
    ("experiencia",  ["experiencia", "nunca he trabajado", "primer trabajo", "primer empleo"]),
    ("funciones",    ["que hace", "que hacen", "funciones", "en que consiste", "actividades",
                      "de que se trata", "que se hace"]),
    ("sueldo",       ["cuanto pagan", "sueldo", "salario", "paga", "pago", "pagan", "cuanto ganan",
                      "cuanto se gana", "cuanto gana"]),
    ("horarios",     ["horario", "horarios", "turno", "turnos", "hora", "entrada", "salida"]),
    ("propinas",     ["propina", "propinas"]),
    ("prestaciones", ["prestaciones", "prestacion", "comida", "comer", "descanso", "beneficios",
                      "dan de comer", "que ofrecen"]),
    ("documentos",   ["documentos", "papeles", "papeleria", "requisitos", "ine", "comprobante",
                      "que necesito", "que piden"]),
    ("entrevista",   ["entrevista", "cita", "direccion", "donde estan", "ubicacion", "donde queda"]),
    ("vacantes",     ["vacantes", "vacante", "puestos", "contratando", "trabajo disponible",
                      "que hay", "solicitan", "buscan"]),
    ("despedida",    ["gracias", "adios", "bye", "hasta luego", "nos vemos"]),
    ("saludo",       ["hola", "buenas", "buen dia", "buenos dias", "que tal", "hey"]),
]


def contiene(texto, frase):
    """Revisa si una palabra o frase completa aparece en el texto."""
    return re.search(r"\b" + re.escape(frase) + r"\b", texto) is not None


def identificar_intencion(texto):
    for intencion, palabras in INTENCIONES:
        if any(contiene(texto, p) for p in palabras):
            return intencion
    return "no_entendido"


def identificar_puesto(tokens):
    for clave, sinonimos in SINONIMOS_PUESTO.items():
        if any(t in sinonimos for t in tokens):
            return clave
    return None


# ------------------------------------------------------------
# 4. RESPUESTAS (consultan la base de conocimiento)
# ------------------------------------------------------------

def lista_puestos():
    return "\n".join(f"  • {p['nombre']}" for p in PUESTOS.values())


def puestos_sin_experiencia():
    return ", ".join(p["nombre"] for p in PUESTOS.values() if p["experiencia"] == 0)


def texto_experiencia(p):
    if p["experiencia"] == 0:
        return "no se requiere experiencia"
    anios = "año" if p["experiencia"] == 1 else "años"
    return f"se requiere mínimo {p['experiencia']} {anios} de experiencia"


def tabla_resumen(campo):
    lineas = []
    for p in PUESTOS.values():
        if campo == "sueldo":
            lineas.append(f"  • {p['nombre']}: {p['sueldo']}")
        elif campo == "horarios":
            lineas.append(f"  • {p['nombre']}: {' / '.join(p['horarios'])}")
    return "\n".join(lineas)


MENU = ("Puedo ayudarte con: vacantes, funciones de cada puesto, sueldos, horarios, "
        "experiencia, prestaciones, propinas, documentos y entrevistas.\n"
        "Si quieres postularte, escribe \"me interesa\".")


def responder_faq(intencion, puesto):
    p = PUESTOS.get(puesto)

    if intencion == "saludo":
        return "¡Hola! Soy el asistente de reclutamiento de El Sauce. 😊\n" + MENU

    if intencion == "vacantes":
        return "Estos son los puestos que estamos contratando:\n" + lista_puestos() + \
               "\n¿Te interesa alguno? Pregúntame por sus funciones, sueldo u horario."

    if intencion == "funciones":
        if p:
            return f"El puesto de {p['nombre']} se encarga de {p['funciones']}"
        return "¿De qué puesto quieres conocer las funciones?\n" + lista_puestos()

    if intencion == "sueldo":
        if p:
            extra = " más propinas" if p["propinas"] else ""
            return f"El sueldo de {p['nombre']} es de {p['sueldo']}{extra}."
        return "Estos son los sueldos por puesto:\n" + tabla_resumen("sueldo")

    if intencion == "horarios":
        if p:
            return (f"Horarios de {p['nombre']}: {' / '.join(p['horarios'])}. "
                    f"{GENERAL['turnos']}")
        return "Horarios por puesto (formato 24 h):\n" + tabla_resumen("horarios") + \
               "\n" + GENERAL["turnos"]

    if intencion == "flexibilidad":
        return GENERAL["flexibilidad"] + " " + GENERAL["turnos"] + \
               " Puedes comentarlo durante tu entrevista."

    if intencion == "experiencia":
        if p:
            return f"Para {p['nombre']} {texto_experiencia(p)}."
        return ("Algunos puestos piden experiencia y otros no. "
                f"Puedes entrar sin experiencia como: {puestos_sin_experiencia()}.")

    if intencion == "prestaciones":
        return ("Ofrecemos:\n"
                f"  • {GENERAL['descanso']}\n"
                f"  • {GENERAL['comida']}\n"
                "  • Propinas (según el puesto)")

    if intencion == "propinas":
        if p:
            return f"El puesto de {p['nombre']} {'sí' if p['propinas'] else 'no'} recibe propinas."
        con = ", ".join(x["nombre"] for x in PUESTOS.values() if x["propinas"])
        return f"Sí se reparten propinas entre: {con}."

    if intencion == "documentos":
        texto = (f"Los documentos obligatorios son: {GENERAL['documentos']}. "
                 f"Es deseable una {GENERAL['deseable']}.")
        con_licencia = [x["nombre"] for x in PUESTOS.values() if x["requiere_licencia"]]
        if p and p["requiere_licencia"]:
            texto += f" Para {p['nombre']} también se requiere licencia de conducir vigente."
        elif puesto is None and con_licencia:
            texto += f" Para {', '.join(con_licencia)} también se requiere licencia de conducir vigente."
        return texto

    if intencion == "entrevista":
        return (f"Las entrevistas son {ENTREVISTA['modalidad']}es en {ENTREVISTA['lugar']}, "
                f"de {ENTREVISTA['dias']} de {ENTREVISTA['horario']} "
                f"y duran {ENTREVISTA['duracion']}. "
                "Para agendar tu cita primero hay que completar un prefiltro rápido "
                "(escribe \"me interesa\" para comenzar).")

    if intencion == "despedida":
        return "¡Gracias por tu interés en El Sauce! Mucho éxito. 👋"

    return "Perdón, no entendí tu mensaje. 🤔\n" + MENU


# ------------------------------------------------------------
# 5. FLUJO CONVERSACIONAL: PREFILTRO DE COMPATIBILIDAD
#    El bot recuerda en qué paso va usando el diccionario "estado".
# ------------------------------------------------------------

SI = ["si", "claro", "sip", "simon", "afirmativo", "correcto", "por supuesto", "yes", "ok"]
NO = ["no", "nop", "nel", "negativo"]


def respuesta_si_no(texto):
    if any(contiene(texto, n) for n in NO):
        return False
    if any(contiene(texto, s) for s in SI):
        return True
    return None


def extraer_numero(tokens):
    for t in tokens:
        if t.isdigit():
            return int(t)
    palabras = {"cero": 0, "ninguno": 0, "nada": 0, "uno": 1, "un": 1, "dos": 2,
                "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "diez": 10}
    for t in tokens:
        if t in palabras:
            return palabras[t]
    return None


def resultado_compatible(estado):
    """El perfil pasó todos los filtros: se pasa a agendar la entrevista."""
    p = PUESTOS[estado["puesto"]]
    estado["paso"] = "dia"
    return (f"✅ ¡Tu perfil es compatible con el puesto de {p['nombre']}!\n"
            f"Vamos a agendar tu entrevista {ENTREVISTA['modalidad']} "
            f"({ENTREVISTA['duracion']}). ¿Qué día te queda mejor? "
            f"({ENTREVISTA['dias']})")


# ------------------------------------------------------------
# 5b. AGENDA DE ENTREVISTAS (simulada en memoria)
#     Los espacios se calculan con el horario y la duración del Excel.
#     AGENDA guarda las citas ocupadas: {"lunes": {"10:00": "Ana"}, ...}
# ------------------------------------------------------------

DIAS_HABILES = ["lunes", "martes", "miercoles", "jueves", "viernes"]
AGENDA = {dia: {} for dia in DIAS_HABILES}


def _a_minutos(hora):
    h, m = hora.split(":")
    return int(h) * 60 + int(m)


def _a_texto(minutos):
    return f"{minutos // 60}:{minutos % 60:02d}"


def espacios_del_dia():
    """Lista de horas de inicio posibles, por ejemplo 10:00, 10:20, ..., 15:40."""
    inicio, fin = re.findall(r"\d{1,2}:\d{2}", ENTREVISTA["horario"])[:2]
    duracion = int(re.search(r"\d+", ENTREVISTA["duracion"]).group())
    return [_a_texto(m) for m in range(_a_minutos(inicio), _a_minutos(fin) - duracion + 1, duracion)]


def espacios_libres(dia):
    return [h for h in espacios_del_dia() if h not in AGENDA[dia]]


def extraer_dia(texto):
    for dia in DIAS_HABILES:
        if contiene(texto, dia):
            return dia
    if contiene(texto, "sabado") or contiene(texto, "domingo"):
        return "fin_de_semana"
    return None


def extraer_hora(texto):
    """Entiende '11', '11:20', 'a las 2' (se asume 14:00)."""
    m = re.search(r"\b(\d{1,2})(?:\s+(\d{2}))?\b", texto)
    if not m:
        return None
    h, mins = int(m.group(1)), int(m.group(2) or 0)
    if 1 <= h <= 7:          # "a las 2" en horario de oficina = 14:00
        h += 12
    return _a_texto(h * 60 + mins)


def ver_agenda():
    """Para el personal de RH: muestra las entrevistas agendadas."""
    hay = False
    for dia in DIAS_HABILES:
        for hora in sorted(AGENDA[dia], key=_a_minutos):
            print(f"{dia.capitalize():<10} {hora:>5}  {AGENDA[dia][hora]}")
            hay = True
    if not hay:
        print("No hay entrevistas agendadas.")


def mostrar_espacios(dia):
    libres = espacios_libres(dia)
    return ", ".join(libres)


def resultado_no_compatible(motivo, sugerir_sin_exp=False):
    texto = f"Gracias por tus respuestas. Por ahora no cumples con un requisito: {motivo}."
    if sugerir_sin_exp:
        texto += f"\nTe pueden interesar puestos que no piden experiencia: {puestos_sin_experiencia()}."
    texto += "\nSi tienes otra duda, con gusto te ayudo."
    return texto


def siguiente_paso_despues_de_horario(estado):
    p = PUESTOS[estado["puesto"]]
    if p["experiencia"] > 0:
        estado["paso"] = "experiencia"
        return f"¿Cuántos años de experiencia tienes como {p['nombre']}? (escribe un número)"
    return siguiente_paso_despues_de_experiencia(estado)


def siguiente_paso_despues_de_experiencia(estado):
    p = PUESTOS[estado["puesto"]]
    if p["requiere_licencia"]:
        estado["paso"] = "licencia"
        return "¿Cuentas con licencia de conducir vigente? (sí / no)"
    return resultado_compatible(estado)


def iniciar_prefiltro(estado, puesto):
    estado["paso"] = "puesto"
    if puesto:
        return procesar_prefiltro(estado, [], puesto)
    return ("¡Qué gusto que quieras unirte! Te haré unas preguntas rápidas "
            "(puedes escribir \"cancelar\" en cualquier momento).\n"
            "¿Qué puesto te interesa?\n" + lista_puestos())


def procesar_prefiltro(estado, tokens, puesto_detectado, texto=""):
    paso = estado["paso"]

    if paso == "puesto":
        if not puesto_detectado:
            return "No reconocí el puesto. Elige uno de estos:\n" + lista_puestos()
        estado["puesto"] = puesto_detectado
        estado["paso"] = "edad"
        return (f"Perfecto, {PUESTOS[puesto_detectado]['nombre']}. "
                "¿Cuántos años tienes? (escribe un número)")

    if paso == "edad":
        # La edad solo se usa para verificar la edad mínima legal (18 años)
        edad = extraer_numero(tokens)
        if edad is None or edad < 10 or edad > 99:
            return "Escribe tu edad con un número, por ejemplo: 25"
        if edad < GENERAL["edad_minima"]:
            estado["paso"] = None
            return resultado_no_compatible(f"tener al menos {GENERAL['edad_minima']} años")
        p = PUESTOS[estado["puesto"]]
        estado["paso"] = "horario"
        return f"Los horarios de {p['nombre']} son: {' / '.join(p['horarios'])}. ¿Puedes cubrir alguno? (sí / no)"

    if paso == "horario":
        r = respuesta_si_no(texto)
        if r is None:
            return "Por favor responde sí o no: ¿puedes cubrir alguno de los horarios?"
        if not r:
            estado["paso"] = None
            return resultado_no_compatible("disponibilidad para los horarios del puesto")
        return siguiente_paso_despues_de_horario(estado)

    if paso == "experiencia":
        anios = extraer_numero(tokens)
        if anios is None:
            return "Escribe tus años de experiencia con un número, por ejemplo: 2"
        p = PUESTOS[estado["puesto"]]
        if anios < p["experiencia"]:
            estado["paso"] = None
            return resultado_no_compatible(f"{texto_experiencia(p)}", sugerir_sin_exp=True)
        return siguiente_paso_despues_de_experiencia(estado)

    if paso == "licencia":
        r = respuesta_si_no(texto)
        if r is None:
            return "Por favor responde sí o no: ¿tienes licencia de conducir vigente?"
        if not r:
            estado["paso"] = None
            return resultado_no_compatible("licencia de conducir vigente")
        return resultado_compatible(estado)

    if paso == "dia":
        dia = extraer_dia(texto)
        if dia == "fin_de_semana":
            return f"Las entrevistas son solo de {ENTREVISTA['dias']}. ¿Qué día de esos prefieres?"
        if dia is None:
            return f"No reconocí el día. Escribe uno de estos: {', '.join(d.capitalize() for d in DIAS_HABILES)}."
        if not espacios_libres(dia):
            return f"El {dia} ya no tiene espacios disponibles. ¿Te queda otro día?"
        estado["dia"] = dia
        estado["paso"] = "hora"
        return f"Horarios disponibles el {dia}: {mostrar_espacios(dia)}. ¿Cuál prefieres?"

    if paso == "hora":
        hora = extraer_hora(texto)
        dia = estado["dia"]
        if hora is None or hora not in espacios_del_dia():
            return f"Elige uno de estos horarios: {mostrar_espacios(dia)}"
        if hora in AGENDA[dia]:
            return f"Ese horario ya está ocupado. Disponibles: {mostrar_espacios(dia)}"
        estado["hora"] = hora
        estado["paso"] = "nombre"
        return "¡Perfecto! Para registrar tu cita, ¿cuál es tu nombre?"

    if paso == "nombre":
        nombre = estado.get("mensaje_original", "").strip().title()
        if len(nombre) < 2:
            return "Por favor escribe tu nombre."
        AGENDA[estado["dia"]][estado["hora"]] = nombre
        estado["paso"] = None
        p = PUESTOS[estado["puesto"]]
        return (f"📅 Listo, {nombre}. Tu entrevista para {p['nombre']} quedó agendada:\n"
                f"  • Día: {estado['dia']}\n"
                f"  • Hora: {estado['hora']}\n"
                f"  • Lugar: {ENTREVISTA['lugar']}\n"
                f"  • Duración: {ENTREVISTA['duracion']}\n"
                "¡Te esperamos!")


# ------------------------------------------------------------
# 6. MOTOR PRINCIPAL DEL CHATBOT
# ------------------------------------------------------------

def nuevo_estado():
    return {"paso": None, "puesto": None, "ultimo_puesto": None}


def responder(mensaje, estado):
    tokens, texto = preprocesar(mensaje)
    puesto = identificar_puesto(tokens)
    estado["mensaje_original"] = mensaje

    # a) Si estamos dentro del prefiltro, seguimos ese flujo
    if estado["paso"]:
        if contiene(texto, "cancelar") or contiene(texto, "salir"):
            estado["paso"] = None
            return "Prefiltro cancelado. " + MENU
        return procesar_prefiltro(estado, tokens, puesto, texto)

    # b) Si no, identificamos la intención
    intencion = identificar_intencion(texto)

    # Si el bot acaba de ofrecer postularse y el usuario dice "sí", iniciamos el prefiltro
    ofrecio = estado.pop("ofrecio_postular", None)
    if ofrecio and intencion == "no_entendido" and respuesta_si_no(texto):
        return iniciar_prefiltro(estado, ofrecio)

    # Memoria de contexto: si no menciona puesto, usamos el último
    if puesto:
        estado["ultimo_puesto"] = puesto
    elif intencion in ("funciones", "sueldo", "horarios"):
        # Solo estas preguntas de seguimiento ("¿y cuánto pagan?") usan el último puesto;
        # "¿reparten propinas?" o "¿puedo entrar sin experiencia?" se responden en general.
        puesto = estado["ultimo_puesto"]

    # Si solo escribe el nombre de un puesto, mostramos su resumen
    if intencion == "no_entendido" and puesto:
        p = PUESTOS[puesto]
        estado["ofrecio_postular"] = puesto
        return (f"{p['nombre']}: sueldo {p['sueldo']}, horario {' / '.join(p['horarios'])}, "
                f"{texto_experiencia(p)}. ¿Quieres saber algo más o postularte?")

    if intencion == "postularse":
        return iniciar_prefiltro(estado, puesto)

    return responder_faq(intencion, puesto)


def chatear():
    """Modo interactivo: escribe mensajes como si fueras un candidato."""
    print("Asistente de RH - El Sauce (escribe 'salir' para terminar)\n")
    estado = nuevo_estado()
    while True:
        mensaje = input("Tú: ")
        if normalizar(mensaje).strip() in ("salir", "exit") and not estado["paso"]:
            print("Bot: ¡Hasta pronto!")
            break
        print("Bot:", responder(mensaje, estado), "\n")


def probar_conversacion(numero, titulo, mensajes):
    """Ejecuta una conversación de prueba y muestra la evidencia."""
    print("=" * 70)
    print(f"Conversación {numero}: {titulo}")
    print("=" * 70)
    estado = nuevo_estado()
    for m in mensajes:
        print(f"Usuario: {m}")
        print(f"Bot: {responder(m, estado)}\n")
