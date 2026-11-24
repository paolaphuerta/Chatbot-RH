"""Interfaz web (Streamlit) del asistente de reclutamiento de El Sauce.

La interfaz se comunica con la API REST (Flask) por HTTP:
- Si existe la variable API_URL (por ejemplo, una URL de Cloudflare Tunnel), usa esa API.
- Si no, levanta la API Flask dentro del mismo servidor, en segundo plano, en localhost.
"""
import os
import threading
import time
import uuid

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Reclutamiento El Sauce", page_icon="🌿", layout="centered")

VERDE = "#00524A"
TIEMPO_ESPERA = 60
NOMBRE_DOC = {"ine": "INE", "licencia": "licencia de conducir", "comprobante": "comprobante de domicilio"}
SUGERENCIAS = ["¿Qué vacantes tienen?", "¿Cuánto pagan?", "¿Qué documentos necesito?", "Me interesa postularme"]


def _secreto(clave, defecto=None):
    try:
        return st.secrets.get(clave, os.environ.get(clave, defecto))
    except Exception:
        return os.environ.get(clave, defecto)


# ============================ Conexión con la API ============================
@st.cache_resource(show_spinner="Cargando los modelos de inteligencia artificial…")
def iniciar_api():
    """Regresa la URL de la API. Si no hay una externa, levanta Flask en segundo plano."""
    externa = _secreto("API_URL")
    if externa:
        return externa.rstrip("/")
    from werkzeug.serving import make_server
    from api.servidor import crear_app

    app = crear_app()                                   # aquí se cargan los modelos (una sola vez)
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
        return None, "No hay conexión con el servicio de inteligencia artificial en este momento."
    except ValueError:
        return None, "El servicio respondió algo inesperado."


try:
    API = iniciar_api()
except Exception as e:                                     # p. ej., falta el modelo
    st.error("No se pudo iniciar el servicio del asistente. Intenta más tarde.")
    st.caption(f"Detalle técnico: {type(e).__name__}: {e}")
    st.stop()

# ============================ Estado de la sesión ============================
if "sesion" not in st.session_state:
    st.session_state.sesion = uuid.uuid4().hex
    st.session_state.historial = []           # [{"rol": "user"/"assistant", "texto": ..., "decision": {...}}]
    st.session_state.espera_documento = None
    st.session_state.clave_archivo = 0


def nueva_conversacion():
    llamar_api("POST", "/api/agente/reiniciar", json={"sesion": st.session_state.sesion})
    st.session_state.sesion = uuid.uuid4().hex
    st.session_state.historial = []
    st.session_state.espera_documento = None
    st.session_state.clave_archivo += 1


def registrar_turno(texto_usuario, datos, error):
    st.session_state.historial.append({"rol": "user", "texto": texto_usuario})
    if error:
        st.session_state.historial.append({"rol": "assistant", "texto": f"⚠️ {error}", "error": True})
        return
    st.session_state.historial.append({"rol": "assistant", "texto": datos["respuesta"], "decision": datos})
    st.session_state.espera_documento = datos.get("espera_documento")


def enviar_mensaje(texto):
    datos, error = llamar_api("POST", "/api/agente/mensaje",
                              json={"sesion": st.session_state.sesion, "mensaje": texto})
    registrar_turno(texto, datos, error)


def enviar_documento(archivo):
    datos, error = llamar_api("POST", "/api/agente/documento", data={"sesion": st.session_state.sesion},
                              files={"archivo": (archivo.name, archivo.getvalue(), archivo.type)})
    registrar_turno(f"📎 {archivo.name}", datos, error)
    st.session_state.clave_archivo += 1


