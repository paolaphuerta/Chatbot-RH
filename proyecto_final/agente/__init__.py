"""Paquete del agente de reclutamiento: conocimiento, NLP, visión y agente híbrido."""
from .agente import AgenteReclutamiento, Decision
from .conocimiento import Almacen, BaseConocimiento
from .nlp import ClasificadorIntenciones
from .vision import ClasificadorDocumentos


def construir_agente():
    """Carga todos los componentes y regresa el agente listo para usarse."""
    kb = BaseConocimiento()
    nlp = ClasificadorIntenciones()
    vision = ClasificadorDocumentos()
    almacen = Almacen()
    return AgenteReclutamiento(kb, nlp, vision, almacen)
