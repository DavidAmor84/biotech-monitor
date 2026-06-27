"""
BIOTECH RADAR ENGINE v4.1
- Lee candidatos del radar_resultado.json existente (generado por el engine v3.2)
- Aplica penalizaciones de calidad de label (boxed warning, HFpEF, etc.)
- Calcula ratio upside/downside con precios objetivo del análisis manual
- Genera biotech_radar_resultado.json compatible con el tab Radar v4.0 del dashboard
- SIN llamadas a APIs externas en tiempo real → termina en <30 segundos
- Diseñado para correr en GitHub Actions sin timeouts

Uso: python biotech_radar_engine_v4.py
Input:  radar_resultado.json (generado por engine v3.2)
Output: biotech_radar_resultado.json
"""

import json, os, datetime

# ─── ARCHIVOS ─────────────────────────────────────────────────────────────────
INPUT_FILE  = "radar_resultado.json"
OUTPUT_FILE = "biotech_radar_resultado.json"

# ─── PENALIZACIONES DE CALIDAD DE LABEL ──────────────────────────────────────
# Reducen el score base cuando el análisis manual identifica gaps estructurales
# Actualizar cuando se haga análisis v3.2 completo de un ticker
LABEL_PENALTIES = {
    # Identificados en análisis 27 jun 2026
    "AKBA": {
        "penalizaciones": ["boxed_warning", "label_restricted", "dialysis_only", "ndd_ckd_door_closed"],
        "ajuste": -8.0,
        "razon": "Boxed warning FDA intrínseco (-2.5) · Label restringido a diálisis (-2.0) · Mercado solo diálisis (-1.5) · FDA cerró puerta NDD-CKD (-2.0)"
    },
    "TENX": {
        "penalizaciones": ["hfpef_graveyard", "no_partnership", "micro_cap"],
        "ajuste": -4.0,
        "razon": "HFpEF cementerio histórico Ph3 (-3.0) · Sin partnership activo (-0.5) · Micro-cap riesgo dilución (-0.5)"
    },
    "IMCR": {
        "penalizaciones": ["ultra_rare_ceiling"],
        "ajuste": -1.5,
        "razon": "Techo revenue por rareza extrema uveal melanoma (-1.5)"
    },
    "ABVX": {
        "penalizaciones": ["class_action", "hta_risk_eu"],
        "ajuste": -2.5,
        "razon": "4 class actions coordinadas (-1.5) · Riesgo HTA EU G-BA/NICE/HAS (-1.0)"
    },
    "ACRV": {
        "penalizaciones": ["micro_cap", "no_partnership", "ph2_early"],
        "ajuste": -2.0,
        "razon": "Micro-cap dilución probable (-1.0) · Sin partnership (-0.5) · Ph2 muy temprano (-0.5)"
    },
    "TARA": {
        "penalizaciones": ["micro_cap", "no_partnership"],
        "ajuste": -2.0,
        "razon": "Micro-cap runway incierto (-1.0) · Sin partnership (-0.5) · Sin catalizador definido (-0.5)"
    },
    "DYN": {
        "penalizaciones": ["insider_selling", "no_partnership"],
        "ajuste": -1.5,
        "razon": "CEO+CMO+CCO vendiendo simultáneamente (-1.0) · Sin partnership activo (-0.5)"
    },
    "VKTX": {
        "penalizaciones": ["no_partnership"],
        "ajuste": -1.0,
        "razon": "Único en sector obesidad sin deal Big Pharma (-1.0)"
    },
    "GPCR": {
        "penalizaciones": ["no_partnership", "ph3_not_started"],
        "ajuste": -1.0,
        "razon": "Sin partnership activo (-0.5) · Ph3 no iniciado aún (-0.5)"
    },
    "BEAM": {
        "penalizaciones": ["no_partnership"],
        "ajuste": -0.5,
        "razon": "Sin partnership activo (-0.5) · Runway ~18 meses ajustado"
    },
}

