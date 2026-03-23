#!/usr/bin/env python3
"""
2026 Conviction Portfolio Tracker — $25K Multi-Theme Dashboard
10 Things Coming in 2026 That Nobody Is Pricing In
Run: streamlit run app.py
"""

import json
import os
from datetime import datetime

import pandas as pd
import streamlit as st
import yfinance as yf

# ═══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════

TOTAL_CAPITAL = 25_000
CASH_DEFAULT  = 0
DATA_FILE     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio_data.json")

# (ticker, company, theme, tier, target_gain%, stop_loss%, trail_pct, alloc_usd, notes)
PORTFOLIO_DEF = [
    # Tier 1 — Own the Atoms Core
    ("FCX",  "Freeport-McMoRan",      "Critical Minerals", 1, 0.40, 0.15, 0.15, 3_000, "Copper #1 input to AI infra + energy transition"),
    ("CEG",  "Constellation Energy",  "Critical Minerals", 1, 0.35, 0.15, 0.15, 2_000, "Nuclear power for datacenters; MSFT offtake deal"),
    ("SQM",  "Soc. Quimica y Minera", "Critical Minerals", 1, 0.45, 0.18, 0.15, 2_000, "Chilean lithium; lowest-cost structure in sector"),
    ("SCCO", "Southern Copper",       "Critical Minerals", 1, 0.40, 0.15, 0.15, 1_500, "Pure-play copper; better margins than FCX"),
    ("VALE", "Vale",                  "Critical Minerals", 1, 0.35, 0.15, 0.15, 1_500, "Brazil iron ore + nickel; cheap on fundamentals"),
    # Tier 2 — LATAM Growth + AI Infrastructure
    ("MELI", "MercadoLibre",          "LATAM Growth",      2, 0.40, 0.12, 0.12, 2_500, "Best LATAM play: e-commerce + fintech + logistics"),
    ("GEV",  "GE Vernova",            "AI Infrastructure", 2, 0.40, 0.12, 0.12, 2_000, "Grid infra for datacenters + renewables"),
    ("LLY",  "Eli Lilly",             "Longevity / GLP-1", 2, 0.35, 0.12, 0.12, 2_000, "Strongest GLP-1 pipeline; cognitive + longevity"),
    ("PLTR", "Palantir",              "AI Infrastructure", 2, 0.50, 0.12, 0.12, 1_500, "AI agents on real operational data; gov + commercial"),
    ("MSFT", "Microsoft",             "AI Infrastructure", 2, 0.30, 0.12, 0.12, 1_500, "Copilot + Azure AI; lowest-risk AI exposure"),
    # Tier 3 — Speculative / High-Upside
    ("ASTS", "AST SpaceMobile",       "Satellite",         3, 1.00, 0.30, 0.20, 1_250, "Direct-to-cell satellite; binary 0 or 10x"),
    ("NVO",  "Novo Nordisk",          "Longevity / GLP-1", 3, 0.35, 0.20, 0.20, 1_000, "GLP-1 diversifier; oral semaglutide pipeline"),
    ("SPGI", "S&P Global",            "AI Infrastructure", 3, 0.25, 0.12, 0.12, 1_000, "Defensive data moat; structural pricing power"),
    ("NU",   "Nu Holdings",           "LATAM Growth",      3, 0.60, 0.20, 0.20, 1_000, "Highest-growth LATAM fintech"),
    ("ZTS",  "Zoetis",                "Longevity / GLP-1", 3, 0.30, 0.20, 0.20,   750, "Animal health moat + pet GLP-1 optionality"),
]

TICKERS = [r[0] for r in PORTFOLIO_DEF]

THEME_EMOJI = {
    "Critical Minerals": "⛏️",
    "LATAM Growth":      "🌎",
    "AI Infrastructure": "🤖",
    "Longevity / GLP-1": "🧬",
    "Satellite":         "🛸",
}

TIER_LABEL = {1: "Tier 1 — Core", 2: "Tier 2 — Growth", 3: "Tier 3 — Speculative"}

# Macro tickers for dashboard
MACRO_TICKERS = [
    "HG=F",    # Copper
    "LIT",     # Lithium ETF proxy
    "DX-Y.NYB",# US Dollar DXY
    "BRL=X",   # BRL/USD
    "SPY",     # S&P 500
    "QQQ",     # Nasdaq
    "^VIX",    # VIX
    "GC=F",    # Gold
]

# China stimulus checklist (same pattern as metals tracker)
CHINA_CHECKS = [
    "PBOC rate cut or RRR reduction announced",
    "China infrastructure spending package announced",
    "China PMI Manufacturing > 50 (expansion)",
    "China copper imports surge (monthly data)",
    "China-US trade deal / tariff reduction news",
    "LATAM trade corridor agreement signed",
]

# AI capex tracker
AI_CAPEX_CHECKS = [
    "Microsoft quarterly capex UP vs prior year",
    "Google/Alphabet quarterly capex UP vs prior year",
    "Meta quarterly capex UP vs prior year",
    "Amazon/AWS quarterly capex UP vs prior year",
    "New datacenter power purchase agreement (nuclear/grid)",
    "US AI infrastructure bill / CHIPS Act expansion",
]

# GLP-1 tracker
GLP1_CHECKS = [
    "FDA approval for new GLP-1 indication (LLY or NVO)",
    "Medicare/Medicaid expanding GLP-1 coverage",
    "LLY oral GLP-1 trial positive data",
    "NVO oral semaglutide approval progress",
    "No GLP-1 price cap legislation advancing",
    "ZTS animal health GLP-1 pipeline update",
]

SELL_RULES = {
    "Critical Minerals": "Trim on copper <$4.00 2+ weeks or China PMI <49 two months. Sell into parabolic moves +40%.",
    "LATAM Growth":      "Sell on BRL breakdown / US tariff escalation / MELI GMV miss >5%. Trim at +40%.",
    "AI Infrastructure": "Sell if hyperscaler capex guidance cut. Watch GEV backlog quarterly. Trim PLTR at +50%.",
    "Longevity / GLP-1": "Sell on FDA rejection or GLP-1 price cap legislation. Trim LLY/NVO at +35%.",
    "Satellite":         "ASTS: hold unless commercial launch fails or Starlink direct-to-cell dominates. Binary position.",
}

# ═══════════════════════════════════════════════════════════════════
# PERSISTENCE
# ═══════════════════════════════════════════════════════════════════