# ============================ Barra lateral ============================
with st.sidebar:
    st.markdown(f"<h2 style='color:{VERDE};margin-bottom:0'>🌿 El Sauce</h2>", unsafe_allow_html=True)
    st.caption("Asistente virtual de reclutamiento")

    salud, error_salud = llamar_api("GET", "/api/salud")
    if salud:
        st.success("Servicio en línea", icon="✅")
    else:
        st.error("Servicio no disponible", icon="⚠️")

    ver_razonamiento = st.toggle("Ver razonamiento del agente", value=True,
                                 help="Muestra qué detectó cada modelo y qué decidió el agente en cada turno.")
    st.button("🔄 Nueva conversación", on_click=nueva_conversacion, use_container_width=True)

    with st.expander("🔒 Aviso de privacidad", expanded=False):
        st.markdown(
            "- Hablas con un **asistente automático**, no con una persona.\n"
            "- Tus documentos se usan **solo para identificar qué tipo de documento son**. "
            "Se analizan en el momento y **no se guardan**.\n"
            "- Solo se registran tu nombre, el puesto y la cita, para que recursos humanos pueda recibirte.\n"
            "- El asistente **no toma la decisión de contratación**: la toma el personal de recursos humanos.\n"
            "- Solo se piden requisitos relacionados con el puesto (edad mínima legal, horario, experiencia y "
            "licencia para repartidores).")
    consentimiento = st.checkbox("Leí y acepto el aviso de privacidad", key="consentimiento")

    if salud:
        with st.expander("ℹ️ Estado técnico"):
            st.write(f"Modelo de texto: SVM · {salud['modelo_texto']['frases_entrenamiento']} frases · "
                     f"{salud['modelo_texto']['intenciones']} intenciones")
            st.write(f"Modelo de visión: EfficientNetB0 ({salud['modelo_vision']['motor']})")
            st.write(f"Activo desde hace {salud['segundos_activo'] // 60} min")

pestana_chat, pestana_rh = st.tabs(["💬 Asistente", "📊 Panel de recursos humanos"])


# ============================ Pestaña: chat ============================
def mostrar_razonamiento(d):
    per = d.get("percepcion", {})
    partes = [f"**Capa {d['capa']}** → acción `{d['accion']}`"]
    if per.get("tipo") == "texto":
        partes.append(f"NLP: intención `{per.get('intencion')}` ({per.get('confianza', 0):.0%})")
    elif per.get("clase"):
        partes.append(f"Visión: `{per['clase']}` ({per.get('confianza', 0):.0%}), se esperaba `{per.get('esperado')}`")
    if d.get("plan"):
        pendientes = " → ".join(p.replace("doc_", "📎 ") for p in d["plan"][:4])
        partes.append(f"Plan: {pendientes}{' …' if len(d['plan']) > 4 else ''}")
    st.caption(" · ".join(partes))


with pestana_chat:
    st.markdown(f"<h3 style='color:{VERDE}'>Trabaja con nosotros</h3>", unsafe_allow_html=True)
    st.caption("Pregúntame por vacantes, sueldos, horarios o requisitos. Si te interesa un puesto, "
               "te ayudo a postularte y a agendar tu entrevista.")

    if not st.session_state.historial:
        with st.chat_message("assistant", avatar="🌿"):
            st.write("¡Hola! Soy el asistente virtual de reclutamiento de El Sauce. ¿En qué te puedo ayudar?")
        columnas = st.columns(len(SUGERENCIAS))
        for col, texto in zip(columnas, SUGERENCIAS):
            if col.button(texto, use_container_width=True):
                with st.spinner("Pensando…"):
                    enviar_mensaje(texto)
                st.rerun()

    for turno in st.session_state.historial:
        with st.chat_message(turno["rol"], avatar="🌿" if turno["rol"] == "assistant" else "🙂"):
            st.markdown(turno["texto"].replace("\n", "  \n"))
            if ver_razonamiento and turno.get("decision"):
                mostrar_razonamiento(turno["decision"])

    # Carga de documentos: solo aparece cuando el agente espera uno
    esperado = st.session_state.espera_documento
    if esperado:
        with st.container(border=True):
            st.markdown(f"**📎 Envía tu {NOMBRE_DOC[esperado]}** (foto o PDF, máximo 10 MB)")
            if not consentimiento:
                st.info("Para enviar documentos, primero acepta el aviso de privacidad en la barra lateral.")
            archivo = st.file_uploader("Documento", type=["jpg", "jpeg", "png", "webp", "heic", "pdf"],
                                       key=f"archivo_{st.session_state.clave_archivo}",
                                       label_visibility="collapsed", disabled=not consentimiento)
            if archivo and st.button("Enviar documento", type="primary"):
                with st.spinner("Analizando el documento…"):
                    enviar_documento(archivo)
                st.rerun()

    if prompt := st.chat_input("Escribe tu mensaje…"):
        with st.spinner("Pensando…"):
            enviar_mensaje(prompt)
        st.rerun()


