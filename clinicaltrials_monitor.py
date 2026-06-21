#!/usr/bin/env python3
"""
ClinicalTrials Monitor v9.2 — Modelo Biotech

Novedades v9.2:
  - Sistema de dos niveles: ACTIVO y WATCHLIST
  - ACTIVO (watchlist=False): 40 ensayos con catalizador próximo.
    Genera alertas completas en cada ejecución.
  - WATCHLIST (watchlist=True): ensayos excluidos del monitor rutinario
    pero consultados para detectar cambios de status relevantes.
    Solo generan alerta si hay un cambio real vs caché anterior
    (status change, fecha adelantada, TERMINATED, COMPLETED inesperado).
    Sin ruido en días normales.
  - JSON incluye secciones separadas "alertas" (activos) y "watchlist_alertas".
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

    # ── DYN — 3 ensayos ───────────────────────────────────────────────────────
    # BLA DMD en revisión FDA (DELIVER) + Ph3 DM1 en curso (HARMONIA) + registracional DM1 (ACHIEVE)
    "DYN": [
        {
            "nct": "NCT05524883",
            "nombre": "DELIVER Ph1/2 registracional — z-rostudirsen — DMD exon 51 · BLA en revisión FDA",
            "sponsor_keywords": ["dyne therapeutics"],
            "drug_keywords": ["dyne-251", "z-rostudirsen"],
            "condition_keywords": ["duchenne", "dmd"],
        },
        {
            "nct": "NCT05481879",
            "nombre": "ACHIEVE Ph1/2 registracional — z-basivarsen — DM1 · Accel. Approval Q1 2027",
            "sponsor_keywords": ["dyne therapeutics"],
            "drug_keywords": ["dyne-101", "z-basivarsen"],
            "condition_keywords": ["myotonic dystrophy", "dm1"],
        },
        {
            "nct": "NCT07486934",
            "nombre": "HARMONIA Ph3 — z-basivarsen — DM1 confirmatorio · primary 2028",
            "sponsor_keywords": ["dyne therapeutics"],
            "drug_keywords": ["dyne-101", "z-basivarsen", "zeleciment basivarsen"],
            "condition_keywords": ["myotonic dystrophy", "dm1"],
        },
    ],

    # ── OCUL — 2 ensayos ──────────────────────────────────────────────────────
    # SOL-1 completó primario (74.1% vs 55.8%) → NDA inminente. SOL-R datos Q1 2027.
    "OCUL": [
        {
            "nct": "NCT06223958",
            "nombre": "SOL-1 Ph3 superioridad — AXPAXLI — wet AMD ✅ datos feb2026 · NDA inminente",
            "sponsor_keywords": ["ocular therapeutix"],
            "drug_keywords": ["otx-tki", "axpaxli", "axitinib implant"],
            "condition_keywords": ["neovascular", "age-related macular degeneration", "amd"],
        },
        {
            "nct": "NCT06495918",
            "nombre": "SOL-R Ph3 no inferioridad — AXPAXLI — wet AMD · datos Q1 2027",
            "sponsor_keywords": ["ocular therapeutix"],
            "drug_keywords": ["otx-tki", "axpaxli", "axitinib implant"],
            "condition_keywords": ["neovascular", "age-related macular degeneration", "amd"],
        },
    ],

    # ── TARA — 1 ensayo ───────────────────────────────────────────────────────
    # Datos 12m BCG-naïve positivos (AUA 2026). Enrollment BCG-unresponsive H2 2026.
    "TARA": [
        {
            "nct": "NCT05951179",
            "nombre": "ADVANCED-2 Ph2 — TARA-002 — NMIBC BCG-naïve/unresponsive CIS",
            "sponsor_keywords": ["protara"],
            "drug_keywords": ["tara-002"],
            "condition_keywords": ["nmibc", "non-muscle invasive bladder cancer", "bladder cancer", "carcinoma in situ"],
        },
    ],

    # ── ABVX — 3 ensayos ──────────────────────────────────────────────────────
    # Mantenimiento positivo 1 jun 2026 → NDA Q4 2026. Los 3 ensayos son el paquete regulatorio.
    "ABVX": [
        {
            "nct": "NCT05507203",
            "nombre": "ABTECT-1 Ph3 inducción — obefazimod — UC ✅ COMPLETADO positivo",
            "sponsor_keywords": ["abivax"],
            "drug_keywords": ["obefazimod", "abx464", "abx-464"],
            "condition_keywords": ["ulcerative colitis"],
        },
        {
            "nct": "NCT05507216",
            "nombre": "ABTECT-2 Ph3 inducción AT-failure — obefazimod — UC ✅ COMPLETADO positivo",
            "sponsor_keywords": ["abivax"],
            "drug_keywords": ["obefazimod", "abx464", "abx-464"],
            "condition_keywords": ["ulcerative colitis"],
        },
        {
            "nct": "NCT05535946",
            "nombre": "ABTECT mantenimiento 44sem — obefazimod (ABX464-107) — UC ✅ DATOS POSITIVOS 1 jun 2026 · NDA Q4 2026",
            "sponsor_keywords": ["abivax"],
            "drug_keywords": ["obefazimod", "abx464", "abx-464"],
            "condition_keywords": ["ulcerative colitis"],
        },
    ],

    # ── VERA — 1 ensayo ───────────────────────────────────────────────────────
    # BLA en revisión Priority Review. PDUFA 7 julio 2026 = 16 días.
    "VERA": [
        {
            "nct": "NCT04716231",
            "nombre": "ORIGIN 3 Ph3 — atacicept — IgAN · PDUFA 7 jul 2026 🔴 INMINENTE",
            "sponsor_keywords": ["vera therapeutics"],
            "drug_keywords": ["atacicept"],
            "condition_keywords": ["iga nephropathy", "igan", "berger"],
        },
    ],

    # ── SNDX — 2 ensayos ──────────────────────────────────────────────────────
    # AUGMENT base comercial. REVEAL es el upside a largo plazo (frontline AML).
    "SNDX": [
        {
            "nct": "NCT04065399",
            "nombre": "AUGMENT-101 Ph1/2 — revumenib — KMT2Ar/NPM1m R/R leukemia (base comercial)",
            "sponsor_keywords": ["syndax"],
            "drug_keywords": ["revumenib", "sndx-5613"],
            "condition_keywords": ["acute myeloid leukemia", "acute lymphoblastic leukemia", "leukemia", "kmt2a", "npm1"],
        },
        {
            "nct": "NCT07211958",
            "nombre": "REVEAL Ph3 — revumenib — NPM1m AML frontline · primary 2029",
            "sponsor_keywords": ["syndax"],
            "drug_keywords": ["revumenib"],
            "condition_keywords": ["acute myeloid leukemia", "aml", "npm1"],
        },
    ],

    # ── VKTX — 3 ensayos ──────────────────────────────────────────────────────
    # VANQUISH-1/2 son los catalizadores principales (Ph3, datos 2027).
    # VENTURE-Oral completado con datos positivos → Ph3 oral en preparación.
    "VKTX": [
        {
            "nct": "NCT07104500",
            "nombre": "VANQUISH-1 Ph3 — VK2735 SC — obesidad sin T2D · 4.500 pac. · datos 2027",
            "sponsor_keywords": ["viking therapeutics"],
            "drug_keywords": ["vk2735", "vk-2735"],
            "condition_keywords": ["obesity", "overweight", "weight"],
        },
        {
            "nct": "NCT07104383",
            "nombre": "VANQUISH-2 Ph3 — VK2735 SC — obesidad + T2D · 1.100 pac. · datos 2027",
            "sponsor_keywords": ["viking therapeutics"],
            "drug_keywords": ["vk2735", "vk-2735"],
            "condition_keywords": ["obesity", "overweight", "weight", "type 2 diabetes"],
        },
        {
            "nct": "NCT06828055",
            "nombre": "VENTURE-Oral Ph2 — VK2735 oral — obesidad ✅ COMPLETADO positivo ago2025 · Ph3 oral en preparación",
            "sponsor_keywords": ["viking therapeutics"],
            "drug_keywords": ["vk2735", "vk-2735"],
            "condition_keywords": ["obesity", "overweight", "weight"],
        },
    ],

    # ── BEAM — 2 ensayos ──────────────────────────────────────────────────────
    # BEACON: BLA risto-cel planeado fin 2026 (RMAT). BEAM-302: Ph2 con datos positivos.
    "BEAM": [
        {
            "nct": "NCT05456880",
            "nombre": "BEACON Ph1/2 — risto-cel (BEAM-101) — SCD · RMAT · BLA fin 2026",
            "sponsor_keywords": ["beam therapeutics"],
            "drug_keywords": ["beam-101", "risto-cel"],
            "condition_keywords": ["sickle cell"],
        },
        {
            "nct": "NCT06389877",
            "nombre": "Ph1/2 — BEAM-302 — AATD · primera corrección genética in vivo · RMAT may2025",
            "sponsor_keywords": ["beam therapeutics"],
            "drug_keywords": ["beam-302"],
            "condition_keywords": ["alpha-1", "alpha 1", "aatd", "antitrypsin"],
        },
    ],

    # ── ACRV — 1 ensayo ───────────────────────────────────────────────────────
    # Ph2 registracional-intent con OncoSignature. Primary endpoint mayo 2027.
    "ACRV": [
        {
            "nct": "NCT05548296",
            "nombre": "Ph1b/2 registracional — ACR-368 + OncoSignature — endometrio/ovario · primary 2027",
            "sponsor_keywords": ["acrivon"],
            "drug_keywords": ["acr-368", "oncosignature"],
            "condition_keywords": ["endometrial", "ovarian", "urothelial", "cancer"],
        },
    ],

    # ── GPCR — 1 ensayo ───────────────────────────────────────────────────────
    # Primary endpoint cumplido oct 2025. Datos de 44 semanas = catalizador próximo.
    "GPCR": [
        {
            "nct": "NCT06693843",
            "nombre": "GLOW Ph2b — aleniglipron oral GLP-1 — obesidad · primario oct2025 · datos 44sem inminentes",
            "sponsor_keywords": ["structure therapeutics"],
            "drug_keywords": ["aleniglipron", "gsbr-1290", "gsbr1290"],
            "condition_keywords": ["obesity", "overweight", "weight"],
        },
    ],

    # ── INSM — 1 ensayo ───────────────────────────────────────────────────────
    # ASPEN completado/aprobado. Se monitoriza para seguimiento de revenue y expansión.
    "INSM": [
        {
            "nct": "NCT04594369",
            "nombre": "ASPEN Ph3 — brensocatib — bronchiectasis ✅ APROBADO ago2025 (BRINSUPRI)",
            "sponsor_keywords": ["insmed"],
            "drug_keywords": ["brensocatib"],
            "condition_keywords": ["bronchiectasis"],
        },
    ],

    # ── ARGX — 7 ensayos ──────────────────────────────────────────────────────
    # Filtro aplicado: se excluyen emlight (pediátrico Ph1b), empasound (Ph1b ultrasound),
    # delayed graft function Ph2, ITP pediátrico, congenital MG natural history.
    # Se incluyen: todos los Ph3 y los Graves' (inicio inminente, mercado de ~$3B).
    "ARGX": [
        # EFGARTIGIMOD — expansión indicaciones
        {
            "nct": "NCT06558279",
            "nombre": "ADAPT OCULUS Ph3 — efgartigimod SC — ocular MG ✅ datos positivos feb2026 · sBLA planeado",
            "sponsor_keywords": ["argenx"],
            "drug_keywords": ["efgartigimod", "vyvgart", "argx-113"],
            "condition_keywords": ["myasthenia gravis", "ocular", "mg"],
        },
        {
            "nct": "NCT06298552",
            "nombre": "ADAPT SERON Ph3 — efgartigimod IV — seronegative gMG · Priority Review PDUFA may2026",
            "sponsor_keywords": ["argenx"],
            "drug_keywords": ["efgartigimod", "vyvgart", "argx-113"],
            "condition_keywords": ["myasthenia gravis", "seronegative", "mg"],
        },
        {
            "nct": "NCT06684847",
            "nombre": "UNITY Ph3 — efgartigimod SC — Sjögren's Disease · primary 2027",
            "sponsor_keywords": ["argenx"],
            "drug_keywords": ["efgartigimod", "vyvgart", "argx-113"],
            "condition_keywords": ["sjogren", "sjögren"],
        },
        {
            "nct": "NCT06544499",
            "nombre": "advance NEXT Ph3 — efgartigimod IV — ITP expansión indicación",
            "sponsor_keywords": ["argenx"],
            "drug_keywords": ["efgartigimod", "vyvgart", "argx-113"],
            "condition_keywords": ["thrombocytopenia", "itp", "immune"],
        },
        {
            # Graves' disease: mercado ~$3B, dos estudios paralelos, inicio jun2026
            "nct": "NCT07596849",
            "nombre": "VitaliThy Ph3 (A) — efgartigimod SC — Graves' Disease · inicio jun2026",
            "sponsor_keywords": ["argenx"],
            "drug_keywords": ["efgartigimod", "vyvgart", "argx-113"],
            "condition_keywords": ["graves", "thyroid", "hyperthyroid"],
        },
        # EMPASIPRUBART — pipeline segundo activo
        {
            "nct": "NCT06742190",
            "nombre": "EMPASSION Ph3 — empasiprubart vs IVIg — MMN · primary 2027",
            "sponsor_keywords": ["argenx"],
            "drug_keywords": ["empasiprubart", "argx-117"],
            "condition_keywords": ["multifocal motor neuropathy", "mmn"],
        },
        {
            "nct": "NCT06920004",
            "nombre": "emvigorate Ph3 — empasiprubart vs IVIg — CIDP head-to-head",
            "sponsor_keywords": ["argenx"],
            "drug_keywords": ["empasiprubart", "argx-117"],
            "condition_keywords": ["chronic inflammatory demyelinating", "cidp"],
        },
    ],

    # ── DNLI — 1 ensayo ───────────────────────────────────────────────────────
    # COMPASS es el confirmatorio obligatorio para AVLAYAH. Sin datos positivos no hay aprobación completa.
    "DNLI": [
        {
            "nct": "NCT05371613",
            "nombre": "COMPASS Ph2/3 confirmatorio — tividenofusp alfa (AVLAYAH) — Hunter MPS II",
            "sponsor_keywords": ["denali"],
            "drug_keywords": ["tividenofusp", "avlayah", "dnl310"],
            "condition_keywords": ["hunter", "mucopolysaccharidosis", "mps"],
        },
    ],

    # ── ALNY — 5 ensayos ──────────────────────────────────────────────────────
    # Filtro: se excluye fitusiran (ya aprobado, gestionado por Sanofi, no mueve ALNY directamente).
    # Se incluye mivelsiran Alzheimer Ph2: si datos positivos → rerating masivo (mercado >$10B).
    # Se incluye mivelsiran CAA Ph2: mismo activo, catalizador paralelo.
    # Se incluye cemdisiran (Regeneron): Ph3 MG completado, datos H2 2025 pendientes publicación.
    "ALNY": [
        {
            "nct": "NCT07181109",
            "nombre": "ZENITH Ph3 CVOT — zilebesiran — hipertensión · 11.000 pac. co-Roche · MACE endpoint",
            "sponsor_keywords": ["alnylam"],
            "drug_keywords": ["zilebesiran", "aln-agt"],
            "condition_keywords": ["hypertension", "cardiovascular", "blood pressure"],
        },
        {
            "nct": "NCT07052903",
            "nombre": "TRITON-CM Ph3 CVOT — nucresiran — ATTR-CM · 1.750 pac. · lanzamiento ~2030",
            "sponsor_keywords": ["alnylam"],
            "drug_keywords": ["nucresiran", "aln-ttrsc04"],
            "condition_keywords": ["transthyretin", "attr", "amyloidosis", "cardiomyopathy"],
        },
        {
            "nct": "NCT07223203",
            "nombre": "TRITON-PN Ph3 — nucresiran — hATTR-PN vs vutrisiran · 125 pac.",
            "sponsor_keywords": ["alnylam"],
            "drug_keywords": ["nucresiran", "aln-ttrsc04"],
            "condition_keywords": ["transthyretin", "attr", "polyneuropathy", "hattr"],
        },
        {
            # mivelsiran CAA Ph2: datos primarios impactarían precio masivamente si positivos
            "nct": "NCT06393712",
            "nombre": "cAPPricorn-1 Ph2 — mivelsiran — CAA (cerebral amyloid angiopathy) · 200 pac.",
            "sponsor_keywords": ["alnylam"],
            "drug_keywords": ["mivelsiran", "aln-app"],
            "condition_keywords": ["cerebral amyloid angiopathy", "caa", "amyloid"],
        },
        {
            # mivelsiran AD Ph2: Early-Onset Alzheimer · inicio jul2026 · potencial enorme si positivo
            "nct": "NCT07636811",
            "nombre": "Ph2 — mivelsiran — Alzheimer's Disease (Down syndrome-associated) · inicio jul2026",
            "sponsor_keywords": ["alnylam"],
            "drug_keywords": ["mivelsiran", "aln-app"],
            "condition_keywords": ["alzheimer", "down syndrome", "dementia"],
        },
    ],

    # ── VRTX — 6 ensayos ──────────────────────────────────────────────────────
    # Filtro: se excluye VX-264 (Ph1 encapsulación, sin readout próximo),
    # VX-993 DPN Ph2 (temprano, no mueve precio), VX-670 DM1 Ph1/2 (muy temprano),
    # LSR (no tiene NCT todavía), ETNA pMN+gMG (Ph2, muy temprano).
    # Se incluyen: los 5 programas con catalizador próximo en 12-18 meses.
    "VRTX": [
        {
            # RAINIER: BLA en rolling review, datos W36 positivos mar2026
            # BLA aceptado por FDA — aprobación acelerada podría llegar en 2026
            "nct": "NCT06564142",
            "nombre": "RAINIER Ph3 — povetacicept — IgAN · BLA rolling review · datos W36 positivos mar2026",
            "sponsor_keywords": ["vertex"],
            "drug_keywords": ["povetacicept", "pove"],
            "condition_keywords": ["iga nephropathy", "igan"],
        },
        {
            # OLYMPUS Ph2b/3: pMN — pivotal, ~176 pac., inicio sep2025
            # Si positivo en IA → segunda indicación importante para povetacicept
            "nct": "NCT07204275",
            "nombre": "OLYMPUS Ph2b/3 — povetacicept — pMN (membranous nephropathy) · pivotal",
            "sponsor_keywords": ["vertex"],
            "drug_keywords": ["povetacicept", "pove"],
            "condition_keywords": ["membranous nephropathy", "pmn", "glomerular"],
        },
        {
            # AMPLITUDE: inaxaplin AMKD — IA datos fin2026/Q1 2027, Breakthrough Therapy
            "nct": "NCT05312879",
            "nombre": "AMPLITUDE Ph2/3 — inaxaplin (VX-147) — AMKD · IA datos fin2026 · Breakthrough Therapy",
            "sponsor_keywords": ["vertex"],
            "drug_keywords": ["inaxaplin", "vx-147"],
            "condition_keywords": ["apol1", "amkd", "kidney", "nephropathy"],
        },
        {
            # FORWARD-101: zimislecel T1D — Ph3 enrollment completada, datos 2026
            # 12/12 pacientes sin insulina exógena en Ph1/2 (NEJM jun2025)
            "nct": "NCT04786262",
            "nombre": "FORWARD-101 Ph1/2/3 — zimislecel (VX-880) — T1D islet cell · NEJM jun2025 · datos Ph3 2026",
            "sponsor_keywords": ["vertex"],
            "drug_keywords": ["zimislecel", "vx-880"],
            "condition_keywords": ["type 1 diabetes", "t1d", "hypoglycemia", "islet"],
        },
        {
            # Suzetrigine DPN Ph3 trial 1 (iniciado antes, enrollment en curso)
            "nct": "NCT06628908",
            "nombre": "Ph3 DPN (1) — suzetrigine (JOURNAVX) — dolor neuropático diabético · primary 2027",
            "sponsor_keywords": ["vertex"],
            "drug_keywords": ["suzetrigine", "vx-548", "journavx"],
            "condition_keywords": ["diabetic peripheral neuropathy", "dpn", "neuropathic pain"],
        },
        {
            # Suzetrigine DPN Ph3 trial 2 (iniciado nov2025)
            "nct": "NCT07231419",
            "nombre": "Ph3 DPN (2) — suzetrigine (JOURNAVX) — dolor neuropático diabético · inicio nov2025",
            "sponsor_keywords": ["vertex"],
            "drug_keywords": ["suzetrigine", "vx-548", "journavx"],
            "condition_keywords": ["diabetic peripheral neuropathy", "dpn", "neuropathic pain"],
        },
    ],

    # ── SENS — 1 ensayo ───────────────────────────────────────────────────────
    # ENHANCE completado/aprobado. Se monitoriza como historial comercial del producto.
    "SENS": [
        {
            "nct": "NCT05131139",
            "nombre": "ENHANCE — Eversense 365 CGM 1 año implantable ✅ COMPLETADO · FDA cleared sep2024",
            "sponsor_keywords": ["senseonics"],
            "drug_keywords": ["eversense", "cgm", "implantable"],
            "condition_keywords": ["diabetes", "glucose"],
        },
    ],
}

# ──────────────────────────────────────────────────────────────────────────────
# WATCHLIST — Ensayos de segundo nivel
# Se monitorean silenciosamente. Solo generan alerta si hay cambio real.
# Criterio de inclusión: ensayo que podría mover precio en el futuro pero
# no tiene catalizador próximo definido o está en fase muy temprana.
# ──────────────────────────────────────────────────────────────────────────────

WATCHLIST_CARTERA = {

    "ARGX": [
        {
            # emnergize Ph3 CIDP placebo-controlled — paralelo a emvigorate
            # Solo activar alerta si status cambia o fecha se adelanta
            "nct": "NCT07091630",
            "nombre": "emnergize Ph3 — empasiprubart — CIDP placebo · plan B si emvigorate falla",
            "watchlist": True,
            "sponsor_keywords": ["argenx"],
            "drug_keywords": ["empasiprubart", "argx-117"],
            "condition_keywords": ["chronic inflammatory demyelinating", "cidp"],
        },
        {
            # VitaliThy segundo estudio paralelo (NCT07570316)
            # Mismo evento que NCT07596849 — monitorizar por si uno suspende
            "nct": "NCT07570316",
            "nombre": "VitaliThy Ph3 (B) — efgartigimod — Graves' Disease · estudio paralelo",
            "watchlist": True,
            "sponsor_keywords": ["argenx"],
            "drug_keywords": ["efgartigimod", "vyvgart", "argx-113"],
            "condition_keywords": ["graves", "thyroid", "hyperthyroid"],
        },
    ],

    "VRTX": [
        {
            # VX-264 DISCONTINUED (marzo 2025): no cumplió endpoint eficacia (C-peptide).
            # Plan B T1D eliminado. FORWARD-101 (zimislecel) es el único activo viable.
            # Mantenemos en watchlist solo para detectar si Vertex anuncia nuevo programa encapsulado.
            "nct": "NCT05210530",
            "nombre": "VX-264 — DISCONTINUED ⚠️ (mar2025 no cumplió eficacia) · solo si Vertex anuncia sucesor",
            "watchlist": True,
            "sponsor_keywords": ["vertex"],
            "drug_keywords": ["vx-264", "zimislecel"],
            "condition_keywords": ["type 1 diabetes", "t1d", "islet"],
        },
        {
            # ETNA Ph2: povetacicept gMG — inicio previsto H1 2026
            # Si datos positivos → 3ª gran indicación para pove
            "nct": "NCT07204275",  # Placeholder — buscar NCT real cuando se registre
            "nombre": "ETNA Ph2 — povetacicept — gMG · inicio H1 2026 (NCT pendiente registro)",
            "watchlist": True,
            "sponsor_keywords": ["vertex"],
            "drug_keywords": ["povetacicept", "pove"],
            "condition_keywords": ["myasthenia gravis", "mg"],
        },
    ],

    "ALNY": [
        {
            # cemdisiran Ph3 MG (Regeneron) — resultados H2 2025 pendientes publicación
            # Si positivo → Regeneron paga milestones a ALNY
            "nct": "NCT04508036",
            "nombre": "cemdisiran Ph3 — MG (partner Regeneron) · resultados H2 2025 pendientes",
            "watchlist": True,
            "sponsor_keywords": ["regeneron"],
            "drug_keywords": ["cemdisiran"],
            "condition_keywords": ["myasthenia gravis", "mg", "complement"],
        },
        {
            # cAPPricorn-1 Ph2: mivelsiran CAA — ya en script activo (NCT06939371)
            # Aquí ponemos el estudio AD específico por Down syndrome
            # NOTA: NCT07636811 ya está en activo — esto es solo para seguimiento de inicio
            "nct": "NCT05231785",
            "nombre": "Ph1 mivelsiran — Alzheimer EOAD · datos Ph1 base para Ph2",
            "watchlist": True,
            "sponsor_keywords": ["alnylam"],
            "drug_keywords": ["mivelsiran", "aln-app"],
            "condition_keywords": ["alzheimer", "amyloid"],
        },
    ],

    "DNLI": [
        {
            # DNL919 TERMINATED (confirmado jun2026) — eliminado del watchlist activo
            # Se mantiene como referencia histórica: pipeline Alzheimer DNLI más temprano de lo previsto
            # NCT05225532 = TERMINATED — no hay plan B BBB platform para AD a corto plazo
            "nct": "NCT05225532",
            "nombre": "DNL919 — TERMINATED ⚠️ — Alzheimer BBB platform · MONITORIZAR solo si hay sustituto",
            "watchlist": True,
            "sponsor_keywords": ["denali"],
            "drug_keywords": ["dnl919", "dnl-919", "biib"],
            "condition_keywords": ["alzheimer", "dementia"],
        },
    ],

    "BEAM": [
        {
            # BEAM-101 BLA submission tracker — seguimiento del IND/BLA process
            # BEACON ya en activo. Este es un ensayo adicional pediátrico si lo hay.
            # Por ahora placeholder para futuros ensayos de expansión
            "nct": "NCT05456880",  # mismo que activo — watchlist solo por si hay expansión label
            "nombre": "BEACON expansión — risto-cel — SCD población pediátrica / nuevas indicaciones",
            "watchlist": True,
            "sponsor_keywords": ["beam therapeutics"],
            "drug_keywords": ["beam-101", "risto-cel"],
            "condition_keywords": ["sickle cell"],
        },
    ],

    "VKTX": [
        {
            # Ph3 VK2735 oral — aún sin NCT registrado (anunciado para Q3 2026)
            # Cuando se registre → mover a ACTIVO inmediatamente
            # Usar NCT06828055 (VENTURE-Oral ya completado) para tracking sponsor
            "nct": "NCT06828055",
            "nombre": "VENTURE-Oral completado — WATCHLIST para detectar registro Ph3 oral VK2735",
            "watchlist": True,
            "sponsor_keywords": ["viking therapeutics"],
            "drug_keywords": ["vk2735"],
            "condition_keywords": ["obesity", "overweight", "weight"],
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
        "version": "v9.2",
        "generado": ahora_str(),
        "fecha": hoy_iso(),
        "resumen": {
            "total_ensayos": 0,
            "watchlist_total": 0,
            "watchlist_con_cambios": 0,
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
        "watchlist_alertas": [],
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

    # ── PROCESAR WATCHLIST ────────────────────────────────────────────────────
    for ticker, ensayos in WATCHLIST_CARTERA.items():
        for ensayo in ensayos:
            nct = ensayo["nct"]
            nombre = ensayo["nombre"]
            time.sleep(0.2)

            try:
                actual = consultar_ensayo(nct, nombre)
                validacion = validar_ensayo(actual, ensayo)
                actual["validacion_ok"] = validacion["ok"]
                actual["watchlist"] = True

                previo = cache.get(f"wl_{nct}")
                cambios = comparar_con_cache(nct, actual, previo)

                # Solo guardar en caché y alertar si hay cambio real
                # (excluir "Primer registro en caché" de alertas)
                cambios_reales = [c for c in cambios if c.get("tipo") != "nuevo"]

                nuevo_cache[f"wl_{nct}"] = {
                    "status": actual.get("status"),
                    "primary_completion_date": actual.get("primary_completion_date"),
                    "study_completion_date": actual.get("study_completion_date"),
                    "last_update_posted": actual.get("last_update_posted"),
                    "enrollment": actual.get("enrollment"),
                    "titulo": actual.get("titulo"),
                    "ticker": ticker,
                    "nombre_usuario": nombre,
                    "validacion_ok": actual.get("validacion_ok"),
                }

                dashboard["resumen"]["watchlist_total"] += 1

                # Solo alertar si hay cambio relevante (no en primer registro)
                status_norm = normalizar_status(actual.get("status", ""))
                evento_critico = status_norm in ("TERMINATED", "SUSPENDED", "WITHDRAWN", "COMPLETED")

                if cambios_reales or (evento_critico and not previo):
                    nivel_wl = "azul"
                    if status_norm in ("TERMINATED", "SUSPENDED", "WITHDRAWN"):
                        nivel_wl = "rojo"
                    elif status_norm == "COMPLETED":
                        nivel_wl = "verde"
                    elif cambios_reales:
                        nivel_wl = "amarillo"

                    dashboard["resumen"]["watchlist_con_cambios"] += 1
                    dashboard["watchlist_alertas"].append({
                        "ticker": ticker,
                        "nct": nct,
                        "nombre": nombre,
                        "nivel": nivel_wl,
                        "badge": badge_nivel(nivel_wl),
                        "status": actual.get("status"),
                        "primary_completion_date": actual.get("primary_completion_date"),
                        "validacion_ok": actual.get("validacion_ok"),
                        "cambios": cambios_reales,
                        "url": actual.get("url"),
                        "watchlist": True,
                    })

            except Exception as e:
                dashboard["resumen"]["errores"] += 1
                print(f"  WATCHLIST ERROR {ticker} {nct}: {e}")

    guardar_cache(nuevo_cache)
    return dashboard

# ──────────────────────────────────────────────────────────────────────────────
# REPORTE
# ──────────────────────────────────────────────────────────────────────────────

def generar_reporte(dashboard):
    r = dashboard["resumen"]
    lines = []
    lines.append("=" * 76)
    lines.append("CLINICALTRIALS MONITOR v9.2 · Modelo Biotech")
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

    # Sección watchlist en reporte
    wl_alertas = dashboard.get("watchlist_alertas", [])
    if wl_alertas:
        lines.append("\n" + "-" * 76)
        lines.append(f"👁️  WATCHLIST — CAMBIOS DETECTADOS ({len(wl_alertas)})")
        lines.append("-" * 76)
        for a in wl_alertas:
            lines.append(f"\n[{a['ticker']}] {a['badge']} {a['nombre']}")
            lines.append(f"NCT: {a['nct']} | Status: {a.get('status', '?')}")
            for c in a.get("cambios", []):
                lines.append(f"  ⚡ {c['mensaje']}")
            lines.append(f"→ {a['url']}")
    else:
        wl_total = dashboard.get("resumen", {}).get("watchlist_total", 0)
        if wl_total:
            lines.append(f"\n👁️  WATCHLIST: {wl_total} ensayos monitorizados sin cambios")

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
