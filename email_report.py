#!/usr/bin/env python3
"""
Conviction Portfolio Tracker — Daily Morning Email
Sends HTML portfolio snapshot via SMTP (same secrets as market-briefing).

Env vars required:
  SMTP_EMAIL          — sender Gmail address
  SMTP_PASSWORD       — Gmail app password
  NOTIFICATION_EMAIL  — recipient address
"""

import json
import logging
import os
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.policy import EmailPolicy

import pandas as pd
import yfinance as yf

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Portfolio definition (keep in sync with app.py) ──────────────────────────

TOTAL_CAPITAL = 25_000

# (ticker, company, theme, tier, target_gain%, stop_loss%, trail_pct, alloc_usd, notes)
PORTFOLIO_DEF = [
    ("FCX",  "Freeport-McMoRan",      "Critical Minerals", 1, 0.40, 0.15, 0.15, 3_000, "Copper #1 input to AI infra + energy transition"),
    ("CEG",  "Constellation Energy",  "Critical Minerals", 1, 0.35, 0.15, 0.15, 2_000, "Nuclear power for datacenters; MSFT offtake deal"),
    ("SQM",  "Soc. Quimica y Minera", "Critical Minerals", 1, 0.45, 0.18, 0.15, 2_000, "Chilean lithium; lowest-cost structure in sector"),
    ("SCCO", "Southern Copper",       "Critical Minerals", 1, 0.40, 0.15, 0.15, 1_500, "Pure-play copper; better margins than FCX"),
    ("VALE", "Vale",                  "Critical Minerals", 1, 0.35, 0.15, 0.15, 1_500, "Brazil iron ore + nickel; cheap on fundamentals"),
    ("MELI", "MercadoLibre",          "LATAM Growth",      2, 0.40, 0.12, 0.12, 2_500, "Best LATAM play: e-commerce + fintech + logistics"),
    ("GEV",  "GE Vernova",            "AI Infrastructure", 2, 0.40, 0.12, 0.12, 2_000, "Grid infra for datacenters + renewables"),
    ("LLY",  "Eli Lilly",             "Longevity / GLP-1", 2, 0.35, 0.12, 0.12, 2_000, "Strongest GLP-1 pipeline; cognitive + longevity"),
    ("PLTR", "Palantir",              "AI Infrastructure", 2, 0.50, 0.12, 0.12, 1_500, "AI agents on real operational data; gov + commercial"),
    ("MSFT", "Microsoft",             "AI Infrastructure", 2, 0.30, 0.12, 0.12, 1_500, "Copilot + Azure AI; lowest-risk AI exposure"),
    ("ASTS", "AST SpaceMobile",       "Satellite",         3, 1.00, 0.30, 0.20, 1_250, "Direct-to-cell satellite; binary 0 or 10x"),
    ("NVO",  "Novo Nordisk",          "Longevity / GLP-1", 3, 0.35, 0.20, 0.20, 1_000, "GLP-1 diversifier; oral semaglutide pipeline"),
    ("SPGI", "S&P Global",            "AI Infrastructure", 3, 0.25, 0.12, 0.12, 1_000, "Defensive data moat; structural pricing power"),
    ("NU",   "Nu Holdings",           "LATAM Growth",      3, 0.60, 0.20, 0.20, 1_000, "Highest-growth LATAM fintech"),
    ("ZTS",  "Zoetis",                "Longevity / GLP-1", 3, 0.30, 0.20, 0.20,   750, "Animal health moat + pet GLP-1 optionality"),
]

TICKERS      = [r[0] for r in PORTFOLIO_DEF]
MACRO_TICKERS = ["HG=F", "LIT", "DX-Y.NYB", "BRL=X", "SPY", "QQQ", "^VIX", "GC=F"]

CHINA_CHECKS = [
    "PBOC rate cut or RRR reduction announced",
    "China infrastructure spending package announced",
    "China PMI Manufacturing > 50 (expansion)",
    "China copper imports surge (monthly data)",
    "China-US trade deal / tariff reduction news",
    "LATAM trade corridor agreement signed",
]
AI_CAPEX_CHECKS = [
    "Microsoft quarterly capex UP vs prior year",
    "Google/Alphabet quarterly capex UP vs prior year",
    "Meta quarterly capex UP vs prior year",
    "Amazon/AWS quarterly capex UP vs prior year",
    "New datacenter power purchase agreement (nuclear/grid)",
    "US AI infrastructure bill / CHIPS Act expansion",
]
GLP1_CHECKS = [
    "FDA approval for new GLP-1 indication (LLY or NVO)",
    "Medicare/Medicaid expanding GLP-1 coverage",
    "LLY oral GLP-1 trial positive data",
    "NVO oral semaglutide approval progress",
    "No GLP-1 price cap legislation advancing",
    "ZTS animal health GLP-1 pipeline update",
]

