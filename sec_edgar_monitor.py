#!/usr/bin/env python3
"""
SEC EDGAR Monitor v2 — Modelo Biotech v3.0
Detector automático de eventos materiales, transacciones insider
y riesgo de dilución para cartera biotech.

CÓMO USAR:
  python sec_edgar_monitor.py          → últimos 7 días
  python sec_edgar_monitor.py 30       → últimos 30 días
  python sec_edgar_monitor.py 7 VERA,INSM,SNDX  → filtrar tickers

Genera dos archivos en la misma carpeta:
  - sec_monitor_reporte.txt     → reporte legible
  - sec_monitor_resultado.json  → datos para el dashboard web
"""

import urllib.request
import json
import datetime
import sys
import os
import difflib

# ── CARTERA ───────────────────────────────────────────────────────────────────
# Solo tickers reales de la cartera. Los CIK se obtienen automáticamente desde:
# https://www.sec.gov/files/company_tickers.json
#
# NWL cotiza en Italia y no tiene CIK SEC, por eso se mantiene como no SEC.
TICKERS_CARTERA = [
    "SNDX", "ARGX", "DYN", "DNLI", "VKTX", "VRTX",
    "ALNY", "BEAM", "OCUL", "CAI", "GPCR", "ABVX",
    "VERA", "ACRV", "TARA", "SENS", "INSM", "NWL"
]

NOMBRES_ESPERADOS = {
    "SNDX": "Syndax Pharmaceuticals",
    "ARGX": "argenx SE",
    "DYN":  "Dyne Therapeutics",
    "DNLI": "Denali Therapeutics",
    "VKTX": "Viking Therapeutics",
    "VRTX": "Vertex Pharmaceuticals",
    "ALNY": "Alnylam Pharmaceuticals",
    "BEAM": "Beam Therapeutics",
    "OCUL": "Ocular Therapeutix",
    "CAI":  "Caris Life Sciences",
    "GPCR": "Structure Therapeutics",
    "ABVX": "Abivax SA",
    "VERA": "Vera Therapeutics",
    "ACRV": "Acrivon Therapeutics",
    "TARA": "Protara Therapeutics",
    "SENS": "Senseonics Holdings",
    "INSM": "Insmed Inc",
    "NWL":  "NewPrinces SpA (BIT — no SEC)",
}


# Alias aceptados para evitar falsos positivos con ADR, nombres legales o mayúsculas SEC.
ALIAS_EMPRESAS = {
    "ABVX": ["Abivax", "Abivax S.A.", "Abivax SA"],
    "ARGX": ["argenx", "argenx SE", "ARGENX SE"],
    "GPCR": ["Structure Therapeutics", "Structure Therapeutics Inc."],
    "ALNY": ["Alnylam Pharmaceuticals", "ALNYLAM PHARMACEUTICALS, INC."],
    "VRTX": ["Vertex Pharmaceuticals", "VERTEX PHARMACEUTICALS INC"],
    "INSM": ["Insmed", "INSMED Inc"],
}

NO_SEC = {
    "NWL": {"cik": None, "nombre": "NewPrinces SpA (BIT — no SEC)"}
}

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def cargar_mapa_ticker_cik():
    """
    Descarga el mapa oficial ticker → CIK de la SEC.
    Devuelve un diccionario:
      {
        "ABVX": {"cik": "000XXXXXXXX", "nombre": "Nombre oficial SEC"},
        ...
      }
    """
    data = fetch_json(SEC_TICKERS_URL)
    mapa = {}

    for item in data.values():
        ticker = str(item.get("ticker", "")).upper().strip()
        cik_str = str(item.get("cik_str", "")).strip()
        title = str(item.get("title", "")).strip()

        if ticker and cik_str:
            mapa[ticker] = {
                "cik": cik_str.zfill(10),
                "nombre": title or NOMBRES_ESPERADOS.get(ticker, ticker)
            }

    return mapa


