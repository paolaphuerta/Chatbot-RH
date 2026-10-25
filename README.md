# Chatbot de Recursos Humanos – Restaurante El Sauce

Asistente inteligente basado en reglas que atiende a candidatos a empleo del restaurante El Sauce (Ciudad Madero, Tamaulipas). Responde preguntas frecuentes sobre las vacantes, aplica un prefiltro de compatibilidad con el puesto y agenda entrevistas.

Proyecto Fase 1 – MBIA2602.

## Problema que resuelve

El restaurante recibe muchas solicitudes de empleo por WhatsApp. La persona encargada de RH responde manualmente, una y otra vez, las mismas preguntas sobre sueldos, horarios, prestaciones y requisitos. El chatbot automatiza esas respuestas y filtra a los candidatos antes de la entrevista.

## Funcionalidades

- **14 intenciones conversacionales:** saludo, vacantes, funciones, sueldo, horarios, flexibilidad, experiencia, prestaciones, propinas, documentos, entrevista, postularse, despedida y mensaje no entendido.
- **Reconocimiento del puesto** mencionado en el mensaje (mesera, cocinero, repartidor, etc.).
- **Memoria de contexto:** entiende preguntas de seguimiento como "¿y cuánto pagan?".
- **Prefiltro de compatibilidad:** edad mínima legal, disponibilidad de horario, experiencia y licencia de conducir (solo repartidor).
- **Agenda de entrevistas:** espacios de 20 minutos, de lunes a viernes, con control de horarios ocupados.
- **Base de conocimiento editable en Excel:** sueldos, horarios y puestos se modifican sin tocar el código.

## Archivos

| Archivo | Descripción |
|---|---|
| `chatbot_rh_el_sauce.py` | Código fuente del chatbot |
| `chatbot_rh_el_sauce.ipynb` | Cuaderno de Google Colab con la ejecución y las pruebas |
| `base_conocimiento.xlsx` | Base de conocimiento (puestos, prestaciones, entrevistas) |
| `requirements.txt` | Librerías necesarias |

## Requisitos

- Python 3.10 o superior
- NLTK
- pandas y openpyxl (para leer el Excel)

## Cómo ejecutarlo en Google Colab

1. Abre un cuaderno nuevo en [Google Colab](https://colab.research.google.com).
2. Instala NLTK: `!pip install nltk`
3. Sube `base_conocimiento.xlsx` al panel de archivos.
4. Pega y ejecuta el contenido de `chatbot_rh_el_sauce.py`.
5. Ejecuta `chatear()` para conversar con el bot. Escribe `salir` para terminar.
6. Ejecuta `ver_agenda()` para consultar las entrevistas agendadas.

## Arquitectura

```
Usuario ──mensaje──▶ Preprocesamiento (NLTK) ──▶ Identificación de intención
                                                        │
Usuario ◀──respuesta── Flujo conversacional ◀───────────┘
                              │   ▲
                       consulta   datos
                              ▼   │
                     Base de conocimiento (Excel)
```

## Próximas fases

- Procesamiento de lenguaje natural para entender mensajes con errores de ortografía o redacción variada.
- Clasificación de imágenes para reconocer los documentos de los candidatos (INE, comprobante de domicilio, CV).
- Integración web y conexión con WhatsApp.
