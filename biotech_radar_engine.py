"""
biotech_radar_engine.py

Script único para GitHub Actions — ejecuta el pipeline completo:
  1. Descarga universo biotech desde NASDAQ Trader
  2. Obtiene financials desde SEC EDGAR (XBRL)
  3. Obtiene precios y market cap desde yfinance
  4. Puntúa con Modelo Biotech v3.2
  5. Genera radar_resultado.json para el dashboard web

Uso:
  python biotech_radar_engine.py
  python biotech_radar_engine.py --user-agent "Nombre email@x.com"
  python biotech_radar_engine.py --limit 50   # para pruebas rápidas

Dependencias:
  pip install requests pandas yfinance
"""

from __future__ import annotations

import argparse
import io
import json
import math
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests

# ── RUTAS ────────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
OUTPUT_JSON = HERE / "radar_resultado.json"
CACHE_DIR = HERE / "cache_radar"
CACHE_DIR.mkdir(exist_ok=True)

# ── CONFIGURACIÓN ─────────────────────────────────────────────────────────────
NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL  = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
SEC_TICKERS_URL   = "https://data.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS   = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_FACTS         = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
CTGOV_URL         = "https://clinicaltrials.gov/api/v2/studies"

BIOTECH_KEYWORDS = [
    "therapeutics","therapy","biotherapeutics","biopharma","biopharmaceutical",
    "pharmaceutical","pharma","biosciences","bioscience","biotech","biotechnology",
    "genomics","genetics","gene","oncology","immuno","neuro","medicines","molecular",
    "precision","rna","vaccine","vaccines","immunology","rare disease",
]
EXCLUDE_KEYWORDS = [
    "acquisition corp","spac","etf","fund","trust","warrant","unit","right",
    "preferred","notes","bank","bancorp","financial","insurance","casino",
    "bitcoin","crypto","blockchain",
]
MANUAL_TICKERS = {
    "ALNY","ARGX","DNLI","DYN","GPCR","OCUL","SNDX","VKTX","NTLA","BEAM",
    "ABVX","ACRV","SENS","VRTX","ARVN","KROS","IMVT","KYMR","RVMD","WVE",
}
PERIODIC_FORMS  = {"10-Q","10-K","20-F","40-F"}
OFFERING_FORMS  = {"S-1","S-3","F-1","F-3","424B5","424B3","424B2","EFFECT","POS AM"}
ACTIVE_STATUSES = {"RECRUITING","ACTIVE_NOT_RECRUITING","NOT_YET_RECRUITING","ENROLLING_BY_INVITATION"}
TARGET_PHASES   = {"PHASE2","PHASE2_PHASE3","PHASE3"}
TODAY           = pd.Timestamp(datetime.now(timezone.utc).date())


# ══════════════════════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════════════════════

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def safe_float(x: Any) -> float | None:
    if x is None: return None
    if isinstance(x, float) and math.isnan(x): return None
    try:
        s = str(x).replace(",","").replace("$","").strip()
        return None if s.lower() in {"","nan","none","na","n/a"} else float(s)
    except: return None

def millions(x: float | None) -> float | None:
    return round(x / 1_000_000, 2) if x is not None else None

def sec_cash_to_usd(v: float | None) -> float | None:
    if v is None: return None
    return v * 1_000_000 if abs(v) < 1_000_000 else v

def contains_any(text: str, kws: list[str]) -> bool:
    t = str(text).lower()
    return any(k in t for k in kws)

def months_until(x: Any) -> float | None:
    try:
        ts = pd.to_datetime(str(x), errors="coerce", utc=True)
        if pd.isna(ts): return None
        return (pd.Timestamp(ts.date()) - TODAY).days / 30.44
    except: return None

def fetch_text(url: str, headers: dict, retries=3, pause=1.0) -> str:
    for _ in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=30)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last = e
            time.sleep(pause)
    raise RuntimeError(f"No se pudo descargar {url}: {last}")

def get_json_cached(session: requests.Session, url: str, cache_name: str,
                    refresh=False, sleep_s=0.12) -> dict:
    cp = CACHE_DIR / cache_name
    if cp.exists() and not refresh:
        return json.loads(cp.read_text(encoding="utf-8"))
    # Construir headers sin el Host de sesión — dejamos que requests lo derive de la URL
    hdrs = {k: v for k, v in session.headers.items() if k.lower() != "host"}
    r = session.get(url, headers=hdrs, timeout=30)
    time.sleep(sleep_s)
    r.raise_for_status()
    data = r.json()
    cp.write_text(json.dumps(data), encoding="utf-8")
    return data