def construir_cartera_desde_sec(tickers):
    """
    Construye CARTERA usando el fichero oficial de la SEC.
    Así evita CIK escritos a mano y reduce errores como ABVX → RVMD.
    """
    mapa_sec = cargar_mapa_ticker_cik()
    cartera = {}

    for ticker in tickers:
        ticker = ticker.upper().strip()

        if ticker in NO_SEC:
            cartera[ticker] = NO_SEC[ticker]
            continue

        encontrado = mapa_sec.get(ticker)

        if encontrado:
            cartera[ticker] = {
                "cik": encontrado["cik"],
                "nombre": encontrado["nombre"],
                "nombre_esperado": NOMBRES_ESPERADOS.get(ticker, encontrado["nombre"]),
                "origen_cik": "SEC company_tickers.json"
            }
        else:
            cartera[ticker] = {
                "cik": None,
                "nombre": NOMBRES_ESPERADOS.get(ticker, ticker),
                "nombre_esperado": NOMBRES_ESPERADOS.get(ticker, ticker),
                "origen_cik": "No encontrado en SEC company_tickers.json",
                "error": "Ticker no encontrado en el mapa oficial ticker → CIK de la SEC"
            }

    return cartera


# Se rellena automáticamente al arrancar el monitor.
CARTERA = {}

# ── CLASIFICACIÓN ─────────────────────────────────────────────────────────────
KEYWORDS_ROJO = [
    "clinical hold", "complete response letter", "crl", "refuse to file",
    "going concern", "bankruptcy", "delisting", "failed to meet",
    "did not meet primary endpoint", "discontinued", "negative topline",
]
KEYWORDS_VERDE = [
    "fda approval", "fda approved", "accelerated approval", "breakthrough therapy",
    "positive topline", "collaboration agreement", "license agreement",
    "acquisition", "merger", "pdufa", "priority review", "fast track",
]
KEYWORDS_AMARILLO = [
    "public offering", "underwritten offering", "registered direct",
    "at-the-market", "convertible notes", "shelf registration", "prospectus",
]

FORMS_OBJETIVO = {"8-K","8-K/A","4","4/A","S-3","S-3/A","S-1","424B4","424B5"}

def clasificar(form, desc="", doc=""):
    texto = (desc + " " + doc).lower()
    if form in ("S-3","S-3/A","424B4","424B5"):
        return "rojo", "🔴 ALTA", "S-3/424B — Posible oferta o dilución inminente"
    if form in ("4","4/A"):
        return "amarillo", "🟡 MEDIA", "Form 4 — Insider transaction detectada"
    if form in ("8-K","8-K/A"):
        for kw in KEYWORDS_ROJO:
            if kw in texto:
                return "rojo", "🔴 ALTA", f"8-K — Evento negativo potencial: '{kw}'"
        for kw in KEYWORDS_VERDE:
            if kw in texto:
                return "verde", "🟢 ALTA", f"8-K — Evento positivo potencial: '{kw}'"
        for kw in KEYWORDS_AMARILLO:
            if kw in texto:
                return "amarillo", "🟡 MEDIA", f"8-K — Posible dilución/oferta: '{kw}'"
        return "azul", "🔵 INFO", "8-K — Evento material. Revisar."
    return "azul", "🔵 INFO", f"{form} — Revisar"


# ── VALIDACIÓN CIK / EMPRESA ──────────────────────────────────────────────────
def normalizar_nombre(nombre):
    """Normaliza nombres para comparar la empresa esperada con la devuelta por SEC."""
    if not nombre:
        return ""
    nombre = nombre.upper()
    reemplazos = {
        " INC.": "", " INC": "", " CORPORATION": "", " CORP.": "", " CORP": "",
        " LTD.": "", " LTD": "", " LIMITED": "", " PLC": "", " S.A.": "",
        " SA": "", " SE": "", " N.V.": "", " NV": "", " AG": "",
        " THERAPEUTICS": "", " PHARMACEUTICALS": "", " PHARMA": "",
        ",": "", ".": "", "-": " ", "_": " "
    }
    for k, v in reemplazos.items():
        nombre = nombre.replace(k, v)
    return " ".join(nombre.split())


