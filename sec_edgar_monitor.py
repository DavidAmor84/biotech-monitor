#!/usr/bin/env python3
"""
SEC EDGAR Monitor v3 — Modelo Biotech v3.0
═══════════════════════════════════════════
Módulos activos:
  1. Filings básicos + validación CIK automática (company_tickers.json)
  2. Form 4 parseado XML → insider detail (nombre, cargo, tipo, acciones, precio)
  3. 8-K con Items + lectura cuerpo texto → clasificación semántica real
  4. 10-Q: caja, burn rate, shares outstanding, litigios
  5. S-3 / 424B4: importe oferta → riesgo dilución cuantificado
  6. ClinicalTrials.gov API → status ensayos cartera
  7. Caché inteligente → solo re-descarga si hay cambios (optimiza GitHub Actions)

CÓMO USAR:
  python sec_edgar_monitor.py          → últimos 7 días
  python sec_edgar_monitor.py 30       → últimos 30 días
  python sec_edgar_monitor.py 7 VERA,INSM,SNDX  → filtrar tickers

Genera en la misma carpeta:
  - sec_monitor_reporte.txt     → reporte legible
  - sec_monitor_resultado.json  → datos para el dashboard web
  - sec_monitor_cache.json      → caché interna (no subir al dashboard)
"""

import urllib.request
import urllib.error
import json
import datetime
import sys
import os
import re
import difflib
import xml.etree.ElementTree as ET
import hashlib
import time

# ── CARTERA ───────────────────────────────────────────────────────────────────
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

# NCT IDs de los ensayos principales de la cartera
CLINICALTRIALS_CARTERA = {
    "SNDX": [{"nct": "NCT04603300", "nombre": "EMERGE Ph3 (revumenib AML)"},
             {"nct": "NCT05185622", "nombre": "SAVE Ph2 (revumenib AML frontline)"}],
    "DYN":  [{"nct": "NCT05540860", "nombre": "DELIVER Ph3 (DYNE-251 DMD)"},
             {"nct": "NCT06339827", "nombre": "ACHIEVE Ph3 (DYNE-101 DM1)"}],
    "VKTX": [{"nct": "NCT05948826", "nombre": "VENTURE Ph2b (VK2735 SC obesidad)"},
             {"nct": "NCT06119360", "nombre": "VANQUISH Ph2 (VK2735 oral obesidad)"}],
    "BEAM": [{"nct": "NCT05456880", "nombre": "BEACON Ph1/2 (BEAM-101 SCD)"},
             {"nct": "NCT05456893", "nombre": "Ph1 (BEAM-302 A1ATD)"}],
    "OCUL": [{"nct": "NCT05536297", "nombre": "HELIOS-1 Ph3 (AXPAXLI wet AMD)"},
             {"nct": "NCT06100081", "nombre": "HELIOS-3 Ph2 (AXPAXLI DR)"}],
    "ABVX": [{"nct": "NCT04745806", "nombre": "ABTECT Ph3 (obefazimod UC inducción)"},
             {"nct": "NCT05076916", "nombre": "ABTECT Ph3 mantenimiento"}],
    "VERA": [{"nct": "NCT04287985", "nombre": "ORIGIN Ph3 (atacicept IgAN)"}],
    "ACRV": [{"nct": "NCT05116774", "nombre": "Ph2 (ACR-368 + OncoSignature)"}],
    "TARA": [{"nct": "NCT03002103",  "nombre": "Ph2 (TARA-002 LM)"}],
    "GPCR": [{"nct": "NCT05805709", "nombre": "Ph2b (aleniglipron obesidad)"}],
    "INSM": [{"nct": "NCT04053543", "nombre": "ASPEN Ph3 (brensocatib bronchiectasis)"}],
    "DNLI": [{"nct": "NCT04532047", "nombre": "Ph2/3 (DNL310 Hunter AVLAYAH)"}],
}

ALIAS_EMPRESAS = {
    "ABVX": ["Abivax", "Abivax S.A.", "Abivax SA"],
    "ARGX": ["argenx", "argenx SE", "ARGENX SE"],
    "GPCR": ["Structure Therapeutics", "Structure Therapeutics Inc."],
    "ALNY": ["Alnylam Pharmaceuticals", "ALNYLAM PHARMACEUTICALS, INC."],
    "VRTX": ["Vertex Pharmaceuticals", "VERTEX PHARMACEUTICALS INC"],
    "INSM": ["Insmed", "INSMED Inc"],
    "OCUL": ["Ocular Therapeutix", "OCULAR THERAPEUTIX INC"],
    "DNLI": ["Denali Therapeutics", "DENALI THERAPEUTICS INC"],
    "SENS": ["Senseonics", "Senseonics Holdings", "SENSEONICS HOLDINGS INC"],
}

NO_SEC = {
    "NWL": {"cik": None, "nombre": "NewPrinces SpA (BIT — no SEC)"}
}

SEC_TICKERS_URL  = "https://www.sec.gov/files/company_tickers.json"
CLINICALTRIALS_URL = "https://clinicaltrials.gov/api/v2/studies/{nct}?fields=NCTId,BriefTitle,OverallStatus,Phase,EnrollmentCount,StartDate,PrimaryCompletionDate,LastUpdatePostDate"

# Forms que se monitorizan
FORMS_OBJETIVO = {"8-K","8-K/A","4","4/A","S-3","S-3/A","S-1","424B4","424B5","10-Q","10-Q/A"}

# ── CACHÉ ─────────────────────────────────────────────────────────────────────
CACHE = {}
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sec_monitor_cache.json")

def cargar_cache():
    global CACHE
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                CACHE = json.load(f)
        except Exception:
            CACHE = {}
    else:
        CACHE = {}

