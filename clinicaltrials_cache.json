#!/usr/bin/env python3
"""
ClinicalTrials Monitor v9.1 — Modelo Biotech

Mejoras v9.1:
  - Valida cada NCT por sponsor, fármaco/intervención e indicación.
  - Marca como error de validación los NCT que no corresponden a la empresa.
  - Mantiene caché para detectar cambios reales entre ejecuciones.
  - Genera:
      clinicaltrials_resultado.json
      clinicaltrials_reporte.txt
      clinicaltrials_cache.json
"""

import json
import datetime
import os
import urllib.request
import urllib.parse
import time

# ──────────────────────────────────────────────────────────────────────────────
# CARTERA / ENSAYOS A MONITORIZAR
# IMPORTANTE:
# Si un NCT es dudoso, el programa lo detectará por sponsor/fármaco/indicación.
# ──────────────────────────────────────────────────────────────────────────────

CLINICALTRIALS_CARTERA = {
    "DYN": [
        {
            "nct": "NCT05524883",
            "nombre": "DELIVER — z-rostudirsen / DYNE-251 — DMD exon 51",
            "sponsor_keywords": ["dyne therapeutics"],
            "drug_keywords": ["dyne-251", "z-rostudirsen"],
            "condition_keywords": ["duchenne", "dmd"],
        },
        {
            "nct": "NCT05481879",
            "nombre": "ACHIEVE — z-basivarsen / DYNE-101 — DM1",
            "sponsor_keywords": ["dyne therapeutics"],
            "drug_keywords": ["dyne-101", "z-basivarsen"],
            "condition_keywords": ["myotonic dystrophy", "dm1"],
        },
        {
            "nct": "NCT07486934",
            "nombre": "HARMONIA — z-basivarsen — DM1 confirmatorio",
            "sponsor_keywords": ["dyne therapeutics"],
            "drug_keywords": ["dyne-101", "z-basivarsen", "zeleciment basivarsen"],
            "condition_keywords": ["myotonic dystrophy", "dm1"],
        },
    ],

    "OCUL": [
        {
            "nct": "NCT06223958",
            "nombre": "SOL-1 — AXPAXLI / OTX-TKI — wet AMD",
            "sponsor_keywords": ["ocular therapeutix"],
            "drug_keywords": ["otx-tki", "axpaxli", "axitinib implant"],
            "condition_keywords": ["neovascular", "age-related macular degeneration", "amd"],
        },
        {
            "nct": "NCT06495918",
            "nombre": "SOL-R — AXPAXLI / OTX-TKI — wet AMD",
            "sponsor_keywords": ["ocular therapeutix"],
            "drug_keywords": ["otx-tki", "axpaxli", "axitinib implant"],
            "condition_keywords": ["neovascular", "age-related macular degeneration", "amd"],
        },
    ],

    "TARA": [
        {
            # Este NCT se mantiene para que la validación detecte si es incorrecto.
            "nct": "NCT05015946",
            "nombre": "ADVANCED-2 — TARA-002 — NMIBC",
            "sponsor_keywords": ["protara"],
            "drug_keywords": ["tara-002"],
            "condition_keywords": ["nmibc", "non-muscle invasive bladder cancer", "bladder cancer"],
        },
    ],

    "ABVX": [
        {
            "nct": "NCT05507203",
            "nombre": "ABTECT-1 — obefazimod / ABX464 — UC",
            "sponsor_keywords": ["abivax"],
            "drug_keywords": ["obefazimod", "abx464", "abx-464"],
            "condition_keywords": ["ulcerative colitis"],
        },
        {
            "nct": "NCT05507216",
            "nombre": "ABTECT-2 — obefazimod / ABX464 — UC",
            "sponsor_keywords": ["abivax"],
            "drug_keywords": ["obefazimod", "abx464", "abx-464"],
            "condition_keywords": ["ulcerative colitis"],
        },
    ],

    "VERA": [
        {
            "nct": "NCT04716231",
            "nombre": "ORIGIN 3 — atacicept — IgAN",
            "sponsor_keywords": ["vera therapeutics"],
            "drug_keywords": ["atacicept"],
            "condition_keywords": ["iga nephropathy", "igan", "berger"],
        },
    ],

    "SNDX": [
        {
            "nct": "NCT04065399",
            "nombre": "AUGMENT-101 — revumenib — KMT2Ar/NPM1m leukemia",
            "sponsor_keywords": ["syndax"],
            "drug_keywords": ["revumenib", "sndx-5613"],
            "condition_keywords": ["acute myeloid leukemia", "acute lymphoblastic leukemia", "leukemia", "kmt2a", "npm1"],
        },
        {
            "nct": "NCT07211958",
            "nombre": "REVEAL — revumenib — NPM1m AML frontline",
            "sponsor_keywords": ["syndax"],
            "drug_keywords": ["revumenib"],
            "condition_keywords": ["acute myeloid leukemia", "aml", "npm1"],
        },
    ],

    "VKTX": [
        {
            # Estos NCT se validan; si no son Viking/VK2735/obesidad, quedarán marcados como ❌.
            "nct": "NCT05948826",
            "nombre": "VENTURE — VK2735 SC — obesidad",
            "sponsor_keywords": ["viking therapeutics"],
            "drug_keywords": ["vk2735", "vk-2735"],
            "condition_keywords": ["obesity", "overweight", "weight"],
        },
        {
            "nct": "NCT06119360",
            "nombre": "VANQUISH — VK2735 oral — obesidad",
            "sponsor_keywords": ["viking therapeutics"],
            "drug_keywords": ["vk2735", "vk-2735"],
            "condition_keywords": ["obesity", "overweight", "weight"],
        },
    ],

    "BEAM": [
        {
            "nct": "NCT05456880",
            "nombre": "BEACON — BEAM-101 / risto-cel — SCD",
            "sponsor_keywords": ["beam therapeutics"],
            "drug_keywords": ["beam-101", "risto-cel"],
            "condition_keywords": ["sickle cell"],
        },
        {
            "nct": "NCT06389877",
            "nombre": "BEAM-302 — AATD",
            "sponsor_keywords": ["beam therapeutics"],
            "drug_keywords": ["beam-302"],
            "condition_keywords": ["alpha-1", "alpha 1", "aatd", "antitrypsin"],
        },
    ],

    "ACRV": [
        {
            "nct": "NCT05548296",
            "nombre": "ACR-368 + OncoSignature — ovario/endometrio/urotelial",
            "sponsor_keywords": ["acrivon"],
            "drug_keywords": ["acr-368", "oncosignature"],
            "condition_keywords": ["endometrial", "ovarian", "urothelial", "cancer"],
        },
    ],

    "GPCR": [
        {
            "nct": "NCT06693843",
            "nombre": "GLOW — aleniglipron / GSBR-1290 — obesidad oral",
            "sponsor_keywords": ["structure therapeutics"],
            "drug_keywords": ["aleniglipron", "gsbr-1290", "gsbr1290"],
            "condition_keywords": ["obesity", "overweight", "weight"],
        },
    ],

    "INSM": [
        {
            "nct": "NCT04594369",
            "nombre": "ASPEN — brensocatib — bronchiectasis",
            "sponsor_keywords": ["insmed"],
            "drug_keywords": ["brensocatib"],
            "condition_keywords": ["bronchiectasis"],
        },
    ],
}