# ══════════════════════════════════════════════════════════════════════════════
# PASO 1 — UNIVERSO BIOTECH
# ══════════════════════════════════════════════════════════════════════════════

def build_universe(limit: int | None = None) -> list[dict]:
    hdr = {"User-Agent": "BiotechRadar/3.0 research script"}
    nasdaq_txt = fetch_text(NASDAQ_LISTED_URL, hdr)
    other_txt  = fetch_text(OTHER_LISTED_URL,  hdr)

    def parse_pipe(txt):
        lines = [l for l in txt.splitlines() if "File Creation Time" not in l]
        return pd.read_csv(io.StringIO("\n".join(lines)), sep="|")

    nasdaq = parse_pipe(nasdaq_txt)
    other  = parse_pipe(other_txt)

    suffix_pats = [
        r"\s*-\s*(common stock|ordinary shares|american depositary.*|ads|adr).*$",
        r"\s*(common stock|ordinary shares|class [ab]).*$",
    ]
    def clean_name(n):
        n = str(n).strip()
        for p in suffix_pats:
            n = re.sub(p, "", n, flags=re.I)
        return re.sub(r"\s+", " ", n).strip(" -,")

    rows = []
    for df, sym_col in [(nasdaq, "Symbol"), (other, "ACT Symbol")]:
        for _, row in df.iterrows():
            ticker = str(row.get(sym_col,"")).strip().replace("$","-")
            name   = str(row.get("Security Name","")).strip()
            if not ticker or re.search(r"[\^/]", ticker): continue
            clean  = clean_name(name)
            inc    = contains_any(clean, BIOTECH_KEYWORDS) or ticker.upper() in MANUAL_TICKERS
            exc    = contains_any(name,  EXCLUDE_KEYWORDS)
            if inc and not exc:
                rows.append({"ticker": ticker.upper(), "company_name": clean})

    seen, out = set(), []
    for r in rows:
        if r["ticker"] not in seen:
            seen.add(r["ticker"])
            out.append(r)

    out.sort(key=lambda x: x["ticker"])
    if limit: out = out[:limit]
    print(f"Universo: {len(out)} tickers biotech")
    return out


# ══════════════════════════════════════════════════════════════════════════════
# PASO 2 — SEC FINANCIALS
# ══════════════════════════════════════════════════════════════════════════════