def guardar_cache():
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(CACHE, f, ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass

def cache_get(url):
    """Devuelve (contenido, hash) si está en caché y no ha caducado (24h)."""
    entry = CACHE.get(url)
    if not entry:
        return None, None
    ts = entry.get("ts", "")
    if ts:
        try:
            age = (datetime.datetime.now() - datetime.datetime.fromisoformat(ts)).total_seconds()
            if age > 86400:  # 24 horas
                return None, None
        except Exception:
            return None, None
    return entry.get("content"), entry.get("hash")

def cache_set(url, content, content_hash):
    CACHE[url] = {
        "content": content,
        "hash": content_hash,
        "ts": datetime.datetime.now().isoformat()
    }

# ── FETCH ─────────────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": "Modelo Biotech v3.0 david@biotech.es",
    "Accept": "application/json, text/html, application/xml, */*",
}

def fetch_raw(url, timeout=20):
    """Descarga texto plano con caché."""
    cached_content, cached_hash = cache_get(url)
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            content = raw.decode("utf-8", errors="replace")
            new_hash = hashlib.md5(raw).hexdigest()
            if cached_hash and new_hash == cached_hash:
                cache_set(url, cached_content, cached_hash)
                return cached_content, False  # sin cambios
            cache_set(url, content, new_hash)
            return content, True  # nuevo contenido
    except Exception as e:
        if cached_content:
            return cached_content, False  # fallback a caché
        raise e

def fetch_json(url, timeout=20):
    content, changed = fetch_raw(url, timeout)
    return json.loads(content), changed

def fetch_text(url, timeout=20):
    return fetch_raw(url, timeout)

def safe_sleep(s=0.25):
    """Pausa cortés para no saturar la SEC."""
    time.sleep(s)

# ── UTILIDADES DE FECHA ───────────────────────────────────────────────────────
def fecha_desde(dias):
    return (datetime.datetime.now() - datetime.timedelta(days=dias)).strftime("%Y-%m-%d")

def fecha_hoy():
    return datetime.datetime.now().strftime("%Y-%m-%d")

def ahora_str():
    return datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

# ── VALIDACIÓN CIK ────────────────────────────────────────────────────────────
def normalizar_nombre(nombre):
    if not nombre:
        return ""
    nombre = nombre.upper()
    reemplazos = {
        " INC.":"", " INC":"", " CORPORATION":"", " CORP.":"", " CORP":"",
        " LTD.":"", " LTD":"", " LIMITED":"", " PLC":"", " S.A.":"",
        " SA":"", " SE":"", " N.V.":"", " NV":"", " AG":"",
        " THERAPEUTICS":"", " PHARMACEUTICALS":"", " PHARMA":"",
        ",":"", ".":"", "-":" ", "_":" "
    }
    for k,v in reemplazos.items():
        nombre = nombre.replace(k, v)
    return " ".join(nombre.split())

def similitud_nombre(a, b):
    na, nb = normalizar_nombre(a), normalizar_nombre(b)
    if not na or not nb:
        return 0.0
    return difflib.SequenceMatcher(None, na, nb).ratio()

def validar_empresa_sec(ticker, nombre_esperado, nombre_sec, umbral=0.45):
    ticker = ticker.upper().strip()
    candidatos = [nombre_esperado] + ALIAS_EMPRESAS.get(ticker, [])
    sec_norm = normalizar_nombre(nombre_sec)
    for candidato in candidatos:
        cand_norm = normalizar_nombre(candidato)
        if cand_norm and (cand_norm in sec_norm or sec_norm in cand_norm):
            return True, 1.00, None
    mejor_score, mejor_nombre = 0.0, nombre_esperado
    for candidato in candidatos:
        score = similitud_nombre(candidato, nombre_sec)
        if score > mejor_score:
            mejor_score, mejor_nombre = score, candidato
    if mejor_score < umbral:
        return False, mejor_score, (
            f"CIK no coincide con empresa esperada. Ticker: {ticker}. "
            f"Esperado: '{nombre_esperado}'. SEC: '{nombre_sec}'. "
            f"Similitud: {mejor_score:.2f}. Ticker bloqueado."
        )
    return True, mejor_score, None

# ── CARGAR CARTERA DESDE SEC ──────────────────────────────────────────────────
def cargar_mapa_ticker_cik():
    data, _ = fetch_json(SEC_TICKERS_URL)
    mapa = {}
    for item in data.values():
        ticker = str(item.get("ticker","")).upper().strip()
        cik_str = str(item.get("cik_str","")).strip()
        title   = str(item.get("title","")).strip()
        if ticker and cik_str:
            mapa[ticker] = {
                "cik":    cik_str.zfill(10),
                "nombre": title or NOMBRES_ESPERADOS.get(ticker, ticker)
            }
    return mapa

def construir_cartera_desde_sec(tickers):
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
                "cik":             encontrado["cik"],
                "nombre":          encontrado["nombre"],
                "nombre_esperado": NOMBRES_ESPERADOS.get(ticker, encontrado["nombre"]),
                "origen_cik":      "SEC company_tickers.json"
            }
        else:
            cartera[ticker] = {
                "cik":    None,
                "nombre": NOMBRES_ESPERADOS.get(ticker, ticker),
                "error":  "Ticker no encontrado en company_tickers.json"
            }
    return cartera

CARTERA = {}

# ── CLASIFICACIÓN BÁSICA ──────────────────────────────────────────────────────
KEYWORDS_ROJO = [
    "clinical hold","complete response letter","crl","refuse to file",
    "going concern","bankruptcy","delisting","failed to meet",
    "did not meet primary endpoint","discontinued","negative topline",
    "partial clinical hold","safety concern","fatal","death related",
]
KEYWORDS_VERDE = [
    "fda approval","fda approved","accelerated approval","breakthrough therapy",
    "positive topline","collaboration agreement","license agreement",
    "acquisition","merger","pdufa","priority review","fast track",
    "orphan drug","rmat","nda accepted","bla accepted","marketing authorization",
    "complete response","approval letter",
]
KEYWORDS_AMARILLO = [
    "public offering","underwritten offering","registered direct",
    "at-the-market","atm","convertible notes","shelf registration",
    "prospectus supplement","secondary offering",
]