API_BASE = "https://clinicaltrials.gov/api/v2/studies/{nct}"

CACHE_FILE = "clinicaltrials_cache.json"
RESULTADO_FILE = "clinicaltrials_resultado.json"
REPORTE_FILE = "clinicaltrials_reporte.txt"

HEADERS = {
    "User-Agent": "Modelo Biotech v9.1 David Amor / ClinicalTrials Monitor",
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

def clean_text(x):
    return str(x or "").lower().replace("—", " ").replace("-", " ")

def contiene_alguna(texto, keywords):
    if not keywords:
        return True
    texto = clean_text(texto)
    return any(clean_text(k) in texto for k in keywords if k)

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
        ("validacion_ok", "Validación"),
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

            elif key == "validacion_ok" and new is False:
                nivel, badge = "rojo", "❌"

            cambios.append({
                "tipo": key,
                "nivel": nivel,
                "badge": badge,
                "mensaje": f"{label}: {old if old is not None else '—'} → {new if new is not None else '—'}"
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
# VALIDACIÓN DE ENSAYO
# ──────────────────────────────────────────────────────────────────────────────

def validar_ensayo(datos, config):
    sponsor_text = " ".join([
        datos.get("sponsor") or "",
        " ".join(datos.get("collaborators") or []),
    ])

    drug_text = " ".join([
        datos.get("titulo") or "",
        datos.get("titulo_oficial") or "",
        " ".join(datos.get("interventions") or []),
    ])

    condition_text = " ".join([
        datos.get("titulo") or "",
        datos.get("titulo_oficial") or "",
        " ".join(datos.get("conditions") or []),
    ])

    errores = []
    detalles = {
        "sponsor_text": sponsor_text,
        "drug_text": drug_text[:600],
        "condition_text": condition_text[:600],
    }

    sponsor_keywords = config.get("sponsor_keywords", [])
    drug_keywords = config.get("drug_keywords", [])
    condition_keywords = config.get("condition_keywords", [])

    if sponsor_keywords and not contiene_alguna(sponsor_text, sponsor_keywords):
        errores.append("Sponsor no coincide")

    if drug_keywords and not contiene_alguna(drug_text, drug_keywords):
        errores.append("Fármaco/intervención no coincide")

    if condition_keywords and not contiene_alguna(condition_text, condition_keywords):
        errores.append("Indicación no coincide")

    return {
        "ok": len(errores) == 0,
        "errores": errores,
        "detalles": detalles,
        "sponsor_keywords": sponsor_keywords,
        "drug_keywords": drug_keywords,
        "condition_keywords": condition_keywords,
    }

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
    sponsor_mod = protocol.get("sponsorCollaboratorsModule", {})

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

    lead_sponsor = sponsor_mod.get("leadSponsor", {}) or {}
    sponsor_name = lead_sponsor.get("name")

    collaborators = sponsor_mod.get("collaborators", []) or []
    collaborator_names = [c.get("name") for c in collaborators if c.get("name")]

    result = {
        "nct": nct,
        "nombre_usuario": nombre_usuario,
        "titulo": ident.get("briefTitle"),
        "titulo_oficial": ident.get("officialTitle"),
        "sponsor": sponsor_name,
        "collaborators": collaborator_names,
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

def elegir_nivel_ticker(niveles):
    if not niveles:
        return "ok"
    prioridad = {"rojo": 4, "verde": 3, "amarillo": 2, "azul": 1, "ok": 0}
    return max(niveles, key=lambda n: prioridad.get(n, 0))

def run_monitor():
    cache = cargar_cache()
    nuevo_cache = {}

    dashboard = {
        "version": "v9.1",
        "generado": ahora_str(),
        "fecha": hoy_iso(),
        "resumen": {
            "total_ensayos": 0,
            "validacion_ok": 0,
            "validacion_error": 0,
            "alertas_rojas": 0,
            "alertas_verdes": 0,
            "alertas_amarillas": 0,
            "alertas_azules": 0,
            "errores": 0,
        },
        "empresas": {},
        "alertas": [],
        "errores_validacion": [],
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
                validacion = validar_ensayo(actual, ensayo)
                actual["validacion"] = validacion
                actual["validacion_ok"] = validacion["ok"]

                previo = cache.get(nct)
                cambios = comparar_con_cache(nct, actual, previo)

                if not validacion["ok"]:
                    nivel_final = "rojo"
                    badge_final = "❌"
                    actual["status_desc"] = "NCT no validado contra empresa/fármaco/indicación"
                    cambios.append({
                        "tipo": "validacion",
                        "nivel": "rojo",
                        "badge": "❌",
                        "mensaje": "; ".join(validacion["errores"])
                    })
                else:
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
                    "sponsor": actual.get("sponsor"),
                    "validacion_ok": actual.get("validacion_ok"),
                }

                dashboard["empresas"][ticker]["ensayos"].append(actual)
                dashboard["resumen"]["total_ensayos"] += 1
                niveles_ticker.append(nivel_final)

                if validacion["ok"]:
                    dashboard["resumen"]["validacion_ok"] += 1
                else:
                    dashboard["resumen"]["validacion_error"] += 1
                    dashboard["errores_validacion"].append({
                        "ticker": ticker,
                        "nct": nct,
                        "nombre": nombre,
                        "errores": validacion["errores"],
                        "sponsor_detectado": actual.get("sponsor"),
                        "titulo_detectado": actual.get("titulo"),
                        "conditions": actual.get("conditions"),
                        "interventions": actual.get("interventions"),
                        "url": actual.get("url"),
                    })

                if nivel_final == "rojo":
                    dashboard["resumen"]["alertas_rojas"] += 1
                elif nivel_final == "verde":
                    dashboard["resumen"]["alertas_verdes"] += 1
                elif nivel_final == "amarillo":
                    dashboard["resumen"]["alertas_amarillas"] += 1
                elif nivel_final == "azul":
                    dashboard["resumen"]["alertas_azules"] += 1

                # Alertas: cambios reales, errores de validación o eventos relevantes.
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
                        "validacion_ok": actual.get("validacion_ok"),
                        "errores_validacion": validacion.get("errores", []),
                        "cambios": cambios,
                        "url": actual.get("url"),
                    })

            except Exception as e:
                dashboard["resumen"]["errores"] += 1
                dashboard["empresas"][ticker]["ensayos"].append({
                    "nct": nct,
                    "nombre_usuario": nombre,
                    "nivel": "rojo",
                    "badge": "❌",
                    "error": str(e)[:300],
                    "url": f"https://clinicaltrials.gov/study/{nct}",
                })
                niveles_ticker.append("rojo")
                print(f"  ERROR {nct}: {e}")

        dashboard["empresas"][ticker]["nivel"] = elegir_nivel_ticker(niveles_ticker)
        dashboard["empresas"][ticker]["badge"] = badge_nivel(dashboard["empresas"][ticker]["nivel"])

    guardar_cache(nuevo_cache)
    return dashboard

# ──────────────────────────────────────────────────────────────────────────────
# REPORTE
# ──────────────────────────────────────────────────────────────────────────────

def generar_reporte(dashboard):
    r = dashboard["resumen"]
    lines = []
    lines.append("=" * 76)
    lines.append("CLINICALTRIALS MONITOR v9.1 · Modelo Biotech")
    lines.append(f"Generado: {dashboard['generado']}")
    lines.append("=" * 76)
    lines.append(
        f"RESUMEN: {r['total_ensayos']} ensayos | "
        f"Validación OK: {r['validacion_ok']} | "
        f"Errores validación: {r['validacion_error']} | "
        f"🔴 {r['alertas_rojas']} | 🟢 {r['alertas_verdes']} | "
        f"🟡 {r['alertas_amarillas']} | 🔵 {r['alertas_azules']} | "
        f"Errores API: {r['errores']}"
    )

    if dashboard.get("errores_validacion"):
        lines.append("\n" + "-" * 76)
        lines.append("❌ ERRORES DE VALIDACIÓN — POSIBLES NCT INCORRECTOS")
        lines.append("-" * 76)
        for e in dashboard["errores_validacion"]:
            lines.append(f"\n[{e['ticker']}] {e['nombre']}")
            lines.append(f"NCT: {e['nct']}")
            lines.append(f"Sponsor detectado: {e.get('sponsor_detectado')}")
            lines.append(f"Título detectado: {e.get('titulo_detectado')}")
            lines.append(f"Errores: {', '.join(e['errores'])}")
            if e.get("conditions"):
                lines.append(f"Conditions: {', '.join(e['conditions'][:5])}")
            if e.get("interventions"):
                lines.append(f"Interventions: {', '.join(e['interventions'][:5])}")
            lines.append(f"→ {e['url']}")

    if dashboard["alertas"]:
        lines.append("\n" + "-" * 76)
        lines.append("ALERTAS / CAMBIOS")
        lines.append("-" * 76)
        for a in dashboard["alertas"]:
            lines.append(f"\n[{a['ticker']}] {a['badge']} {a['nombre']}")
            lines.append(f"NCT: {a['nct']} | Status: {a['status']}")
            if a.get("primary_completion_date"):
                lines.append(f"Primary completion: {a['primary_completion_date']}")
            if not a.get("validacion_ok", True):
                lines.append(f"Validación: ❌ {', '.join(a.get('errores_validacion', []))}")
            for c in a.get("cambios", []):
                lines.append(f"  {c['badge']} {c['mensaje']}")
            lines.append(f"→ {a['url']}")

    lines.append("\n" + "-" * 76)
    lines.append("DETALLE POR EMPRESA")
    lines.append("-" * 76)

    for ticker, data in dashboard["empresas"].items():
        lines.append(f"\n{data['badge']} [{ticker}]")
        for e in data["ensayos"]:
            if e.get("error"):
                lines.append(f"  ❌ {e['nombre_usuario']} ({e['nct']}): {e['error']}")
                continue

            valid = "OK" if e.get("validacion_ok") else "ERROR"
            lines.append(f"  {e['badge']} {e['nombre_usuario']} | Validación: {valid}")
            lines.append(f"     NCT: {e['nct']} | Status: {e['status_desc']}")
            if e.get("sponsor"):
                lines.append(f"     Sponsor: {e['sponsor']}")
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
            if not e.get("validacion_ok"):
                lines.append(f"     ❌ Validación: {', '.join(e['validacion']['errores'])}")
            lines.append(f"     → {e['url']}")

    lines.append("\n" + "=" * 76)
    lines.append("Fuente: ClinicalTrials.gov API v2")
    lines.append("=" * 76)
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
    print(f"\nJSON  → {RESULTADO_FILE}")
    print(f"TXT   → {REPORTE_FILE}")
    print(f"CACHE → {CACHE_FILE}")