CASH_TAGS    = ["CashAndCashEquivalentsAtCarryingValue",
                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents","Cash"]
ST_INV_TAGS  = ["ShortTermInvestments","MarketableSecuritiesCurrent","AvailableForSaleSecuritiesCurrent"]
DEBT_TAGS    = ["LongTermDebtCurrent","ShortTermBorrowings","LongTermDebtNoncurrent","ConvertibleNotesPayable"]
OPCF_TAGS    = ["NetCashProvidedByUsedInOperatingActivities"]
NETLOSS_TAGS = ["NetIncomeLoss","ProfitLoss"]
RD_TAGS      = ["ResearchAndDevelopmentExpense"]
GNA_TAGS     = ["GeneralAndAdministrativeExpense"]

def units_for_tag(facts: dict, tag: str) -> list[dict]:
    for ns in ("us-gaap", "dei"):
        item = facts.get("facts",{}).get(ns,{}).get(tag)
        if item:
            rows = []
            for unit, vals in item.get("units",{}).items():
                for v in vals:
                    rows.append({**v, "unit": unit, "tag": tag})
            return rows
    return []

def latest_instant(facts, tags, forms=None):
    cands = []
    for tag in tags:
        for r in units_for_tag(facts, tag):
            if "val" not in r: continue
            if forms and r.get("form","") not in forms: continue
            if r.get("unit") not in {"USD","shares"}: continue
            cands.append(r)
    if not cands: return None, None
    cands.sort(key=lambda r: (str(r.get("end","")), str(r.get("filed",""))), reverse=True)
    b = cands[0]
    return safe_float(b.get("val")), b.get("tag")

def latest_duration(facts, tags, forms=None, max_days=120):
    cands = []
    for tag in tags:
        for r in units_for_tag(facts, tag):
            if "val" not in r or r.get("unit") != "USD": continue
            if forms and r.get("form","") not in forms: continue
            try:
                s = pd.to_datetime(r.get("start"), errors="coerce")
                e = pd.to_datetime(r.get("end"),   errors="coerce")
                if pd.isna(s) or pd.isna(e): continue
                days = (e - s).days
                if days < 60 or days > max_days: continue
            except: continue
            cands.append(r)
    if not cands: return None, None
    cands.sort(key=lambda r: (str(r.get("end","")), str(r.get("filed",""))), reverse=True)
    b = cands[0]
    return safe_float(b.get("val")), b.get("tag")

def sum_latest(facts, tags):
    total, used = 0.0, []
    for tag in tags:
        v, t = latest_instant(facts, [tag], PERIODIC_FORMS)
        if v is not None:
            total += v
            used.append(t or tag)
    return (total if used else None), used

def get_sec_financials(universe: list[dict], session: requests.Session) -> dict[str, dict]:
    # Cargar mapa CIK
    cik_data = get_json_cached(session, SEC_TICKERS_URL, "company_tickers.json")
    cik_map  = {str(v.get("ticker","")).upper(): int(v["cik_str"])
                for v in cik_data.values() if v.get("ticker")}

    results = {}
    total = len(universe)
    for i, company in enumerate(universe, 1):
        ticker = company["ticker"]
        cik    = cik_map.get(ticker)
        if not cik:
            results[ticker] = {"error": "sin_cik"}
            continue
        c10 = str(cik).zfill(10)
        try:
            subs  = get_json_cached(session, SEC_SUBMISSIONS.format(cik=c10), f"subs_{c10}.json")
            facts = get_json_cached(session, SEC_FACTS.format(cik=c10),       f"facts_{c10}.json")

            # Filings recientes — señales dilución
            recent = subs.get("filings",{}).get("recent",{})
            forms_list  = recent.get("form",[])
            dates_list  = recent.get("filingDate",[])
            cutoff_180  = (TODAY - pd.Timedelta(days=180)).isoformat()
            cutoff_365  = (TODAY - pd.Timedelta(days=365)).isoformat()
            offering_180 = any(f in OFFERING_FORMS and d >= cutoff_180
                               for f,d in zip(forms_list, dates_list))
            offering_365 = any(f in OFFERING_FORMS and d >= cutoff_365
                               for f,d in zip(forms_list, dates_list))

            # Métricas XBRL
            cash,  _  = latest_instant(facts, CASH_TAGS,  PERIODIC_FORMS)
            sti,   _  = sum_latest(facts, ST_INV_TAGS)
            debt,  _  = sum_latest(facts, DEBT_TAGS)
            opcf,  _  = latest_duration(facts, OPCF_TAGS,    PERIODIC_FORMS)
            netloss,_ = latest_duration(facts, NETLOSS_TAGS, PERIODIC_FORMS)
            rd,    _  = latest_duration(facts, RD_TAGS,      PERIODIC_FORMS)
            gna,   _  = latest_duration(facts, GNA_TAGS,     PERIODIC_FORMS)
            shares,_  = latest_instant(facts, ["EntityCommonStockSharesOutstanding"])

            cash_total = None
            if cash is not None or sti is not None:
                cash_total = (cash or 0) + (sti[0] if isinstance(sti, tuple) else (sti or 0))

            # Burn rate
            q_burn = None
            if opcf is not None and opcf < 0:
                q_burn = abs(opcf)
            elif netloss is not None and netloss < 0:
                q_burn = abs(netloss)
            elif rd or gna:
                q_burn = (rd or 0) + (gna or 0)

            m_burn   = q_burn / 3 if q_burn and q_burn > 0 else None
            cash_m   = millions(cash_total)
            runway   = (cash_total / m_burn) if cash_total and m_burn and m_burn > 0 else None
            debt_m   = millions(debt[0] if isinstance(debt, tuple) else debt)
            cps      = millions(cash_total / shares) if cash_total and shares and shares > 0 else None

            results[ticker] = {
                "cash": cash_m,
                "debt": debt_m or 0,
                "quarterly_burn": millions(q_burn),
                "operating_cf_quarter": millions(opcf),
                "cash_runway_months": round(runway, 1) if runway else None,
                "shares_outstanding": shares,
                "cash_per_share": cps,
                "offering_180d": offering_180,
                "offering_365d": offering_365,
                "dilution_risk": _classify_dilution(runway, offering_180, offering_365),
                "sec_quality": "GOOD" if cash_m and q_burn else ("PARTIAL" if cash_m else "LOW"),
            }
        except Exception as e:
            results[ticker] = {"error": str(e)[:120]}
        if i % 50 == 0:
            print(f"  SEC: {i}/{total}")
        time.sleep(0.12)

    print(f"SEC financials: {sum(1 for v in results.values() if 'error' not in v)}/{total} OK")
    return results

def _classify_dilution(runway, off180, off365):
    if runway and runway < 9:  return "HIGH"
    if off180 and (not runway or runway < 18): return "HIGH"
    if runway and runway < 12: return "HIGH"
    if off180:  return "MEDIUM"
    if off365:  return "MEDIUM"
    if runway and runway >= 18: return "LOW"
    return "UNKNOWN"


# ══════════════════════════════════════════════════════════════════════════════
# PASO 3 — YFINANCE PRECIOS
# ══════════════════════════════════════════════════════════════════════════════

def get_prices(tickers: list[str], batch_size=100) -> dict[str, dict]:
    try:
        import yfinance as yf
    except ImportError:
        print("yfinance no instalado — sin datos de precio")
        return {}

    results = {}
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i+batch_size]
        try:
            raw = yf.download(batch, period="1d", auto_adjust=True,
                              progress=False, threads=True)
            if len(batch) == 1:
                t = batch[0]
                if not raw.empty and "Close" in raw.columns:
                    p = safe_float(raw["Close"].iloc[-1])
                    if p and p > 0: results[t] = {"price": p}
            else:
                if "Close" in raw.columns.get_level_values(0) and not raw.empty:
                    closes  = raw["Close"].iloc[-1]
                    volumes = raw["Volume"].iloc[-1] if "Volume" in raw.columns.get_level_values(0) else pd.Series()
                    for t in batch:
                        p = safe_float(closes.get(t))
                        v = safe_float(volumes.get(t)) if not volumes.empty else None
                        if p and p > 0:
                            results[t] = {"price": p, "volume": v}
        except Exception as e:
            print(f"  yfinance batch error: {e}")
        if i + batch_size < len(tickers):
            time.sleep(0.5)

    # fast_info para market_cap y shares
    print(f"  yfinance fast_info para {len(results)} tickers...")
    for t, data in results.items():
        try:
            fi = yf.Ticker(t).fast_info
            mc = safe_float(getattr(fi, "market_cap", None))
            sh = safe_float(getattr(fi, "shares", None))
            if mc and mc > 0: data["market_cap"] = mc
            if sh and sh > 0: data["shares_outstanding"] = sh
        except: pass
        time.sleep(0.05)

    print(f"Precios: {len(results)}/{len(tickers)} OK")
    return results