def similitud_nombre(nombre_esperado, nombre_sec):
    """Devuelve una similitud 0-1 entre el nombre esperado y el nombre oficial SEC."""
    a = normalizar_nombre(nombre_esperado)
    b = normalizar_nombre(nombre_sec)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def validar_empresa_sec(ticker, nombre_esperado, nombre_sec, umbral=0.45):
    """
    Comprueba que el CIK devuelva una empresa razonablemente parecida.
    Usa alias para ADR y nombres legales. Si falla, el ticker se bloquea.
    """
    ticker = ticker.upper().strip()
    candidatos = [nombre_esperado] + ALIAS_EMPRESAS.get(ticker, [])

    mejor_score = 0.0
    mejor_nombre = nombre_esperado

    for candidato in candidatos:
        score = similitud_nombre(candidato, nombre_sec)
        if score > mejor_score:
            mejor_score = score
            mejor_nombre = candidato

    # Coincidencia directa por nombre normalizado: más fuerte que el ratio.
    sec_norm = normalizar_nombre(nombre_sec)
    for candidato in candidatos:
        cand_norm = normalizar_nombre(candidato)
        if cand_norm and (cand_norm in sec_norm or sec_norm in cand_norm):
            return True, 1.00, None

    if mejor_score < umbral:
        return False, mejor_score, (
            f"Posible CIK incorrecto o empresa no coincidente. "
            f"Ticker: {ticker}. Esperado: '{nombre_esperado}'. SEC: '{nombre_sec}'. "
            f"Mejor coincidencia: '{mejor_nombre}'. Similitud: {mejor_score:.2f}. "
            f"Se ignora este ticker para evitar alertas falsas."
        )

    return True, mejor_score, None


# ── FETCH ─────────────────────────────────────────────────────────────────────
def fetch_json(url):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Modelo Biotech v3.0 david@biotech.es")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))

def fecha_desde(dias):
    return (datetime.datetime.now() - datetime.timedelta(days=dias)).strftime("%Y-%m-%d")

def fecha_hoy():
    return datetime.datetime.now().strftime("%Y-%m-%d")

def ahora_str():
    return datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

# ── CONSULTA EDGAR ────────────────────────────────────────────────────────────
def get_filings(ticker, cik, dias, nombre_esperado=None):
    cik_padded = cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    try:
        data = fetch_json(url)
    except Exception as e:
        return [], str(e)

    # Comprobación adicional: validar que el CIK corresponde a la empresa esperada
    company_name_sec = data.get("name", "")
    if company_name_sec:
        print(f"      Empresa SEC: {company_name_sec}")
        if nombre_esperado:
            empresa_ok, score, aviso = validar_empresa_sec(ticker, nombre_esperado, company_name_sec)
            if empresa_ok:
                print(f"      Validación CIK: ✅ OK ({score:.2f})")
            else:
                print(f"      Validación CIK: ⚠️ ALERTA ({score:.2f})")
                return [], aviso

    recent = data.get("filings", {}).get("recent", {})
    if not recent:
        return [], "Sin datos"

    forms        = recent.get("form", [])
    dates        = recent.get("filingDate", [])
    accessions   = recent.get("accessionNumber", [])
    primaries    = recent.get("primaryDocument", [])
    descriptions = recent.get("primaryDocDescription", [])

    cutoff   = fecha_desde(dias)
    cik_num  = cik.lstrip("0")
    results  = []

    for form, date, acc, prim, desc in zip(forms, dates, accessions, primaries, descriptions):
        if date < cutoff:
            break
        if form not in FORMS_OBJETIVO:
            continue
        acc_fmt  = acc.replace("-", "")
        url_doc  = f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_fmt}/{prim}"
        nivel, badge, resumen = clasificar(form, desc, prim)
        results.append({
            "form":    form,
            "fecha":   date,
            "nivel":   nivel,
            "badge":   badge,
            "resumen": resumen,
            "detalle": desc or prim or "",
            "empresa_sec": company_name_sec,
            "url":     url_doc,
        })

    return results, None

# ── RESUMEN POR TICKER ────────────────────────────────────────────────────────
def resumen_ticker(filings):
    """Devuelve el nivel más alto de alerta de un ticker."""
    niveles = [f["nivel"] for f in filings]
    if "rojo"    in niveles: return "rojo",    "🔴"
    if "verde"   in niveles: return "verde",   "🟢"
    if "amarillo"in niveles: return "amarillo","🟡"
    if "azul"    in niveles: return "azul",    "🔵"
    return "ok", "✅"