THEME_EMOJI = {
    "Critical Minerals": "⛏️",
    "LATAM Growth":      "🌎",
    "AI Infrastructure": "🤖",
    "Longevity / GLP-1": "🧬",
    "Satellite":         "🛸",
}

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio_data.json")


# ── Data loading ─────────────────────────────────────────────────────────────

def load_data() -> dict:
    defaults = {
        "positions": {
            t: {"entry_price": None, "position_usd": alloc, "highest_price": None}
            for t, _, _, _, _, _, _, alloc, _ in PORTFOLIO_DEF
        },
        "cash":         0,
        "china_checks": [False] * len(CHINA_CHECKS),
        "ai_checks":    [False] * len(AI_CAPEX_CHECKS),
        "glp1_checks":  [False] * len(GLP1_CHECKS),
    }
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE) as f:
                saved = json.load(f)
            for k, v in defaults.items():
                saved.setdefault(k, v)
            return saved
        except Exception as e:
            log.warning(f"Could not load {DATA_FILE}: {e}")
    return defaults


def fetch_prices() -> dict:
    all_tickers = TICKERS + MACRO_TICKERS
    prices = {t: None for t in all_tickers}
    try:
        raw = yf.download(all_tickers, period="5d", auto_adjust=True, progress=False, threads=True)
        if isinstance(raw.columns, pd.MultiIndex):
            for t in all_tickers:
                try:
                    prices[t] = round(float(raw["Close"][t].dropna().iloc[-1]), 4)
                except Exception:
                    pass
        else:
            prices[all_tickers[0]] = round(float(raw["Close"].dropna().iloc[-1]), 4)
    except Exception:
        for t in all_tickers:
            try:
                hist = yf.Ticker(t).history(period="5d")
                if not hist.empty:
                    prices[t] = round(float(hist["Close"].iloc[-1]), 4)
            except Exception:
                pass
    return prices


# ── Business logic ───────────────────────────────────────────────────────────

def compute_signal(price, entry, highest, stop_pct, trail_pct, target_pct, tier) -> tuple[str, str]:
    if price is None:
        return "—", "none"
    if not entry or entry <= 0:
        return "NOT ENTERED", "none"
    trail_stop = (highest * (1 - trail_pct)) if highest else (entry * (1 - stop_pct))
    hard_stop  = entry * (1 - stop_pct)
    if price < trail_stop or price < hard_stop:
        return "SELL", "sell"
    gain    = (price - entry) / entry
    trim_hi = 0.40 if tier < 3 else 0.60
    trim_lo = 0.25 if tier < 3 else 0.40
    if gain >= trim_hi:
        return "TRIM 25%", "trim"
    if gain >= trim_lo:
        return "TRIM 15%", "trim"
    return "HOLD", "hold"


def theme_regime(prices, china_checks, ai_checks, glp1_checks) -> dict:
    copper       = prices.get("HG=F")
    china_active = sum(1 for c in china_checks if c)
    ai_active    = sum(1 for c in ai_checks if c)
    glp1_active  = sum(1 for c in glp1_checks if c)

    if copper is None:
        minerals = ("NO COPPER DATA", "none")
    elif copper >= 4.30:
        minerals = ("COPPER STRONG — HOLD MINERALS", "hold")
    elif copper >= 4.00:
        minerals = ("COPPER FADING — TRIM MINERALS", "trim")
    else:
        minerals = ("COPPER BROKEN — EXIT MINERALS", "sell")

    brl = prices.get("BRL=X")
    if china_active >= 3:
        latam = ("CHINA STIMULUS ACTIVE — HOLD LATAM", "hold")
    elif brl and brl > 6.0:
        latam = (f"BRL WEAK ({brl:.2f}) — WATCH LATAM", "sell")
    else:
        latam = ("LATAM NEUTRAL — MONITOR", "trim")

    if ai_active >= 4:
        ai = ("AI CAPEX EXPANDING — HOLD AI INFRA", "hold")
    elif ai_active >= 2:
        ai = ("AI CAPEX MIXED — TRIM ON WEAKNESS", "trim")
    else:
        ai = ("AI CAPEX SIGNALS WEAK — REDUCE", "sell")

    if glp1_active >= 4:
        glp1 = ("GLP-1 PIPELINE STRONG — HOLD BIOTECH", "hold")
    elif glp1_active >= 2:
        glp1 = ("GLP-1 MIXED — WATCH PIPELINE", "trim")
    else:
        glp1 = ("GLP-1 HEADWINDS — TRIM BIOTECH", "sell")

    return {
        "Critical Minerals": minerals,
        "LATAM Growth":      latam,
        "AI Infrastructure": ai,
        "Longevity / GLP-1": glp1,
        "Satellite":         ("HOLD unless launch fails — binary bet", "hold"),
    }