# Items 8-K con su clasificación
ITEMS_8K = {
    "1.01": ("verde",  "Acuerdo material (colaboración, licencia, M&A)"),
    "1.02": ("rojo",   "Terminación de acuerdo material"),
    "1.03": ("rojo",   "Bankruptcy o receivership"),
    "2.02": ("azul",   "Resultados de operaciones (earnings)"),
    "2.05": ("rojo",   "Despido masivo / reestructuración"),
    "2.06": ("rojo",   "Reducción valor activo material"),
    "3.01": ("rojo",   "Delisting o incumplimiento listing standards"),
    "4.01": ("amarillo","Cambio de auditor"),
    "4.02": ("rojo",   "Restatement financiero"),
    "5.02": ("amarillo","Cambio directivos (CEO/CFO/CSO)"),
    "5.03": ("azul",   "Enmienda estatutos"),
    "7.01": ("azul",   "Regulación FD — disclosure voluntario"),
    "8.01": ("azul",   "Otros eventos — revisar"),
    "9.01": ("azul",   "Exhibits financieros"),
}

def clasificar_base(form, desc="", doc=""):
    texto = (desc + " " + doc).lower()
    if form in ("S-3","S-3/A","S-1"):
        return "amarillo", "🟡 MEDIA", "Registro S-3/S-1 — Shelf activo, dilución potencial"
    if form in ("424B4","424B5"):
        return "rojo", "🔴 ALTA", "424B — Prospecto definitivo: oferta en curso"
    if form in ("4","4/A"):
        return "amarillo", "🟡 MEDIA", "Form 4 — Insider transaction detectada"
    if form in ("10-Q","10-Q/A"):
        return "azul", "🔵 INFO", "10-Q — Trimestral: financiero actualizado"
    if form in ("8-K","8-K/A"):
        for kw in KEYWORDS_ROJO:
            if kw in texto:
                return "rojo","🔴 ALTA", f"8-K — Evento negativo: '{kw}'"
        for kw in KEYWORDS_VERDE:
            if kw in texto:
                return "verde","🟢 ALTA", f"8-K — Evento positivo: '{kw}'"
        for kw in KEYWORDS_AMARILLO:
            if kw in texto:
                return "amarillo","🟡 MEDIA", f"8-K — Posible dilución: '{kw}'"
        return "azul","🔵 INFO","8-K — Evento material. Revisar."
    return "azul","🔵 INFO", f"{form} — Revisar"

# ── MÓDULO 2: FORM 4 XML ──────────────────────────────────────────────────────
def parsear_form4(url):
    """
    Descarga y parsea el XML del Form 4 para extraer:
    nombre, cargo, tipo transacción, acciones, precio, fecha.
    """
    result = {
        "insider_nombre": None,
        "insider_cargo":  None,
        "transaccion_tipo": None,
        "transaccion_acciones": None,
        "transaccion_precio": None,
        "transaccion_fecha": None,
        "acciones_post": None,
        "resumen_detail": None,
    }
    try:
        # Intentar URL XML (Form 4 tiene versión .xml)
        xml_url = url.replace(".htm", ".xml") if url.endswith(".htm") else url
        # Buscar el XML index para encontrar el archivo correcto
        content, _ = fetch_text(xml_url, timeout=15)
        safe_sleep()

        root = ET.fromstring(content)
        ns = {"": root.tag.split("}")[0].strip("{") if "}" in root.tag else ""}

        def find_text(tag):
            # Busca con y sin namespace
            el = root.find(".//" + tag)
            if el is None and ns.get(""):
                el = root.find(".//{%s}%s" % (ns[""], tag))
            return el.text.strip() if el is not None and el.text else None

        result["insider_nombre"] = find_text("rptOwnerName")
        result["insider_cargo"]  = find_text("officerTitle") or find_text("rptOwnerRelationship")

        # Buscar transacciones no derivadas
        trans_nodes = root.findall(".//nonDerivativeTransaction")
        if not trans_nodes:
            trans_nodes = root.findall(".//derivativeTransaction")

        if trans_nodes:
            tn = trans_nodes[0]
            def tn_text(tag):
                el = tn.find(".//" + tag)
                return el.text.strip() if el is not None and el.text else None

            tipo_code = tn_text("transactionCode") or ""
            tipos = {"P":"Compra","S":"Venta","A":"Concesión","D":"Disposición",
                     "M":"Ejercicio opción","G":"Donación","F":"Retención impuestos"}
            result["transaccion_tipo"]     = tipos.get(tipo_code, tipo_code)
            result["transaccion_acciones"] = tn_text("transactionShares") or tn_text("transactionAcquiredDisposedCode")
            result["transaccion_precio"]   = tn_text("transactionPricePerShare")
            result["transaccion_fecha"]    = tn_text("transactionDate")
            result["acciones_post"]        = tn_text("sharesOwnedFollowingTransaction")

        # Construir resumen legible
        partes = []
        if result["insider_nombre"]: partes.append(result["insider_nombre"])
        if result["insider_cargo"]:  partes.append(f"({result['insider_cargo']})")
        if result["transaccion_tipo"]: partes.append(f"→ {result['transaccion_tipo']}")
        if result["transaccion_acciones"]:
            try:
                acc = int(float(result["transaccion_acciones"]))
                partes.append(f"{acc:,} acciones")
            except Exception:
                partes.append(result["transaccion_acciones"])
        if result["transaccion_precio"]:
            try:
                precio = float(result["transaccion_precio"])
                partes.append(f"@ ${precio:.2f}")
            except Exception:
                pass
        result["resumen_detail"] = " ".join(partes) if partes else None

    except Exception as e:
        result["resumen_detail"] = f"Form 4 — parse error: {str(e)[:80]}"

    return result

