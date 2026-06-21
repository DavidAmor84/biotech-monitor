#!/usr/bin/env python3
"""
ClinicalTrials Monitor v9.0 — Modelo Biotech

Genera:
  - clinicaltrials_resultado.json
  - clinicaltrials_reporte.txt
  - clinicaltrials_cache.json

Uso:
  python clinicaltrials_monitor.py
"""

import json
import datetime
import os
import urllib.request
import urllib.parse
import urllib.error
import time

# ──────────────────────────────────────────────────────────────────────────────
# CARTERA / ENSAYOS A MONITORIZAR
# ──────────────────────────────────────────────────────────────────────────────

CLINICALTRIALS_CARTERA = {
    "DYN": [
        {"nct": "NCT05524883", "nombre": "DELIVER — z-rostudirsen / DYNE-251 — DMD exon 51"},
        {"nct": "NCT05481879", "nombre": "ACHIEVE — z-basivarsen / DYNE-101 — DM1"},
        {"nct": "NCT07486934", "nombre": "HARMONIA — z-basivarsen — DM1 confirmatorio"},
    ],
    "OCUL": [
        {"nct": "NCT06223958", "nombre": "SOL-1 — AXPAXLI — wet AMD"},
        {"nct": "NCT06495918", "nombre": "SOL-R — AXPAXLI — wet AMD"},
    ],
    "TARA": [
        {"nct": "NCT05015946", "nombre": "ADVANCED-2 — TARA-002 — NMIBC"},
    ],
    "ABVX": [
        {"nct": "NCT05507203", "nombre": "ABTECT-1 — obefazimod — UC"},
        {"nct": "NCT05507216", "nombre": "ABTECT-2 — obefazimod — UC"},
    ],
    "VERA": [
        {"nct": "NCT04716231", "nombre": "ORIGIN 3 — atacicept — IgAN"},
    ],
    "SNDX": [
        {"nct": "NCT04065399", "nombre": "AUGMENT-101 — revumenib — KMT2Ar/NPM1m leukemia"},
        {"nct": "NCT07211958", "nombre": "REVEAL — revumenib — NPM1m AML frontline"},
    ],
    "VKTX": [
        {"nct": "NCT05948826", "nombre": "VENTURE — VK2735 SC — obesidad"},
        {"nct": "NCT06119360", "nombre": "VANQUISH — VK2735 oral — obesidad"},
    ],
    "BEAM": [
        {"nct": "NCT05456880", "nombre": "BEACON — BEAM-101 / risto-cel — SCD"},
        {"nct": "NCT06389877", "nombre": "BEAM-302 — AATD"},
    ],
    "ACRV": [
        {"nct": "NCT05548296", "nombre": "ACR-368 + OncoSignature — ovario/endometrio/urotelial"},
    ],
    "GPCR": [
        {"nct": "NCT06693843", "nombre": "GLOW — aleniglipron / GSBR-1290 — obesidad oral"},
    ],
    "INSM": [
        {"nct": "NCT04594369", "nombre": "ASPEN — brensocatib — bronchiectasis"},
    ],
}

API_BASE = "https://clinicaltrials.gov/api/v2/studies/{nct}"

CACHE_FILE = "clinicaltrials_cache.json"
RESULTADO_FILE = "clinicaltrials_resultado.json"
REPORTE_FILE = "clinicaltrials_reporte.txt"

HEADERS = {
    "User-Agent": "Modelo Biotech v9 David Amor / ClinicalTrials Monitor",
    "Accept": "application/json",
}

# ──────────────────────────────────────────────────────────────────────────────
# UTILIDADES
# ──────────────────────────────────────────────────────────────────────────────

def ahora_str():
    return datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

def hoy_iso():
    return datetime.datetime.now().strftime("%Y-%m-%d")

def cargar_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def guardar_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def fetch_json(url, timeout=25):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))