# ── HTML email builder ───────────────────────────────────────────────────────

REGIME_BG   = {"hold": "#0a3d22", "trim": "#3d2800", "sell": "#3d0a0a", "none": "#1a1a2e"}
REGIME_FG   = {"hold": "#2ecc71", "trim": "#f39c12", "sell": "#e74c3c", "none": "#aaaaaa"}
REGIME_BD   = {"hold": "#27ae60", "trim": "#f39c12", "sell": "#e74c3c", "none": "#555555"}
SIGNAL_BG   = {"sell": "#c0392b", "trim": "#d68910", "hold": "#1e8449", "none": "#555555"}
SIGNAL_FG   = "#ffffff"


def _pct(v, decimals=1) -> str:
    if v is None:
        return "—"
    return f"{'+'if v>=0 else ''}{v*100:.{decimals}f}%"


def build_html(data: dict, prices: dict) -> str:
    pos_data     = data["positions"]
    cash         = data.get("cash", 0)
    china_checks = data.get("china_checks", [False] * len(CHINA_CHECKS))
    ai_checks    = data.get("ai_checks",    [False] * len(AI_CAPEX_CHECKS))
    glp1_checks  = data.get("glp1_checks",  [False] * len(GLP1_CHECKS))

    regimes = theme_regime(prices, china_checks, ai_checks, glp1_checks)

    now = datetime.now(timezone.utc).strftime("%A %B %-d, %Y at %H:%M UTC")

    # ── Portfolio totals ──────────────────────────────────────────────────────
    total_invested = sum(p["position_usd"] for p in pos_data.values())
    mkt_value = total_gain = 0.0
    sell_count = trim_count = 0
    entered_count = 0

    for t, _, _, tier, tgt_pct, stop_pct, trail_pct, alloc, _ in PORTFOLIO_DEF:
        pos     = pos_data.get(t, {})
        price   = prices.get(t)
        entry   = pos.get("entry_price")
        pusd    = pos.get("position_usd") or alloc
        highest = pos.get("highest_price")
        if price and entry and entry > 0:
            curr_val   = (pusd / entry) * price
            mkt_value += curr_val
            total_gain += curr_val - pusd
            entered_count += 1
            _, sk = compute_signal(price, entry, highest, stop_pct, trail_pct, tgt_pct, tier)
            if sk == "sell": sell_count += 1
            elif sk == "trim": trim_count += 1
        else:
            mkt_value += pusd

    total_acct = mkt_value + cash
    gain_pct   = (total_gain / total_invested * 100) if total_invested > 0 else 0
    gain_color = "#2ecc71" if total_gain >= 0 else "#e74c3c"
    gain_sign  = "+" if total_gain >= 0 else ""

    # ── Alert banner ──────────────────────────────────────────────────────────
    if sell_count > 0:
        alert_bg, alert_fg, alert_txt = "#3d0a0a", "#ff6b6b", f"🚨 {sell_count} SELL SIGNAL{'S' if sell_count>1 else ''} — ACTION REQUIRED"
    elif trim_count > 0:
        alert_bg, alert_fg, alert_txt = "#3d2800", "#f39c12", f"✂️ {trim_count} TRIM SIGNAL{'S' if trim_count>1 else ''} — REVIEW POSITIONS"
    else:
        alert_bg, alert_fg, alert_txt = "#0a3d22", "#2ecc71", "✅ ALL POSITIONS NOMINAL — NO ACTION NEEDED"

    # ── Macro values ──────────────────────────────────────────────────────────
    copper = prices.get("HG=F")
    lit    = prices.get("LIT")
    dxy    = prices.get("DX-Y.NYB")
    brl    = prices.get("BRL=X")
    vix    = prices.get("^VIX")
    spy    = prices.get("SPY")
    gold   = prices.get("GC=F")

    copper_warn = copper is not None and copper < 4.00
    brl_warn    = brl    is not None and brl    > 6.0
    vix_warn    = vix    is not None and vix    > 30

    def macro_val(v, fmt) -> str:
        return fmt.format(v) if v is not None else "—"

    # ── Position rows ─────────────────────────────────────────────────────────
    pos_rows_html = ""
    current_theme = None

    for t, company, theme, tier, tgt_pct, stop_pct, trail_pct, alloc, _ in PORTFOLIO_DEF:
        if theme != current_theme:
            em = THEME_EMOJI.get(theme, "")
            pos_rows_html += f"""
            <tr>
              <td colspan="9" style="background:#1e1b4b;color:#c4b5fd;font-weight:700;
                font-size:11px;text-transform:uppercase;letter-spacing:1px;
                padding:6px 10px;border-bottom:1px solid #3d3d6d;">
                {em} {theme}
              </td>
            </tr>"""
            current_theme = theme

        pos     = pos_data.get(t, {})
        price   = prices.get(t)
        entry   = pos.get("entry_price")
        pusd    = pos.get("position_usd") or alloc
        highest = pos.get("highest_price")

        trail_stop = None
        if entry and entry > 0:
            trail_stop = (highest * (1 - trail_pct)) if highest else (entry * (1 - stop_pct))

        signal_lbl, sig_key = compute_signal(price, entry, highest, stop_pct, trail_pct, tgt_pct, tier)

        if price and entry and entry > 0:
            gpct     = (price - entry) / entry
            gain_str = _pct(gpct)
            gain_col = "#2ecc71" if gpct >= 0 else "#e74c3c"
            curr_val = (pusd / entry) * price
            val_str  = f"${curr_val:,.0f}"
            tgt_str  = f"+{tgt_pct*100:.0f}%"
            stop_str = f"${trail_stop:.2f}" if trail_stop else "—"
        else:
            gain_str = "—"
            gain_col = "#888888"
            val_str  = f"${pusd:,.0f}"
            tgt_str  = f"+{tgt_pct*100:.0f}%"
            stop_str = "—"

        row_bg = "#3d0a0a" if sig_key=="sell" else "#3d2800" if sig_key=="trim" else "#121212"
        sbg    = SIGNAL_BG.get(sig_key, "#555")
        price_str = f"${price:.2f}" if price else "—"
        entry_str = f"${entry:.2f}" if entry else "—"

        pos_rows_html += f"""
        <tr style="background:{row_bg};border-bottom:1px solid #2a2a2a;">
          <td style="padding:6px 8px;font-weight:700;color:#e0e0e0;">{t}</td>
          <td style="padding:6px 8px;color:#c0c0c0;font-size:12px;">{company}</td>
          <td style="padding:6px 8px;color:#e0e0e0;">{price_str}</td>
          <td style="padding:6px 8px;color:#aaaaaa;">{entry_str}</td>
          <td style="padding:6px 8px;color:{gain_col};font-weight:600;">{gain_str}</td>
          <td style="padding:6px 8px;color:#888888;">{stop_str}</td>
          <td style="padding:6px 8px;color:#e0e0e0;">{val_str}</td>
          <td style="padding:6px 8px;color:#aaaaaa;">{tgt_str}</td>
          <td style="padding:6px 8px;text-align:center;">
            <span style="background:{sbg};color:#fff;font-weight:700;font-size:11px;
              padding:2px 8px;border-radius:4px;">{signal_lbl}</span>
          </td>
        </tr>"""

    # ── Regime banners ────────────────────────────────────────────────────────
    regime_html = ""
    for theme in ["Critical Minerals", "LATAM Growth", "AI Infrastructure", "Longevity / GLP-1", "Satellite"]:
        mode_txt, key = regimes[theme]
        em = THEME_EMOJI.get(theme, "")
        bg, fg, bd = REGIME_BG[key], REGIME_FG[key], REGIME_BD[key]
        regime_html += f"""
        <tr>
          <td style="padding:6px 10px;background:{bg};color:{fg};font-weight:700;
            border-left:4px solid {bd};font-size:13px;">
            {em} {theme}
          </td>
          <td style="padding:6px 10px;background:{bg};color:{fg};font-size:13px;">{mode_txt}</td>
        </tr>"""

    # ── Sell signal tracker ───────────────────────────────────────────────────
    sell_checks = [
        ("⛏️ Copper < $4.00/lb for 2+ weeks",              copper_warn),
        ("🇧🇷 BRL/USD > 6.00 (currency stress)",            brl_warn),
        ("📊 VIX > 30 (fear elevated)",                     vix_warn),
        ("🤖 Hyperscaler cuts capex guidance (earnings)",   False),
        ("🧬 FDA rejects major GLP-1 pipeline drug",        False),
        ("🛸 ASTS misses commercial launch milestone",      False),
        ("🌎 US imposes LATAM tariffs / trade escalation",  False),
        ("🟠 China PMI < 49 for two consecutive months",    False),
    ]
    triggered = sum(1 for _, t in sell_checks if t)

    sell_rows_html = ""
    for label, is_t in sell_checks:
        icon = "🔴" if is_t else "✅"
        bg   = "#3d0a0a" if is_t else "#0a1f12"
        sell_rows_html += f"""
        <tr style="background:{bg};">
          <td style="padding:5px 10px;color:#e0e0e0;font-size:13px;">{icon} {label}</td>
        </tr>"""

    if triggered >= 2:
        sell_summary = f'<div style="background:#c0392b;color:#fff;font-weight:700;padding:8px 12px;border-radius:4px;margin-top:8px;">⚠️ {triggered} SIGNALS ACTIVE — REDUCE AFFECTED THEMES 30–50%</div>'
    elif triggered == 1:
        sell_summary = '<div style="background:#d68910;color:#fff;font-weight:700;padding:8px 12px;border-radius:4px;margin-top:8px;">⚠️ 1 SIGNAL ACTIVE — Monitor closely before acting</div>'
    else:
        sell_summary = '<div style="background:#1e8449;color:#fff;font-weight:700;padding:8px 12px;border-radius:4px;margin-top:8px;">✅ No sell signals — All theses intact</div>'

    # ── Checklist status summary ──────────────────────────────────────────────
    china_n  = sum(1 for c in china_checks if c)
    ai_n     = sum(1 for c in ai_checks if c)
    glp1_n   = sum(1 for c in glp1_checks if c)

    def checklist_color(n, total):
        if n >= total * 0.67: return "#2ecc71"
        if n >= total * 0.33: return "#f39c12"
        return "#e74c3c"

    checklist_rows = f"""
    <tr style="background:#121212;border-bottom:1px solid #2a2a2a;">
      <td style="padding:8px 12px;font-size:13px;">
        <span style="color:#c4b5fd;font-weight:700;">⛏️ China / Critical Minerals</span>
      </td>
      <td style="padding:8px 12px;">
        <span style="color:{checklist_color(china_n, len(CHINA_CHECKS))};font-weight:700;font-size:15px;">
          {china_n}/{len(CHINA_CHECKS)}
        </span>
      </td>
      <td style="padding:8px 12px;color:#aaaaaa;font-size:12px;">
        {'Strong bull case' if china_n>=4 else 'Cautious' if china_n>=2 else 'Headwind'}
      </td>
    </tr>
    <tr style="background:#121212;border-bottom:1px solid #2a2a2a;">
      <td style="padding:8px 12px;font-size:13px;">
        <span style="color:#c4b5fd;font-weight:700;">🤖 AI Infrastructure / Capex</span>
      </td>
      <td style="padding:8px 12px;">
        <span style="color:{checklist_color(ai_n, len(AI_CAPEX_CHECKS))};font-weight:700;font-size:15px;">
          {ai_n}/{len(AI_CAPEX_CHECKS)}
        </span>
      </td>
      <td style="padding:8px 12px;color:#aaaaaa;font-size:12px;">
        {'Capex expanding' if ai_n>=4 else 'Mixed' if ai_n>=2 else 'Watch carefully'}
      </td>
    </tr>
    <tr style="background:#121212;">
      <td style="padding:8px 12px;font-size:13px;">
        <span style="color:#c4b5fd;font-weight:700;">🧬 GLP-1 / Longevity Pipeline</span>
      </td>
      <td style="padding:8px 12px;">
        <span style="color:{checklist_color(glp1_n, len(GLP1_CHECKS))};font-weight:700;font-size:15px;">
          {glp1_n}/{len(GLP1_CHECKS)}
        </span>
      </td>
      <td style="padding:8px 12px;color:#aaaaaa;font-size:12px;">
        {'Pipeline strong' if glp1_n>=4 else 'Monitor' if glp1_n>=2 else 'Headwinds'}
      </td>
    </tr>"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Conviction Portfolio — Daily Report</title>
</head>
<body style="margin:0;padding:0;background:#0a0a0a;font-family:Arial,Helvetica,sans-serif;color:#e0e0e0;">
<div style="max-width:800px;margin:0 auto;padding:16px;">

  <!-- Header -->
  <div style="background:#1e1b4b;border-radius:10px;padding:20px 24px;margin-bottom:16px;
              border-left:5px solid #a78bfa;">
    <div style="font-size:22px;font-weight:800;color:#e0e0ff;">
      💼 2026 Conviction Portfolio
    </div>
    <div style="font-size:13px;color:#9090c0;margin-top:4px;">{now}</div>
  </div>

  <!-- Alert Banner -->
  <div style="background:{alert_bg};border-radius:8px;padding:14px 18px;margin-bottom:16px;
              border:2px solid {alert_fg};text-align:center;font-weight:800;
              font-size:15px;color:{alert_fg};">
    {alert_txt}
  </div>

  <!-- Summary Metrics -->
  <table width="100%" cellpadding="0" cellspacing="8" style="margin-bottom:16px;">
    <tr>
      <td style="background:#1a1a2e;border:2px solid #a78bfa;border-radius:8px;
                 padding:12px 16px;width:25%;text-align:center;">
        <div style="font-size:10px;color:#c4b5fd;text-transform:uppercase;letter-spacing:1px;font-weight:700;">Total Account</div>
        <div style="font-size:22px;font-weight:700;color:#fff;margin-top:4px;">${total_acct:,.0f}</div>
        <div style="font-size:11px;color:#888;">Capital: ${TOTAL_CAPITAL:,}</div>
      </td>
      <td style="background:#1a1a2e;border:2px solid #a78bfa;border-radius:8px;
                 padding:12px 16px;width:25%;text-align:center;">
        <div style="font-size:10px;color:#c4b5fd;text-transform:uppercase;letter-spacing:1px;font-weight:700;">Portfolio Value</div>
        <div style="font-size:22px;font-weight:700;color:#fff;margin-top:4px;">${mkt_value:,.0f}</div>
        <div style="font-size:11px;color:#888;">${total_invested:,.0f} invested</div>
      </td>
      <td style="background:#1a1a2e;border:2px solid #a78bfa;border-radius:8px;
                 padding:12px 16px;width:25%;text-align:center;">
        <div style="font-size:10px;color:#c4b5fd;text-transform:uppercase;letter-spacing:1px;font-weight:700;">Total P&amp;L</div>
        <div style="font-size:22px;font-weight:700;color:{gain_color};margin-top:4px;">
          {gain_sign}${total_gain:,.0f}
        </div>
        <div style="font-size:11px;color:{gain_color};">{gain_sign}{gain_pct:.1f}%</div>
      </td>
      <td style="background:#1a1a2e;border:2px solid #a78bfa;border-radius:8px;
                 padding:12px 16px;width:25%;text-align:center;">
        <div style="font-size:10px;color:#c4b5fd;text-transform:uppercase;letter-spacing:1px;font-weight:700;">Cash</div>
        <div style="font-size:22px;font-weight:700;color:#fff;margin-top:4px;">${cash:,.0f}</div>
        <div style="font-size:11px;color:#888;">{entered_count}/15 positions entered</div>
      </td>
    </tr>
  </table>

  <!-- Macro Strip -->
  <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:16px;border-collapse:collapse;
    background:#1a1a2e;border-radius:8px;border:1px solid #3d3d6d;overflow:hidden;">
    <tr style="background:#1e1b4b;">
      <td colspan="8" style="padding:8px 12px;font-size:11px;font-weight:700;
        color:#c4b5fd;text-transform:uppercase;letter-spacing:1px;">📊 Macro Metrics</td>
    </tr>
    <tr style="text-align:center;">
      <td style="padding:10px 8px;border-right:1px solid #2a2a3d;">
        <div style="font-size:10px;color:#aaa;margin-bottom:3px;">🟠 Copper</div>
        <div style="font-weight:700;color:{'#e74c3c' if copper_warn else '#e0e0e0'};">
          {macro_val(copper, "${:.3f}")}</div>
      </td>
      <td style="padding:10px 8px;border-right:1px solid #2a2a3d;">
        <div style="font-size:10px;color:#aaa;margin-bottom:3px;">🔋 Lithium (LIT)</div>
        <div style="font-weight:700;color:#e0e0e0;">{macro_val(lit, "${:.2f}")}</div>
      </td>
      <td style="padding:10px 8px;border-right:1px solid #2a2a3d;">
        <div style="font-size:10px;color:#aaa;margin-bottom:3px;">💵 DXY</div>
        <div style="font-weight:700;color:#e0e0e0;">{macro_val(dxy, "{:.2f}")}</div>
      </td>
      <td style="padding:10px 8px;border-right:1px solid #2a2a3d;">
        <div style="font-size:10px;color:#aaa;margin-bottom:3px;">🇧🇷 BRL/USD</div>
        <div style="font-weight:700;color:{'#e74c3c' if brl_warn else '#e0e0e0'};">
          {macro_val(brl, "{:.4f}")}</div>
      </td>
      <td style="padding:10px 8px;border-right:1px solid #2a2a3d;">
        <div style="font-size:10px;color:#aaa;margin-bottom:3px;">📊 VIX</div>
        <div style="font-weight:700;color:{'#e74c3c' if vix_warn else '#e0e0e0'};">
          {macro_val(vix, "{:.1f}")}</div>
      </td>
      <td style="padding:10px 8px;border-right:1px solid #2a2a3d;">
        <div style="font-size:10px;color:#aaa;margin-bottom:3px;">📈 SPY</div>
        <div style="font-weight:700;color:#e0e0e0;">{macro_val(spy, "${:.2f}")}</div>
      </td>
      <td style="padding:10px 8px;border-right:1px solid #2a2a3d;">
        <div style="font-size:10px;color:#aaa;margin-bottom:3px;">📈 QQQ</div>
        <div style="font-weight:700;color:#e0e0e0;">{macro_val(prices.get('QQQ'), "${:.2f}")}</div>
      </td>
      <td style="padding:10px 8px;">
        <div style="font-size:10px;color:#aaa;margin-bottom:3px;">🥇 Gold</div>
        <div style="font-weight:700;color:#e0e0e0;">{macro_val(gold, "${:.0f}")}</div>
      </td>
    </tr>
  </table>

  <!-- Position Table -->
  <div style="background:#1a1a2e;border-radius:8px;border:1px solid #3d3d6d;
              margin-bottom:16px;overflow:hidden;">
    <div style="background:#1e1b4b;padding:8px 12px;font-size:11px;font-weight:700;
                color:#c4b5fd;text-transform:uppercase;letter-spacing:1px;">
      💼 Positions
    </div>
    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
      <tr style="background:#1e1b4b;font-size:10px;color:#9090c0;text-transform:uppercase;
                 letter-spacing:0.5px;">
        <th style="padding:6px 8px;text-align:left;">Ticker</th>
        <th style="padding:6px 8px;text-align:left;">Company</th>
        <th style="padding:6px 8px;text-align:left;">Price</th>
        <th style="padding:6px 8px;text-align:left;">Entry</th>
        <th style="padding:6px 8px;text-align:left;">% Gain</th>
        <th style="padding:6px 8px;text-align:left;">Trail Stop</th>
        <th style="padding:6px 8px;text-align:left;">Value</th>
        <th style="padding:6px 8px;text-align:left;">Target</th>
        <th style="padding:6px 8px;text-align:center;">Signal</th>
      </tr>
      {pos_rows_html}
    </table>
  </div>

  <!-- Theme Regimes -->
  <div style="background:#1a1a2e;border-radius:8px;border:1px solid #3d3d6d;
              margin-bottom:16px;overflow:hidden;">
    <div style="background:#1e1b4b;padding:8px 12px;font-size:11px;font-weight:700;
                color:#c4b5fd;text-transform:uppercase;letter-spacing:1px;">
      🎯 Theme Regimes
    </div>
    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
      {regime_html}
    </table>
  </div>

  <!-- Sell Signal Tracker -->
  <div style="background:#1a1a2e;border-radius:8px;border:1px solid #3d3d6d;
              margin-bottom:16px;overflow:hidden;">
    <div style="background:#1e1b4b;padding:8px 12px;font-size:11px;font-weight:700;
                color:#c4b5fd;text-transform:uppercase;letter-spacing:1px;">
      🚨 Sell Signal Tracker — 2+ signals = reduce affected theme 30–50%
    </div>
    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
      {sell_rows_html}
    </table>
    <div style="padding:8px 10px;">{sell_summary}</div>
  </div>

  <!-- Thesis Checklist Status -->
  <div style="background:#1a1a2e;border-radius:8px;border:1px solid #3d3d6d;
              margin-bottom:16px;overflow:hidden;">
    <div style="background:#1e1b4b;padding:8px 12px;font-size:11px;font-weight:700;
                color:#c4b5fd;text-transform:uppercase;letter-spacing:1px;">
      🔎 Thesis Tracker — Update checklists in the Streamlit app
    </div>
    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
      <tr style="background:#1e1b4b;font-size:10px;color:#9090c0;text-transform:uppercase;">
        <th style="padding:6px 12px;text-align:left;">Checklist</th>
        <th style="padding:6px 12px;text-align:left;">Active</th>
        <th style="padding:6px 12px;text-align:left;">Status</th>
      </tr>
      {checklist_rows}
    </table>
  </div>

  <!-- Footer -->
  <div style="text-align:center;font-size:11px;color:#555;padding:16px 0;">
    Conviction Portfolio Tracker &mdash; 10 Things Coming in 2026<br>
    Update entry prices &amp; checklists in the Streamlit dashboard (port 8507)
  </div>

</div>
</body>
</html>"""

    return html