def _default_data() -> dict:
    return {
        "positions": {
            t: {"entry_price": None, "position_usd": alloc, "highest_price": None}
            for t, _, _, _, _, _, _, alloc, _ in PORTFOLIO_DEF
        },
        "cash":          CASH_DEFAULT,
        "china_checks":  [False] * len(CHINA_CHECKS),
        "ai_checks":     [False] * len(AI_CAPEX_CHECKS),
        "glp1_checks":   [False] * len(GLP1_CHECKS),
        "last_updated":  None,
    }


def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE) as f:
                saved = json.load(f)
            dflt = _default_data()
            for k, v in dflt.items():
                if k not in saved:
                    saved[k] = v
            for lst_key, ref in [("china_checks", CHINA_CHECKS), ("ai_checks", AI_CAPEX_CHECKS), ("glp1_checks", GLP1_CHECKS)]:
                while len(saved[lst_key]) < len(ref):
                    saved[lst_key].append(False)
            for t, _, _, _, _, _, _, alloc, _ in PORTFOLIO_DEF:
                if t not in saved["positions"]:
                    saved["positions"][t] = {"entry_price": None, "position_usd": alloc, "highest_price": None}
            return saved
        except Exception:
            pass
    return _default_data()


def save_data(data: dict):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ═══════════════════════════════════════════════════════════════════
# PRICE FETCHING
# ═══════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300, show_spinner=False)
def fetch_prices() -> dict:
    all_tickers = TICKERS + MACRO_TICKERS
    prices = {t: None for t in all_tickers}
    try:
        raw = yf.download(all_tickers, period="5d", auto_adjust=True, progress=False, threads=True)
        if isinstance(raw.columns, pd.MultiIndex):
            for ticker in all_tickers:
                try:
                    prices[ticker] = round(float(raw["Close"][ticker].dropna().iloc[-1]), 4)
                except Exception:
                    pass
        else:
            prices[all_tickers[0]] = round(float(raw["Close"].dropna().iloc[-1]), 4)
    except Exception:
        for ticker in all_tickers:
            try:
                hist = yf.Ticker(ticker).history(period="5d")
                if not hist.empty:
                    prices[ticker] = round(float(hist["Close"].iloc[-1]), 4)
            except Exception:
                pass
    return prices


# ═══════════════════════════════════════════════════════════════════
# BUSINESS LOGIC
# ═══════════════════════════════════════════════════════════════════

def compute_signal(price, entry, highest, stop_pct, trail_pct, target_pct, tier) -> tuple:
    if price is None:
        return "—", "none"
    if not entry or entry <= 0:
        return "⬜ NOT ENTERED", "none"

    trail_stop = (highest * (1 - trail_pct)) if highest else (entry * (1 - stop_pct))
    hard_stop   = entry * (1 - stop_pct)

    if price < trail_stop or price < hard_stop:
        return "🚨 SELL", "sell"

    gain = (price - entry) / entry

    # Tier 3 speculative: wider trim thresholds
    trim_hi = 0.40 if tier < 3 else 0.60
    trim_lo = 0.25 if tier < 3 else 0.40

    if gain >= trim_hi:
        return "✂️ TRIM 25%", "trim"
    if gain >= trim_lo:
        return "✂️ TRIM 15%", "trim"

    return "✅ HOLD", "hold"


def fmt_pct(v, decimals=1) -> str:
    if v is None:
        return "—"
    return f"{'+' if v >= 0 else ''}{v * 100:.{decimals}f}%"


def theme_regime(prices: dict, china_checks: list, ai_checks: list, glp1_checks: list) -> dict:
    """Compute per-theme macro regime signal."""
    copper = prices.get("HG=F")
    china_active = sum(1 for c in china_checks if c)
    ai_active    = sum(1 for c in ai_checks if c)
    glp1_active  = sum(1 for c in glp1_checks if c)

    # Copper / Critical Minerals regime
    if copper is None:
        minerals_mode, minerals_key = "⚪ NO COPPER DATA", "none"
    elif copper >= 4.30:
        minerals_mode, minerals_key = "🟢 COPPER STRONG — HOLD MINERALS", "hold"
    elif copper >= 4.00:
        minerals_mode, minerals_key = "🟡 COPPER FADING — TRIM MINERALS", "trim"
    else:
        minerals_mode, minerals_key = "🔴 COPPER BROKEN — EXIT MINERALS", "sell"

    # LATAM regime (China + BRL proxy)
    brl = prices.get("BRL=X")
    if china_active >= 3:
        latam_mode, latam_key = "🟢 CHINA STIMULUS ACTIVE — HOLD LATAM", "hold"
    elif brl and brl > 6.0:
        latam_mode, latam_key = "🔴 BRL WEAK (>{:.2f}) — WATCH LATAM".format(brl), "sell"
    else:
        latam_mode, latam_key = "🟡 LATAM NEUTRAL — MONITOR", "trim"

    # AI regime
    if ai_active >= 4:
        ai_mode, ai_key = "🟢 AI CAPEX EXPANDING — HOLD AI INFRA", "hold"
    elif ai_active >= 2:
        ai_mode, ai_key = "🟡 AI CAPEX MIXED — TRIM ON WEAKNESS", "trim"
    else:
        ai_mode, ai_key = "🔴 AI CAPEX SIGNALS WEAK — REDUCE", "sell"

    # GLP-1 regime
    if glp1_active >= 4:
        glp1_mode, glp1_key = "🟢 GLP-1 PIPELINE STRONG — HOLD BIOTECH", "hold"
    elif glp1_active >= 2:
        glp1_mode, glp1_key = "🟡 GLP-1 MIXED — WATCH PIPELINE", "trim"
    else:
        glp1_mode, glp1_key = "🔴 GLP-1 HEADWINDS — TRIM BIOTECH", "sell"

    return {
        "Critical Minerals": (minerals_mode, minerals_key),
        "LATAM Growth":      (latam_mode,    latam_key),
        "AI Infrastructure": (ai_mode,       ai_key),
        "Longevity / GLP-1": (glp1_mode,     glp1_key),
        "Satellite":         ("🛸 HOLD unless launch fails — binary bet", "hold"),
    }


# ═══════════════════════════════════════════════════════════════════
# CHART DATA & TECHNICAL INDICATORS
# ═══════════════════════════════════════════════════════════════════

