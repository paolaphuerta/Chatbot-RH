"""Módulo de visión por computadora.

Clasifica la foto o el PDF que envía el candidato en: INE, licencia,
comprobante de domicilio u otro. Usa el modelo EfficientNetB0 entrenado en el
Avance 2. Para que la aplicación sea ligera en la nube, se prefiere la versión
TensorFlow Lite del modelo (`modelo_documentos.tflite`); si no existe, se usa
el modelo Keras completo.

Las imágenes se procesan en memoria y no se guardan.
"""
import io
import json
import os
import threading

import numpy as np
from PIL import Image, ImageOps

try:                                   # fotos de iPhone (.HEIC)
    from pillow_heif import register_heif_opener
    register_heif_opener()
except Exception:
    pass

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARPETA_MODELO = os.path.join(RAIZ, "modelo")
TAM = 224
UMBRAL_IMAGEN = 0.60
EXTENSIONES = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".pdf")
TAMANO_MAXIMO_MB = 10


class ArchivoInvalido(ValueError):
    """El archivo no es una imagen o PDF que se pueda leer."""


def cargar_imagen(contenido, nombre, tam=TAM):
    """Convierte los bytes de una foto o PDF en una imagen RGB de tam×tam sin deformarla."""
    nombre = nombre.lower()
    if not nombre.endswith(EXTENSIONES):
        raise ArchivoInvalido("Formato no permitido. Envía una foto (JPG, PNG, HEIC, WEBP) o un PDF.")
    if len(contenido) > TAMANO_MAXIMO_MB * 1024 * 1024:
        raise ArchivoInvalido(f"El archivo pesa más de {TAMANO_MAXIMO_MB} MB.")
    try:
        if nombre.endswith(".pdf"):
            import fitz                          # PyMuPDF
            pagina = fitz.open(stream=contenido, filetype="pdf")[0]
            pix = pagina.get_pixmap(dpi=100)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        else:
            img = Image.open(io.BytesIO(contenido))
            img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as e:
        raise ArchivoInvalido("No se pudo leer el archivo; puede estar dañado.") from e
    return ImageOps.pad(img, (tam, tam), color=(0, 0, 0))


class ClasificadorDocumentos:
    def __init__(self, carpeta=CARPETA_MODELO):
        with open(os.path.join(carpeta, "clases.json"), encoding="utf-8") as f:
            self.clases = json.load(f)
        self.simulado = os.environ.get("VISION_SIMULADA") == "1"   # solo para pruebas automáticas
        self.motor = "simulado" if self.simulado else None
        # El intérprete de TFLite no admite dos clasificaciones al mismo tiempo:
        # con varios candidatos simultáneos, cada imagen espera su turno.
        self._candado = threading.Lock()
        if self.simulado:
            return

        ruta_tflite = os.path.join(carpeta, "modelo_documentos.tflite")
        ruta_keras = os.path.join(carpeta, "modelo_documentos.keras")
        if os.path.exists(ruta_tflite):
            Interprete = self._interprete_tflite()
            self.interprete = Interprete(model_path=ruta_tflite)
            self.interprete.allocate_tensors()
            self.entrada = self.interprete.get_input_details()[0]["index"]
            self.salida = self.interprete.get_output_details()[0]["index"]
            self.motor = "tflite"
        elif os.path.exists(ruta_keras):
            import keras
            self.modelo = keras.models.load_model(ruta_keras)
            self.motor = "keras"
        else:
            raise FileNotFoundError("No se encontró el modelo en la carpeta 'modelo/'.")

    @staticmethod
    def _interprete_tflite():
        for modulo in ("ai_edge_litert.interpreter", "tflite_runtime.interpreter"):
            try:
                return __import__(modulo, fromlist=["Interpreter"]).Interpreter
            except ImportError:
                continue
        import tensorflow as tf
        return tf.lite.Interpreter

    def predecir(self, contenido, nombre):
        """Regresa (clase, confianza, probabilidades). Con confianza baja, la clase es 'dudoso'."""
        img = cargar_imagen(contenido, nombre)
        if self.simulado:            # usa el inicio del nombre del archivo: ine_..., otro_..., dudoso_...
            pref = os.path.basename(nombre).split("_")[0].lower()
            clase = pref if pref in self.clases else "dudoso"
            conf = 0.91 if clase != "dudoso" else 0.40
            probs = {c: (conf if c == clase else round((1 - conf) / 3, 3)) for c in self.clases}
            return clase, conf, probs

        x = np.asarray(img, dtype=np.float32)[None, ...]
        if self.motor == "tflite":
            with self._candado:
                self.interprete.set_tensor(self.entrada, x)
                self.interprete.invoke()
                p = self.interprete.get_tensor(self.salida)[0].copy()
        else:
            with self._candado:
                p = self.modelo.predict(x, verbose=0)[0]
        i = int(np.argmax(p))
        conf = float(p[i])
        probs = {c: round(float(v), 3) for c, v in zip(self.clases, p)}
        return ("dudoso" if conf < UMBRAL_IMAGEN else self.clases[i]), conf, probs