# ─── PRECIOS OBJETIVO (análisis manual v3.2) ──────────────────────────────────
# precio_exito: escenario aprobación/éxito
# precio_fracaso: floor de caja o escenario fracaso
PRICE_TARGETS = {
    "AKBA":  {"exito": 4.50,   "fracaso": 0.40,  "actual": 0.92},
    "FDMT":  {"exito": 35.00,  "fracaso": 8.00,  "actual": 14.00},
    "DNLI":  {"exito": 52.00,  "fracaso": 13.00, "actual": 23.31},
    "IMCR":  {"exito": 65.00,  "fracaso": 18.00, "actual": 28.61},
    "RIGL":  {"exito": 2.20,   "fracaso": 0.45,  "actual": 0.65},
    "TENX":  {"exito": 5.00,   "fracaso": 0.25,  "actual": 1.20},
    "VERA":  {"exito": 108.00, "fracaso": 18.00, "actual": 35.09},
    "INSM":  {"exito": 240.00, "fracaso": 80.00, "actual": 95.80},
    "ABVX":  {"exito": 170.00, "fracaso": 33.00, "actual": 99.15},
    "VKTX":  {"exito": 118.00, "fracaso": 15.00, "actual": 30.38},
    "GPCR":  {"exito": 130.00, "fracaso": 18.00, "actual": 44.51},
    "BEAM":  {"exito": 85.00,  "fracaso": 12.00, "actual": 34.14},
    "OCUL":  {"exito": 31.00,  "fracaso": 5.00,  "actual": 9.43},
    "DYN":   {"exito": 52.00,  "fracaso": 6.00,  "actual": 19.80},
    "DNLI":  {"exito": 52.00,  "fracaso": 13.00, "actual": 23.31},
    "ARGX":  {"exito": 1200.0, "fracaso": 600.0, "actual": 773.80},
    "VRTX":  {"exito": 615.00, "fracaso": 375.0, "actual": 451.63},
    "ALNY":  {"exito": 460.00, "fracaso": 248.0, "actual": 278.09},
    "SNDX":  {"exito": 48.00,  "fracaso": 12.00, "actual": 19.00},
    "CAI":   {"exito": 42.00,  "fracaso": 11.00, "actual": 18.47},
    "ACRV":  {"exito": 6.00,   "fracaso": 0.55,  "actual": 1.57},
    "TARA":  {"exito": 9.00,   "fracaso": 1.50,  "actual": 3.98},
    "SENS":  {"exito": 17.00,  "fracaso": 4.00,  "actual": 6.74},
}

# ─── FLAGS DE ALERTA ──────────────────────────────────────────────────────────
FLAG_DEFINITIONS = {
    "boxed_warning":       {"emoji": "⬛", "color": "#ff4444", "label": "Boxed Warning FDA"},
    "label_restricted":    {"emoji": "🔒", "color": "#ff6b6b", "label": "Label restringido"},
    "dialysis_only":       {"emoji": "💊", "color": "#ff6b6b", "label": "Solo pacientes diálisis"},
    "ndd_ckd_door_closed": {"emoji": "🚪", "color": "#ff9a5c", "label": "FDA cerró expansión NDD-CKD"},
    "hfpef_graveyard":     {"emoji": "💀", "color": "#ff4444", "label": "HFpEF — cementerio Ph3"},
    "no_partnership":      {"emoji": "🤝", "color": "#ffe566", "label": "Sin partnership activo"},
    "micro_cap":           {"emoji": "💧", "color": "#ffe566", "label": "Micro-cap — riesgo dilución"},
    "ultra_rare_ceiling":  {"emoji": "📈", "color": "#ffe566", "label": "Techo revenue por rareza extrema"},
    "class_action":        {"emoji": "⚖️",  "color": "#ff6b6b", "label": "Class actions coordinadas"},
    "hta_risk_eu":         {"emoji": "🇪🇺", "color": "#ff9a5c", "label": "Riesgo HTA Europa"},
    "insider_selling":     {"emoji": "🔴", "color": "#ff4444", "label": "Insiders vendiendo en mercado"},
    "ph3_not_started":     {"emoji": "🌱", "color": "#8899bb", "label": "Ph3 no iniciado aún"},
    "ph2_early":           {"emoji": "🌱", "color": "#8899bb", "label": "Fase temprana Ph2"},
    "ratio_insuficiente":  {"emoji": "📐", "color": "#ff9a5c", "label": "Ratio upside/downside <3x"},
    "score_gap":           {"emoji": "⚠️",  "color": "#ffe566", "label": "Discrepancia score Radar vs Modelo"},
}

MIN_RATIO = 3.0

def calc_ratio(actual, exito, fracaso):
    if not actual or not exito or not fracaso:
        return None
    upside   = exito - actual
    downside = actual - fracaso
    if downside <= 0:
        return 99.0
    return round(upside / downside, 2)