# ============================ Pestaña: panel de RH ============================
with pestana_rh:
    st.markdown(f"<h3 style='color:{VERDE}'>Monitoreo del asistente</h3>", unsafe_allow_html=True)
    clave_rh = _secreto("RH_CLAVE")
    acceso = bool(clave_rh) and st.text_input("Clave de recursos humanos", type="password") == clave_rh

    m, err = llamar_api("GET", "/api/metricas")
    if err:
        st.error(f"No se pudieron obtener las métricas: {err}")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Peticiones", m["peticiones"])
        c2.metric("Latencia promedio", f"{m['latencia_promedio_ms']:.0f} ms")
        c3.metric("Tasa de error", f"{m['tasa_error']:.1%}")
        c4.metric("Conversaciones activas", m["sesiones_activas"])

        def grafica(titulo, datos):
            st.markdown(f"**{titulo}**")
            if datos:
                serie = pd.Series(datos).sort_values(ascending=True)
                st.bar_chart(serie, horizontal=True, color=VERDE, height=36 * len(serie) + 40)
            else:
                st.caption("Sin datos todavía.")

        g1, g2 = st.columns(2)
        with g1:
            grafica("Intenciones detectadas (NLP)", m["intenciones"])
        with g2:
            grafica("Documentos clasificados (visión)", m["documentos"])
        grafica("Acciones del agente", m["acciones"])

        st.markdown("**Rendimiento por servicio de la API**")
        st.dataframe(pd.DataFrame(m["por_ruta"]).T.rename(columns={
            "peticiones": "Peticiones", "errores": "Errores", "latencia_promedio_ms": "Latencia promedio (ms)"}),
            use_container_width=True)
        if m["ultimos_errores"]:
            with st.expander(f"Últimos errores ({len(m['ultimos_errores'])})"):
                st.dataframe(pd.DataFrame(m["ultimos_errores"]), use_container_width=True, hide_index=True)

    st.markdown("**Entrevistas agendadas**")
    agenda, err = llamar_api("GET", "/api/agenda")
    if err:
        st.error(err)
    elif not agenda["citas"]:
        st.caption("Todavía no hay entrevistas agendadas.")
    else:
        tabla = pd.DataFrame(agenda["citas"])
        if not acceso:                                   # protección de datos personales
            tabla["nombre"] = tabla["nombre"].apply(lambda n: " ".join(p[0] + "." for p in str(n).split()))
            st.caption("Los nombres se muestran abreviados. Ingresa la clave de recursos humanos para verlos completos.")
        st.dataframe(tabla.rename(columns={"dia": "Día", "hora": "Hora", "nombre": "Nombre", "puesto": "Puesto",
                                           "documentos": "Documentos recibidos", "por_revisar": "Por revisar"}),
                     use_container_width=True, hide_index=True)

    with st.expander("Desempeño de los modelos (evaluación del Avance 2)"):
        st.markdown(
            "| Modelo | Accuracy | Precision | Recall | F1 |\n|---|---|---|---|---|\n"
            "| Intenciones (SVM + TF-IDF) | 0.938 | 0.943 | 0.942 | 0.940 |\n"
            "| Documentos (EfficientNetB0) | 0.867 | 0.900 | 0.867 | 0.872 |")
        st.caption("Valores macro sobre el conjunto de prueba. Validación cruzada del modelo de texto: 0.775 ± 0.045.")