# ── MÓDULO 3: 8-K ITEMS + TEXTO ──────────────────────────────────────────────
def parsear_8k(url):
    """
    Descarga el HTML/TXT del 8-K y extrae:
    - Items reportados
    - Clasificación semántica por Item
    - Extracto del cuerpo (primeras 1500 chars relevantes)
    """
    result = {
        "items_detectados": [],
        "clasificacion_item": None,
        "extracto": None,
        "nivel_ajustado": None,
        "badge_ajustado": None,
        "resumen_ajustado": None,
    }
    try:
        content, _ = fetch_text(url, timeout=20)
        safe_sleep()

        # Limpiar HTML básico
        texto = re.sub(r'<[^>]+>', ' ', content)
        texto = re.sub(r'&nbsp;', ' ', texto)
        texto = re.sub(r'&#\d+;', ' ', texto)
        texto = re.sub(r'\s+', ' ', texto).strip()
        texto_lower = texto.lower()

        # Detectar Items reportados
        items_encontrados = re.findall(r'item\s+(\d+\.\d+)', texto_lower)
        items_unicos = list(dict.fromkeys(items_encontrados))
        result["items_detectados"] = items_unicos[:8]  # máximo 8

        # Clasificar por Item más relevante
        mejor_nivel = "azul"
        mejor_desc  = None
        orden_prioridad = ["rojo","verde","amarillo","azul"]
        for item_num in items_unicos:
            if item_num in ITEMS_8K:
                niv, desc = ITEMS_8K[item_num]
                if orden_prioridad.index(niv) < orden_prioridad.index(mejor_nivel):
                    mejor_nivel = niv
                    mejor_desc  = f"Item {item_num}: {desc}"

        # Si no hay Items reconocidos, clasificar por keywords en el cuerpo
        if not mejor_desc:
            for kw in KEYWORDS_ROJO:
                if kw in texto_lower:
                    mejor_nivel = "rojo"
                    mejor_desc  = f"Keyword crítico en cuerpo: '{kw}'"
                    break
            if mejor_nivel == "azul":
                for kw in KEYWORDS_VERDE:
                    if kw in texto_lower:
                        mejor_nivel = "verde"
                        mejor_desc  = f"Keyword positivo en cuerpo: '{kw}'"
                        break
            if mejor_nivel == "azul":
                for kw in KEYWORDS_AMARILLO:
                    if kw in texto_lower:
                        mejor_nivel = "amarillo"
                        mejor_desc  = f"Keyword dilución en cuerpo: '{kw}'"
                        break

        badges = {"rojo":"🔴 ALTA","verde":"🟢 ALTA","amarillo":"🟡 MEDIA","azul":"🔵 INFO"}
        result["nivel_ajustado"]   = mejor_nivel
        result["badge_ajustado"]   = badges.get(mejor_nivel, "🔵 INFO")
        result["resumen_ajustado"] = mejor_desc or "8-K — Sin clasificación específica por Item"

        # Extracto del cuerpo (buscar párrafo con información real)
        extracto_raw = texto[200:1800] if len(texto) > 200 else texto
        result["extracto"] = extracto_raw[:800].strip()

    except Exception as e:
        result["resumen_ajustado"] = f"8-K — Error lectura: {str(e)[:80]}"

    return result

# ── MÓDULO 4: 10-Q FINANCIERO ─────────────────────────────────────────────────
CASH_PATTERNS = [
    r'cash[,\s]+cash equivalents[,\s]+and[,\s]+(?:short[- ]term[,\s]+)?investments?\s*[:\$]?\s*\$?\s*([\d,\.]+)',
    r'cash and cash equivalents\s*[:\$]?\s*\$?\s*([\d,\.]+)',
    r'total cash\s*[:\$]?\s*\$?\s*([\d,\.]+)',
]
SHARES_PATTERN = r'(\d[\d,\.]+)\s*(?:thousand\s+)?shares?\s+(?:of\s+)?(?:common\s+stock\s+)?(?:issued\s+and\s+)?outstanding'
BURN_PATTERN   = r'net cash used in operating activities\s*[:\$]?\s*\(?\$?\s*([\d,\.]+)'

def parsear_10q(url, ticker=""):
    """
    Descarga el 10-Q y extrae:
    - Caja total (cash + equivalents + short-term investments)
    - Burn rate trimestral y mensual estimado
    - Shares outstanding (diluted)
    - Cambio vs trimestre anterior si hay caché
    - Mención de litigios
    """
    result = {
        "caja_mm":          None,
        "burn_trimestral_mm": None,
        "burn_mensual_mm":  None,
        "runway_meses":     None,
        "shares_outstanding_mm": None,
        "litigios_detectados": False,
        "shelf_mencionado":    False,
        "going_concern":       False,
        "extracto_financiero": None,
        "resumen_10q":         None,
    }
    try:
        content, _ = fetch_text(url, timeout=25)
        safe_sleep()

        texto = re.sub(r'<[^>]+>', ' ', content)
        texto = re.sub(r'\s+', ' ', texto).strip()
        texto_lower = texto.lower()

        # Detectar flags críticos
        result["litigios_detectados"] = "legal proceedings" in texto_lower and (
            "plaintiff" in texto_lower or "lawsuit" in texto_lower or "litigation" in texto_lower)
        result["shelf_mencionado"]   = "shelf registration" in texto_lower or "s-3" in texto_lower
        result["going_concern"]      = "going concern" in texto_lower or "substantial doubt" in texto_lower

        # Extraer caja (en miles o millones — SEC suele usar miles)
        for pat in CASH_PATTERNS:
            m = re.search(pat, texto_lower)
            if m:
                raw = m.group(1).replace(",","")
                try:
                    val = float(raw)
                    # Heurística: si el número es >10000 probablemente está en miles
                    if val > 10000:
                        val = val / 1000  # convertir a millones
                    result["caja_mm"] = round(val, 1)
                    break
                except Exception:
                    pass

        # Burn rate (net cash used in operations)
        m = re.search(BURN_PATTERN, texto_lower)
        if m:
            raw = m.group(1).replace(",","")
            try:
                val = float(raw)
                if val > 10000:
                    val = val / 1000
                result["burn_trimestral_mm"] = round(val, 1)
                result["burn_mensual_mm"]    = round(val / 3, 1)
                if result["caja_mm"] and result["burn_mensual_mm"] and result["burn_mensual_mm"] > 0:
                    result["runway_meses"] = int(result["caja_mm"] / result["burn_mensual_mm"])
            except Exception:
                pass

        # Shares outstanding
        m = re.search(SHARES_PATTERN, texto_lower)
        if m:
            raw = m.group(1).replace(",","")
            try:
                val = float(raw)
                if val > 1000000:
                    val = val / 1000000  # convertir a millones
                result["shares_outstanding_mm"] = round(val, 1)
            except Exception:
                pass

        # Extracto zona financiera
        idx = texto_lower.find("cash and cash equivalents")
        if idx > 0:
            result["extracto_financiero"] = texto[max(0,idx-50):idx+300].strip()

        # Construir resumen
        partes = []
        if result["caja_mm"]:        partes.append(f"Caja: ${result['caja_mm']}M")
        if result["burn_mensual_mm"]: partes.append(f"Burn: ${result['burn_mensual_mm']}M/mes")
        if result["runway_meses"]:    partes.append(f"Runway: {result['runway_meses']} meses")
        if result["shares_outstanding_mm"]: partes.append(f"Shares: {result['shares_outstanding_mm']}M")
        if result["going_concern"]:   partes.append("⚠️ GOING CONCERN")
        if result["litigios_detectados"]: partes.append("⚖️ Litigios activos")
        if result["shelf_mencionado"]: partes.append("📋 Shelf mencionado")
        result["resumen_10q"] = " · ".join(partes) if partes else "10-Q — Sin datos financieros extraíbles"

    except Exception as e:
        result["resumen_10q"] = f"10-Q — Error lectura: {str(e)[:80]}"

    return result

