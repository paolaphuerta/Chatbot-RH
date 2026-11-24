"""Interfaz web (Streamlit) del asistente de reclutamiento de El Sauce.

Dos páginas:
- «Trabaja con nosotros»: chat del candidato con el agente (texto, respuestas rápidas y documentos).
- «Panel de RH»: monitoreo del servicio y agenda de entrevistas.

La interfaz se comunica con la API REST (Flask) por HTTP:
- Si existe la variable API_URL (por ejemplo, una URL de Cloudflare Tunnel), usa esa API.
- Si no, levanta la API Flask dentro del mismo servidor, en segundo plano, en localhost.
"""
import os
import threading
import time
import uuid
from datetime import date

import pandas as pd
import requests
import streamlit as st

RAIZ = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(RAIZ, "assets", "logo.png")
ARBOL = os.path.join(RAIZ, "assets", "arbol.png")

st.set_page_config(page_title="Trabaja en El Sauce", page_icon=ARBOL, layout="centered")

NARANJA, CAFE, VERDE = "#E8721C", "#4A2F12", "#7F9F17"
TIEMPO_ESPERA = 60
NOMBRE_DOC = {"ine": "INE", "licencia": "licencia de conducir", "comprobante": "comprobante de domicilio"}
AYUDA_DOC = {"ine": "Frente de tu credencial para votar, completa y sin reflejos.",
             "licencia": "Frente de tu licencia de conducir vigente.",
             "comprobante": "Recibo de luz o agua reciente. Puede ser foto o el PDF que descargas."}
SUGERENCIAS = ["¿Qué vacantes tienen?", "¿Cuánto pagan?", "¿Qué documentos necesito?", "Me interesa postularme"]
ACCIONES = {
    "responder_faq": "Respondió una pregunta frecuente", "ofrecer_postulacion": "Ofreció postularse",
    "iniciar_postulacion": "Inició la postulación", "registrar_dato": "Registró el dato y avanzó el plan",
    "aclarar": "Pidió aclaración", "responder_faq_y_retomar": "Resolvió la duda y retomó el plan",
    "rechazar_por_requisito": "Requisito no cumplido", "solicitar_documento": "Solicitó documento",
    "aceptar_documento": "Validó el documento", "solicitar_reenvio": "Pidió reenvío del documento",
    "escalar_a_rh": "Escaló el caso a RH", "agendar_entrevista": "Agendó la entrevista",
    "replanificar_cita": "Replanificó la cita", "cancelar_postulacion": "Canceló la postulación",
    "documento_no_solicitado": "Documento fuera de tiempo", "archivo_invalido": "Archivo no válido",
    "acuse": "Acuse", "declinar_oferta": "El candidato declinó",
}
OBJETIVOS = {"puesto": "puesto", "edad": "edad", "horario": "horario", "experiencia": "experiencia",
             "licencia": "licencia", "doc_ine": "INE", "doc_licencia": "licencia (doc.)",
             "doc_comprobante": "comprobante", "dia": "día", "hora": "hora", "nombre": "nombre"}

