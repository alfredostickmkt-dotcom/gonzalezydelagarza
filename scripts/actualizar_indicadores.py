#!/usr/bin/env python3
"""Actualiza indicadores.json con datos de la API SIE de Banxico.

Se actualizan automaticamente:
  - Tipo de cambio FIX  (serie SF43718)
  - UDIS                (serie SP68257)
  - INPC general        (serie SP1)

NO se tocan: UMA, salario minimo y recargos. Esos se editan a mano una vez al ano.

Seguridad: el token llega por la variable de entorno BANXICO_TOKEN (secreto de GitHub).
Este programa nunca lo imprime ni lo guarda en ningun archivo.
Si algo falla, termina con error y NO modifica indicadores.json.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

ARCHIVO = "indicadores.json"
BASE = "https://www.banxico.org.mx/SieAPIRest/service/v1/series/"
URL = BASE + "SF43718,SP1/datos/oportuno"
# Banxico publica las UDIS por adelantado (hasta el dia 10 o 25). El dato "oportuno"
# seria de una fecha futura; por eso se pide la UDI del dia que vera el visitante.
URL_UDI = BASE + "SP68257/datos/%s/%s"
NOTA = ("Tipo de cambio, UDIS e INPC se actualizan automaticamente desde Banxico; "
        "UMA, salario minimo y recargos se actualizan manualmente. "
        "Confirma en la fuente oficial.")
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
# Rangos razonables para detectar datos corruptos antes de publicarlos.
RANGOS = {"SF43718": (10, 40), "SP68257": (5, 20), "SP1": (100, 300)}


def fallar(mensaje):
    print("ERROR: " + mensaje, file=sys.stderr)
    sys.exit(1)


def dia_objetivo():
    """Dia que vera el visitante: la tarea corre en la noche (hora de Mexico),
    asi que sumar 12 horas da el dia siguiente; si se corre a mano en la manana, da el mismo dia."""
    return (datetime.now(ZoneInfo("America/Mexico_City")) + timedelta(hours=12)).date()


def consultar(token, url=URL):
    req = urllib.request.Request(
        url, headers={"Bmx-Token": token, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        fallar("Banxico respondio HTTP %s" % e.code)
    except Exception as e:  # red caida, JSON invalido, etc.
        fallar("No se pudo consultar Banxico (%s)" % type(e).__name__)


def ultimo(resp, id_serie):
    try:
        series = resp["bmx"]["series"]
    except (KeyError, TypeError):
        fallar("Respuesta de Banxico con formato inesperado")
    for s in series:
        if s.get("idSerie") == id_serie:
            datos = s.get("datos") or []
            if not datos:
                fallar("Serie %s sin datos" % id_serie)
            d = datos[-1]
            try:
                valor = float(str(d["dato"]).replace(",", ""))
                dd, mm, aaaa = d["fecha"].split("/")
                int(dd), int(mm), int(aaaa)
            except Exception:
                fallar("Dato no numerico o fecha invalida en serie %s" % id_serie)
            bajo, alto = RANGOS[id_serie]
            if not (bajo <= valor <= alto):
                fallar("Serie %s fuera de rango esperado: %s" % (id_serie, valor))
            return int(dd), int(mm), int(aaaa), valor
    fallar("Serie %s no vino en la respuesta" % id_serie)


def poner(datos, prefijo, etiqueta, valor):
    """Reemplaza la fila cuya etiqueta empieza con 'prefijo'; si no existe, la agrega."""
    for fila in datos:
        if fila[0].startswith(prefijo):
            fila[0], fila[1] = etiqueta, valor
            return
    datos.append([etiqueta, valor])


def main():
    token = os.environ.get("BANXICO_TOKEN", "").strip()
    if not token:
        fallar("Falta el secreto BANXICO_TOKEN")
    resp = consultar(token)

    d, m, a, fix = ultimo(resp, "SF43718")
    obj = dia_objetivo()
    resp_udi = consultar(token, URL_UDI % ((obj - timedelta(days=10)).isoformat(), obj.isoformat()))
    ud, um, ua, udi = ultimo(resp_udi, "SP68257")
    if (obj - datetime(ua, um, ud).date()).days > 5:
        fallar("La UDI mas reciente (%02d/%02d/%d) esta muy atrasada" % (ud, um, ua))
    _, mes_inpc, _, inpc = ultimo(resp, "SP1")

    with open(ARCHIVO, encoding="utf-8") as f:
        original = json.load(f)
    nuevo = json.loads(json.dumps(original))  # copia

    poner(nuevo["datos"], "Tipo de cambio",
          "Tipo de cambio al %02d/%02d/%02d" % (d, m, a % 100), "%.4f" % fix)
    poner(nuevo["datos"], "UDIS", "UDIS al %02d/%02d/%02d" % (ud, um, ua % 100), "%.6f" % udi)
    poner(nuevo["datos"], "INPC", "INPC " + MESES[mes_inpc - 1], "%.3f" % inpc)
    nuevo["nota"] = NOTA

    if nuevo == original:
        print("Sin cambios.")
        return
    with open(ARCHIVO, "w", encoding="utf-8") as f:
        json.dump(nuevo, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("Actualizado: FIX %.4f (%02d/%02d/%d), UDIS %.6f (%02d/%02d/%d), INPC %s %.3f"
          % (fix, d, m, a, udi, ud, um, ua, MESES[mes_inpc - 1], inpc))


if __name__ == "__main__":
    main()
