# Proyecto final – Aplicación web del asistente de reclutamiento

Aplicación web que integra el **chatbot NLP**, el **clasificador de documentos (visión)** y un **agente inteligente híbrido** para el área de recursos humanos del restaurante El Sauce.

## Arquitectura

```
Navegador ──► Streamlit (app.py) ──HTTP──► API REST Flask (api/servidor.py)
                                                 │
                                    Agente híbrido (agente/agente.py)
                         ┌───────────────┬───────┴───────┬────────────────┐
                    NLP (SVM)     Visión (EfficientNetB0)  Base Excel   Agenda SQLite
                  agente/nlp.py     agente/vision.py      agente/conocimiento.py
```

- **Capa reactiva:** responde de inmediato las preguntas frecuentes.
- **Capa deliberativa:** tiene la meta de completar la postulación, mantiene el estado del candidato y en cada turno planea los requisitos pendientes (datos, documentos, cita) para decidir la siguiente acción.

## API REST

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/salud` | Estado del servicio y de los modelos |
| POST | `/api/intencion` | Clasifica la intención de un mensaje |
| POST | `/api/documento` | Clasifica un archivo (INE, licencia, comprobante, otro) |
| POST | `/api/agente/mensaje` | Turno de conversación con el agente |
| POST | `/api/agente/documento` | Envía un documento al agente |
| POST | `/api/agente/reiniciar` | Reinicia la conversación |
| GET | `/api/agenda` | Entrevistas agendadas |
| GET | `/api/metricas` | Métricas de operación (monitoreo) |

## Ejecución local

```bash
pip install -r requirements.txt
streamlit run app.py          # interfaz + API integrada
python -m api.servidor        # solo la API, en el puerto 5000
```

## Despliegue

- **Streamlit Community Cloud:** archivo principal `proyecto_final/app.py`, Python 3.12.
- **Cloudflare Tunnel:** `Proyecto_Final_Modelo_y_API.ipynb` expone la API desde Google Colab para probarla.

## Privacidad

Los documentos se procesan en memoria y no se guardan. Solo se registran nombre, puesto y cita. Los nombres en el panel de recursos humanos se muestran abreviados sin la clave `RH_CLAVE`.