# ── SMTP send ─────────────────────────────────────────────────────────────────

SMTP_SERVERS = {
    "gmail.com":    "smtp.gmail.com",
    "yahoo.com":    "smtp.mail.yahoo.com",
    "outlook.com":  "smtp-mail.outlook.com",
    "hotmail.com":  "smtp-mail.outlook.com",
}


def send_email(subject: str, html: str) -> bool:
    smtp_email = os.environ.get("SMTP_EMAIL")
    smtp_pass  = os.environ.get("SMTP_PASSWORD")
    to_email   = os.environ.get("NOTIFICATION_EMAIL")

    if not smtp_email or not smtp_pass or not to_email:
        log.warning("SMTP credentials not set — dry run only. Set SMTP_EMAIL, SMTP_PASSWORD, NOTIFICATION_EMAIL.")
        print("\n--- EMAIL WOULD BE SENT ---")
        print(f"To:      {to_email or '(not set)'}")
        print(f"Subject: {subject}")
        print("--- (HTML body omitted) ---\n")
        return False

    domain      = smtp_email.split("@")[-1].lower()
    smtp_server = SMTP_SERVERS.get(domain, f"smtp.{domain}")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = smtp_email
    msg["To"]      = to_email
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(smtp_server, 587) as server:
            server.starttls()
            server.login(smtp_email, smtp_pass)
            policy = EmailPolicy(max_line_length=998, utf8=True)
            server.sendmail(smtp_email, to_email, msg.as_bytes(policy=policy))
        log.info(f"Email sent to {to_email}: {subject}")
        return True
    except Exception as e:
        log.error(f"SMTP error: {e}")
        return False


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    log.info("Fetching prices...")
    prices = fetch_prices()
    fetched = sum(1 for v in prices.values() if v is not None)
    log.info(f"Got prices for {fetched}/{len(prices)} tickers")

    log.info("Loading portfolio data...")
    data = load_data()

    log.info("Building email...")
    html = build_html(data, prices)

    date_str = datetime.now().strftime("%b %-d, %Y")
    subject  = f"Conviction Portfolio — {date_str}"

    log.info("Sending email...")
    send_email(subject, html)


if __name__ == "__main__":
    main()
