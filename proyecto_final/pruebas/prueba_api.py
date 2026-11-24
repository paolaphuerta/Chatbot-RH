"""Pruebas automáticas de la API y del agente (modo de visión simulado)."""
import io, os, sys, json
os.environ["VISION_SIMULADA"] = "1"
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
import agente.conocimiento as con
con.RUTA_BD = os.path.join(RAIZ, "pruebas", "prueba.db")
if os.path.exists(con.RUTA_BD): os.remove(con.RUTA_BD)
from agente import AgenteReclutamiento, BaseConocimiento, ClasificadorIntenciones, ClasificadorDocumentos, Almacen
from api.servidor import crear_app

ag = AgenteReclutamiento(BaseConocimiento(), ClasificadorIntenciones(), ClasificadorDocumentos(), Almacen(con.RUTA_BD))
cli = crear_app(ag).test_client()
IMG = open(os.path.join(RAIZ, "pruebas", "img.png"), "rb").read()

def msg(s, m):
    r = cli.post("/api/agente/mensaje", json={"sesion": s, "mensaje": m}).get_json()
    print(f"Usuario: {m}\n   [{r['capa']} · {r['accion']} · {r['percepcion'].get('intencion')} {r['percepcion'].get('confianza')} · plan={r['plan'][:3]}]\nBot: {r['respuesta']}\n")
    return r
def doc(s, nombre):
    r = cli.post("/api/agente/documento", data={"sesion": s, "archivo": (io.BytesIO(IMG), nombre)},
                 content_type="multipart/form-data").get_json()
    print(f"Usuario: [archivo {nombre}]\n   [{r['capa']} · {r['accion']} · {r['percepcion'].get('clase')} {r['percepcion'].get('confianza')}]\nBot: {r['respuesta']}\n")
    return r

conv = {
 "1": ["holaa buenas tardes", "q vacantes tienen", "que hace un runner", "y cuanto pagan", "dan seguro social?", "quiero pedir unos tacos"],
}
for m in conv["1"]: msg("s1", m)
print("="*60)
for m in ["me intereza el trabajo", "mesera", "tengo 25", "si", "cuanto pagan?", "2"]: msg("s2", m)
doc("s2", "ine_a.jpg"); doc("s2", "licencia_a.jpg"); doc("s2", "comprobante_a.pdf.png")
for m in ["el sabado", "martes", "a las 11", "laura gomez"]: msg("s2", m)
print("="*60)
for m in ["cocinera", "si", "17"]: msg("s3", m)
print("="*60)
for m in ["quiero postularme de repartidor", "30", "si", "3", "si"]: msg("s4", m)
for n in ["dudoso_a.jpg", "otro_a.jpg", "dudoso_b.jpg"]: doc("s4", n)
doc("s4", "licencia_b.jpg"); doc("s4", "comprobante_b.png")
for m in ["martes", "11", "carlos"]: msg("s4", m)
print("="*60, "\nErrores:")
print(cli.post("/api/agente/mensaje", json={"sesion": "x"}).get_json())
print(cli.post("/api/agente/mensaje", data="hola").get_json())
print(cli.post("/api/documento", data={"archivo": (io.BytesIO(b"hola"), "x.txt")}, content_type="multipart/form-data").get_json())
print(cli.post("/api/documento", data={"archivo": (io.BytesIO(b"no soy imagen"), "x.jpg")}, content_type="multipart/form-data").get_json())
print(cli.get("/api/noexiste").get_json(), cli.get("/api/agente/mensaje").status_code)
print(cli.post("/api/intencion", json={"mensaje": "cuanto pagan d mesra"}).get_json())
print(json.dumps(cli.get("/api/agenda").get_json(), ensure_ascii=False))
m = cli.get("/api/metricas").get_json(); print({k: m[k] for k in ["peticiones","errores","tasa_error","latencia_promedio_ms","acciones"]})
print(cli.get("/api/salud").get_json())