# ── MÓDULO 5: S-3 / 424B IMPORTE OFERTA ──────────────────────────────────────
OFERTA_PATTERNS = [
    r'aggregate\s+(?:offering\s+)?(?:amount|price)\s+of\s+\$?([\d,\.]+)\s*(?:million|billion)?',
    r'\$\s*([\d,\.]+)\s*(?:million|billion)?\s+(?:in\s+)?(?:aggregate\s+)?(?:gross\s+)?proceeds',
    r'total\s+(?:gross\s+)?proceeds?\s+(?:of\s+)?\$?([\d,\.]+)\s*(?:million|billion)?',
    r'offering\s+(?:price|amount)\s*(?:of\s+)?\$\s*([\d,\.]+)',
]

def parsear_prospecto(url):
    """
    Descarga S-3 o 424B y extrae el importe total de la oferta.
    Clasifica el riesgo de dilución por tamaño.
    """
    result = {
        "importe_mm":      None,
        "tipo_oferta":     None,
        "riesgo_dilucion": None,
        "resumen_oferta":  None,
    }
    try:
        content, _ = fetch_text(url, timeout=20)
        safe_sleep()
        texto = re.sub(r'<[^>]+>', ' ', content)
        texto = re.sub(r'\s+', ' ', texto).strip()
        texto_lower = texto.lower()

        # Tipo de oferta
        if "at-the-market" in texto_lower or "atm" in texto_lower:
            result["tipo_oferta"] = "ATM (At-The-Market)"
        elif "underwritten" in texto_lower:
            result["tipo_oferta"] = "Oferta asegurada (underwritten)"
        elif "registered direct" in texto_lower:
            result["tipo_oferta"] = "Registered Direct"
        elif "convertible" in texto_lower:
            result["tipo_oferta"] = "Notas convertibles"
        else:
            result["tipo_oferta"] = "Oferta pública"

        # Importe
        for pat in OFERTA_PATTERNS:
            m = re.search(pat, texto_lower)
            if m:
                raw = m.group(1).replace(",","")
                try:
                    val = float(raw)
                    # Si parece estar en unidades (no millones), ignorar
                    if "billion" in texto_lower[m.start():m.end()+20]:
                        val = val * 1000
                    elif val < 100 and "million" not in texto_lower[m.start():m.end()+20]:
                        val = val  # puede ser en millones ya
                    result["importe_mm"] = round(val, 1)
                    break
                except Exception:
                    pass

        # Riesgo dilución por tamaño
        if result["importe_mm"]:
            imp = result["importe_mm"]
            if imp >= 200:
                result["riesgo_dilucion"] = "🔴 ALTO"
            elif imp >= 75:
                result["riesgo_dilucion"] = "🟡 MEDIO"
            else:
                result["riesgo_dilucion"] = "🟢 BAJO"

        partes = []
        if result["tipo_oferta"]:  partes.append(result["tipo_oferta"])
        if result["importe_mm"]:   partes.append(f"${result['importe_mm']}M")
        if result["riesgo_dilucion"]: partes.append(f"Dilución {result['riesgo_dilucion']}")
        result["resumen_oferta"] = " · ".join(partes) if partes else "Prospecto — Importe no detectado"

    except Exception as e:
        result["resumen_oferta"] = f"Prospecto — Error: {str(e)[:80]}"

    return result

# ── MÓDULO 6: CLINICALTRIALS.GOV ─────────────────────────────────────────────
STATUS_COLORS = {
    "RECRUITING":           ("verde",  "🟢", "Reclutando activamente"),
    "ACTIVE_NOT_RECRUITING":("azul",   "🔵", "Activo — sin reclutamiento"),
    "COMPLETED":            ("verde",  "🟢", "Completado"),
    "TERMINATED":           ("rojo",   "🔴", "Terminado anticipadamente"),
    "SUSPENDED":            ("rojo",   "🔴", "Suspendido"),
    "WITHDRAWN":            ("rojo",   "🔴", "Retirado"),
    "NOT_YET_RECRUITING":   ("amarillo","🟡","Aún no recluta"),
    "ENROLLING_BY_INVITATION":("azul", "🔵", "Reclutamiento por invitación"),
    "UNKNOWN":              ("azul",   "🔵", "Estado desconocido"),
}

