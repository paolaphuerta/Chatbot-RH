"""Módulo de procesamiento de lenguaje natural (NLP).

Preprocesamiento con NLTK (normalización, tokenización, eliminación de stopwords
y stemming) y clasificador de intenciones SVM con TF-IDF de palabras y de
fragmentos de letras, el mismo modelo evaluado en el Avance 2.
"""
import os
import re
import unicodedata

import nltk
import pandas as pd
from nltk.stem import SnowballStemmer
from nltk.tokenize import wordpunct_tokenize
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_DATASET = os.path.join(RAIZ, "datos", "dataset_intenciones.csv")
UMBRAL_TEXTO = 0.30

# Palabras de la lista de stopwords que sí ayudan a distinguir intenciones
CONSERVAR = {"cuanto", "cuanta", "cuantos", "cuantas", "donde", "cuando", "como", "cual", "cuales", "sin", "no"}


def normalizar(texto):
    texto = unicodedata.normalize("NFD", str(texto).lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"[^a-z0-9 ]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _cargar_stopwords():
    try:
        from nltk.corpus import stopwords
        try:
            palabras = stopwords.words("spanish")
        except LookupError:
            nltk.download("stopwords", quiet=True)
            palabras = stopwords.words("spanish")
    except Exception:            # sin internet: se sigue sin stopwords en lugar de fallar
        palabras = []
    return {normalizar(p) for p in palabras} - CONSERVAR


class ClasificadorIntenciones:
    def __init__(self, ruta_dataset=RUTA_DATASET):
        self.stemmer = SnowballStemmer("spanish")
        self.stopwords = _cargar_stopwords()
        datos = pd.read_csv(ruta_dataset)
        self.num_frases = len(datos)
        self.modelo = Pipeline([
            ("tfidf", FeatureUnion([
                ("palabras", TfidfVectorizer(ngram_range=(1, 2))),
                ("letras", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))),
            ])),
            ("clf", CalibratedClassifierCV(LinearSVC(C=1.0), cv=3)),
        ])
        self.modelo.fit(datos["texto"].apply(self.preprocesar), datos["intencion"])
        self.intenciones = list(self.modelo.classes_)

    def preprocesar(self, texto):
        """Normalización → tokenización → stopwords → stemming."""
        tokens = wordpunct_tokenize(normalizar(texto))
        raices = [self.stemmer.stem(t) for t in tokens if t not in self.stopwords]
        return " ".join(raices) if raices else normalizar(texto)

    def predecir(self, mensaje):
        """Regresa (intención, confianza). Con confianza baja, la intención es 'no_entendido'."""
        if not normalizar(mensaje):
            return "no_entendido", 0.0
        p = self.modelo.predict_proba([self.preprocesar(mensaje)])[0]
        i = int(p.argmax())
        intencion = self.intenciones[i] if p[i] >= UMBRAL_TEXTO else "no_entendido"
        return intencion, float(p[i])
