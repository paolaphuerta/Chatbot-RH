# Chatbot de Recursos Humanos – Restaurante El Sauce

Asistente inteligente que atiende a candidatos a empleo del restaurante El Sauce (Ciudad Madero, Tamaulipas): responde preguntas sobre las vacantes, aplica un prefiltro de compatibilidad, recibe y valida los documentos del candidato y agenda su entrevista.

Proyecto del curso **Desarrollo de Aplicaciones con Inteligencia Artificial** – Juana Paola Puente Huerta.

## Avances

| Avance | Qué se agregó | Archivos |
|---|---|---|
| **1. Chatbot basado en reglas** | Intenciones por palabras clave, prefiltro, agenda de entrevistas y base de conocimiento en Excel | `chatbot_rh_el_sauce.py`, `base_conocimiento.xlsx` |
| **2. Versión multimodal** | Clasificador de intenciones (TF-IDF + SVM), clasificador de documentos (CNN con EfficientNetB0) e integración en el chatbot | archivos que empiezan con `Avance2_` y `dataset_intenciones.csv` |

## Avance 2

| Archivo | Descripción |
|---|---|
| `Avance2_Clasificador_Intenciones.ipynb` | Preprocesamiento (tokenización, normalización, stopwords, stemming), TF-IDF y comparación Naive Bayes vs SVM |
| `dataset_intenciones.csv` | 320 frases etiquetadas en 15 intenciones |
| `Avance2_Clasificador_Documentos.ipynb` | CNN con transferencia de aprendizaje (EfficientNetB0) para reconocer INE, licencia, comprobante de domicilio u otra imagen; métricas y matriz de confusión |
| `Avance2_Integracion_Multimodal.ipynb` | Chatbot que entiende texto y valida los documentos enviados por el candidato |

### Resultados principales

| Componente | Modelo | Accuracy (prueba) |
|---|---|---|
| Intenciones | SVM con TF-IDF de palabras y n-gramas de caracteres | 0.938 (validación cruzada: 0.775 ± 0.045) |
| Documentos | EfficientNetB0 + ajuste fino | 0.867 |

### Flujo del chatbot

```
Mensaje ──► Preprocesamiento NLTK ──► SVM (intención) ──┐
                                                         ├──► Flujo conversacional ◄──► Base de conocimiento (Excel)
Foto/PDF ──► CNN EfficientNetB0 (tipo de documento) ────┘              │
                                                                        └──► Agenda de entrevistas
```

### Privacidad

Las imágenes de entrenamiento contienen identificaciones reales, por lo que **no se incluyen en este repositorio** (ver `.gitignore`). Se guardan en una carpeta privada de Google Drive. Los cuadernos muestran las INE y licencias difuminadas.

## Cómo ejecutarlo

Los cuadernos están hechos para **Google Colab**. Requieren la siguiente estructura en Google Drive:

```
MyDrive/ChatbotRH/
   base_conocimiento.xlsx
   dataset_intenciones.csv
   documentos/{ine, licencia, comprobante, otro}/   (imágenes de entrenamiento)
   modelo/                                           (se crea al entrenar)
   pruebas/                                          (imágenes nuevas para probar)
```

1. Ejecutar `Avance2_Clasificador_Documentos.ipynb` con GPU para entrenar y guardar el modelo.
2. Ejecutar `Avance2_Clasificador_Intenciones.ipynb` para evaluar el clasificador de texto.
3. Ejecutar `Avance2_Integracion_Multimodal.ipynb` para probar el chatbot completo.