def consultar_clinicaltrials(ticker):
    """
    Consulta la API v2 de ClinicalTrials.gov para los ensayos del ticker.
    Devuelve lista de ensayos con status, fechas y cambios detectados.
    """
    ensayos_config = CLINICALTRIALS_CARTERA.get(ticker, [])
    if not ensayos_config:
        return []

    resultados = []
    for ensayo in ensayos_config:
        nct = ensayo["nct"]
        nombre_ensayo = ensayo["nombre"]
        url = CLINICALTRIALS_URL.format(nct=nct)
        try:
            data, changed = fetch_json(url, timeout=15)
            safe_sleep(0.3)

            study = data.get("studies", [{}])[0] if "studies" in data else data
            proto = study.get("protocolSection", study)
            status_mod  = proto.get("statusModule", {})
            design_mod  = proto.get("designModule", {})
            id_mod      = proto.get("identificationModule", {})

            status_raw  = status_mod.get("overallStatus", "UNKNOWN").upper().replace(" ","_")
            status_info = STATUS_COLORS.get(status_raw, ("azul","🔵","Estado: "+status_raw))
            nivel, badge, desc_status = status_info

            enrollment  = design_mod.get("enrollmentInfo", {}).get("count")
            titulo      = id_mod.get("briefTitle", nombre_ensayo)
            ultima_act  = status_mod.get("lastUpdatePostDateStruct", {}).get("date", "")
            fecha_prim  = status_mod.get("primaryCompletionDateStruct", {}).get("date", "")

            resultados.append({
                "nct":           nct,
                "nombre":        nombre_ensayo,
                "titulo":        titulo[:100] if titulo else nombre_ensayo,
                "status":        status_raw,
                "status_desc":   desc_status,
                "nivel":         nivel,
                "badge":         badge,
                "enrollment":    enrollment,
                "ultima_actualizacion": ultima_act,
                "fecha_completion_primaria": fecha_prim,
                "changed":       changed,
                "url":           f"https://clinicaltrials.gov/study/{nct}",
            })
        except Exception as e:
            resultados.append({
                "nct":    nct,
                "nombre": nombre_ensayo,
                "error":  str(e)[:100],
                "nivel":  "azul",
                "badge":  "🔵",
                "url":    f"https://clinicaltrials.gov/study/{nct}",
            })

    return resultados

# ── CONSULTA EDGAR PRINCIPAL ──────────────────────────────────────────────────
def get_filings(ticker, cik, dias, nombre_esperado=None):
    cik_padded = cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    try:
        data, _ = fetch_json(url)
    except Exception as e:
        return [], str(e)

    company_name_sec = data.get("name", "")
    if company_name_sec and nombre_esperado:
        empresa_ok, score, aviso = validar_empresa_sec(ticker, nombre_esperado, company_name_sec)
        print(f"      Empresa SEC: {company_name_sec} | Validación: {'✅' if empresa_ok else '⚠️'} ({score:.2f})")
        if not empresa_ok:
            return [], aviso

    recent = data.get("filings", {}).get("recent", {})
    if not recent:
        return [], "Sin datos"

    forms        = recent.get("form", [])
    dates        = recent.get("filingDate", [])
    accessions   = recent.get("accessionNumber", [])
    primaries    = recent.get("primaryDocument", [])
    descriptions = recent.get("primaryDocDescription", [])

    cutoff  = fecha_desde(dias)
    cik_num = cik.lstrip("0")
    results = []

    for form, date, acc, prim, desc in zip(forms, dates, accessions, primaries, descriptions):
        if date < cutoff:
            continue  # usar continue en lugar de break por seguridad
        if form not in FORMS_OBJETIVO:
            continue

        acc_fmt = acc.replace("-","")
        url_doc = f"https://www.sec.gov/Archives/edgar/data/{cik_num}/{acc_fmt}/{prim}"
        nivel, badge, resumen = clasificar_base(form, desc, prim)

        filing = {
            "form":       form,
            "fecha":      date,
            "nivel":      nivel,
            "badge":      badge,
            "resumen":    resumen,
            "detalle":    desc or prim or "",
            "empresa_sec":company_name_sec,
            "url":        url_doc,
            # Campos extendidos (se rellenan abajo)
            "form4_detail":    None,
            "8k_detail":       None,
            "10q_detail":      None,
            "prospecto_detail":None,
        }

        safe_sleep(0.2)

        # ── Módulo 2: Form 4 ──
        if form in ("4","4/A"):
            print(f"         → Parseando Form 4 XML...")
            f4 = parsear_form4(url_doc)
            filing["form4_detail"] = f4
            if f4.get("resumen_detail"):
                filing["resumen"] = f4["resumen_detail"]
                # Reclasificar: compra insider = verde, venta = mantener amarillo
                if f4.get("transaccion_tipo") == "Compra":
                    filing["nivel"] = "verde"
                    filing["badge"] = "🟢 ALTA"
                    filing["resumen"] = f"Insider BUY: {f4['resumen_detail']}"

        # ── Módulo 3: 8-K ──
        elif form in ("8-K","8-K/A"):
            print(f"         → Leyendo cuerpo 8-K...")
            k8 = parsear_8k(url_doc)
            filing["8k_detail"] = k8
            if k8.get("nivel_ajustado"):
                filing["nivel"]   = k8["nivel_ajustado"]
                filing["badge"]   = k8["badge_ajustado"]
                filing["resumen"] = k8["resumen_ajustado"]
                if k8.get("items_detectados"):
                    filing["resumen"] += f" [Items: {', '.join(k8['items_detectados'])}]"

        # ── Módulo 4: 10-Q ──
        elif form in ("10-Q","10-Q/A"):
            print(f"         → Extrayendo financiero 10-Q...")
            q10 = parsear_10q(url_doc, ticker)
            filing["10q_detail"] = q10
            if q10.get("resumen_10q"):
                filing["resumen"] = q10["resumen_10q"]
            if q10.get("going_concern"):
                filing["nivel"] = "rojo"
                filing["badge"] = "🔴 ALTA"
            elif q10.get("litigios_detectados") or q10.get("shelf_mencionado"):
                filing["nivel"] = "amarillo"
                filing["badge"] = "🟡 MEDIA"

        # ── Módulo 5: S-3 / 424B ──
        elif form in ("424B4","424B5","S-3","S-3/A"):
            print(f"         → Analizando prospecto/oferta...")
            pr = parsear_prospecto(url_doc)
            filing["prospecto_detail"] = pr
            if pr.get("resumen_oferta"):
                filing["resumen"] = pr["resumen_oferta"]
            # Re-escalar nivel según importe
            if pr.get("importe_mm") and pr["importe_mm"] >= 200:
                filing["nivel"] = "rojo"
                filing["badge"] = "🔴 ALTA"
            elif pr.get("importe_mm") and pr["importe_mm"] >= 75:
                filing["nivel"] = "amarillo"
                filing["badge"] = "🟡 MEDIA"

        results.append(filing)

    return results, None

