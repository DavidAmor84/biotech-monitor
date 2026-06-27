
"""
BIOTECH RADAR ENGINE v4.0
Mejoras sobre v3.2:
  1. Penalizaciones de calidad de label (boxed warning, label restringido, HFpEF, etc.)
  2. Filtro ratio upside/downside >= 3x con floor de caja
  3. Score pre-análisis v3.2 diferenciado del score de cribado crudo
  4. Flags de alerta exportados al JSON para el dashboard

Autor: Modelo Biotech v3.2 | Junio 2026
"""

import json, os, time, csv, difflib, datetime, math
import urllib.request, urllib.error

# ─── CONFIGURACIÓN ────────────────────────────────────────────────────────────
SEC_TICKERS_URL   = "https://www.sec.gov/files/company_tickers.json"
FINNHUB_TOKEN     = os.environ.get("FINNHUB_TOKEN", "")   # secret en GitHub Actions
AV_KEY            = os.environ.get("AV_KEY", "")
OUTPUT_FILE       = "biotech_radar_resultado.json"
SEC_FINANCIALS_CSV= "sec_financials.csv"          # CSV estático en repo
MAX_RESULTS       = 150                           # candidatos en JSON final

# ─── UNIVERSO DE INDICACIONES CON TASAS PoS BIO/IQVIA 2024 ──────────────────
# (fase → indicación → PoS base %)
POS_BASE = {
    "ph1":  {"oncology": 0.07, "rare_disease": 0.12, "cns": 0.07, "autoimmune": 0.08,
             "metabolic": 0.09, "cardiovascular": 0.09, "ophthalmic": 0.10, "other": 0.08},
    "ph2":  {"oncology": 0.07, "rare_disease": 0.20, "cns": 0.10, "autoimmune": 0.12,
             "metabolic": 0.12, "cardiovascular": 0.14, "ophthalmic": 0.15, "other": 0.12},
    "ph3":  {"oncology": 0.55, "rare_disease": 0.65, "cns": 0.50, "autoimmune": 0.62,
             "metabolic": 0.60, "cardiovascular": 0.60, "ophthalmic": 0.65, "other": 0.58},
    "nda":  {"oncology": 0.85, "rare_disease": 0.88, "cns": 0.82, "autoimmune": 0.86,
             "metabolic": 0.85, "cardiovascular": 0.85, "ophthalmic": 0.87, "other": 0.84},
    "approved": {"all": 1.00},
}

# ─── MODIFICADORES PoS ────────────────────────────────────────────────────────
POS_MODS = {
    # Positivos
    "breakthrough_therapy":     +0.10,
    "fast_track":               +0.05,
    "orphan_drug":              +0.07,
    "rmat":                     +0.08,
    "spa_fda":                  +0.15,
    "nejm_publication":         +0.10,
    "ph3_superiority":          +0.08,
    "ph3_data_positive":        +0.05,
    # Negativos
    "boxed_warning":            -0.15,   # NUEVO v4
    "label_restricted":         -0.12,   # NUEVO v4 — label limitado vs solicitud original
    "hfpef_indication":         -0.18,   # NUEVO v4 — cementerio histórico Ph3
    "cns_hard_target":          -0.15,   # diana maldita CNS
    "crl_history":              -0.15,   # CRL previo del sponsor
    "endpoint_change":          -0.12,   # cambio de endpoint durante ensayo
    "no_peer_review":           -0.08,   # solo press release
    "ph3_recently_started":     -0.10,   # Ph3 iniciado <6 meses
    "competitive_approved":     -0.05,   # competidor aprobado en misma línea
    "micro_cap_dilution":       -0.10,   # <$50M cap, dilución probable
}

# ─── PENALIZACIONES DE CALIDAD DE LABEL (NUEVO v4) ───────────────────────────
# Reducen el score de cribado antes de presentar candidatos
LABEL_QUALITY_PENALTIES = {
    "boxed_warning":        -2.5,   # boxed warning FDA intrínseco al mecanismo
    "label_restricted":     -2.0,   # FDA negó expansión; label < solicitud original
    "dialysis_only":        -1.5,   # mercado limitado a pacientes en diálisis
    "hfpef_graveyard":      -3.0,   # indicación con múltiples fracasos Ph3 históricos
    "no_partnership":       -1.0,   # sin partner activo (penalización suave en cribado)
    "ultra_rare_ceiling":   -1.5,   # techo de revenue limitado por rareza extrema
    "ndd_ckd_door_closed":  -2.0,   # FDA cerró puerta a expansión NDD-CKD
}