def get_nested(d, path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
        if cur is None:
            return default
    return cur

def normalizar_status(status):
    if not status:
        return "UNKNOWN"
    return str(status).upper().replace(" ", "_")

# ──────────────────────────────────────────────────────────────────────────────
# CLASIFICACIÓN
# ──────────────────────────────────────────────────────────────────────────────

def clasificar_status(status):
    status = normalizar_status(status)

    if status in ("TERMINATED", "SUSPENDED", "WITHDRAWN"):
        return "rojo", "🔴", "Ensayo detenido/suspendido/retirado"

    if status in ("COMPLETED",):
        return "verde", "🟢", "Ensayo completado"

    if status in ("RECRUITING",):
        return "azul", "🔵", "Reclutando"

    if status in ("ACTIVE_NOT_RECRUITING",):
        return "azul", "🔵", "Activo, sin reclutamiento"

    if status in ("NOT_YET_RECRUITING",):
        return "amarillo", "🟡", "Aún no recluta"

    if status in ("ENROLLING_BY_INVITATION",):
        return "azul", "🔵", "Reclutamiento por invitación"

    return "azul", "🔵", f"Estado: {status}"

def comparar_con_cache(nct, actual, previo):
    cambios = []

    if not previo:
        cambios.append({
            "tipo": "nuevo",
            "nivel": "azul",
            "badge": "🔵",
            "mensaje": "Primer registro en caché"
        })
        return cambios

    campos = [
        ("status", "Estado"),
        ("primary_completion_date", "Primary completion"),
        ("study_completion_date", "Study completion"),
        ("last_update_posted", "Última actualización"),
        ("enrollment", "Enrollment"),
    ]

    for key, label in campos:
        old = previo.get(key)
        new = actual.get(key)
        if old != new:
            nivel = "azul"
            badge = "🔵"

            if key == "status":
                if normalizar_status(new) in ("TERMINATED", "SUSPENDED", "WITHDRAWN"):
                    nivel, badge = "rojo", "🔴"
                elif normalizar_status(new) == "COMPLETED":
                    nivel, badge = "verde", "🟢"
                else:
                    nivel, badge = "amarillo", "🟡"

            elif key in ("primary_completion_date", "study_completion_date"):
                nivel, badge = "amarillo", "🟡"

            cambios.append({
                "tipo": key,
                "nivel": nivel,
                "badge": badge,
                "mensaje": f"{label}: {old or '—'} → {new or '—'}"
            })

    return cambios

def nivel_ensayo(nivel_base, cambios):
    prioridad = {"rojo": 4, "verde": 3, "amarillo": 2, "azul": 1, "ok": 0}
    niveles = [nivel_base] + [c.get("nivel", "azul") for c in cambios]
    return max(niveles, key=lambda n: prioridad.get(n, 0))

def badge_nivel(nivel):
    return {
        "rojo": "🔴",
        "verde": "🟢",
        "amarillo": "🟡",
        "azul": "🔵",
        "ok": "✅",
    }.get(nivel, "🔵")

# ──────────────────────────────────────────────────────────────────────────────
# PARSEO CLINICALTRIALS.GOV API v2
# ──────────────────────────────────────────────────────────────────────────────

def consultar_ensayo(nct, nombre_usuario):
    url = API_BASE.format(nct=urllib.parse.quote(nct))
    data = fetch_json(url)

    protocol = data.get("protocolSection", {})
    ident = protocol.get("identificationModule", {})
    status_mod = protocol.get("statusModule", {})
    design = protocol.get("designModule", {})
    arms = protocol.get("armsInterventionsModule", {})

    status = normalizar_status(status_mod.get("overallStatus", "UNKNOWN"))
    nivel_base, badge_base, status_desc = clasificar_status(status)

    enrollment_info = design.get("enrollmentInfo", {})
    enrollment = enrollment_info.get("count")

    phases = design.get("phases") or []
    if isinstance(phases, list):
        phase = ", ".join(phases)
    else:
        phase = str(phases) if phases else None

    conditions = protocol.get("conditionsModule", {}).get("conditions", [])
    interventions = arms.get("interventions", [])

    intervention_names = []
    for i in interventions:
        name = i.get("name")
        if name:
            intervention_names.append(name)

    result = {
        "nct": nct,
        "nombre_usuario": nombre_usuario,
        "titulo": ident.get("briefTitle"),
        "titulo_oficial": ident.get("officialTitle"),
        "status": status,
        "status_desc": status_desc,
        "nivel_base": nivel_base,
        "badge_base": badge_base,
        "phase": phase,
        "enrollment": enrollment,
        "primary_completion_date": get_nested(status_mod, ["primaryCompletionDateStruct", "date"]),
        "primary_completion_type": get_nested(status_mod, ["primaryCompletionDateStruct", "type"]),
        "study_completion_date": get_nested(status_mod, ["completionDateStruct", "date"]),
        "study_completion_type": get_nested(status_mod, ["completionDateStruct", "type"]),
        "start_date": get_nested(status_mod, ["startDateStruct", "date"]),
        "last_update_posted": get_nested(status_mod, ["lastUpdatePostDateStruct", "date"]),
        "conditions": conditions,
        "interventions": intervention_names,
        "url": f"https://clinicaltrials.gov/study/{nct}",
    }

    return result

# ──────────────────────────────────────────────────────────────────────────────
# RUNNER
# ──────────────────────────────────────────────────────────────────────────────

def run_monitor():
    cache = cargar_cache()
    nuevo_cache = {}

    dashboard = {
        "version": "v9.0",
        "generado": ahora_str(),
        "fecha": hoy_iso(),
        "resumen": {
            "total_ensayos": 0,
            "alertas_rojas": 0,
            "alertas_verdes": 0,
            "alertas_amarillas": 0,
            "alertas_azules": 0,
            "errores": 0,
        },
        "empresas": {},
        "alertas": [],
    }

    for ticker, ensayos in CLINICALTRIALS_CARTERA.items():
        print(f"[{ticker}] Consultando {len(ensayos)} ensayo(s)...")
        dashboard["empresas"][ticker] = {
            "ensayos": [],
            "nivel": "ok",
            "badge": "✅",
        }

        niveles_ticker = []

        for ensayo in ensayos:
            nct = ensayo["nct"]
            nombre = ensayo["nombre"]
            time.sleep(0.25)

            try:
                actual = consultar_ensayo(nct, nombre)
                previo = cache.get(nct)
                cambios = comparar_con_cache(nct, actual, previo)

                nivel_final = nivel_ensayo(actual["nivel_base"], cambios)
                badge_final = badge_nivel(nivel_final)

                actual["cambios"] = cambios
                actual["nivel"] = nivel_final
                actual["badge"] = badge_final
                actual["error"] = None

                nuevo_cache[nct] = {
                    "status": actual.get("status"),
                    "primary_completion_date": actual.get("primary_completion_date"),
                    "study_completion_date": actual.get("study_completion_date"),
                    "last_update_posted": actual.get("last_update_posted"),
                    "enrollment": actual.get("enrollment"),
                    "titulo": actual.get("titulo"),
                    "ticker": ticker,
                    "nombre_usuario": nombre,
                }

                dashboard["empresas"][ticker]["ensayos"].append(actual)
                dashboard["resumen"]["total_ensayos"] += 1
                niveles_ticker.append(nivel_final)

                if nivel_final == "rojo":
                    dashboard["resumen"]["alertas_rojas"] += 1
                elif nivel_final == "verde":
                    dashboard["resumen"]["alertas_verdes"] += 1
                elif nivel_final == "amarillo":
                    dashboard["resumen"]["alertas_amarillas"] += 1
                elif nivel_final == "azul":
                    dashboard["resumen"]["alertas_azules"] += 1

                # Solo guardamos alertas si hay cambio real o evento importante.
                if cambios or nivel_final in ("rojo", "verde"):
                    dashboard["alertas"].append({
                        "ticker": ticker,
                        "nct": nct,
                        "nombre": nombre,
                        "nivel": nivel_final,
                        "badge": badge_final,
                        "status": actual.get("status"),
                        "primary_completion_date": actual.get("primary_completion_date"),
                        "mensaje": actual.get("status_desc"),
                        "cambios": cambios,
                        "url": actual.get("url"),
                    })

            except Exception as e:
                dashboard["resumen"]["errores"] += 1
                dashboard["empresas"][ticker]["ensayos"].append({
                    "nct": nct,
                    "nombre_usuario": nombre,
                    "nivel": "azul",
                    "badge": "🔵",
                    "error": str(e)[:200],
                    "url": f"https://clinicaltrials.gov/study/{nct}",
                })
                print(f"  ERROR {nct}: {e}")

        dashboard["empresas"][ticker]["nivel"] = elegir_nivel_ticker(niveles_ticker)
        dashboard["empresas"][ticker]["badge"] = badge_nivel(dashboard["empresas"][ticker]["nivel"])

    guardar_cache(nuevo_cache)
    return dashboard

def elegir_nivel_ticker(niveles):
    if not niveles:
        return "ok"
    prioridad = {"rojo": 4, "verde": 3, "amarillo": 2, "azul": 1, "ok": 0}
    return max(niveles, key=lambda n: prioridad.get(n, 0))

# ──────────────────────────────────────────────────────────────────────────────
# REPORTE
# ──────────────────────────────────────────────────────────────────────────────

def generar_reporte(dashboard):
    r = dashboard["resumen"]
    lines = []
    lines.append("=" * 70)
    lines.append("CLINICALTRIALS MONITOR v9.0 · Modelo Biotech")
    lines.append(f"Generado: {dashboard['generado']}")
    lines.append("=" * 70)
    lines.append(
        f"RESUMEN: {r['total_ensayos']} ensayos | "
        f"🔴 {r['alertas_rojas']} | 🟢 {r['alertas_verdes']} | "
        f"🟡 {r['alertas_amarillas']} | 🔵 {r['alertas_azules']} | "
        f"Errores: {r['errores']}"
    )

    if dashboard["alertas"]:
        lines.append("\n" + "-" * 70)
        lines.append("ALERTAS / CAMBIOS")
        lines.append("-" * 70)
        for a in dashboard["alertas"]:
            lines.append(f"\n[{a['ticker']}] {a['badge']} {a['nombre']}")
            lines.append(f"NCT: {a['nct']} | Status: {a['status']}")
            if a.get("primary_completion_date"):
                lines.append(f"Primary completion: {a['primary_completion_date']}")
            for c in a.get("cambios", []):
                lines.append(f"  {c['badge']} {c['mensaje']}")
            lines.append(f"→ {a['url']}")

    lines.append("\n" + "-" * 70)
    lines.append("DETALLE POR EMPRESA")
    lines.append("-" * 70)

    for ticker, data in dashboard["empresas"].items():
        lines.append(f"\n{data['badge']} [{ticker}]")
        for e in data["ensayos"]:
            if e.get("error"):
                lines.append(f"  ❌ {e['nombre_usuario']} ({e['nct']}): {e['error']}")
                continue

            lines.append(f"  {e['badge']} {e['nombre_usuario']}")
            lines.append(f"     NCT: {e['nct']} | Status: {e['status_desc']}")
            if e.get("phase"):
                lines.append(f"     Phase: {e['phase']}")
            if e.get("enrollment"):
                lines.append(f"     Enrollment: {e['enrollment']}")
            if e.get("primary_completion_date"):
                t = e.get("primary_completion_type") or ""
                lines.append(f"     Primary completion: {e['primary_completion_date']} {t}")
            if e.get("study_completion_date"):
                t = e.get("study_completion_type") or ""
                lines.append(f"     Study completion: {e['study_completion_date']} {t}")
            if e.get("last_update_posted"):
                lines.append(f"     Last update posted: {e['last_update_posted']}")
            lines.append(f"     → {e['url']}")

    lines.append("\n" + "=" * 70)
    lines.append("Fuente: ClinicalTrials.gov API v2")
    lines.append("=" * 70)
    return "\n".join(lines)

# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    dashboard = run_monitor()
    reporte = generar_reporte(dashboard)

    with open(RESULTADO_FILE, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, ensure_ascii=False, indent=2)

    with open(REPORTE_FILE, "w", encoding="utf-8") as f:
        f.write(reporte)

    print(reporte)
    print(f"\nJSON → {RESULTADO_FILE}")
    print(f"TXT  → {REPORTE_FILE}")
    print(f"CACHE → {CACHE_FILE}")