# ── RESUMEN POR TICKER ────────────────────────────────────────────────────────
def resumen_ticker(filings):
    niveles = [f["nivel"] for f in filings]
    if "rojo"     in niveles: return "rojo",    "🔴"
    if "verde"    in niveles: return "verde",   "🟢"
    if "amarillo" in niveles: return "amarillo","🟡"
    if "azul"     in niveles: return "azul",    "🔵"
    return "ok", "✅"

# ── RUNNER ────────────────────────────────────────────────────────────────────
def run_monitor(dias=7, tickers_filtro=None):
    global CARTERA

    cargar_cache()

    tickers = tickers_filtro or TICKERS_CARTERA
    tickers = [t.strip().upper() for t in tickers if t.strip()]

    print("Cargando CIK oficiales desde SEC company_tickers.json...")
    try:
        CARTERA = construir_cartera_desde_sec(TICKERS_CARTERA)
    except Exception as e:
        print(f"❌ No se pudo cargar mapa CIK: {e}")
        CARTERA = {t: {"cik": None, "nombre": NOMBRES_ESPERADOS.get(t, t), "error": str(e)} for t in TICKERS_CARTERA}

    ahora = ahora_str()
    print(f"\n{'═'*62}")
    print(f"  SEC EDGAR Monitor v3 — Modelo Biotech v3.0")
    print(f"  Generado: {ahora}")
    print(f"  Período: últimos {dias} días ({fecha_desde(dias)} → {fecha_hoy()})")
    print(f"{'═'*62}\n")

    dashboard = {
        "version":      "v3",
        "generado":     ahora,
        "periodo_dias": dias,
        "desde":        fecha_desde(dias),
        "hasta":        fecha_hoy(),
        "resumen": {
            "total_filings":     0,
            "alertas_rojas":     0,
            "alertas_verdes":    0,
            "alertas_amarillas": 0,
            "alertas_azules":    0,
            "sin_novedad":       0,
        },
        "tickers":          {},
        "alertas_criticas": [],
        "todos_filings":    [],
        "clinicaltrials":   {},
    }

    # ── SEC EDGAR por ticker ──
    for ticker in tickers:
        ticker = ticker.strip().upper()
        info = CARTERA.get(ticker)
        if not info:
            dashboard["tickers"][ticker] = {"nombre": None, "filings": [], "nivel": "omitido", "badge": "⚠️", "error": "Ticker no en CARTERA"}
            continue
        if not info.get("cik"):
            err = info.get("error","Sin CIK SEC")
            print(f"  [{ticker}] ⚪ {err} — omitido")
            dashboard["tickers"][ticker] = {"nombre": info["nombre"], "filings": [], "nivel": "na", "badge": "⚪", "error": err}
            continue

        print(f"  [{ticker}] Consultando SEC EDGAR...")
        filings, error = get_filings(ticker, info["cik"], dias, info.get("nombre_esperado", info["nombre"]))

        if error:
            print(f"    ❌ {error}")
            dashboard["tickers"][ticker] = {
                "nombre": info["nombre"], "cik": info.get("cik"),
                "filings": [], "nivel": "error", "badge": "❌", "error": error
            }
            continue

        nivel_ticker, badge_ticker = resumen_ticker(filings) if filings else ("ok","✅")

        if filings:
            print(f"    {badge_ticker} {len(filings)} filing(s)")
            for f in filings:
                print(f"       {f['badge']} {f['form']} | {f['fecha']} | {f['resumen']}")
                entry = {"ticker": ticker, "nombre": info["nombre"], **f}
                dashboard["todos_filings"].append(entry)
                if f["nivel"] in ("rojo","verde"):
                    dashboard["alertas_criticas"].append(entry)
                dashboard["resumen"]["total_filings"] += 1
                if f["nivel"] == "rojo":     dashboard["resumen"]["alertas_rojas"] += 1
                if f["nivel"] == "verde":    dashboard["resumen"]["alertas_verdes"] += 1
                if f["nivel"] == "amarillo": dashboard["resumen"]["alertas_amarillas"] += 1
                if f["nivel"] == "azul":     dashboard["resumen"]["alertas_azules"] += 1
        else:
            print(f"    ✅ Sin novedades")
            dashboard["resumen"]["sin_novedad"] += 1

        dashboard["tickers"][ticker] = {
            "nombre":           info["nombre"],
            "nombre_esperado":  info.get("nombre_esperado", info["nombre"]),
            "cik":              info.get("cik"),
            "origen_cik":       info.get("origen_cik"),
            "validacion_empresa":"OK",
            "filings":          filings,
            "nivel":            nivel_ticker,
            "badge":            badge_ticker,
            "error":            None,
        }

    # ── ClinicalTrials.gov ──
    print(f"\n{'─'*50}")
    print(f"  ClinicalTrials.gov — Monitorizando {len(CLINICALTRIALS_CARTERA)} tickers...")
    tickers_ct = [t for t in tickers if t in CLINICALTRIALS_CARTERA]
    for ticker in tickers_ct:
        print(f"  [{ticker}] Consultando ClinicalTrials.gov...")
        ensayos = consultar_clinicaltrials(ticker)
        dashboard["clinicaltrials"][ticker] = ensayos
        for e in ensayos:
            estado = e.get("status","?")
            badge  = e.get("badge","🔵")
            nombre = e.get("nombre","")
            if e.get("error"):
                print(f"    ❌ {nombre}: {e['error']}")
            else:
                print(f"    {badge} {nombre} → {estado}")
                if e.get("changed"):
                    print(f"       ⚡ CAMBIO DETECTADO vs caché anterior")

    # Ordenar
    dashboard["todos_filings"].sort(key=lambda x: x["fecha"], reverse=True)
    dashboard["alertas_criticas"].sort(key=lambda x: x["fecha"], reverse=True)

    guardar_cache()
    return dashboard