# ─── FILTRO RATIO UPSIDE/DOWNSIDE (NUEVO v4) ─────────────────────────────────
MIN_UPSIDE_DOWNSIDE_RATIO = 3.0   # hard filter: si ratio < 3x → flag "ratio_insuficiente"

def calc_ratio_upside_downside(precio_actual, precio_exito, precio_fracaso):
    """Calcula ratio upside/downside. Retorna None si no hay datos."""
    if not precio_actual or not precio_exito or not precio_fracaso:
        return None
    upside   = precio_exito   - precio_actual
    downside = precio_actual  - precio_fracaso
    if downside <= 0:
        return 99.0   # downside teórico 0 (precio < caja)
    return round(upside / downside, 2)

# ─── CATÁLOGO DE FLAGS DE ALERTA (NUEVO v4) ──────────────────────────────────
# Flags exportados al JSON → dashboard los muestra en tarjeta del candidato
FLAG_DEFINITIONS = {
    "boxed_warning":            {"emoji": "⬛", "color": "#ff4444", "label": "Boxed Warning FDA"},
    "label_restricted":         {"emoji": "🔒", "color": "#ff6b6b", "label": "Label restringido vs solicitud"},
    "ratio_insuficiente":       {"emoji": "📐", "color": "#ff9a5c", "label": "Ratio upside/downside <3x"},
    "hfpef_graveyard":          {"emoji": "💀", "color": "#ff4444", "label": "Indicación HFpEF — cementerio Ph3"},
    "no_partnership":           {"emoji": "🤝", "color": "#ffe566", "label": "Sin partnership activo"},
    "micro_cap_dilution":       {"emoji": "💧", "color": "#ffe566", "label": "Micro-cap — riesgo dilución"},
    "insider_selling":          {"emoji": "🔴", "color": "#ff4444", "label": "Insiders vendiendo en mercado abierto"},
    "crl_history":              {"emoji": "📋", "color": "#ff9a5c", "label": "CRL previo del sponsor"},
    "ultra_rare_ceiling":       {"emoji": "📈", "color": "#ffe566", "label": "Techo revenue por rareza extrema"},
    "phase_early":              {"emoji": "🌱", "color": "#8899bb", "label": "Fase temprana — Ph1/Ph2"},
    "datos_pendientes":         {"emoji": "⏳", "color": "#00bcd4", "label": "Datos próximos — catalizador binario"},
    "score_gap_radar_modelo":   {"emoji": "⚠️",  "color": "#ffe566", "label": "Discrepancia score Radar vs Modelo completo"},
}