@st.cache_data(ttl=300, show_spinner=False)
def fetch_all_chart_data(tickers: tuple) -> dict:
    """Batch-fetch 6 months of daily OHLCV for all tickers in one request."""
    result = {}
    try:
        raw = yf.download(list(tickers), period="6mo", interval="1d",
                          auto_adjust=True, progress=False, threads=True)
        if not isinstance(raw.columns, pd.MultiIndex):
            return result
        for ticker in tickers:
            try:
                df = pd.DataFrame({
                    m: raw[m][ticker] for m in ["Open", "High", "Low", "Close", "Volume"]
                }).dropna()
                df.index = pd.to_datetime(df.index)
                if len(df) >= 60:
                    result[ticker] = df
            except Exception:
                pass
    except Exception:
        pass
    return result


def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def _bollinger(close: pd.Series, period: int = 20, std_dev: float = 2.0):
    mid = close.rolling(period).mean()
    sigma = close.rolling(period).std()
    return mid + std_dev * sigma, mid, mid - std_dev * sigma


def _ichimoku(high: pd.Series, low: pd.Series, close: pd.Series):
    tenkan = (high.rolling(9).max()  + low.rolling(9).min())  / 2
    kijun  = (high.rolling(26).max() + low.rolling(26).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(26)
    span_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
    chikou = close.shift(-26)
    return tenkan, kijun, span_a, span_b, chikou


def _psar(df: pd.DataFrame, af0: float = 0.02, af_step: float = 0.02, af_max: float = 0.2):
    hi = df["High"].values
    lo = df["Low"].values
    n  = len(hi)
    sar  = lo.copy()
    bull = True
    af   = af0
    hp, lp = hi[0], lo[0]
    for i in range(1, n):
        p = sar[i - 1]
        if bull:
            sar[i] = p + af * (hp - p)
            sar[i] = min(sar[i], lo[i - 1], lo[max(0, i - 2)])
            if lo[i] < sar[i]:
                bull, sar[i], lp, af = False, hp, lo[i], af0
            else:
                if hi[i] > hp:
                    hp = hi[i]
                    af = min(af + af_step, af_max)
        else:
            sar[i] = p + af * (lp - p)
            sar[i] = max(sar[i], hi[i - 1], hi[max(0, i - 2)])
            if hi[i] > sar[i]:
                bull, sar[i], hp, af = True, lp, hi[i], af0
            else:
                if lo[i] < lp:
                    lp = lo[i]
                    af = min(af + af_step, af_max)
    s  = pd.Series(sar, index=df.index)
    cl = df["Close"]
    return s.where(cl > s), s.where(cl <= s)


def _adx(df: pd.DataFrame, period: int = 14):
    hi, lo, cl = df["High"], df["Low"], df["Close"]
    prev_cl = cl.shift(1)
    tr = pd.concat([(hi - lo), (hi - prev_cl).abs(), (lo - prev_cl).abs()], axis=1).max(axis=1)
    up   = hi - hi.shift(1)
    down = lo.shift(1) - lo
    dm_p = up.where((up > down) & (up > 0), 0.0)
    dm_m = down.where((down > up) & (down > 0), 0.0)
    alpha  = 1 / period
    atr    = tr.ewm(alpha=alpha, adjust=False).mean()
    sdm_p  = dm_p.ewm(alpha=alpha, adjust=False).mean()
    sdm_m  = dm_m.ewm(alpha=alpha, adjust=False).mean()
    di_p = 100 * sdm_p / atr
    di_m = 100 * sdm_m / atr
    dx   = 100 * (di_p - di_m).abs() / (di_p + di_m).replace(0, float("nan"))
    adx  = dx.ewm(alpha=alpha, adjust=False).mean()
    return adx, di_p, di_m


def _macd(close: pd.Series, fast: int = 3, slow: int = 6, signal: int = 7):
    line = _ema(close, fast) - _ema(close, slow)
    sig  = _ema(line, signal)
    return line, sig, line - sig


def _tsi(close: pd.Series, long: int = 7, short: int = 4, signal: int = 7):
    pc  = close.diff()
    ds  = _ema(_ema(pc,       long), short)
    dsa = _ema(_ema(pc.abs(), long), short)
    tsi = 100 * ds / dsa
    return tsi, _ema(tsi, signal)


def _cloud_fill_traces(dates, sa_arr, sb_arr):
    import plotly.graph_objects as go
    traces = []
    n = len(dates)
    if n == 0:
        return traces

    def valid_bull(i):
        return not pd.isna(sa_arr[i]) and not pd.isna(sb_arr[i]) and sa_arr[i] >= sb_arr[i]

    def valid_bear(i):
        return not pd.isna(sa_arr[i]) and not pd.isna(sb_arr[i]) and sa_arr[i] < sb_arr[i]

    def segments(check_fn):
        segs, start = [], None
        for i in range(n):
            if check_fn(i) and start is None:
                start = i
            elif not check_fn(i) and start is not None:
                segs.append((start, i - 1))
                start = None
        if start is not None:
            segs.append((start, n - 1))
        return segs

    for s, e in segments(valid_bull):
        d = list(dates[s : e + 1])
        a = list(sa_arr[s : e + 1])
        b = list(sb_arr[s : e + 1])
        traces.append(go.Scatter(x=d + d[::-1], y=a + b[::-1], fill="toself",
                                 fillcolor="rgba(0,180,0,0.18)", line=dict(width=0),
                                 showlegend=False, hoverinfo="skip"))
    for s, e in segments(valid_bear):
        d = list(dates[s : e + 1])
        a = list(sa_arr[s : e + 1])
        b = list(sb_arr[s : e + 1])
        traces.append(go.Scatter(x=d + d[::-1], y=b + a[::-1], fill="toself",
                                 fillcolor="rgba(210,0,0,0.18)", line=dict(width=0),
                                 showlegend=False, hoverinfo="skip"))
    return traces


def render_chart(ticker: str, df: pd.DataFrame):
    """3-month daily chart: BB(20,2) · Ichimoku · PSAR · ADX · MACD(3,6,7) · TSI(7,4,7)."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    if df.empty or len(df) < 60:
        st.warning(f"Not enough data to render chart for {ticker}.")
        return

    cl, hi, lo = df["Close"], df["High"], df["Low"]
    bb_up, bb_mid, bb_lo              = _bollinger(cl)
    tenkan, kijun, span_a, span_b, chikou = _ichimoku(hi, lo, cl)
    psar_bull, psar_bear              = _psar(df)
    adx, di_p, di_m                   = _adx(df)
    macd_l, macd_s, macd_h            = _macd(cl)
    tsi_l, tsi_s                      = _tsi(cl)

    D   = df.iloc[-65:]
    idx = D.index

    def _s(series):
        return series.reindex(idx)

    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True,
        row_heights=[0.52, 0.16, 0.16, 0.16],
        vertical_spacing=0.025,
        subplot_titles=[
            f"{ticker} — Daily · 3 months  |  BB(20,2)  ·  Ichimoku Cloud  ·  Parabolic SAR",
            "ADX(14)  /  +DI  /  −DI", "MACD (3, 6, 7)", "TSI (7, 4, 7)",
        ],
    )

    bu, bl = _s(bb_up).values, _s(bb_lo).values
    valid = ~(pd.isna(bu) | pd.isna(bl))
    if valid.any():
        vd = list(idx[valid])
        fig.add_trace(go.Scatter(x=vd + vd[::-1], y=list(bu[valid]) + list(bl[valid][::-1]),
                                 fill="toself", fillcolor="rgba(255,165,0,0.06)",
                                 line=dict(width=0), showlegend=False, hoverinfo="skip"), row=1, col=1)

    for t in _cloud_fill_traces(idx, _s(span_a).values, _s(span_b).values):
        fig.add_trace(t, row=1, col=1)

    fig.add_trace(go.Candlestick(x=idx, open=D["Open"], high=D["High"], low=D["Low"], close=D["Close"],
                                 name=ticker, increasing_line_color="#26a69a",
                                 decreasing_line_color="#ef5350", showlegend=False), row=1, col=1)

    fig.add_trace(go.Scatter(x=idx, y=_s(bb_up),  name="BB Upper",
                             line=dict(color="rgba(255,165,0,0.75)", width=1, dash="dot")), row=1, col=1)
    fig.add_trace(go.Scatter(x=idx, y=_s(bb_mid), name="BB Mid",
                             line=dict(color="rgba(255,165,0,0.45)", width=1, dash="dash")), row=1, col=1)
    fig.add_trace(go.Scatter(x=idx, y=_s(bb_lo),  name="BB Lower",
                             line=dict(color="rgba(255,165,0,0.75)", width=1, dash="dot")), row=1, col=1)

    fig.add_trace(go.Scatter(x=idx, y=_s(tenkan), name="Tenkan",
                             line=dict(color="rgba(0,210,210,0.9)",  width=1.2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=idx, y=_s(kijun),  name="Kijun",
                             line=dict(color="rgba(230,80,80,0.9)",  width=1.2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=idx, y=_s(span_a), name="Span A",
                             line=dict(color="rgba(0,180,0,0.55)",   width=1)), row=1, col=1)
    fig.add_trace(go.Scatter(x=idx, y=_s(span_b), name="Span B",
                             line=dict(color="rgba(210,0,0,0.55)",   width=1)), row=1, col=1)
    fig.add_trace(go.Scatter(x=idx, y=_s(chikou), name="Chikou",
                             line=dict(color="rgba(160,0,220,0.65)", width=1, dash="dot")), row=1, col=1)

    pb  = _s(psar_bull).dropna()
    pbe = _s(psar_bear).dropna()
    fig.add_trace(go.Scatter(x=pb.index,  y=pb.values,  mode="markers", name="PSAR Bull",
                             marker=dict(symbol="circle", size=4, color="rgba(0,210,110,0.85)")), row=1, col=1)
    fig.add_trace(go.Scatter(x=pbe.index, y=pbe.values, mode="markers", name="PSAR Bear",
                             marker=dict(symbol="circle", size=4, color="rgba(220,55,55,0.85)")), row=1, col=1)

    fig.add_trace(go.Scatter(x=idx, y=_s(adx),  name="ADX",
                             line=dict(color="#e0e0e0", width=1.6)), row=2, col=1)
    fig.add_trace(go.Scatter(x=idx, y=_s(di_p), name="+DI",
                             line=dict(color="#26a69a", width=1.2)), row=2, col=1)
    fig.add_trace(go.Scatter(x=idx, y=_s(di_m), name="−DI",
                             line=dict(color="#ef5350", width=1.2)), row=2, col=1)
    fig.add_hline(y=25, line=dict(color="rgba(200,200,200,0.3)", width=1, dash="dot"), row=2, col=1)

    fig.add_trace(go.Scatter(x=idx, y=_s(macd_l), name="MACD",
                             line=dict(color="#2196f3", width=1.5)), row=3, col=1)
    fig.add_trace(go.Scatter(x=idx, y=_s(macd_s), name="Signal",
                             line=dict(color="#ff9800", width=1.2)), row=3, col=1)
    hist_vals = _s(macd_h)
    fig.add_trace(go.Bar(x=idx, y=hist_vals, name="Hist", showlegend=False,
                         marker_color=["rgba(38,166,154,0.75)" if v >= 0 else "rgba(239,83,80,0.75)"
                                       for v in hist_vals.fillna(0)]), row=3, col=1)
    fig.add_hline(y=0, line=dict(color="rgba(200,200,200,0.25)", width=1), row=3, col=1)

    fig.add_trace(go.Scatter(x=idx, y=_s(tsi_l), name="TSI",
                             line=dict(color="#ce93d8", width=1.5)), row=4, col=1)
    fig.add_trace(go.Scatter(x=idx, y=_s(tsi_s), name="TSI Sig",
                             line=dict(color="#ffcc02", width=1.2)), row=4, col=1)
    fig.add_hline(y=0, line=dict(color="rgba(200,200,200,0.25)", width=1), row=4, col=1)

    fig.update_layout(
        height=880, paper_bgcolor="#1a1a2e", plot_bgcolor="#1a1a2e",
        font=dict(color="#d0d0d0", size=11),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="left", x=0,
                    bgcolor="rgba(0,0,0,0.35)", font=dict(size=10), itemsizing="constant"),
        margin=dict(l=60, r=20, t=40, b=20),
        xaxis_rangeslider_visible=False, hovermode="x unified", barmode="overlay",
    )
    grid = dict(gridcolor="rgba(80,80,80,0.3)", zerolinecolor="rgba(80,80,80,0.4)", showgrid=True)
    for r in range(1, 5):
        fig.update_xaxes(**grid, showticklabels=(r == 4), row=r, col=1)
        fig.update_yaxes(**grid, row=r, col=1)

    st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════
# CSS
# ═══════════════════════════════════════════════════════════════════

CSS = """
<style>
.main .block-container { padding: 0.5rem 0.75rem 3rem; max-width: 1400px; }
.stTabs [data-baseweb="tab"] { font-size: 0.85rem; padding: 0.35rem 0.65rem; color: #a78bfa !important; font-weight: 600; }
.stTabs [data-baseweb="tab"]:hover { color: #c4b5fd !important; }
.stTabs [aria-selected="true"] { color: #c4b5fd !important; border-bottom: 2px solid #c4b5fd !important; }

.mode-banner {
    padding: 1rem 1.5rem; border-radius: 8px;
    font-size: 1rem; font-weight: 800;
    text-align: center; letter-spacing: 0.5px;
    margin-bottom: 0.6rem;
}
.mode-hold { background:#0d3d22; color:#2ecc71; border:2px solid #27ae60; }
.mode-trim { background:#3d2800; color:#f39c12; border:2px solid #f39c12; }
.mode-sell { background:#3d0d0d; color:#e74c3c; border:2px solid #e74c3c; }
.mode-none { background:#2a2a2a; color:#aaa;    border:2px solid #555; }

.metric-row { display:flex; flex-wrap:wrap; gap:0.6rem; margin-bottom:1rem; }
.mcard {
    background:#1e1b4b; border:2px solid #a78bfa; border-radius:8px;
    padding:0.65rem 1rem; flex:1; min-width:110px;
}
.mcard .lbl { font-size:0.62rem; color:#c4b5fd; text-transform:uppercase; letter-spacing:1px; font-weight:700; }
.mcard .val { font-size:1.25rem; font-weight:700; margin-top:2px; color:#ffffff; }
.mcard .sub { font-size:0.72rem; color:#d0d0d0; }

.sig-box { padding:0.45rem 0.75rem; border-radius:5px; margin:0.2rem 0; border-left:3px solid; }
.sig-sell { background:#3d0d0d; border-color:#e74c3c; }
.sig-ok   { background:#0d3d22; border-color:#27ae60; }
.sig-warn { background:#3d2800; border-color:#f39c12; }
.sig-blue { background:#0d1f3d; border-color:#60a5fa; }

.c-green { color:#2ecc71 !important; font-weight:600; }
.c-red   { color:#e74c3c !important; font-weight:600; }
.c-gray  { color:#888 !important; }

.theme-header {
    font-size:0.8rem; font-weight:700; text-transform:uppercase;
    letter-spacing:1px; color:#c4b5fd; margin:1rem 0 0.3rem;
    border-bottom: 1px solid #3d3d6d; padding-bottom:4px;
}
</style>
"""


# ═══════════════════════════════════════════════════════════════════
# TAB: PORTFOLIO
# ═══════════════════════════════════════════════════════════════════

def render_portfolio(data: dict, prices: dict):
    pos_data = data["positions"]
    cash = data["cash"]

    # ── Totals ─────────────────────────────────────────────────────
    total_invested = sum(p["position_usd"] for p in pos_data.values())
    mkt_value = 0.0
    total_gain = 0.0

    for t, _, _, _, _, _, _, alloc, _ in PORTFOLIO_DEF:
        pos   = pos_data[t]
        price = prices.get(t)
        entry = pos["entry_price"]
        pusd  = pos["position_usd"] or alloc
        if price and entry and entry > 0:
            curr_val   = (pusd / entry) * price
            mkt_value += curr_val
            total_gain += curr_val - pusd
        else:
            mkt_value += pusd

    total_acct = mkt_value + cash
    gain_pct   = (total_gain / total_invested * 100) if total_invested > 0 else 0
    sign       = "+" if total_gain >= 0 else ""
    gc         = "c-green" if total_gain >= 0 else "c-red"

    st.markdown(f"""
    <div class="metric-row">
        <div class="mcard"><div class="lbl">Total Account</div><div class="val">${total_acct:,.0f}</div><div class="sub">Capital: ${TOTAL_CAPITAL:,}</div></div>
        <div class="mcard"><div class="lbl">Portfolio</div><div class="val">${mkt_value:,.0f}</div><div class="sub">${total_invested:,.0f} invested</div></div>
        <div class="mcard"><div class="lbl">P&amp;L</div><div class="val {gc}">{sign}${total_gain:,.0f}</div><div class="sub {gc}">{sign}{gain_pct:.1f}%</div></div>
        <div class="mcard"><div class="lbl">Cash</div><div class="val">${cash:,.0f}</div><div class="sub">Dry powder 🎯</div></div>
    </div>
    """, unsafe_allow_html=True)

    # ── Build rows grouped by tier ──────────────────────────────────
    sell_count = trim_count = 0
    rows = []
    for t, company, theme, tier, tgt_pct, stop_pct, trail_pct, alloc, notes in PORTFOLIO_DEF:
        pos     = pos_data[t]
        price   = prices.get(t)
        entry   = pos["entry_price"]
        pusd    = pos["position_usd"] or alloc
        highest = pos["highest_price"]

        trail_stop = (highest * (1 - trail_pct)) if highest else (entry * (1 - stop_pct) if entry else 0)

        if price and entry and entry > 0:
            curr_val = (pusd / entry) * price
            gpct     = (price - entry) / entry
            gain_str = fmt_pct(gpct)
        else:
            curr_val = pusd
            gpct     = None
            gain_str = "—"

        tgt_price  = entry * (1 + tgt_pct) if entry else None
        to_tgt     = fmt_pct((tgt_price - price) / price, 0) if (price and tgt_price) else "—"
        weight_pct = pusd / total_invested * 100 if total_invested > 0 else 0
        signal, sig_key = compute_signal(price, entry, highest, stop_pct, trail_pct, tgt_pct, tier)

        if sig_key == "sell": sell_count += 1
        elif sig_key == "trim": trim_count += 1

        rows.append({
            "Ticker":     t,
            "Company":    f"{THEME_EMOJI.get(theme,'')} {company}",
            "Theme":      theme,
            "Tier":       tier,
            "Price":      f"${price:.2f}" if price else "—",
            "Entry":      f"${entry:.2f}" if entry else "—",
            "Value":      f"${curr_val:,.0f}",
            "Trail Stop": f"${trail_stop:.2f}" if trail_stop else "—",
            "% Gain":     gain_str,
            "To Target":  to_tgt,
            "Weight":     f"{weight_pct:.0f}%",
            "Signal":     signal,
        })

    df = pd.DataFrame(rows)

    def _row_bg(row):
        if "SELL" in str(row["Signal"]):
            return ["background-color:#3d0d0d; color:#ffbbbb"] * len(row)
        if "TRIM" in str(row["Signal"]):
            return ["background-color:#3d2800; color:#ffd080"] * len(row)
        return [""] * len(row)

    def _style_pct(col):
        return col.map(lambda v:
            "color:#2ecc71; font-weight:600" if str(v).startswith("+") else
            "color:#e74c3c; font-weight:600" if str(v).startswith("-") else "color:#888"
        )

    def _style_signal(col):
        return col.map(lambda v:
            "background-color:#c0392b; color:white; font-weight:700; border-radius:4px; text-align:center" if "SELL" in str(v) else
            "background-color:#d68910; color:white; font-weight:700; border-radius:4px; text-align:center" if "TRIM" in str(v) else
            "background-color:#1e8449; color:white; font-weight:700; border-radius:4px; text-align:center" if "HOLD" in str(v) else
            "color:#888"
        )

    display_df = df.drop(columns=["Theme", "Tier"])
    styled = (
        display_df.style
        .apply(_row_bg, axis=1)
        .apply(_style_pct, subset=["% Gain", "To Target"])
        .apply(_style_signal, subset=["Signal"])
        .hide(axis="index")
    )
    st.dataframe(styled, use_container_width=True, height=590)

    if sell_count > 0:
        st.error(f"🚨 {sell_count} position(s) triggered SELL — action required!")
    if trim_count > 0:
        st.warning(f"✂️ {trim_count} position(s) at TRIM levels")
    if sell_count == 0 and trim_count == 0:
        st.success("✅ All positions nominal — no action needed")

    # ── Theme allocation breakdown ──────────────────────────────────
    st.markdown("---")
    st.markdown("##### Allocation by Theme")
    themes = {}
    for t, _, theme, tier, _, _, _, alloc, _ in PORTFOLIO_DEF:
        themes.setdefault(theme, {"tickers": [], "usd": 0, "tier": tier})
        themes[theme]["tickers"].append(t)
        themes[theme]["usd"] += pos_data[t]["position_usd"] or alloc

    cols = st.columns(len(themes))
    for i, (theme, info) in enumerate(themes.items()):
        em  = THEME_EMOJI.get(theme, "")
        pct = info["usd"] / TOTAL_CAPITAL * 100
        with cols[i]:
            st.markdown(f"**{em} {theme}**")
            st.markdown(f"${info['usd']:,} · {pct:.0f}%")
            st.caption(" · ".join(info["tickers"]))
            st.caption(SELL_RULES.get(theme, ""))

    # ── Stock Chart ────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("##### Stock Chart")
    st.caption("Daily · 3 months · BB(20,2) · Ichimoku Cloud · Parabolic SAR · ADX(14) · MACD(3,6,7) · TSI(7,4,7)")
    chart_ticker = st.selectbox(
        "Select ticker to chart",
        TICKERS,
        key="chart_ticker_select",
        label_visibility="collapsed",
    )
    with st.spinner("Loading chart data…"):
        all_chart_data = fetch_all_chart_data(tuple(TICKERS))
    render_chart(chart_ticker, all_chart_data.get(chart_ticker, pd.DataFrame()))


# ═══════════════════════════════════════════════════════════════════
# TAB: DASHBOARD
# ═══════════════════════════════════════════════════════════════════

def render_dashboard(data: dict, prices: dict):
    china_checks = data.get("china_checks", [False] * len(CHINA_CHECKS))
    ai_checks    = data.get("ai_checks",    [False] * len(AI_CAPEX_CHECKS))
    glp1_checks  = data.get("glp1_checks",  [False] * len(GLP1_CHECKS))

    regimes = theme_regime(prices, china_checks, ai_checks, glp1_checks)

    # ── Theme Regime Banners ────────────────────────────────────────
    st.markdown("### 🎯 Theme Regime Dashboard")
    c1, c2 = st.columns(2)
    banner_order = [
        ("Critical Minerals", c1), ("LATAM Growth", c2),
        ("AI Infrastructure", c1), ("Longevity / GLP-1", c2),
    ]
    for theme, col in banner_order:
        mode, key = regimes[theme]
        em = THEME_EMOJI.get(theme, "")
        with col:
            st.markdown(
                f'<div class="mode-banner mode-{key}">{em} {theme}<br><span style="font-size:0.85rem">{mode}</span></div>',
                unsafe_allow_html=True
            )
    # Satellite separately
    mode, key = regimes["Satellite"]
    st.markdown(
        f'<div class="mode-banner mode-{key}">🛸 Satellite (ASTS) — {mode}</div>',
        unsafe_allow_html=True
    )

    st.divider()

    # ── Macro Metrics Row ───────────────────────────────────────────
    st.markdown("### 📊 Macro Metrics")
    copper = prices.get("HG=F")
    lit    = prices.get("LIT")
    dxy    = prices.get("DX-Y.NYB")
    brl    = prices.get("BRL=X")
    vix    = prices.get("^VIX")
    spy    = prices.get("SPY")

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1: st.metric("🟠 Copper (HG=F)", f"${copper:.3f}" if copper else "—")
    with c2: st.metric("🔋 Lithium (LIT)", f"${lit:.2f}" if lit else "—")
    with c3: st.metric("💵 DXY", f"{dxy:.2f}" if dxy else "—", help="Strong DXY = headwind for commodities/LATAM")
    with c4: st.metric("🇧🇷 BRL/USD", f"{brl:.4f}" if brl else "—", help=">6.0 = BRL stress signal")
    with c5: st.metric("📊 VIX", f"{vix:.1f}" if vix else "—")
    with c6: st.metric("📈 SPY", f"${spy:.2f}" if spy else "—")

    st.divider()

    # ── Three Checklist Columns ─────────────────────────────────────
    st.markdown("### 🔎 Thesis Tracker — Update Weekly")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("**⛏️ China / Critical Minerals**")
        china_active = sum(1 for c in china_checks if c)
        if china_active >= 4:
            st.success(f"✅ {china_active}/{len(CHINA_CHECKS)} signals — Strong bull case")
        elif china_active >= 2:
            st.info(f"🔵 {china_active}/{len(CHINA_CHECKS)} signals — Cautious")
        else:
            st.warning(f"⚠️ {china_active}/{len(CHINA_CHECKS)} signals — Headwind")
        for i, label in enumerate(CHINA_CHECKS):
            is_on = china_checks[i] if i < len(china_checks) else False
            css  = "sig-blue" if is_on else "sig-ok"
            icon = "✅" if is_on else "⬜"
            st.markdown(f'<div class="sig-box {css}">{icon} {label}</div>', unsafe_allow_html=True)

    with col2:
        st.markdown("**🤖 AI Infrastructure / Capex**")
        ai_active = sum(1 for c in ai_checks if c)
        if ai_active >= 4:
            st.success(f"✅ {ai_active}/{len(AI_CAPEX_CHECKS)} signals — Capex expanding")
        elif ai_active >= 2:
            st.info(f"🔵 {ai_active}/{len(AI_CAPEX_CHECKS)} signals — Mixed")
        else:
            st.warning(f"⚠️ {ai_active}/{len(AI_CAPEX_CHECKS)} signals — Watch carefully")
        for i, label in enumerate(AI_CAPEX_CHECKS):
            is_on = ai_checks[i] if i < len(ai_checks) else False
            css  = "sig-blue" if is_on else "sig-ok"
            icon = "✅" if is_on else "⬜"
            st.markdown(f'<div class="sig-box {css}">{icon} {label}</div>', unsafe_allow_html=True)

    with col3:
        st.markdown("**🧬 GLP-1 / Longevity Pipeline**")
        glp1_active = sum(1 for c in glp1_checks if c)
        if glp1_active >= 4:
            st.success(f"✅ {glp1_active}/{len(GLP1_CHECKS)} signals — Pipeline strong")
        elif glp1_active >= 2:
            st.info(f"🔵 {glp1_active}/{len(GLP1_CHECKS)} signals — Monitor")
        else:
            st.warning(f"⚠️ {glp1_active}/{len(GLP1_CHECKS)} signals — Headwinds")
        for i, label in enumerate(GLP1_CHECKS):
            is_on = glp1_checks[i] if i < len(glp1_checks) else False
            css  = "sig-blue" if is_on else "sig-ok"
            icon = "✅" if is_on else "⬜"
            st.markdown(f'<div class="sig-box {css}">{icon} {label}</div>', unsafe_allow_html=True)

    st.caption("👉 Update all checklists in the Settings tab")

    st.divider()

    # ── Sell Signal Checklist ───────────────────────────────────────
    st.markdown("### 🚨 Sell Signal Tracker")
    st.caption("2+ signals across ANY theme = reduce that theme by 30–50%.")

    copper_warn = copper is not None and copper < 4.00
    brl_warn    = brl is not None and brl > 6.0
    vix_warn    = vix is not None and vix > 30

    checks = [
        ("⛏️  Copper < $4.00/lb for 2+ weeks",               copper_warn),
        ("🇧🇷 BRL/USD > 6.00 (currency stress)",              brl_warn),
        ("📊  VIX > 30 (fear elevated — reduce risk overall)", vix_warn),
        ("🤖  Hyperscaler cuts capex guidance (earnings)",     False),
        ("🧬  FDA rejects major GLP-1 pipeline drug",          False),
        ("🛸  ASTS misses commercial launch milestone",        False),
        ("🌎  US imposes LATAM tariffs / trade escalation",    False),
        ("🟠  China PMI < 49 for two consecutive months",      False),
    ]

    triggered = sum(1 for _, t in checks if t)
    for label, is_t in checks:
        css  = "sig-sell" if is_t else "sig-ok"
        icon = "🔴" if is_t else "✅"
        st.markdown(f'<div class="sig-box {css}">{icon} {label}</div>', unsafe_allow_html=True)

    st.markdown("")
    if triggered >= 2:
        st.error(f"⚠️ **{triggered} signals active — REDUCE AFFECTED THEMES BY 30–50%**")
    elif triggered == 1:
        st.warning("⚠️ **1 signal active — Monitor closely before acting**")
    else:
        st.success("✅ **No sell signals — All theses intact**")

    st.divider()

    # ── Weekly Routine ──────────────────────────────────────────────
    st.markdown("### ⏱️ 30-Second Weekly System")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("""
**Step 1 — Theme Regimes**
- 🟢 HOLD → do nothing
- 🟡 TRIM → reduce weakest position in that theme
- 🔴 SELL → exit smallest/weakest name in theme first
        """)
    with c2:
        st.markdown("""
**Step 2 — Portfolio Tab**
- Check Signal column (SELL / TRIM / HOLD)
- Check % Gain (trim at +25–40% depending on tier)
- ASTS: check launch milestones only
        """)
    with c3:
        st.markdown("""
**Step 3 — Thesis Checks**
- Update 3 checklists in Settings
- 4+ China signals = stay long minerals/LATAM
- 4+ AI signals = stay long GEV/PLTR/MSFT
- FDA/pipeline news = reassess LLY/NVO/ZTS
        """)

    st.divider()

    # ── Position Sizing Reference ───────────────────────────────────
    st.markdown("### 💰 Allocation Reference")
    sizing = {
        "Ticker":   [r[0] for r in PORTFOLIO_DEF],
        "Company":  [r[1] for r in PORTFOLIO_DEF],
        "Theme":    [r[2] for r in PORTFOLIO_DEF],
        "Tier":     [TIER_LABEL[r[3]] for r in PORTFOLIO_DEF],
        "Alloc $":  [f"${r[7]:,}" for r in PORTFOLIO_DEF],
        "Alloc %":  [f"{r[7]/TOTAL_CAPITAL*100:.0f}%" for r in PORTFOLIO_DEF],
        "Target":   [f"+{r[4]*100:.0f}%" for r in PORTFOLIO_DEF],
        "Stop":     [f"-{r[5]*100:.0f}%" for r in PORTFOLIO_DEF],
        "Trail":    [f"{r[6]*100:.0f}%" for r in PORTFOLIO_DEF],
    }
    st.dataframe(pd.DataFrame(sizing), use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════
# TAB: SETTINGS
# ═══════════════════════════════════════════════════════════════════

def render_settings(data: dict):
    st.markdown("### ⚙️ Settings")
    st.caption("Set your actual buy prices and position sizes. Highest price auto-tracks from live feed.")

    with st.form("settings_form", clear_on_submit=False):
        st.markdown("#### Cash")
        cash = st.number_input("Cash / Dry Powder ($)", min_value=0.0,
                               value=float(data.get("cash", CASH_DEFAULT)),
                               step=50.0, format="%.0f")

        st.markdown("---")
        st.markdown("#### ⛏️ China / Critical Minerals Tracker")
        china_checks = data.get("china_checks", [False] * len(CHINA_CHECKS))
        new_china = []
        for i, label in enumerate(CHINA_CHECKS):
            val = st.checkbox(label, value=china_checks[i] if i < len(china_checks) else False, key=f"china_{i}")
            new_china.append(val)

        st.markdown("---")
        st.markdown("#### 🤖 AI Infrastructure / Capex Tracker")
        ai_checks = data.get("ai_checks", [False] * len(AI_CAPEX_CHECKS))
        new_ai = []
        for i, label in enumerate(AI_CAPEX_CHECKS):
            val = st.checkbox(label, value=ai_checks[i] if i < len(ai_checks) else False, key=f"ai_{i}")
            new_ai.append(val)

        st.markdown("---")
        st.markdown("#### 🧬 GLP-1 / Longevity Pipeline Tracker")
        glp1_checks = data.get("glp1_checks", [False] * len(GLP1_CHECKS))
        new_glp1 = []
        for i, label in enumerate(GLP1_CHECKS):
            val = st.checkbox(label, value=glp1_checks[i] if i < len(glp1_checks) else False, key=f"glp1_{i}")
            new_glp1.append(val)

        st.markdown("---")
        st.markdown("#### Positions")
        st.caption("Highest Price auto-updates from price feed. Set entry price once you buy.")

        new_positions = {}
        prev_tier = None
        for t, company, theme, tier, tgt_pct, stop_pct, trail_pct, alloc, notes in PORTFOLIO_DEF:
            if tier != prev_tier:
                st.markdown(f"**{TIER_LABEL[tier]}**")
                prev_tier = tier
            pos = data["positions"].get(t, {})
            em  = THEME_EMOJI.get(theme, "")
            st.markdown(
                f"{em} **{t} — {company}** &nbsp;|&nbsp; "
                f"Target: +{tgt_pct*100:.0f}% &nbsp; Stop: -{stop_pct*100:.0f}% &nbsp; Trail: {trail_pct*100:.0f}% &nbsp; Alloc: ${alloc:,}"
            )
            st.caption(notes)
            c1, c2, c3 = st.columns(3)
            with c1:
                entry = st.number_input("Entry Price ($)", min_value=0.0,
                                        value=float(pos.get("entry_price") or 0),
                                        step=0.01, format="%.2f", key=f"e_{t}")
            with c2:
                pos_usd = st.number_input("Position Size ($)", min_value=0.0,
                                          value=float(pos.get("position_usd") or alloc),
                                          step=100.0, format="%.0f", key=f"p_{t}")
            with c3:
                highest = st.number_input("Highest Price ($)", min_value=0.0,
                                          value=float(pos.get("highest_price") or 0),
                                          step=0.01, format="%.2f", key=f"h_{t}",
                                          help="Auto-updated by price feed. Trailing stop ratchets from here.")
            new_positions[t] = {
                "entry_price":   entry   if entry   > 0 else None,
                "position_usd":  pos_usd,
                "highest_price": highest if highest > 0 else pos.get("highest_price"),
            }
            st.markdown("---")

        submitted = st.form_submit_button("💾 Save All Settings", type="primary", use_container_width=True)

    if submitted:
        data["cash"]         = cash
        data["china_checks"] = new_china
        data["ai_checks"]    = new_ai
        data["glp1_checks"]  = new_glp1
        data["positions"]    = new_positions
        save_data(data)
        st.success("✅ Settings saved!")
        st.rerun()

    # ── Stop Reference ──────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Trailing Stop Reference by Tier")
    ref = {
        "Tier":          ["Tier 1 — Core (FCX, CEG, SQM, SCCO, VALE)",
                          "Tier 2 — Growth (MELI, GEV, LLY, PLTR, MSFT)",
                          "Tier 3 — Speculative (ASTS, NVO, SPGI, NU, ZTS)"],
        "Trail %":       ["15%", "12%", "20%"],
        "Trim at":       ["+25% → 15%, +40% → 25%", "+25% → 15%, +40% → 25%", "+40% → 15%, +60% → 25%"],
        "Logic":         [
            "Commodities move fast. Trail tight, sell copper breakdown.",
            "Quality compounders — give more room before trimming.",
            "High vol / binary. Wide trail. ASTS = hold unless thesis breaks.",
        ],
    }
    st.dataframe(pd.DataFrame(ref), use_container_width=True, hide_index=True)

    st.markdown("#### Macro Sell Triggers by Theme")
    sell_ref = {
        "Theme":   list(SELL_RULES.keys()),
        "Sell Rules": list(SELL_RULES.values()),
    }
    st.dataframe(pd.DataFrame(sell_ref), use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════

def main():
    st.set_page_config(
        page_title="🚀 2026 Conviction Portfolio",
        page_icon="🚀",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(CSS, unsafe_allow_html=True)

    data = load_data()

    h1, h2 = st.columns([7, 1])
    with h1:
        st.markdown("## 🚀 2026 Conviction Portfolio — $25K Multi-Theme")
    with h2:
        st.markdown("&nbsp;", unsafe_allow_html=True)
        if st.button("🔄 Refresh", use_container_width=True, help="Clear cache and reload prices"):
            st.cache_data.clear()
            st.rerun()

    if data.get("last_updated"):
        try:
            dt = datetime.fromisoformat(data["last_updated"])
            st.caption(f"Prices cached 5 min · Last fetch: {dt.strftime('%b %d %H:%M:%S')} · Click Refresh to force reload")
        except Exception:
            pass

    with st.spinner("Loading live prices..."):
        prices = fetch_prices()

    # Auto-update highest prices
    changed = False
    for ticker, *_ in PORTFOLIO_DEF:
        price = prices.get(ticker)
        if price:
            curr_high = data["positions"][ticker].get("highest_price")
            if curr_high is None or price > curr_high:
                data["positions"][ticker]["highest_price"] = price
                changed = True

    data["last_updated"] = datetime.now().isoformat()
    if changed:
        save_data(data)

    t1, t2, t3 = st.tabs(["📊 Portfolio", "🌐 Dashboard", "⚙️ Settings"])
    with t1:
        render_portfolio(data, prices)
    with t2:
        render_dashboard(data, prices)
    with t3:
        render_settings(data)


if __name__ == "__main__":
    main()
