#!/usr/bin/env python3
"""
Finnhub News Monitor v1.0
Cartera Biotech — David Amor
Plazo: 72h · Ejecutado via GitHub Actions Mon-Fri 7:00 UTC
Publica: noticias_resultado.json en GitHub Pages
"""

import urllib.request
import urllib.parse
import json
import datetime
import time

# ── CONFIG ────────────────────────────────────────────────────────────────────
FINNHUB_TOKEN = "d8o115hr01qvtr6lomngd8o115hr01qvtr6lomo0"
PLAZO_HORAS   = 72
MAX_NOTICIAS  = 5  # máximo por ticker en el JSON

TICKERS = [
    "SNDX","ARGX","DYN","DNLI","VKTX","VRTX",
    "ALNY","BEAM","OCUL","CAI","GPCR","ABVX",
    "VERA","ACRV","TARA","SENS","INSM"
    # NWL excluido — BIT (Borsa Italiana), no cubre Finnhub
]

# Keywords → badge urgente 🔴
KEYWORDS_URGENTE = [
    "pdufa","fda","approval","approved","reject","crl","complete response",
    "bla","nda","sBLA","phase 3","ph3","phase 2","ph2","data","results",
    "earnings","revenue","guidance","trial","clinical","breakthrough",
    "partnership","deal","acquisition","merger"
]

# ── HELPERS ───────────────────────────────────────────────────────────────────
def fetch_json(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"  ERROR fetch: {e}")
        return None

def es_urgente(titulo, resumen=""):
    texto = (titulo + " " + resumen).lower()
    return any(k in texto for k in KEYWORDS_URGENTE)

def nivel_noticia(urgente):
    return "rojo" if urgente else "azul"

def badge_noticia(urgente):
    return "🔴" if urgente else "🔵"

def fecha_legible(ts):
    try:
        dt = datetime.datetime.utcfromtimestamp(int(ts))
        return dt.strftime("%d %b %Y %H:%M UTC")
    except:
        return str(ts)

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    ahora    = datetime.datetime.utcnow()
    desde    = ahora - datetime.timedelta(hours=PLAZO_HORAS)
    fecha_to = ahora.strftime("%Y-%m-%d")
    fecha_from = desde.strftime("%Y-%m-%d")

    print(f"Finnhub News Monitor v1.0")
    print(f"Período: {fecha_from} → {fecha_to} ({PLAZO_HORAS}h)")
    print(f"Tickers: {len(TICKERS)}\n")

    resultado = {
        "generado": ahora.strftime("%d/%m/%Y %H:%M UTC"),
        "plazo_horas": PLAZO_HORAS,
        "desde": fecha_from,
        "hasta": fecha_to,
        "tickers": {},
        "resumen": {
            "total_noticias": 0,
            "tickers_con_noticias": 0,
            "alertas_urgentes": 0,
            "sin_noticias": 0
        },
        "todas_noticias": []
    }

    for ticker in TICKERS:
        print(f"  {ticker}...", end=" ")
        url = (
            f"https://finnhub.io/api/v1/company-news"
            f"?symbol={ticker}"
            f"&from={fecha_from}"
            f"&to={fecha_to}"
            f"&token={FINNHUB_TOKEN}"
        )
        data = fetch_json(url)
        time.sleep(0.3)  # rate limit

        if not data or not isinstance(data, list):
            print("sin datos")
            resultado["tickers"][ticker] = {
                "nombre": ticker,
                "noticias": [],
                "nivel": "ok",
                "total": 0
            }
            resultado["resumen"]["sin_noticias"] += 1
            continue

        # Filtrar últimas 72h exactas (a veces Finnhub devuelve más)
        cutoff_ts = int(desde.timestamp())
        noticias_raw = [n for n in data if int(n.get("datetime", 0)) >= cutoff_ts]

        # Clasificar y construir lista
        noticias = []
        tiene_urgente = False
        for n in noticias_raw[:MAX_NOTICIAS]:
            titulo  = n.get("headline", "")
            resumen = n.get("summary", "")
            urgente = es_urgente(titulo, resumen)
            if urgente:
                tiene_urgente = True

            noticia = {
                "ticker":   ticker,
                "titulo":   titulo[:200],
                "resumen":  resumen[:300] if resumen else "",
                "fuente":   n.get("source", ""),
                "fecha":    fecha_legible(n.get("datetime", 0)),
                "url":      n.get("url", ""),
                "imagen":   n.get("image", ""),
                "urgente":  urgente,
                "nivel":    nivel_noticia(urgente),
                "badge":    badge_noticia(urgente)
            }
            noticias.append(noticia)
            resultado["todas_noticias"].append(noticia)

        nivel_ticker = "rojo" if tiene_urgente else ("azul" if noticias else "ok")
        resultado["tickers"][ticker] = {
            "nombre":  ticker,
            "noticias": noticias,
            "nivel":    nivel_ticker,
            "total":    len(noticias)
        }

        if noticias:
            resultado["resumen"]["tickers_con_noticias"] += 1
            resultado["resumen"]["total_noticias"] += len(noticias)
        else:
            resultado["resumen"]["sin_noticias"] += 1
        if tiene_urgente:
            resultado["resumen"]["alertas_urgentes"] += 1

        estado = f"{len(noticias)} noticias" + (" 🔴 URGENTE" if tiene_urgente else "")
        print(estado)

    # Ordenar todas_noticias por urgente primero, luego por fecha
    resultado["todas_noticias"].sort(
        key=lambda x: (0 if x["urgente"] else 1, x["fecha"]),
    )

    print(f"\nResumen:")
    print(f"  Total noticias: {resultado['resumen']['total_noticias']}")
    print(f"  Tickers con noticias: {resultado['resumen']['tickers_con_noticias']}")
    print(f"  Alertas urgentes: {resultado['resumen']['alertas_urgentes']}")
    print(f"  Sin noticias: {resultado['resumen']['sin_noticias']}")

    with open("noticias_resultado.json", "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    print(f"\n✅ noticias_resultado.json guardado.")

if __name__ == "__main__":
    main()