# ─── FUNCIÓN PRINCIPAL DE SCORING v4 ─────────────────────────────────────────
def calcular_score_v4(empresa: dict) -> dict:
    """
    Calcula score de cribado v4 aplicando:
      - Score base (0–20) por activos clínicos, fase, área
      - Modificadores PoS calibrados BIO/IQVIA
      - Penalizaciones de calidad de label (NUEVO)
      - Filtro ratio upside/downside (NUEVO)
      - Generación de flags de alerta (NUEVO)

    empresa: dict con campos del CSV SEC (o de la API)
    Retorna: dict con score_v4, pos_ajustada, ratio, flags, veredicto
    """
    score_base = empresa.get("score_base", 10.0)   # score crudo del cribado anterior
    area       = empresa.get("area", "other").lower()
    fase       = empresa.get("fase", "ph2").lower()
    mods_activos = empresa.get("modificadores", [])   # lista de strings

    # ── 1. PoS calibrada ──────────────────────────────────────────────────────
    pos_base = POS_BASE.get(fase, POS_BASE["ph2"]).get(area, 0.10)
    pos_mod  = sum(POS_MODS.get(m, 0) for m in mods_activos)
    pos_final = max(0.03, min(0.97, pos_base + pos_mod))

    # ── 2. Penalizaciones de calidad de label (NUEVO v4) ─────────────────────
    penalizaciones_label = empresa.get("penalizaciones_label", [])
    penalty_total = sum(LABEL_QUALITY_PENALTIES.get(p, 0) for p in penalizaciones_label)
    score_v4 = round(max(0.0, score_base + penalty_total), 1)

    # ── 3. Flags de alerta ────────────────────────────────────────────────────
    flags = []
    for pen in penalizaciones_label:
        if pen in FLAG_DEFINITIONS:
            flags.append(pen)

    precio_actual  = empresa.get("precio_actual", None)
    precio_exito   = empresa.get("precio_exito", None)
    precio_fracaso = empresa.get("precio_fracaso", None)
    caja_por_acc   = empresa.get("caja_por_accion", None)

    # Usar floor de caja como precio fracaso si no se define explícitamente
    if not precio_fracaso and caja_por_acc:
        precio_fracaso = caja_por_acc * 0.7   # descuento al 70% de caja (dilución esperada)

    ratio = calc_ratio_upside_downside(precio_actual, precio_exito, precio_fracaso)

    if ratio is not None and ratio < MIN_UPSIDE_DOWNSIDE_RATIO:
        flags.append("ratio_insuficiente")

    # Flags automáticos por modificadores
    if "micro_cap_dilution" in mods_activos:
        flags.append("micro_cap_dilution")
    if "crl_history" in mods_activos:
        flags.append("crl_history")
    if fase in ("ph1", "ph2"):
        flags.append("phase_early")

    # Discrepancia score radar vs modelo completo (si diferencia > 4 puntos)
    if score_v4 < score_base - 4:
        flags.append("score_gap_radar_modelo")

    # ── 4. Veredicto v4 ───────────────────────────────────────────────────────
    if score_v4 >= 16:
        veredicto = "PRIORIDAD"
    elif score_v4 >= 14:
        veredicto = "ANALIZAR"
    elif score_v4 >= 11:
        veredicto = "WATCHLIST"
    else:
        veredicto = "DESCARTAR"

    # ── 5. Razón legible del score (NUEVO v4) ─────────────────────────────────
    razones = []
    for pen in penalizaciones_label:
        d = LABEL_QUALITY_PENALTIES.get(pen, 0)
        if d != 0:
            desc = FLAG_DEFINITIONS.get(pen, {}).get("label", pen)
            razones.append(f"{desc}: {d:+.1f}pts")

    if ratio is not None:
        razones.append(f"Ratio upside/downside: {ratio:.1f}x {'✅' if ratio >= 3 else '❌ <3x'}")

    return {
        "score_v4":         score_v4,
        "score_base":       score_base,
        "pos_ajustada":     round(pos_final * 100, 1),
        "ratio_ud":         ratio,
        "flags":            list(dict.fromkeys(flags)),   # deduplica preservando orden
        "veredicto":        veredicto,
        "razones_ajuste":   razones,
    }


# ─── REGLAS DE PENALIZACIÓN AUTOMÁTICA POR TICKER (NUEVO v4) ─────────────────
# Mapeo ticker → penalizaciones de label conocidas
# Se actualiza cuando el modelo completo identifica un gap que el cribado ignora
TICKER_LABEL_PENALTIES = {
    # Identificados en análisis 27 jun 2026
    "AKBA": ["boxed_warning", "label_restricted", "dialysis_only", "ndd_ckd_door_closed"],
    "TENX": ["hfpef_graveyard", "no_partnership", "micro_cap_dilution"],
    "IMCR": ["ultra_rare_ceiling"],
    "RIGL": [],   # comercial sólido, sin penalizaciones de label
    "FDMT": [],   # pipeline limpio, penaliza solo si IOI en Ph3
    "DNLI": [],   # ya en cartera, aprobado
    # Cartera existente
    "ABVX": ["label_restricted"],   # riesgo litigio + HTA
    "ACRV": ["micro_cap_dilution"],
    "TARA": ["micro_cap_dilution"],
    "BEAM": [],
    "GPCR": ["no_partnership"],
    "VKTX": ["no_partnership"],
    "DYN":  ["no_partnership"],
}

# ─── PRECIO_EXITO / PRECIO_FRACASO POR TICKER (NUEVO v4) ─────────────────────
# Estimaciones para filtro ratio — se actualizan tras análisis completo
TICKER_PRICE_TARGETS = {
    "AKBA": {"exito": 4.50,  "fracaso": 0.40},
    "TENX": {"exito": 5.00,  "fracaso": 0.25},
    "IMCR": {"exito": 65.00, "fracaso": 18.00},
    "RIGL": {"exito": 2.20,  "fracaso": 0.45},
    "FDMT": {"exito": 35.00, "fracaso": 8.00},
    "DNLI": {"exito": 52.00, "fracaso": 13.00},
    "VERA": {"exito": 108.00,"fracaso": 18.00},
    "INSM": {"exito": 240.00,"fracaso": 80.00},
    "ABVX": {"exito": 170.00,"fracaso": 33.00},
    "VKTX": {"exito": 118.00,"fracaso": 15.00},
    "GPCR": {"exito": 130.00,"fracaso": 18.00},
    "BEAM": {"exito": 85.00, "fracaso": 12.00},
    "OCUL": {"exito": 31.00, "fracaso": 5.00},
    "DYN":  {"exito": 52.00, "fracaso": 6.00},
}