def procesar_candidato(empresa):
    """Toma un candidato del radar v3.2 y aplica ajustes v4."""
    ticker     = empresa.get("ticker", "").upper()
    score_base = float(empresa.get("score", 10.0))

    # Penalizaciones de label
    pen_data   = LABEL_PENALTIES.get(ticker, {})
    ajuste     = pen_data.get("ajuste", 0.0)
    razon_pen  = pen_data.get("razon", "")
    flags_pen  = pen_data.get("penalizaciones", [])
    score_v4   = round(max(0.0, score_base + ajuste), 1)

    # Veredicto v4
    if score_v4 >= 16:
        veredicto = "PRIORIDAD"
    elif score_v4 >= 14:
        veredicto = "ANALIZAR"
    elif score_v4 >= 11:
        veredicto = "WATCHLIST"
    else:
        veredicto = "DESCARTAR"

    # Ratio upside/downside
    pt = PRICE_TARGETS.get(ticker, {})
    actual  = pt.get("actual")
    exito   = pt.get("exito")
    fracaso = pt.get("fracaso")
    ratio   = calc_ratio(actual, exito, fracaso)

    # Flags
    flags = list(flags_pen)
    if ratio is not None and ratio < MIN_RATIO:
        flags.append("ratio_insuficiente")
    if ajuste < -4:
        flags.append("score_gap")

    # Razones legibles
    razones = []
    if razon_pen:
        razones.append(razon_pen)
    if ratio is not None:
        ok = "✅" if ratio >= MIN_RATIO else "❌ <3x"
        razones.append(f"Ratio upside/downside: {ratio:.1f}x {ok}")

    return {
        "ticker":        ticker,
        "empresa":       empresa.get("company_name", ticker),
        "area":          empresa.get("therapeutic_area", ""),
        "fase":          empresa.get("stage", ""),
        "activos":       empresa.get("n_active", 0),
        "score_base":    score_base,
        "score_v4":      score_v4,
        "veredicto":     veredicto,
        "flags":         list(dict.fromkeys(flags)),
        "razones_ajuste": razones,
        "ratio_ud":      ratio,
        "pos_ajustada":  round(float(empresa.get("base_pos", 0.10)) * 100, 1),
        # Campos del v3.2 para compatibilidad
        "market_cap":    empresa.get("market_cap"),
        "runway_display": empresa.get("runway_display"),
        "dilution_risk": empresa.get("dilution_risk"),
        "next_catalyst_date": empresa.get("next_catalyst_date"),
        "hard_fails":    empresa.get("hard_fails", []),
        "reasons":       empresa.get("reasons", []),
        "price":         actual,
    }

def main():
    ts = datetime.datetime.utcnow().strftime("%d %b %Y %H:%M UTC")
    print(f"[Radar v4.1] Iniciando · {ts}")

    # Cargar radar v3.2
    if not os.path.exists(INPUT_FILE):
        print(f"[ERROR] No se encuentra {INPUT_FILE}")
        print("Ejecuta primero el engine v3.2 para generar radar_resultado.json")
        return

    with open(INPUT_FILE, encoding="utf-8") as f:
        radar_v32 = json.load(f)

    candidatas = radar_v32.get("candidatas", [])
    print(f"[OK] {len(candidatas)} candidatos cargados de {INPUT_FILE}")

    # Procesar con ajustes v4
    resultados = [procesar_candidato(e) for e in candidatas]
    resultados.sort(key=lambda x: x["score_v4"], reverse=True)

    # Resumen
    conteo = {"PRIORIDAD": 0, "ANALIZAR": 0, "WATCHLIST": 0, "DESCARTAR": 0}
    for r in resultados:
        conteo[r["veredicto"]] = conteo.get(r["veredicto"], 0) + 1

    # Estadísticas de gaps detectados
    con_gap = [r for r in resultados if "score_gap" in r["flags"]]

    payload = {
        "version":          "4.1",
        "generado":         ts,
        "total_analizados": len(resultados),
        "resumen":          conteo,
        "gaps_detectados":  len(con_gap),
        "flag_definitions": FLAG_DEFINITIONS,
        "candidatos":       resultados,
        "fuente_v32":       radar_v32.get("generado", ""),
        "nota": "Scores ajustados con penalizaciones de calidad de label (análisis manual v3.2). "
                "Ratio upside/downside calculado con precios objetivo del análisis más reciente."
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"[OK] {OUTPUT_FILE} generado · {len(resultados)} candidatos")
    print(f"     PRIORIDAD: {conteo['PRIORIDAD']} · ANALIZAR: {conteo['ANALIZAR']} · "
          f"WATCHLIST: {conteo['WATCHLIST']} · DESCARTAR: {conteo['DESCARTAR']}")
    print(f"     Gaps detectados (score ajustado >4pts): {len(con_gap)}")

    # Preview de los gaps más relevantes
    if con_gap:
        print("\n[GAPS IDENTIFICADOS]")
        for r in con_gap:
            diff = r["score_v4"] - r["score_base"]
            print(f"  {r['ticker']:6} {r['score_base']:.1f} → {r['score_v4']:.1f} ({diff:+.1f})  {r['veredicto']}")

if __name__ == "__main__":
    main()