# ══════════════════════════════════════════════════════════════════════════════
# PASO 4 — CLINICAL TRIALS (ligero — solo ensayos activos Ph2/3)
# ══════════════════════════════════════════════════════════════════════════════

CORP_PAT = r"\b(incorporated|inc\.?|corp\.?|ltd\.?|limited|plc|s\.a\.|sa|ag|nv|llc|co\.?|company|holdings?)\b"

def clean_for_ct(name: str) -> str:
    n = re.sub(r"\s*-\s*(common stock|ordinary shares|american depositary.*).*$", "", name, flags=re.I)
    n = re.sub(CORP_PAT, "", n, flags=re.I)
    n = re.sub(r"[^A-Za-z0-9 ']", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return " ".join(n.split()[:5])

def get_trials(universe: list[dict]) -> dict[str, list[dict]]:
    results = {c["ticker"]: [] for c in universe}
    total = len(universe)
    hdrs  = {"User-Agent": "BiotechRadar/3.0 research script"}

    for i, company in enumerate(universe, 1):
        ticker = company["ticker"]
        query  = clean_for_ct(company["company_name"])
        if not query: continue
        ck = CACHE_DIR / f"ct_{re.sub(r'[^A-Za-z0-9]','_',ticker)}.json"
        try:
            if ck.exists():
                payload = json.loads(ck.read_text(encoding="utf-8"))
            else:
                r = requests.get(CTGOV_URL, headers=hdrs, timeout=40, params={
                    "query.spons": query, "pageSize": 50, "format": "json"
                })
                r.raise_for_status()
                payload = r.json()
                ck.write_text(json.dumps(payload), encoding="utf-8")
                time.sleep(0.15)

            for study in payload.get("studies", []):
                proto  = study.get("protocolSection", {})
                design = proto.get("designModule", {})
                status = proto.get("statusModule", {})
                phases = design.get("phases", [])
                overall = status.get("overallStatus")
                if not any(p in TARGET_PHASES for p in phases): continue
                if overall not in ACTIVE_STATUSES | {"COMPLETED"}: continue
                conds = proto.get("conditionsModule",{}).get("conditions",[])
                arms  = proto.get("armsInterventionsModule",{})
                interventions = [x.get("name") for x in arms.get("interventions",[]) if x.get("name")]
                sponsor = proto.get("sponsorCollaboratorsModule",{}).get("leadSponsor",{}).get("name","")
                pcd = status.get("primaryCompletionDateStruct",{}).get("date","")
                enroll = design.get("enrollmentInfo",{}).get("count")
                results[ticker].append({
                    "nct_id": proto.get("identificationModule",{}).get("nctId",""),
                    "phases": phases,
                    "overall_status": overall,
                    "conditions": conds,
                    "interventions": interventions,
                    "lead_sponsor": sponsor,
                    "primary_completion_date": pcd,
                    "enrollment": enroll,
                })
        except Exception as e:
            pass
        if i % 50 == 0:
            print(f"  ClinicalTrials: {i}/{total}")

    found = sum(1 for v in results.values() if v)
    print(f"ClinicalTrials: {found}/{total} con ensayos")
    return results


# ══════════════════════════════════════════════════════════════════════════════
# PASO 5 — SCORING v3.2
# ══════════════════════════════════════════════════════════════════════════════

PHASE_W = {"PHASE3":3,"PHASE2_PHASE3":2,"PHASE2":1}
BIG_PHARMA = ["pfizer","novartis","roche","genentech","merck","msd","bristol","bms",
              "abbvie","eli lilly","lilly","johnson","janssen","sanofi","astrazeneca",
              "gsk","glaxosmithkline","takeda","amgen","biogen","gilead","novo nordisk",
              "bayer","boehringer","daiichi","astellas","ucb","ipsen","servier","sobi","chugai"]

AREA_TERMS = {
    "Oncology":     ["cancer","carcinoma","tumor","tumour","neoplasm","lymphoma","leukemia","myeloma","sarcoma","melanoma","glioma"],
    "Rare disease": ["rare","duchenne","hemophilia","orphan","huntington","ataxia","dystrophy","spinal muscular","als ","amyotrophic"],
    "CNS":          ["alzheimer","parkinson","depression","schizophrenia","epilepsy","migraine","autism","cns","neurolog","multiple sclerosis"],
    "Autoimmune":   ["lupus","psoriasis","dermatitis","colitis","crohn","arthritis","autoimmune","asthma","myasthenia","cidp","igan"],
    "Ophthalmic":   ["macular degeneration","amd","retina","retinal","diabetic retinopathy","glaucoma","ophthalm","ocular","geographic atrophy"],
    "Metabolic":    ["obesity","diabetes","nash","mash","metabolic","glucose","glp-1","insulin resistance"],
    "Cardiovascular":["cardiac","cardiomyopathy","heart failure","coronary","hypertension","atherosclerosis","myocardial","atrial fibrillation","cardiovascular"],
}
AREA_POS = {
    "Oncology":      (0.18, 0.065),
    "Rare disease":  (0.35, 0.20),
    "CNS":           (0.25, 0.095),
    "Autoimmune":    (0.30, 0.125),
    "Ophthalmic":    (0.55, 0.20),
    "Metabolic":     (0.30, 0.12),
    "Cardiovascular":(0.65, 0.15),
    "Other":         (0.28, 0.125),
}

def detect_area(conds: list[str]) -> str:
    t = " ".join(conds).lower()
    for area, terms in AREA_TERMS.items():
        if any(term in t for term in terms):
            return area
    return "Other"

def score_company(ticker: str, company_name: str,
                  trials: list[dict],
                  fin: dict,
                  prices: dict) -> dict:
    score = 0.0
    reasons = []
    hard_fails = []
    RUNWAY_CAP = 60

    # ── Fase ──────────────────────────────────────────────────
    best_phase_w = 0
    for tr in trials:
        for p in tr.get("phases",[]):
            best_phase_w = max(best_phase_w, PHASE_W.get(p,0))
    phase_pts = {3:2.0, 2:1.5, 1:1.0, 0:0.0}[best_phase_w]
    score += phase_pts
    if best_phase_w == 3:
        best_phase = "PHASE3"; reasons.append("Fase III detectada (+2).")
    elif best_phase_w == 2:
        best_phase = "PHASE2_PHASE3"; reasons.append("Fase II/III detectada (+1.5).")
    elif best_phase_w == 1:
        best_phase = "PHASE2"; reasons.append("Fase II detectada (+1).")
    else:
        best_phase = "NONE"
        hard_fails.append("Sin Fase II/III.")
        reasons.append("Sin Fase II/III (+0).")

    # ── Ensayos activos ───────────────────────────────────────
    n_active = sum(1 for t in trials if t.get("overall_status") in ACTIVE_STATUSES)
    n_trials = len(trials)
    if n_active >= 3:   pts = 2.0; reasons.append(f"{n_active} ensayos activos (+2).")
    elif n_active >= 1: pts = 1.0; reasons.append(f"{n_active} ensayo(s) activo(s) (+1).")
    else:
        pts = 0.0
        hard_fails.append("Sin ensayos activos." if n_trials else "Sin ensayos válidos.")
        reasons.append("Sin ensayos activos (+0).")
    score += pts

    # ── Catalizador ───────────────────────────────────────────
    catalyst_months_list = []
    for tr in trials:
        m = months_until(tr.get("primary_completion_date"))
        if m is not None and m >= 0:
            catalyst_months_list.append((m, tr.get("primary_completion_date","")))
    catalyst_months_list.sort(key=lambda x: x[0])
    next_cat_m    = catalyst_months_list[0][0] if catalyst_months_list else None
    next_cat_date = catalyst_months_list[0][1] if catalyst_months_list else ""
    if next_cat_m is not None and 3 <= next_cat_m <= 9:
        pts = 2.0; reasons.append(f"Catalizador óptimo 3-9m: {next_cat_date} (+2).")
    elif next_cat_m is not None and next_cat_m <= 12:
        pts = 1.0; reasons.append(f"Catalizador en 12m: {next_cat_date} (+1).")
    elif next_cat_m is not None and next_cat_m <= 18:
        pts = 0.5; reasons.append(f"Catalizador en 18m: {next_cat_date} (+0.5).")
    else:
        pts = 0.0
        hard_fails.append("Sin catalizador ≤12m.")
        reasons.append("Sin catalizador claro ≤12m (+0).")
    score += pts

    # ── Diversificación ───────────────────────────────────────
    all_conds  = list({c for t in trials for c in t.get("conditions",[])})
    all_drugs  = list({d for t in trials for d in t.get("interventions",[])})
    n_c, n_d   = len(all_conds), len(all_drugs)
    if n_d >= 3 or n_c >= 3:   pts = 2.0; reasons.append(f"Pipeline diversificado ≥3 activos/indicaciones (+2).")
    elif n_d >= 2 or n_c >= 2: pts = 1.0; reasons.append(f"Diversificación parcial (+1).")
    else:                       pts = 0.0; reasons.append("Single-asset probable (+0).")
    score += pts

    # ── Enrollment ────────────────────────────────────────────
    enrolls = [safe_float(t.get("enrollment")) for t in trials if safe_float(t.get("enrollment"))]
    max_enroll = max(enrolls) if enrolls else None
    if max_enroll and max_enroll >= 300:   pts = 2.0; reasons.append(f"Enrollment máx. {int(max_enroll)} (+2).")
    elif max_enroll and max_enroll >= 100: pts = 1.0; reasons.append(f"Enrollment máx. {int(max_enroll)} (+1).")
    else:                                  pts = 0.0; reasons.append("Tamaño muestral bajo/N/D (+0).")
    score += pts

    # ── Partnership ───────────────────────────────────────────
    co_lower = company_name.lower()
    co_is_bp = any(bp in co_lower for bp in BIG_PHARMA)
    sponsors = [t.get("lead_sponsor","").lower() for t in trials]
    ext_bp   = [s for s in sponsors
                if any(bp in s for bp in BIG_PHARMA)
                and not any(w in s for w in co_lower.split() if len(w)>4)]
    if co_is_bp:           pts = 0.0; reasons.append("Empresa es Big Pharma, no aplica partnership (+0).")
    elif ext_bp:           pts = 2.0; reasons.append(f"Partnership Big Pharma: '{ext_bp[0]}' (+2).")
    elif any(s for s in sponsors if s and not any(w in s for w in co_lower.split() if len(w)>4)):
                           pts = 0.5; reasons.append("Sponsor externo detectado (+0.5).")
    else:                  pts = 0.0; reasons.append("Sin partnership Big Pharma (+0).")
    score += pts

    # ── Área y PoS ────────────────────────────────────────────
    area = detect_area(all_conds)
    ph3, ph2 = AREA_POS.get(area, (0.28, 0.125))
    pos = ph3 if "PHASE3" in best_phase else ph2
    if pos >= 0.50:   pts = 2.0; reasons.append(f"PoS alta {area} {pos:.0%} (+2).")
    elif pos >= 0.20: pts = 1.0; reasons.append(f"PoS media {area} {pos:.0%} (+1).")
    else:             pts = 0.0; reasons.append(f"PoS baja {area} {pos:.0%} (+0).")
    score += pts

    # ── Finanzas ──────────────────────────────────────────────
    cashflow_pos = False
    runway_display = None

    if fin and "error" not in fin:
        cash_m  = safe_float(fin.get("cash"))
        cash_usd = sec_cash_to_usd(cash_m)
        debt_m  = safe_float(fin.get("debt")) or 0
        runway  = safe_float(fin.get("cash_runway_months"))
        opcf    = safe_float(fin.get("operating_cf_quarter"))
        dilution = str(fin.get("dilution_risk","")).lower()

        pdata   = prices.get(ticker, {})
        mc      = safe_float(pdata.get("market_cap"))
        price   = safe_float(pdata.get("price"))
        volume  = safe_float(pdata.get("volume"))
        debt_usd = sec_cash_to_usd(debt_m * 1e6 if debt_m and debt_m < 1e6 else debt_m) or 0
        ev = (mc + debt_usd - (cash_usd or 0)) if mc is not None else None

        # Runway / cashflow
        cashflow_pos = opcf is not None and opcf > 0
        if cashflow_pos:
            pts = 2.0; reasons.append("Cash flow operativo positivo: sin riesgo burn (+2).")
            runway_display = RUNWAY_CAP
        elif runway and runway >= 24:
            pts = 2.0; reasons.append(f"Runway {runway:.0f}m (+2).")
            runway_display = min(runway, RUNWAY_CAP)
        elif runway and runway >= 18:
            pts = 1.5; reasons.append(f"Runway {runway:.0f}m (+1.5).")
            runway_display = min(runway, RUNWAY_CAP)
        elif runway and runway >= 12:
            pts = 1.0; reasons.append(f"Runway {runway:.0f}m (+1).")
            runway_display = min(runway, RUNWAY_CAP)
        else:
            pts = 0.0; hard_fails.append("Runway <12m.")
            reasons.append("Runway insuficiente (+0).")
            runway_display = runway or 0
        score += pts

        # Dilución
        if "low" in dilution or dilution in {"none",""}:
            pts = 2.0; reasons.append("Dilución baja (+2).")
        elif "medium" in dilution:
            pts = 1.0; reasons.append("Dilución media (+1).")
        else:
            pts = 0.0; hard_fails.append("Dilución alta.")
            reasons.append("Dilución alta (+0).")
        score += pts

        # Cash/EV
        if cash_usd is not None and ev is not None:
            if ev <= 0:
                pts = 2.0; reasons.append(f"EV negativo — caja > market cap (+2).")
            elif cash_usd >= ev:
                pts = 1.5; reasons.append(f"Caja ${cash_m:.0f}M ≥ EV (+1.5).")
            elif cash_usd >= 0.5 * ev:
                pts = 1.0; reasons.append(f"Caja ${cash_m:.0f}M ≥ 50% EV (+1).")
            else:
                pts = 0.0; reasons.append(f"Caja ${cash_m:.0f}M < 50% EV (+0).")
        else:
            pts = 0.0; reasons.append("Sin datos caja/EV (+0).")
        score += pts

        # Oportunidad tamaño
        if mc is not None:
            if mc < 50e6:           opp = -1.0; reasons.append("Market cap <50M: riesgo liquidez (-1).")
            elif mc < 100e6:        opp =  0.5; reasons.append("Market cap 50-100M: ineficiencia posible (+0.5).")
            elif mc <= 5e9:         opp =  2.0; reasons.append("Market cap 100M-5B: rango objetivo (+2).")
            elif mc <= 10e9:        opp =  0.5; reasons.append("Market cap 5-10B (+0.5).")
            elif mc <= 20e9:        opp = -1.5; reasons.append("Market cap 10-20B (-1.5).")
            else:                   opp = -3.0; reasons.append("Market cap >20B (-3).")
            score += max(-4.0, min(4.0, opp))
        if volume is not None and volume < 100_000:
            score -= 1.0; reasons.append("Volumen bajo <100k/día (-1).")
    else:
        score += 1.0
        reasons.append("Sin datos financieros — neutral (+1).")
        cash_m = ev = mc = price = volume = runway = None
        dilution = "UNKNOWN"
        cash_usd = debt_usd = None

    # ── Penalizaciones ────────────────────────────────────────
    if n_trials == 0:   score = min(score, 6.0)
    if len(hard_fails) >= 2: score = min(score, 11.0)
    elif len(hard_fails) == 1: score = min(score, 14.0)
    score = max(0.0, min(20.0, round(score, 2)))

    verdict = ("PRIORIDAD ABSOLUTA" if score >= 18
               else "ANALIZAR" if score >= 15
               else "WATCHLIST" if score >= 12
               else "DESCARTAR")
    if len(hard_fails) >= 2: verdict = "DESCARTAR"

    return {
        "ticker": ticker,
        "company_name": company_name,
        "score": score,
        "verdict": verdict,
        "hard_fail_count": len(hard_fails),
        "hard_fails": hard_fails,
        "reasons": reasons,
        "n_trials": n_trials,
        "n_active": n_active,
        "next_catalyst_date": next_cat_date,
        "next_catalyst_months": round(next_cat_m, 1) if next_cat_m is not None else None,
        "therapeutic_area": area,
        "base_pos": pos,
        "max_enrollment": int(max_enroll) if max_enroll else None,
        "cashflow_positive": cashflow_pos,
        "runway_months": safe_float(fin.get("cash_runway_months")) if fin and "error" not in fin else None,
        "runway_display": round(runway_display, 1) if runway_display is not None else None,
        "cash_m": safe_float(fin.get("cash")) if fin and "error" not in fin else None,
        "dilution_risk": str(fin.get("dilution_risk","")) if fin and "error" not in fin else "UNKNOWN",
        "market_cap": prices.get(ticker,{}).get("market_cap"),
        "price": prices.get(ticker,{}).get("price"),
        "enterprise_value": ev if fin and "error" not in fin else None,
        "partnership_big_pharma": bool(ext_bp) if not co_is_bp else False,
    }


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-agent", default="BiotechRadar davidamor84 contact@example.com")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--skip-ct", action="store_true", help="Saltar ClinicalTrials (usa caché)")
    args = parser.parse_args()

    print(f"=== Biotech Radar Engine — {now_iso()} ===")

    # Paso 1 — Universo
    universe = build_universe(args.limit)

    # Paso 2 — SEC
    sec_session = requests.Session()
    sec_session.headers.update({
        "User-Agent": args.user_agent,
        "Accept-Encoding": "gzip, deflate",
    })
    print("Descargando SEC financials...")
    try:
        financials = get_sec_financials(universe, sec_session)
        print(f"SEC OK: {sum(1 for v in financials.values() if 'error' not in v)} tickers con datos")
    except Exception as e:
        print(f"AVISO: SEC financials fallaron ({e}) — continuando sin datos financieros SEC")
        financials = {c["ticker"]: {"error": str(e)} for c in universe}

    # Paso 3 — Precios
    print("Descargando precios yfinance...")
    tickers_list = [c["ticker"] for c in universe]
    prices = get_prices(tickers_list)

    # Paso 4 — ClinicalTrials
    print("Consultando ClinicalTrials...")
    trials_map = get_trials(universe)

    # Paso 5 — Scoring
    print("Calculando scores v3.2...")
    scored = []
    for company in universe:
        t   = company["ticker"]
        fin = financials.get(t, {})
        trs = trials_map.get(t, [])
        prc = prices
        s   = score_company(t, company["company_name"], trs, fin, prc)
        scored.append(s)

    scored.sort(key=lambda x: (-x["score"], x["hard_fail_count"]))

    # Estadísticas
    dist = {}
    for s in scored:
        dist[s["verdict"]] = dist.get(s["verdict"], 0) + 1

    output = {
        "generado": now_iso(),
        "total_empresas": len(scored),
        "distribucion": dist,
        "candidatas": scored,
    }

    OUTPUT_JSON.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== COMPLETADO ===")
    print(f"Empresas: {len(scored)}")
    print(f"Distribución: {dist}")
    print(f"JSON: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