# ─── CARGA DEL CSV FINANCIERO ESTÁTICO ───────────────────────────────────────
def cargar_financieros_csv(path=SEC_FINANCIALS_CSV):
    """Lee sec_financials.csv y retorna dict {ticker: {campo: valor}}"""
    resultado = {}
    if not os.path.exists(path):
        print(f"[WARN] {path} no encontrado — usando solo datos de API")
        return resultado
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ticker = row.get("ticker", "").upper().strip()
            if ticker:
                resultado[ticker] = {k: v for k, v in row.items()}
    print(f"[CSV] {len(resultado)} tickers cargados de {path}")
    return resultado


# ─── FETCH PRECIO ACTUAL ──────────────────────────────────────────────────────
def fetch_precio_finnhub(ticker, token=FINNHUB_TOKEN):
    if not token:
        return None
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={token}"
        req = urllib.request.Request(url, headers={"User-Agent": "biotech-radar/4.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
            precio = data.get("c", 0)
            return float(precio) if precio and precio > 0 else None
    except Exception as e:
        print(f"[WARN] Finnhub {ticker}: {e}")
        return None


# ─── MOTOR PRINCIPAL ──────────────────────────────────────────────────────────
def run_radar_v4(candidatos_raw: list, financieros_csv: dict) -> list:
    """
    candidatos_raw: lista de dicts con campos mínimos:
        ticker, empresa, area, fase, score_base, modificadores, activos
    financieros_csv: dict {ticker: row_csv}

    Retorna: lista de candidatos enriquecidos con score_v4, flags, ratio
    """
    resultados = []
    for emp in candidatos_raw:
        ticker = emp.get("ticker", "").upper()

        # Enriquecer con penalizaciones conocidas
        emp.setdefault("penalizaciones_label",
                       TICKER_LABEL_PENALTIES.get(ticker, []))

        # Precio actual (Finnhub o CSV)
        if not emp.get("precio_actual"):
            precio_csv = financieros_csv.get(ticker, {}).get("precio_actual")
            emp["precio_actual"] = float(precio_csv) if precio_csv else fetch_precio_finnhub(ticker)

        # Precios objetivo desde tabla maestra
        if ticker in TICKER_PRICE_TARGETS and not emp.get("precio_exito"):
            emp["precio_exito"]   = TICKER_PRICE_TARGETS[ticker]["exito"]
            emp["precio_fracaso"] = TICKER_PRICE_TARGETS[ticker]["fracaso"]

        # Caja por acción desde CSV
        if not emp.get("caja_por_accion"):
            cash_str = financieros_csv.get(ticker, {}).get("cash_per_share")
            emp["caja_por_accion"] = float(cash_str) if cash_str else None

        # Calcular score v4
        resultado_score = calcular_score_v4(emp)
        emp.update(resultado_score)
        resultados.append(emp)

        time.sleep(0.15)   # rate limit Finnhub

    # Ordenar por score_v4 desc
    resultados.sort(key=lambda x: x.get("score_v4", 0), reverse=True)
    return resultados[:MAX_RESULTS]


# ─── EXPORTAR JSON PARA DASHBOARD ────────────────────────────────────────────
def exportar_json(candidatos: list, output=OUTPUT_FILE):
    """Genera JSON compatible con el dashboard index.html"""
    ts = datetime.datetime.utcnow().strftime("%d %b %Y %H:%M UTC")

    # Resumen por veredicto
    conteo = {"PRIORIDAD": 0, "ANALIZAR": 0, "WATCHLIST": 0, "DESCARTAR": 0}
    for c in candidatos:
        v = c.get("veredicto", "DESCARTAR")
        conteo[v] = conteo.get(v, 0) + 1

    # Estadísticas de flags
    flag_counts = {}
    for c in candidatos:
        for f in c.get("flags", []):
            flag_counts[f] = flag_counts.get(f, 0) + 1

    payload = {
        "version":          "4.0",
        "generado":         ts,
        "total_analizados": len(candidatos),
        "resumen":          conteo,
        "flag_stats":       flag_counts,
        "flag_definitions": FLAG_DEFINITIONS,
        "candidatos":       candidatos,
        "mejoras_v4": [
            "Penalizaciones de calidad de label (boxed_warning, label_restricted, HFpEF, etc.)",
            "Filtro ratio upside/downside ≥3x con floor de caja",
            "Score pre-análisis v3.2 diferenciado del score crudo",
            "Flags de alerta exportados al dashboard",
            "Razones legibles del ajuste de score por candidato",
        ]
    }

    with open(output, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[OK] Exportado {output} ({len(candidatos)} candidatos, {ts})")
    return payload


# ─── DEMO / TEST CON TICKERS DEL ANÁLISIS 27 JUN 2026 ────────────────────────
if __name__ == "__main__":
    print("=== BIOTECH RADAR ENGINE v4.0 ===")

    # Simulación de candidatos tal como vendrían del pipeline de SEC financials
    candidatos_test = [
        {
            "ticker": "AKBA", "empresa": "Akebia Therapeutics",
            "area": "metabolic", "fase": "approved",
            "score_base": 18.5,   # score crudo del radar anterior
            "modificadores": ["boxed_warning", "label_restricted", "competitive_approved"],
            "activos": 5,
            "precio_actual": 0.92,
        },
        {
            "ticker": "FDMT", "empresa": "4D Molecular Therapeutics",
            "area": "ophthalmic", "fase": "ph3",
            "score_base": 18.5,
            "modificadores": ["rmat", "ph3_data_positive", "ph3_recently_started"],
            "activos": 8,
            "precio_actual": 14.00,
        },
        {
            "ticker": "DNLI", "empresa": "Denali Therapeutics",
            "area": "rare_disease", "fase": "approved",
            "score_base": 18.0,
            "modificadores": ["nejm_publication", "breakthrough_therapy"],
            "activos": 6,
            "precio_actual": 23.31,
        },
        {
            "ticker": "IMCR", "empresa": "Immunocore Holdings",
            "area": "oncology", "fase": "approved",
            "score_base": 18.0,
            "modificadores": ["nejm_publication", "ph3_superiority"],
            "activos": 9,
            "precio_actual": 28.61,
        },
        {
            "ticker": "RIGL", "empresa": "Rigel Pharmaceuticals",
            "area": "oncology", "fase": "approved",
            "score_base": 18.0,
            "modificadores": [],
            "activos": 9,
            "precio_actual": 0.65,
        },
        {
            "ticker": "TENX", "empresa": "Tenax Therapeutics",
            "area": "cardiovascular", "fase": "ph3",
            "score_base": 18.0,
            "modificadores": ["hfpef_indication", "no_partnership", "micro_cap_dilution"],
            "activos": 3,
            "precio_actual": 1.20,
        },
        # Candidatos adicionales con perfil limpio para comparación
        {
            "ticker": "VERA", "empresa": "Vera Therapeutics",
            "area": "autoimmune", "fase": "nda",
            "score_base": 17.0,
            "modificadores": ["breakthrough_therapy", "fast_track", "nejm_publication", "spa_fda"],
            "activos": 2,
            "precio_actual": 35.09,
        },
        {
            "ticker": "INSM", "empresa": "Insmed",
            "area": "rare_disease", "fase": "approved",
            "score_base": 17.5,
            "modificadores": ["nejm_publication"],
            "activos": 4,
            "precio_actual": 95.80,
        },
    ]

    financieros = cargar_financieros_csv()
    candidatos_scored = run_radar_v4(candidatos_test, financieros)
    payload = exportar_json(candidatos_scored)

    # Imprimir resumen en consola
    print(f"\n{'TICKER':<8} {'SCORE_BASE':>10} {'SCORE_v4':>9} {'VEREDICTO':<12} {'RATIO':>7}  FLAGS")
    print("─" * 80)
    for c in candidatos_scored:
        ratio_str = f"{c['ratio_ud']:.1f}x" if c.get("ratio_ud") else "  N/A"
        flags_str = " ".join(
            FLAG_DEFINITIONS.get(f, {}).get("emoji", "?") for f in c.get("flags", [])[:5]
        )
        gap = c['score_v4'] - c['score_base']
        gap_str = f"({gap:+.1f})" if gap != 0 else ""
        print(f"{c['ticker']:<8} {c['score_base']:>10.1f} {c['score_v4']:>7.1f}{gap_str:<7} "
              f"{c['veredicto']:<12} {ratio_str:>7}  {flags_str}")

    print(f"\nResumen: {payload['resumen']}")
    print(f"Flags más frecuentes: {sorted(payload['flag_stats'].items(), key=lambda x: -x[1])[:5]}")