# ── RUNNER ────────────────────────────────────────────────────────────────────
def run_monitor(dias=7, tickers_filtro=None):
    global CARTERA

    tickers = tickers_filtro or TICKERS_CARTERA
    tickers = [t.strip().upper() for t in tickers if t.strip()]

    print("Cargando CIK oficiales desde SEC company_tickers.json...")
    try:
        CARTERA = construir_cartera_desde_sec(TICKERS_CARTERA)
    except Exception as e:
        print(f"❌ No se pudo cargar el mapa oficial ticker → CIK de la SEC: {e}")
        CARTERA = {t: {"cik": None, "nombre": NOMBRES_ESPERADOS.get(t, t), "error": str(e)} for t in TICKERS_CARTERA}

    ahora   = ahora_str()

    print(f"\n{'═'*62}")
    print(f"  SEC EDGAR MONITOR · Modelo Biotech v3.0")
    print(f"  Generado: {ahora}")
    print(f"  Período: últimos {dias} días ({fecha_desde(dias)} → {fecha_hoy()})")
    print(f"{'═'*62}\n")

    # Datos para el dashboard
    dashboard = {
        "generado":   ahora,
        "periodo_dias": dias,
        "desde":      fecha_desde(dias),
        "hasta":      fecha_hoy(),
        "resumen": {
            "total_filings": 0,
            "alertas_rojas":    0,
            "alertas_verdes":   0,
            "alertas_amarillas":0,
            "alertas_azules":   0,
            "sin_novedad":      0,
        },
        "tickers": {},
        "alertas_criticas": [],   # Solo rojas y verdes — para mostrar arriba
        "todos_filings": [],      # Todos ordenados por fecha desc
    }

    for ticker in tickers:
        ticker = ticker.strip().upper()
        info = CARTERA.get(ticker)
        if not info:
            print(f"  [{ticker}] ⚠️ No está en CARTERA — omitido")
            dashboard["tickers"][ticker] = {
                "nombre": None, "filings": [],
                "nivel": "omitido", "badge": "⚠️", "error": "Ticker no incluido en CARTERA"
            }
            continue
        if not info["cik"]:
            err = info.get("error") or "Sin CIK SEC"
            print(f"  [{ticker}] ⚪ {err} — omitido")
            dashboard["tickers"][ticker] = {
                "nombre": info["nombre"], "filings": [],
                "nivel": "na", "badge": "⚪", "error": err
            }
            continue

        print(f"  [{ticker}] Consultando...", end=" ")
        filings, error = get_filings(ticker, info["cik"], dias, info.get("nombre_esperado", info["nombre"]))

        if error:
            print(f"❌ {error}")
            dashboard["tickers"][ticker] = {
                "nombre": info["nombre"],
                "nombre_esperado": info.get("nombre_esperado", info["nombre"]),
                "cik": info.get("cik"),
                "origen_cik": info.get("origen_cik"),
                "validacion_empresa": "ERROR",
                "filings": [],
                "nivel": "error", "badge": "❌", "error": error
            }
            continue

        nivel_ticker, badge_ticker = resumen_ticker(filings) if filings else ("ok","✅")

        if filings:
            print(f"{badge_ticker} {len(filings)} filing(s)")
            for f in filings:
                print(f"     {f['badge']} {f['form']} | {f['fecha']} | {f['resumen']}")
                dashboard["todos_filings"].append({
                    "ticker": ticker, "nombre": info["nombre"], **f
                })
                if f["nivel"] in ("rojo","verde"):
                    dashboard["alertas_criticas"].append({
                        "ticker": ticker, "nombre": info["nombre"], **f
                    })
                # Contadores
                dashboard["resumen"]["total_filings"] += 1
                if f["nivel"] == "rojo":    dashboard["resumen"]["alertas_rojas"] += 1
                if f["nivel"] == "verde":   dashboard["resumen"]["alertas_verdes"] += 1
                if f["nivel"] == "amarillo":dashboard["resumen"]["alertas_amarillas"] += 1
                if f["nivel"] == "azul":    dashboard["resumen"]["alertas_azules"] += 1
        else:
            print("✅ Sin novedades")
            dashboard["resumen"]["sin_novedad"] += 1

        dashboard["tickers"][ticker] = {
            "nombre":  info["nombre"],
            "nombre_esperado": info.get("nombre_esperado", info["nombre"]),
            "cik": info.get("cik"),
            "origen_cik": info.get("origen_cik"),
            "validacion_empresa": "OK",
            "filings": filings,
            "nivel":   nivel_ticker,
            "badge":   badge_ticker,
            "error":   None,
        }

    # Ordenar todos los filings por fecha desc
    dashboard["todos_filings"].sort(key=lambda x: x["fecha"], reverse=True)
    dashboard["alertas_criticas"].sort(key=lambda x: x["fecha"], reverse=True)

    return dashboard