# ============================ Estilo visual ============================
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Lora:wght@600;700&family=Nunito+Sans:wght@400;600;700&display=swap');
html, body, .stMarkdown, p, li, label, input, textarea, button {{ font-family: 'Nunito Sans', sans-serif; }}
h1, h2, h3, .titulo {{ font-family: 'Lora', serif !important; color: {CAFE} !important; }}
#MainMenu, footer, [data-testid="stDecoration"], [data-testid="stToolbarActions"] {{ display: none !important; }}
.block-container {{ padding-top: 1.2rem; max-width: 760px; }}
.encabezado {{ text-align: center; margin: 0 0 .25rem; }}
.encabezado p {{ color: {CAFE}; opacity: .8; margin: .1rem 0 0; font-size: 1.02rem; }}
.aviso {{ font-size: .82rem; color: {CAFE}; opacity: .75; text-align: center; margin-bottom: .6rem; }}
[data-testid="stChatMessage"] {{ border-radius: 18px; padding: .7rem 1rem; margin-bottom: .45rem; }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {{
    background: #FDEBDD; flex-direction: row-reverse; margin-left: 12%; }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {{
    text-align: right; }}
[data-testid="stChatMessage"]:not(:has([data-testid="stChatMessageAvatarUser"])) {{
    background: #F7F3EC; margin-right: 6%; }}
[data-testid="stChatMessageAvatarUser"] {{ background: {NARANJA}; }}
.chips {{ margin-top: .35rem; line-height: 1.9; }}
.chip {{ display: inline-block; padding: 1px 10px; border-radius: 999px; font-size: .74rem; margin-right: 4px; }}
.chip-reactiva {{ background: #E8F1CF; color: #4C6110; }}
.chip-deliberativa {{ background: #FCE1CC; color: #8A3E07; }}
.chip-nlp {{ background: #EDE8F7; color: #4A3A7A; }}
.chip-vision {{ background: #DDEFF3; color: #1F5866; }}
.chip-plan {{ background: #EFEAE4; color: {CAFE}; }}
.progreso-texto {{ font-size: .85rem; color: {CAFE}; margin-bottom: -.4rem; }}
[data-testid="stProgress"] > div > div > div > div {{ background-color: {NARANJA}; }}
.tarjeta-doc {{ background: #FFF8F1; border: 1px dashed {NARANJA}; border-radius: 14px; padding: .8rem 1rem .2rem; }}
.kpi {{ background: #FFF8F1; border-radius: 14px; padding: .7rem 1rem; }}
</style>
""", unsafe_allow_html=True)


def _secreto(clave, defecto=None):
    try:
        return st.secrets.get(clave, os.environ.get(clave, defecto))
    except Exception:
        return os.environ.get(clave, defecto)


# ============================ Conexión con la API ============================
@st.cache_resource(show_spinner="Preparando al asistente…")
def iniciar_api():
    """Regresa la URL de la API. Si no hay una externa, levanta Flask en segundo plano."""
    externa = _secreto("API_URL")
    if externa:
        return externa.rstrip("/")
    from werkzeug.serving import make_server
    from api.servidor import crear_app

    app = crear_app()                                            # aquí se cargan los modelos (una sola vez)
    servidor = make_server("127.0.0.1", 0, app, threaded=True)   # puerto libre
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{servidor.server_port}"
    for _ in range(50):
        try:
            if requests.get(url + "/api/salud", timeout=2).ok:
                break
        except requests.RequestException:
            time.sleep(0.2)
    return url


def llamar_api(metodo, ruta, **kwargs):
    """Llama a la API y regresa (datos, error). Nunca lanza excepciones a la interfaz."""
    try:
        r = requests.request(metodo, API + ruta, timeout=TIEMPO_ESPERA, **kwargs)
        datos = r.json()
        if not r.ok or not datos.get("ok", False):
            return None, datos.get("error", f"Error {r.status_code}")
        return datos, None
    except requests.Timeout:
        return None, "El servicio tardó demasiado en responder. Intenta de nuevo."
    except requests.ConnectionError:
        return None, "No hay conexión con el servicio en este momento. Intenta de nuevo en unos minutos."
    except ValueError:
        return None, "El servicio respondió algo inesperado."


try:
    API = iniciar_api()
except Exception as e:                                           # p. ej., falta el modelo
    st.error("No se pudo iniciar el asistente. Intenta más tarde.")
    st.caption(f"Detalle técnico: {type(e).__name__}: {e}")
    st.stop()

# ============================ Estado de la sesión ============================
ss = st.session_state
if "sesion" not in ss:
    ss.sesion = uuid.uuid4().hex
    ss.historial = []            # [{"rol": "user"/"assistant", "texto": ..., "decision": {...}}]
    ss.ultima = None             # última decisión del agente
    ss.version = 0               # cambia la clave de los widgets para limpiarlos
    ss.demo = False


def nueva_conversacion():
    llamar_api("POST", "/api/agente/reiniciar", json={"sesion": ss.sesion})
    ss.sesion, ss.historial, ss.ultima = uuid.uuid4().hex, [], None
    ss.version += 1


def registrar_turno(texto_usuario, datos, error):
    ss.historial.append({"rol": "user", "texto": texto_usuario})
    ss.version += 1                         # limpia los botones de respuesta y el cargador de archivos
    if error:
        ss.historial.append({"rol": "assistant", "texto": f"⚠️ {error}", "error": True})
        return
    ss.historial.append({"rol": "assistant", "texto": datos["respuesta"], "decision": datos})
    ss.ultima = datos


def enviar_mensaje(texto):
    with st.spinner("Escribiendo…"):
        datos, error = llamar_api("POST", "/api/agente/mensaje", json={"sesion": ss.sesion, "mensaje": texto})
    registrar_turno(texto, datos, error)


def enviar_documento(archivo):
    with st.spinner("Revisando tu documento…"):
        datos, error = llamar_api("POST", "/api/agente/documento", data={"sesion": ss.sesion},
                                  files={"archivo": (archivo.name, archivo.getvalue(), archivo.type)})
    registrar_turno(f"📎 {archivo.name}", datos, error)


# ============================ Componentes ============================
def chips_razonamiento(d):
    per = d.get("percepcion", {})
    chips = [f"<span class='chip chip-{d['capa']}'>Capa {d['capa']}</span>",
             f"<span class='chip chip-plan'>{ACCIONES.get(d['accion'], d['accion'])}</span>"]
    if per.get("tipo") == "texto":
        chips.append(f"<span class='chip chip-nlp'>NLP · {per.get('intencion')} {per.get('confianza', 0):.0%}</span>")
    elif per.get("clase"):
        chips.append(f"<span class='chip chip-vision'>Visión · {per['clase']} {per.get('confianza', 0):.0%}"
                     f" (esperaba {per.get('esperado')})</span>")
    if d.get("plan"):
        pendientes = " → ".join(OBJETIVOS.get(p, p) for p in d["plan"][:4])
        chips.append(f"<span class='chip chip-plan'>Plan: {pendientes}{' …' if len(d['plan']) > 4 else ''}</span>")
    st.markdown(f"<div class='chips'>{''.join(chips)}</div>", unsafe_allow_html=True)


def encabezado(subtitulo):
    _, centro, _ = st.columns([1, 2, 1])
    centro.image(LOGO, width=280)
    st.markdown(f"<div class='encabezado'><p>{subtitulo}</p></div>", unsafe_allow_html=True)


# ============================ Página: chat del candidato ============================
def pagina_candidato():
    encabezado("¿Quieres trabajar con nosotros? Pregúntame por vacantes, sueldos y horarios, "
               "o postúlate y agenda tu entrevista aquí mismo.")
    st.markdown("<div class='aviso'>🔒 Hablas con un asistente automático. Tus documentos se revisan al momento "
                "y no se guardan. La decisión de contratación la toma recursos humanos.</div>",
                unsafe_allow_html=True)
    with st.expander("Aviso de privacidad"):
        st.markdown(
            "- **Qué datos usamos:** tus respuestas del chat, tu nombre y la fecha de tu entrevista.\n"
            "- **Tus documentos** (INE, licencia, comprobante) solo se analizan para saber qué tipo de documento son. "
            "Se procesan en memoria y **no se guardan**.\n"
            "- **Solo preguntamos requisitos del puesto:** edad mínima legal, disponibilidad de horario, experiencia "
            "y licencia para repartidores.\n"
            "- **Decisión humana:** el asistente organiza la postulación; recursos humanos revisa los documentos "
            "originales y decide en la entrevista.")

    d = ss.ultima
    if d and d.get("progreso"):
        p = d["progreso"]
        st.markdown(f"<div class='progreso-texto'><b>Tu postulación</b> · paso {p['paso']} de {p['total']} · "
                    f"{p['etapa']}</div>", unsafe_allow_html=True)
        st.progress(min(p["paso"] / p["total"], 1.0))

    if not ss.historial:
        with st.chat_message("assistant", avatar=ARBOL):
            st.markdown("¡Hola! 👋 Soy el asistente de reclutamiento de **El Sauce**. ¿En qué te puedo ayudar?")
    for turno in ss.historial:
        with st.chat_message(turno["rol"], avatar=ARBOL if turno["rol"] == "assistant" else None):
            st.markdown(turno["texto"].replace("\n", "  \n"))
            if ss.demo and turno.get("decision"):
                chips_razonamiento(turno["decision"])

    esperado = d.get("espera_documento") if d else None
    if esperado:                                             # el agente espera un documento
        with st.container(border=True):
            st.markdown(f"**📎 Envía tu {NOMBRE_DOC[esperado]}**  \n<small>{AYUDA_DOC[esperado]} "
                        f"Foto o PDF, máximo 10 MB.</small>", unsafe_allow_html=True)
            acepto = st.checkbox("Acepto que mi documento se analice para validarlo. Entiendo que no se guarda.",
                                 key="consentimiento")
            archivo = st.file_uploader("Documento", type=["jpg", "jpeg", "png", "webp", "heic", "pdf"],
                                       key=f"archivo_{ss.version}", label_visibility="collapsed",
                                       disabled=not acepto)
            if archivo and st.button("Enviar documento", type="primary"):
                enviar_documento(archivo)
                st.rerun()
    else:
        opciones = (d or {}).get("opciones") or ([] if ss.historial else SUGERENCIAS)
        if opciones:
            elegida = st.pills("Respuestas rápidas", opciones, key=f"opcion_{ss.version}",
                               label_visibility="collapsed")
            if elegida:
                enviar_mensaje(elegida)
                st.rerun()

    if texto := st.chat_input("Escribe tu mensaje…"):
        enviar_mensaje(texto)
        st.rerun()


# ============================ Página: panel de RH ============================
def fecha_legible(valor):
    try:
        f = date.fromisoformat(valor)
        dias = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
        return f"{dias[f.weekday()]} {f.day:02d}/{f.month:02d}"
    except (TypeError, ValueError):
        return valor


def pagina_rh():
    st.markdown("<h2 class='titulo'>Panel de recursos humanos</h2>", unsafe_allow_html=True)
    st.caption("Monitoreo del asistente y entrevistas agendadas.")
    clave_rh = _secreto("RH_CLAVE")
    acceso = bool(clave_rh) and st.text_input("Clave de recursos humanos", type="password",
                                              help="Necesaria para ver los nombres completos de los candidatos.") == clave_rh

    m, err = llamar_api("GET", "/api/metricas")
    if err:
        st.error(f"No se pudieron obtener las métricas: {err}")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Peticiones", m["peticiones"])
        c2.metric("Latencia promedio", f"{m['latencia_promedio_ms']:.0f} ms")
        c3.metric("Tasa de error", f"{m['tasa_error']:.1%}")
        c4.metric("Conversaciones", m["sesiones_activas"])

        def grafica(titulo, datos, color):
            st.markdown(f"**{titulo}**")
            if datos:
                serie = pd.Series(datos).sort_values(ascending=True)
                st.bar_chart(serie, horizontal=True, color=color, height=34 * len(serie) + 40)
            else:
                st.caption("Sin datos todavía.")

        g1, g2 = st.columns(2)
        with g1:
            grafica("Intenciones detectadas (NLP)", m["intenciones"], VERDE)
        with g2:
            grafica("Documentos clasificados (visión)", m["documentos"], NARANJA)
        grafica("Acciones del agente", {ACCIONES.get(k, k): v for k, v in m["acciones"].items()}, CAFE)

        st.markdown("**Rendimiento por servicio de la API**")
        if m["por_ruta"]:
            st.dataframe(pd.DataFrame(m["por_ruta"]).T.rename(columns={
                "peticiones": "Peticiones", "errores": "Errores", "latencia_promedio_ms": "Latencia promedio (ms)"}))
        if m["ultimos_errores"]:
            with st.expander(f"Últimos errores ({len(m['ultimos_errores'])})"):
                st.dataframe(pd.DataFrame(m["ultimos_errores"]), hide_index=True)

    st.markdown("**Entrevistas agendadas**")
    agenda, err = llamar_api("GET", "/api/agenda")
    if err:
        st.error(err)
    elif not agenda["citas"]:
        st.caption("Todavía no hay entrevistas agendadas.")
    else:
        tabla = pd.DataFrame(agenda["citas"])
        tabla["dia"] = tabla["dia"].apply(fecha_legible)
        if not acceso:                                         # protección de datos personales
            tabla["nombre"] = tabla["nombre"].apply(lambda n: " ".join(p[0] + "." for p in str(n).split()))
            st.caption("Los nombres se muestran abreviados. Ingresa la clave de RH para verlos completos.")
        st.dataframe(tabla.rename(columns={"dia": "Día", "hora": "Hora", "nombre": "Nombre", "puesto": "Puesto",
                                           "documentos": "Documentos validados", "por_revisar": "Revisar en entrevista"}), hide_index=True)

    with st.expander("Desempeño de los modelos (evaluación del Avance 2)"):
        st.markdown(
            "| Modelo | Accuracy | Precision | Recall | F1 |\n|---|---|---|---|---|\n"
            "| Intenciones (SVM + TF-IDF) | 0.938 | 0.943 | 0.942 | 0.940 |\n"
            "| Documentos (EfficientNetB0) | 0.867 | 0.900 | 0.867 | 0.872 |")
        st.caption("Valores macro sobre el conjunto de prueba. Validación cruzada del modelo de texto: 0.775 ± 0.045.")


# ============================ Navegación y barra lateral ============================
navegacion = st.navigation([
    st.Page(pagina_candidato, title="Trabaja con nosotros", icon="💬", default=True),
    st.Page(pagina_rh, title="Panel de RH", icon="📊", url_path="panel-rh"),
])

with st.sidebar:
    st.image(LOGO, width=200)
    salud, _ = llamar_api("GET", "/api/salud")
    st.caption("🟢 Servicio en línea" if salud else "🔴 Servicio no disponible")
    st.button("Nueva conversación", on_click=nueva_conversacion, icon="🔄")
    st.toggle("Modo demostración", key="demo",
              help="Muestra el razonamiento del agente en cada respuesta: capa, acción, modelos y plan.")
    if salud and ss.demo:
        st.caption(f"NLP: SVM · {salud['modelo_texto']['frases_entrenamiento']} frases · "
                   f"{salud['modelo_texto']['intenciones']} intenciones  \n"
                   f"Visión: EfficientNetB0 ({salud['modelo_vision']['motor']})  \n"
                   f"Activo desde hace {salud['segundos_activo'] // 60} min")

navegacion.run()