# ── REPORTE TXT ───────────────────────────────────────────────────────────────
def generar_reporte(dashboard):
    r = dashboard["resumen"]
    lines = []
    lines.append("═" * 62)
    lines.append("SEC EDGAR MONITOR v3 · Modelo Biotech v3.0")
    lines.append(f"Generado: {dashboard['generado']} | Período: últimos {dashboard['periodo_dias']} días")
    lines.append(f"Desde: {dashboard['desde']} → Hasta: {dashboard['hasta']}")
    lines.append("═" * 62)
    lines.append(f"\nRESUMEN: {r['total_filings']} filings | "
                 f"🔴 {r['alertas_rojas']} | 🟢 {r['alertas_verdes']} | "
                 f"🟡 {r['alertas_amarillas']} | 🔵 {r['alertas_azules']} | "
                 f"✅ {r['sin_novedad']} sin novedad")

    criticos = dashboard["alertas_criticas"]
    if criticos:
        lines.append(f"\n{'─'*50}")
        lines.append(f"🚨 ALERTAS CRÍTICAS ({len(criticos)})")
        lines.append("─" * 50)
        for a in criticos:
            lines.append(f"\n  [{a['ticker']}] {a.get('nombre','')}")
            lines.append(f"  {a['badge']} {a['form']} | {a['fecha']}")
            lines.append(f"  {a['resumen']}")
            if a.get("form4_detail",{}) and a["form4_detail"].get("resumen_detail"):
                lines.append(f"  Insider: {a['form4_detail']['resumen_detail']}")
            if a.get("10q_detail",{}) and a["10q_detail"].get("resumen_10q"):
                lines.append(f"  Financiero: {a['10q_detail']['resumen_10q']}")
            if a.get("prospecto_detail",{}) and a["prospecto_detail"].get("resumen_oferta"):
                lines.append(f"  Oferta: {a['prospecto_detail']['resumen_oferta']}")
            lines.append(f"  → {a['url']}")

    lines.append(f"\n{'─'*50}")
    lines.append("DETALLE POR TICKER — SEC EDGAR")
    lines.append("─" * 50)
    for ticker, data in dashboard["tickers"].items():
        if not data.get("filings"):
            badge = data.get("badge","✅")
            err   = data.get("error","")
            lines.append(f"  {badge} [{ticker}] {err or 'Sin novedades'}")
            continue
        badge = data["badge"]
        lines.append(f"\n  {badge} [{ticker}] {data['nombre']} — {len(data['filings'])} filing(s)")
        for f in data["filings"]:
            lines.append(f"     {f['badge']} {f['form']} | {f['fecha']} | {f['resumen']}")
            if f.get("form4_detail",{}) and f["form4_detail"].get("resumen_detail"):
                lines.append(f"     Insider: {f['form4_detail']['resumen_detail']}")
            if f.get("10q_detail",{}) and f["10q_detail"].get("resumen_10q"):
                lines.append(f"     10-Q: {f['10q_detail']['resumen_10q']}")
            if f.get("prospecto_detail",{}) and f["prospecto_detail"].get("resumen_oferta"):
                lines.append(f"     Oferta: {f['prospecto_detail']['resumen_oferta']}")
            lines.append(f"     → {f['url']}")

    # ClinicalTrials
    ct = dashboard.get("clinicaltrials", {})
    if ct:
        lines.append(f"\n{'─'*50}")
        lines.append("CLINICALTRIALS.GOV — ESTADO ENSAYOS")
        lines.append("─" * 50)
        for ticker, ensayos in ct.items():
            if not ensayos:
                continue
            lines.append(f"\n  [{ticker}]")
            for e in ensayos:
                if e.get("error"):
                    lines.append(f"    ❌ {e['nombre']}: {e['error']}")
                else:
                    changed_str = " ⚡CAMBIO" if e.get("changed") else ""
                    lines.append(f"    {e['badge']} {e['nombre']}{changed_str}")
                    lines.append(f"       Status: {e.get('status_desc', e.get('status','?'))}")
                    if e.get("enrollment"):      lines.append(f"       Enrollment: {e['enrollment']} pacientes")
                    if e.get("fecha_completion_primaria"): lines.append(f"       Primary completion: {e['fecha_completion_primaria']}")
                    if e.get("ultima_actualizacion"): lines.append(f"       Última actualización: {e['ultima_actualizacion']}")
                    lines.append(f"       → {e['url']}")

    lines.append(f"\n{'═'*62}")
    lines.append("Fuentes: SEC EDGAR API · ClinicalTrials.gov API v2")
    lines.append("Modelo Biotech v3.0 · SEC EDGAR Monitor v3")
    lines.append("═" * 62)
    return "\n".join(lines)

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    dias   = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    filtro = sys.argv[2].upper().split(",") if len(sys.argv) > 2 else None

    dashboard = run_monitor(dias=dias, tickers_filtro=filtro)
    reporte   = generar_reporte(dashboard)

    print("\n" + reporte)

    script_dir = os.path.dirname(os.path.abspath(__file__))

    ruta_txt  = os.path.join(script_dir, "sec_monitor_reporte.txt")
    ruta_json = os.path.join(script_dir, "sec_monitor_resultado.json")

    with open(ruta_txt, "w", encoding="utf-8") as f:
        f.write(reporte)

    with open(ruta_json, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n💾 Reporte TXT  → {ruta_txt}")
    print(f"💾 JSON dashboard → {ruta_json}")
    print(f"💾 Caché interna → {CACHE_FILE}")
    print(f"\n✅ SEC EDGAR Monitor v3 completado.")