# ── REPORTE TXT ───────────────────────────────────────────────────────────────
def generar_reporte(dashboard):
    r = dashboard["resumen"]
    lines = []
    lines.append("═" * 62)
    lines.append("SEC EDGAR MONITOR · Modelo Biotech v3.0")
    lines.append(f"Generado: {dashboard['generado']} | Período: últimos {dashboard['periodo_dias']} días")
    lines.append(f"Desde: {dashboard['desde']} → Hasta: {dashboard['hasta']}")
    lines.append("═" * 62)
    lines.append(f"\nRESUMEN: {r['total_filings']} filings | "
                 f"🔴 {r['alertas_rojas']} | 🟢 {r['alertas_verdes']} | "
                 f"🟡 {r['alertas_amarillas']} | 🔵 {r['alertas_azules']} | "
                 f"✅ {r['sin_novedad']} sin novedad")

    # Críticos
    criticos = dashboard["alertas_criticas"]
    if criticos:
        lines.append(f"\n{'─'*50}")
        lines.append(f"🚨 ALERTAS CRÍTICAS ({len(criticos)})")
        lines.append("─" * 50)
        for a in criticos:
            lines.append(f"\n  [{a['ticker']}] {a['nombre']}")
            lines.append(f"  {a['badge']} {a['form']} | {a['fecha']}")
            lines.append(f"  {a['resumen']}")
            if a.get("empresa_sec"):
                lines.append(f"  Empresa SEC: {a['empresa_sec']}")
            lines.append(f"  Detalle: {a['detalle']}")
            lines.append(f"  → {a['url']}")

    # Por ticker
    lines.append(f"\n{'─'*50}")
    lines.append("DETALLE POR TICKER")
    lines.append("─" * 50)
    for ticker, data in dashboard["tickers"].items():
        if data.get("error") == "Sin CIK SEC":
            continue
        badge = data["badge"]
        filings = data["filings"]
        if not filings:
            lines.append(f"  {badge} [{ticker}] Sin novedades")
            continue
        lines.append(f"\n  {badge} [{ticker}] {data['nombre']} — {len(filings)} filing(s)")
        for f in filings:
            lines.append(f"     {f['badge']} {f['form']} | {f['fecha']} | {f['resumen']}")
            if f.get("empresa_sec"):
                lines.append(f"     Empresa SEC: {f['empresa_sec']}")
            lines.append(f"     → {f['url']}")

    lines.append(f"\n{'═'*62}")
    lines.append("Fuente: SEC EDGAR API pública · data.sec.gov")
    lines.append("Modelo Biotech v3.0 · Módulo 1: SEC EDGAR Monitor v2")
    lines.append("═" * 62)
    return "\n".join(lines)

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    dias = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    filtro = sys.argv[2].upper().split(",") if len(sys.argv) > 2 else None

    dashboard = run_monitor(dias=dias, tickers_filtro=filtro)
    reporte   = generar_reporte(dashboard)

    print("\n" + reporte)

    # Guardar en la misma carpeta que el script
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # TXT legible
    ruta_txt = os.path.join(script_dir, "sec_monitor_reporte.txt")
    with open(ruta_txt, "w", encoding="utf-8") as f:
        f.write(reporte)

    # JSON para el dashboard — nombre fijo que el HTML buscará
    ruta_json = os.path.join(script_dir, "sec_monitor_resultado.json")
    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n💾 Reporte TXT → {ruta_txt}")
    print(f"💾 JSON dashboard → {ruta_json}")
    print(f"\n✅ Listo. Sube sec_monitor_resultado.json a Netlify junto con el HTML.")

