#!/usr/bin/env python3
"""
ClinicalTrials Monitor v9.3 — Modelo Biotech

Funciones:
- Consulta ClinicalTrials.gov API v2.
- Valida cada NCT por sponsor, fármaco e indicación.
- Clasifica relevancia del ensayo: alta / media / baja.
- Añade catalizador, ventana, prioridad, estrellas y tipo.
- Mantiene caché para detectar cambios.
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


# =============================================================================
# CONFIGURACIÓN DE CARTERA / ENSAYOS
# =============================================================================

CLINICALTRIALS_CARTERA = {
    "DYN": [
        {
            "nct": "NCT05524883",
            "nombre": "DELIVER Ph1/2 registracional — z-rostudirsen — DMD exon 51 · BLA en revisión FDA",
            "sponsor_keywords": ["dyne therapeutics"],
            "drug_keywords": ["dyne-251", "z-rostudirsen"],
            "condition_keywords": ["duchenne", "dmd"],
            "prioridad": "alta",
            "tipo": "registracional",
            "catalizador": "BLA / posible aprobación acelerada",
            "ventana": "2026-2027",
            "monitorizar": True,
            "peso_importancia": 10,
        },
        {
            "nct": "NCT05481879",
            "nombre": "ACHIEVE Ph1/2 registracional — z-basivarsen — DM1 · Accel. Approval Q1 2027",
            "sponsor_keywords": ["dyne therapeutics"],
            "drug_keywords": ["dyne-101", "z-basivarsen"],
            "condition_keywords": ["myotonic dystrophy", "dm1"],
            "prioridad": "alta",
            "tipo": "registracional",
            "catalizador": "posible aprobación acelerada",
            "ventana": "2027",
            "monitorizar": True,
            "peso_importancia": 10,
        },
        {
            "nct": "NCT07486934",
            "nombre": "HARMONIA Ph3 — z-basivarsen — DM1 confirmatorio · primary 2028",
            "sponsor_keywords": ["dyne therapeutics"],
            "drug_keywords": ["dyne-101", "z-basivarsen", "zeleciment basivarsen"],
            "condition_keywords": ["myotonic dystrophy", "dm1"],
            "prioridad": "alta",
            "tipo": "pivotal",
            "catalizador": "confirmatorio Phase 3",
            "ventana": "2028",
            "monitorizar": True,
            "peso_importancia": 9,
        },
    ],

    "OCUL": [
        {
            "nct": "NCT06223958",
            "nombre": "SOL-1 Ph3 superioridad — AXPAXLI — wet AMD · NDA inminente",
            "sponsor_keywords": ["ocular therapeutix"],
            "drug_keywords": ["otx-tki", "axpaxli", "axitinib implant"],
            "condition_keywords": ["neovascular", "age-related macular degeneration", "amd"],
            "prioridad": "alta",
            "tipo": "pivotal",
            "catalizador": "NDA / datos SOL-1",
            "ventana": "2026",
            "monitorizar": True,
            "peso_importancia": 10,
        },
        {
            "nct": "NCT06495918",
            "nombre": "SOL-R Ph3 no inferioridad — AXPAXLI — wet AMD · datos Q1 2027",
            "sponsor_keywords": ["ocular therapeutix"],
            "drug_keywords": ["otx-tki", "axpaxli", "axitinib implant"],
            "condition_keywords": ["neovascular", "age-related macular degeneration", "amd"],
            "prioridad": "alta",
            "tipo": "pivotal",
            "catalizador": "datos SOL-R",
            "ventana": "2027",
            "monitorizar": True,
            "peso_importancia": 9,
        },
    ],

    "TARA": [
        {
            "nct": "NCT05951179",
            "nombre": "ADVANCED-2 Ph2 — TARA-002 — NMIBC BCG-naïve/unresponsive CIS",
            "sponsor_keywords": ["protara"],
            "drug_keywords": ["tara-002"],
            "condition_keywords": ["nmibc", "non-muscle invasive bladder cancer", "bladder cancer", "carcinoma in situ"],
            "prioridad": "alta",
            "tipo": "phase2_registracional",
            "catalizador": "datos ADVANCED-2",
            "ventana": "2026-2027",
            "monitorizar": True,
            "peso_importancia": 9,
        },
    ],

    "ABVX": [
        {
            "nct": "NCT05507203",
            "nombre": "ABTECT-1 Ph3 inducción — obefazimod — UC",
            "sponsor_keywords": ["abivax"],
            "drug_keywords": ["obefazimod", "abx464", "abx-464"],
            "condition_keywords": ["ulcerative colitis"],
            "prioridad": "alta",
            "tipo": "pivotal",
            "catalizador": "datos Phase 3 / paquete NDA",
            "ventana": "2026",
            "monitorizar": True,
            "peso_importancia": 9,
        },
        {
            "nct": "NCT05507216",
            "nombre": "ABTECT-2 Ph3 inducción AT-failure — obefazimod — UC",
            "sponsor_keywords": ["abivax"],
            "drug_keywords": ["obefazimod", "abx464", "abx-464"],
            "condition_keywords": ["ulcerative colitis"],
            "prioridad": "alta",
            "tipo": "pivotal",
            "catalizador": "datos Phase 3 / paquete NDA",
            "ventana": "2026",
            "monitorizar": True,
            "peso_importancia": 9,
        },
        {
            "nct": "NCT05535946",
            "nombre": "ABTECT mantenimiento 44sem — obefazimod (ABX464-107) — UC",
            "sponsor_keywords": ["abivax"],
            "drug_keywords": ["obefazimod", "abx464", "abx-464"],
            "condition_keywords": ["ulcerative colitis"],
            "prioridad": "alta",
            "tipo": "pivotal_mantenimiento",
            "catalizador": "datos mantenimiento / NDA",
            "ventana": "2026",
            "monitorizar": True,
            "peso_importancia": 10,
        },
    ],

    "VERA": [
        {
            "nct": "NCT04716231",
            "nombre": "ORIGIN 3 Ph3 — atacicept — IgAN · PDUFA 7 jul 2026 ⚡ URGENTE",
            "sponsor_keywords": ["vera therapeutics"],
            "drug_keywords": ["atacicept"],
            "condition_keywords": ["iga nephropathy", "igan", "berger"],
            "prioridad": "alta",
            "tipo": "regulatorio",
            "catalizador": "PDUFA 7 jul 2026 — catalizador más próximo de cartera",
            "ventana": "jul 2026",
            "monitorizar": True,
            "peso_importancia": 10,
        },
    ],

    "SNDX": [
        {
            "nct": "NCT04065399",
            "nombre": "AUGMENT-101 Ph1/2 — revumenib — KMT2Ar/NPM1m R/R leukemia",
            "sponsor_keywords": ["syndax"],
            "drug_keywords": ["revumenib", "sndx-5613"],
            "condition_keywords": ["acute myeloid leukemia", "aml", "acute lymphoblastic leukemia", "leukemia", "kmt2a", "npm1"],
            "prioridad": "alta",
            "tipo": "base_comercial",
            "catalizador": "expansión etiqueta / ventas",
            "ventana": "2026-2027",
            "monitorizar": True,
            "peso_importancia": 8,
        },
        {
            "nct": "NCT07211958",
            "nombre": "REVEAL Ph3 — revumenib — NPM1m AML frontline",
            "sponsor_keywords": ["syndax"],
            "drug_keywords": ["revumenib"],
            "condition_keywords": ["acute myeloid leukemia", "aml", "npm1"],
            "prioridad": "alta",
            "tipo": "pivotal",
            "catalizador": "frontline AML",
            "ventana": "2029",
            "monitorizar": True,
            "peso_importancia": 8,
        },
    ],

    "VKTX": [
        {
            "nct": "NCT07104500",
            "nombre": "VANQUISH-1 Ph3 — VK2735 SC — obesidad sin T2D",
            "sponsor_keywords": ["viking therapeutics"],
            "drug_keywords": ["vk2735", "vk-2735"],
            "condition_keywords": ["obesity", "overweight", "weight"],
            "prioridad": "alta",
            "tipo": "pivotal",
            "catalizador": "datos Phase 3 obesidad",
            "ventana": "2027",
            "monitorizar": True,
            "peso_importancia": 10,
        },
        {
            "nct": "NCT07104383",
            "nombre": "VANQUISH-2 Ph3 — VK2735 SC — obesidad + T2D",
            "sponsor_keywords": ["viking therapeutics"],
            "drug_keywords": ["vk2735", "vk-2735"],
            "condition_keywords": ["obesity", "overweight", "weight", "type 2 diabetes"],
            "prioridad": "alta",
            "tipo": "pivotal",
            "catalizador": "datos Phase 3 obesidad/T2D",
            "ventana": "2027",
            "monitorizar": True,
            "peso_importancia": 10,
        },
        {
            "nct": "NCT06828055",
            "nombre": "VENTURE-Oral Ph2 — VK2735 oral — obesidad",
            "sponsor_keywords": ["viking therapeutics"],
            "drug_keywords": ["vk2735", "vk-2735"],
            "condition_keywords": ["obesity", "overweight", "weight"],
            "prioridad": "alta",
            "tipo": "phase2_oral",
            "catalizador": "transición a Phase 3 oral",
            "ventana": "2026-2027",
            "monitorizar": True,
            "peso_importancia": 9,
        },
    ],

    "BEAM": [
        {
            "nct": "NCT05456880",
            "nombre": "BEACON Ph1/2 — risto-cel (BEAM-101) — SCD",
            "sponsor_keywords": ["beam therapeutics"],
            "drug_keywords": ["beam-101", "risto-cel"],
            "condition_keywords": ["sickle cell"],
            "prioridad": "alta",
            "tipo": "registracional",
            "catalizador": "BLA / RMAT",
            "ventana": "2026-2028",
            "monitorizar": True,
            "peso_importancia": 8,
        },
        {
            "nct": "NCT06389877",
            "nombre": "Ph1/2 — BEAM-302 — AATD",
            "sponsor_keywords": ["beam therapeutics"],
            "drug_keywords": ["beam-302"],
            "condition_keywords": ["alpha-1", "alpha 1", "aatd", "antitrypsin"],
            "prioridad": "media",
            "tipo": "phase1_2",
            "catalizador": "datos tempranos",
            "ventana": "2026-2028",
            "monitorizar": True,
            "peso_importancia": 6,
        },
    ],

    "ACRV": [
        {
            "nct": "NCT05548296",
            "nombre": "Ph1b/2 registracional — ACR-368 + OncoSignature — endometrio/ovario",
            "sponsor_keywords": ["acrivon"],
            "drug_keywords": ["acr-368", "oncosignature"],
            "condition_keywords": ["endometrial", "ovarian", "urothelial", "cancer"],
            "prioridad": "alta",
            "tipo": "phase2_registracional",
            "catalizador": "datos registracionales / biomarcador",
            "ventana": "2027",
            "monitorizar": True,
            "peso_importancia": 8,
        },
    ],

    "GPCR": [
        {
            "nct": "NCT06693843",
            "nombre": "GLOW Ph2b — aleniglipron oral GLP-1 — obesidad",
            "sponsor_keywords": ["structure therapeutics"],
            "drug_keywords": ["aleniglipron", "gsbr-1290", "gsbr1290"],
            "condition_keywords": ["obesity", "overweight", "weight"],
            "prioridad": "alta",
            "tipo": "phase2b",
            "catalizador": "datos 44 semanas / paso a Phase 3",
            "ventana": "2026",
            "monitorizar": True,
            "peso_importancia": 9,
        },
    ],

    "INSM": [
        {
            "nct": "NCT04594369",
            "nombre": "ASPEN Ph3 — brensocatib — bronchiectasis",
            "sponsor_keywords": ["insmed"],
            "drug_keywords": ["brensocatib"],
            "condition_keywords": ["bronchiectasis"],
            "prioridad": "media",
            "tipo": "aprobado",
            "catalizador": "comercialización / label",
            "ventana": "2026",
            "monitorizar": True,
            "peso_importancia": 6,
        },
    ],

    "ARGX": [
        {
            "nct": "NCT06558279",
            "nombre": "ADAPT OCULUS Ph3 — efgartigimod SC — ocular MG",
            "sponsor_keywords": ["argenx"],
            "drug_keywords": ["efgartigimod", "vyvgart", "argx-113"],
            "condition_keywords": ["myasthenia gravis", "ocular", "mg"],
            "prioridad": "alta",
            "tipo": "pivotal",
            "catalizador": "sBLA / expansión indicación",
            "ventana": "2026",
            "monitorizar": True,
            "peso_importancia": 8,
        },
        {
            "nct": "NCT06298552",
            "nombre": "ADAPT SERON ✅ APROBADO 8 may2026 — efgartigimod IV — seronegative gMG (label expansion todos serotipos)",
            "sponsor_keywords": ["argenx"],
            "drug_keywords": ["efgartigimod", "vyvgart", "argx-113"],
            "condition_keywords": ["myasthenia gravis", "seronegative", "mg"],
            "prioridad": "alta",
            "tipo": "aprobado",
            "catalizador": "✅ APROBADO FDA 8 may2026 — 1ª terapia gMG independiente del anticuerpo",
            "ventana": "aprobado",
            "monitorizar": True,
            "peso_importancia": 8,
        },
        {
            "nct": "NCT06684847",
            "nombre": "UNITY Ph3 — efgartigimod SC — Sjögren's Disease",
            "sponsor_keywords": ["argenx"],
            "drug_keywords": ["efgartigimod", "vyvgart", "argx-113"],
            "condition_keywords": ["sjögren", "sjogren"],
            "prioridad": "media",
            "tipo": "pivotal",
            "catalizador": "datos Phase 3",
            "ventana": "2027",
            "monitorizar": True,
            "peso_importancia": 7,
        },
        {
            "nct": "NCT06742190",
            "nombre": "EMPASSION Ph3 — empasiprubart vs IVIg — MMN",
            "sponsor_keywords": ["argenx"],
            "drug_keywords": ["empasiprubart"],
            "condition_keywords": ["multifocal motor neuropathy", "mmn"],
            "prioridad": "media",
            "tipo": "pivotal",
            "catalizador": "datos Phase 3",
            "ventana": "2026-2027",
            "monitorizar": True,
            "peso_importancia": 7,
        },
        {
            "nct": "NCT06920004",
            "nombre": "emvigorate Ph3 — empasiprubart vs IVIg — CIDP head-to-head",
            "sponsor_keywords": ["argenx"],
            "drug_keywords": ["empasiprubart"],
            "condition_keywords": ["cidp", "chronic inflammatory demyelinating polyneuropathy"],
            "prioridad": "media",
            "tipo": "pivotal",
            "catalizador": "datos Phase 3",
            "ventana": "2027-2030",
            "monitorizar": True,
            "peso_importancia": 7,
        },
    ],

    "DNLI": [
        {
            "nct": "NCT05371613",
            "nombre": "COMPASS Ph2/3 — tividenofusp alfa (DNL310) — Hunter MPS II",
            "sponsor_keywords": ["denali"],
            "drug_keywords": ["tividenofusp", "dnl310", "dnl-310"],
            "condition_keywords": ["mucopolysaccharidosis", "hunter", "mps ii"],
            "prioridad": "alta",
            "tipo": "pivotal",
            "catalizador": "Phase 2/3 / posible aprobación",
            "ventana": "2027",
            "monitorizar": True,
            "peso_importancia": 9,
        },
    ],

    "ALNY": [
        {
            "nct": "NCT07181109",
            "nombre": "ZENITH Ph3 CVOT — zilebesiran — hipertensión",
            "sponsor_keywords": ["alnylam"],
            "drug_keywords": ["zilebesiran"],
            "condition_keywords": ["hypertension", "cardiovascular"],
            "prioridad": "media",
            "tipo": "cvot",
            "catalizador": "CVOT / MACE endpoint",
            "ventana": "2030",
            "monitorizar": True,
            "peso_importancia": 7,
        },
        {
            "nct": "NCT07052903",
            "nombre": "TRITON-CM Ph3 — nucresiran — ATTR-CM",
            "sponsor_keywords": ["alnylam"],
            "drug_keywords": ["nucresiran"],
            "condition_keywords": ["transthyretin", "amyloidosis", "cardiomyopathy", "attr"],
            "prioridad": "alta",
            "tipo": "pivotal",
            "catalizador": "ATTR-CM Phase 3",
            "ventana": "2030",
            "monitorizar": True,
            "peso_importancia": 8,
        },
        {
            "nct": "NCT07223203",
            "nombre": "TRITON-PN Ph3 — nucresiran — hATTR-PN",
            "sponsor_keywords": ["alnylam"],
            "drug_keywords": ["nucresiran"],
            "condition_keywords": ["transthyretin", "amyloidosis", "polyneuropathy", "hattr"],
            "prioridad": "media",
            "tipo": "pivotal",
            "catalizador": "hATTR-PN Phase 3",
            "ventana": "2027-2031",
            "monitorizar": True,
            "peso_importancia": 7,
        },
        {
            "nct": "NCT06393712",
            "nombre": "cAPPricorn-1 Ph2 — mivelsiran — CAA",
            "sponsor_keywords": ["alnylam"],
            "drug_keywords": ["mivelsiran", "aln-app", "aln app"],
            "condition_keywords": ["cerebral amyloid angiopathy", "amyloid"],
            "prioridad": "media",
            "tipo": "phase2",
            "catalizador": "datos Phase 2 CNS",
            "ventana": "2027-2029",
            "monitorizar": True,
            "peso_importancia": 6,
        },
    ],

    "VRTX": [
        {
            "nct": "NCT06564142",
            "nombre": "RAINIER Ph3 — povetacicept — IgAN",
            "sponsor_keywords": ["vertex", "alpine"],
            "drug_keywords": ["povetacicept"],
            "condition_keywords": ["iga nephropathy", "igan"],
            "prioridad": "alta",
            "tipo": "pivotal",
            "catalizador": "BLA / datos Phase 3",
            "ventana": "2028",
            "monitorizar": True,
            "peso_importancia": 8,
        },
        {
            "nct": "NCT05312879",
            "nombre": "AMPLITUDE Ph2/3 — inaxaplin (VX-147) — AMKD",
            "sponsor_keywords": ["vertex"],
            "drug_keywords": ["vx-147", "inaxaplin"],
            "condition_keywords": ["apol1", "kidney"],
            "prioridad": "alta",
            "tipo": "pivotal",
            "catalizador": "interim analysis / breakthrough",
            "ventana": "2026-2028",
            "monitorizar": True,
            "peso_importancia": 8,
        },
        {
            "nct": "NCT04786262",
            "nombre": "FORWARD-101 Ph1/2/3 — zimislecel (VX-880) — T1D",
            "sponsor_keywords": ["vertex"],
            "drug_keywords": ["vx-880", "zimislecel"],
            "condition_keywords": ["type 1 diabetes"],
            "prioridad": "alta",
            "tipo": "cell_therapy",
            "catalizador": "datos Phase 3",
            "ventana": "2026-2030",
            "monitorizar": True,
            "peso_importancia": 8,
        },
    ],

    "SENS": [
        {
            "nct": "NCT05131139",
            "nombre": "ENHANCE — Eversense 365 CGM",
            "sponsor_keywords": ["senseonics"],
            "drug_keywords": ["eversense", "cgm"],
            "condition_keywords": ["diabetes"],
            "prioridad": "media",
            "tipo": "device",
            "catalizador": "FDA / comercialización",
            "ventana": "2026",
            "monitorizar": True,
            "peso_importancia": 5,
        },
    ],
}


# =============================================================================
# CONSTANTES
# =============================================================================

API_BASE = "https://clinicaltrials.gov/api/v2/studies/{nct}"
CACHE_FILE = "clinicaltrials_cache.json"
RESULTADO_FILE = "clinicaltrials_resultado.json"
REPORTE_FILE = "clinicaltrials_reporte.txt"

HEADERS = {
    "User-Agent": "ClinicalTrials Monitor v9.3 David Amor",
    "Accept": "application/json",
}


# =============================================================================
# UTILIDADES
# =============================================================================

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
    return str(x or "").lower().replace("—", " ").replace("-", " ").replace("_", " ")


def contiene_alguna(texto, keywords):
    if not keywords:
        return True
    texto = clean_text(texto)
    return any(clean_text(k) in texto for k in keywords if k)


# =============================================================================
# CLASIFICACIÓN
# =============================================================================

def clasificar_status(status):
    status = normalizar_status(status)

    if status in ("TERMINATED", "SUSPENDED", "WITHDRAWN"):
        return "rojo", "🔴", "Ensayo detenido/suspendido/retirado"

    if status == "COMPLETED":
        return "verde", "🟢", "Ensayo completado"

    if status == "RECRUITING":
        return "azul", "🔵", "Reclutando"

    if status == "ACTIVE_NOT_RECRUITING":
        return "azul", "🔵", "Activo, sin reclutamiento"

    if status == "NOT_YET_RECRUITING":
        return "amarillo", "🟡", "Aún no recluta"

    if status == "ENROLLING_BY_INVITATION":
        return "azul", "🔵", "Reclutamiento por invitación"

    return "azul", "🔵", f"Estado: {status}"


def calcular_relevancia(datos, config):
    prioridad = config.get("prioridad")
    tipo = config.get("tipo") or "seguimiento"
    phase = datos.get("phase") or ""

    if not prioridad:
        if "PHASE3" in phase or "pivotal" in tipo or "registracional" in tipo:
            prioridad = "alta"
        elif "PHASE2" in phase:
            prioridad = "media"
        else:
            prioridad = "baja"

    estrellas = {
        "alta": "⭐⭐⭐",
        "media": "⭐⭐",
        "baja": "⭐",
    }.get(prioridad, "⭐")

    return {
        "prioridad": prioridad,
        "estrellas": estrellas,
        "tipo": tipo,
        "catalizador": config.get("catalizador"),
        "ventana": config.get("ventana"),
        "monitorizar": config.get("monitorizar", True),
        "peso_importancia": config.get("peso_importancia", 5),
    }


def badge_nivel(nivel):
    return {
        "rojo": "🔴",
        "verde": "🟢",
        "amarillo": "🟡",
        "azul": "🔵",
        "ok": "✅",
    }.get(nivel, "🔵")


def elegir_nivel_ticker(niveles):
    if not niveles:
        return "ok"
    prioridad = {"rojo": 4, "verde": 3, "amarillo": 2, "azul": 1, "ok": 0}
    return max(niveles, key=lambda n: prioridad.get(n, 0))


def nivel_ensayo(nivel_base, cambios):
    prioridad = {"rojo": 4, "verde": 3, "amarillo": 2, "azul": 1, "ok": 0}
    niveles = [nivel_base] + [c.get("nivel", "azul") for c in cambios]
    return max(niveles, key=lambda n: prioridad.get(n, 0))


# =============================================================================
# API / VALIDACIÓN
# =============================================================================

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

    enrollment_info = design.get("enrollmentInfo", {}) or {}
    enrollment = enrollment_info.get("count")

    phases = design.get("phases") or []
    phase = ", ".join(phases) if isinstance(phases, list) else str(phases) if phases else None

    conditions = protocol.get("conditionsModule", {}).get("conditions", []) or []

    interventions = arms.get("interventions", []) or []
    intervention_names = []
    for i in interventions:
        name = i.get("name")
        if name:
            intervention_names.append(name)

    lead_sponsor = sponsor_mod.get("leadSponsor", {}) or {}
    sponsor_name = lead_sponsor.get("name")

    collaborators = sponsor_mod.get("collaborators", []) or []
    collaborator_names = [c.get("name") for c in collaborators if c.get("name")]

    return {
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


def validar_ensayo(datos, config):
    sponsor_text = " ".join([datos.get("sponsor") or "", " ".join(datos.get("collaborators") or [])])
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

    if config.get("sponsor_keywords") and not contiene_alguna(sponsor_text, config["sponsor_keywords"]):
        errores.append("Sponsor no coincide")

    if config.get("drug_keywords") and not contiene_alguna(drug_text, config["drug_keywords"]):
        errores.append("Fármaco/intervención no coincide")

    if config.get("condition_keywords") and not contiene_alguna(condition_text, config["condition_keywords"]):
        errores.append("Indicación no coincide")

    return {
        "ok": len(errores) == 0,
        "errores": errores,
        "detalles": {
            "sponsor_text": sponsor_text,
            "drug_text": drug_text[:700],
            "condition_text": condition_text[:700],
        },
        "sponsor_keywords": config.get("sponsor_keywords", []),
        "drug_keywords": config.get("drug_keywords", []),
        "condition_keywords": config.get("condition_keywords", []),
    }


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
        ("prioridad", "Prioridad"),
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

            elif key == "prioridad" and new == "alta":
                nivel, badge = "amarillo", "🟡"

            cambios.append({
                "tipo": key,
                "nivel": nivel,
                "badge": badge,
                "mensaje": f"{label}: {old if old is not None else '—'} → {new if new is not None else '—'}",
            })

    return cambios


# =============================================================================
# RUNNER
# =============================================================================

def run_monitor():
    cache = cargar_cache()
    nuevo_cache = {}

    dashboard = {
        "version": "v9.3",
        "generado": ahora_str(),
        "fecha": hoy_iso(),
        "resumen": {
            "total_ensayos": 0,
            "prioridad_alta": 0,
            "prioridad_media": 0,
            "prioridad_baja": 0,
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
            "score_relevancia": 0,
        }

        niveles_ticker = []
        score_ticker = 0

        for ensayo in ensayos:
            nct = ensayo["nct"]
            nombre = ensayo["nombre"]
            time.sleep(0.25)

            try:
                actual = consultar_ensayo(nct, nombre)

                validacion = validar_ensayo(actual, ensayo)
                actual["validacion"] = validacion
                actual["validacion_ok"] = validacion["ok"]

                relevancia = calcular_relevancia(actual, ensayo)
                actual.update(relevancia)

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
                        "mensaje": "; ".join(validacion["errores"]),
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
                    "prioridad": actual.get("prioridad"),
                    "tipo": actual.get("tipo"),
                    "catalizador": actual.get("catalizador"),
                    "ventana": actual.get("ventana"),
                    "peso_importancia": actual.get("peso_importancia"),
                }

                dashboard["empresas"][ticker]["ensayos"].append(actual)
                dashboard["resumen"]["total_ensayos"] += 1
                niveles_ticker.append(nivel_final)

                score_ticker += int(actual.get("peso_importancia") or 0)

                prioridad = actual.get("prioridad")
                if prioridad == "alta":
                    dashboard["resumen"]["prioridad_alta"] += 1
                elif prioridad == "media":
                    dashboard["resumen"]["prioridad_media"] += 1
                else:
                    dashboard["resumen"]["prioridad_baja"] += 1

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

                if cambios or nivel_final in ("rojo", "verde") or actual.get("prioridad") == "alta":
                    dashboard["alertas"].append({
                        "ticker": ticker,
                        "nct": nct,
                        "nombre": nombre,
                        "nivel": nivel_final,
                        "badge": badge_final,
                        "status": actual.get("status"),
                        "primary_completion_date": actual.get("primary_completion_date"),
                        "mensaje": actual.get("status_desc"),
                        "prioridad": actual.get("prioridad"),
                        "estrellas": actual.get("estrellas"),
                        "tipo": actual.get("tipo"),
                        "catalizador": actual.get("catalizador"),
                        "ventana": actual.get("ventana"),
                        "peso_importancia": actual.get("peso_importancia"),
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
                print(f"ERROR {ticker} {nct}: {e}")

        dashboard["empresas"][ticker]["nivel"] = elegir_nivel_ticker(niveles_ticker)
        dashboard["empresas"][ticker]["badge"] = badge_nivel(dashboard["empresas"][ticker]["nivel"])
        dashboard["empresas"][ticker]["score_relevancia"] = score_ticker

    guardar_cache(nuevo_cache)
    return dashboard


# =============================================================================
# REPORTE
# =============================================================================

def generar_reporte(dashboard):
    r = dashboard["resumen"]
    lines = []
    lines.append("=" * 84)
    lines.append("CLINICALTRIALS MONITOR v9.3 · Modelo Biotech")
    lines.append(f"Generado: {dashboard['generado']}")
    lines.append("=" * 84)
    lines.append(
        f"RESUMEN: {r['total_ensayos']} ensayos | "
        f"Alta: {r['prioridad_alta']} | Media: {r['prioridad_media']} | Baja: {r['prioridad_baja']} | "
        f"Validación OK: {r['validacion_ok']} | Errores validación: {r['validacion_error']} | "
        f"🔴 {r['alertas_rojas']} | 🟢 {r['alertas_verdes']} | "
        f"🟡 {r['alertas_amarillas']} | 🔵 {r['alertas_azules']} | "
        f"Errores API: {r['errores']}"
    )

    if dashboard.get("errores_validacion"):
        lines.append("\n" + "-" * 84)
        lines.append("❌ ERRORES DE VALIDACIÓN — POSIBLES NCT INCORRECTOS")
        lines.append("-" * 84)
        for e in dashboard["errores_validacion"]:
            lines.append(f"\n[{e['ticker']}] {e['nombre']}")
            lines.append(f"NCT: {e['nct']}")
            lines.append(f"Sponsor detectado: {e.get('sponsor_detectado')}")
            lines.append(f"Título detectado: {e.get('titulo_detectado')}")
            lines.append(f"Errores: {', '.join(e['errores'])}")
            lines.append(f"→ {e['url']}")

    lines.append("\n" + "-" * 84)
    lines.append("DETALLE POR EMPRESA")
    lines.append("-" * 84)

    empresas_ordenadas = sorted(
        dashboard["empresas"].items(),
        key=lambda kv: kv[1].get("score_relevancia", 0),
        reverse=True,
    )

    for ticker, data in empresas_ordenadas:
        lines.append(f"\n{data['badge']} [{ticker}] · Score relevancia: {data.get('score_relevancia', 0)}")
        ensayos_ordenados = sorted(
            data["ensayos"],
            key=lambda e: e.get("peso_importancia", 0),
            reverse=True,
        )
        for e in ensayos_ordenados:
            if e.get("error"):
                lines.append(f"  ❌ {e['nombre_usuario']} ({e['nct']}): {e['error']}")
                continue
            valid = "OK" if e.get("validacion_ok") else "ERROR"
            lines.append(
                f"  {e['badge']} {e.get('estrellas', '')} {e['nombre_usuario']} "
                f"| Prioridad: {e.get('prioridad')} | Validación: {valid}"
            )
            lines.append(f"     NCT: {e['nct']} | Status: {e['status_desc']} | Tipo: {e.get('tipo')}")
            if e.get("catalizador"):
                lines.append(f"     Catalizador: {e.get('catalizador')} | Ventana: {e.get('ventana')}")
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

    lines.append("\n" + "=" * 84)
    lines.append("Fuente: ClinicalTrials.gov API v2")
    lines.append("=" * 84)
    return "\n".join(lines)


# =============================================================================
# MAIN
# =============================================================================

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
