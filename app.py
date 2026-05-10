import streamlit as st
import requests
import json
import os
from datetime import datetime, date
from btc_context import BTC_HISTORICAL_CONTEXT

st.set_page_config(page_title="Agente BTC", page_icon="₿", layout="wide")

FEEDBACK_FILE = "feedbacks.json"

for key, val in [("messages", []), ("feedbacks", [])]:
    if key not in st.session_state:
        st.session_state[key] = val

def load_feedbacks():
    try:
        if os.path.exists(FEEDBACK_FILE):
            with open(FEEDBACK_FILE) as f:
                st.session_state.feedbacks = json.load(f)
    except:
        st.session_state.feedbacks = []

def save_feedbacks():
    try:
        with open(FEEDBACK_FILE, "w") as f:
            json.dump(st.session_state.feedbacks, f, ensure_ascii=False, indent=2)
    except:
        pass

load_feedbacks()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json"
}

def calc_ema(closes, period):
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = price * k + ema * (1 - k)
    return round(ema, 0)

def calc_sma(closes, period):
    if len(closes) < period:
        return None
    return round(sum(closes[-period:]) / period, 0)

# ── Dados macro dos EUA via FRED (gratuito, sem key) ────────────────────────
@st.cache_data(ttl=86400)
def get_macro_data():
    macro = {}
    try:
        # Taxa de juros Fed Funds via FRED API (sem key, endpoint público)
        r = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": "FEDFUNDS",
                "api_key": "4a91b29932e776f7d4d73b7d70c37ec5",
                "file_type": "json",
                "limit": 2,
                "sort_order": "desc"
            },
            headers=HEADERS, timeout=10
        )
        if r.status_code == 200:
            obs = r.json().get("observations", [])
            if obs:
                macro["fed_rate"] = float(obs[0]["value"])
                macro["fed_rate_prev"] = float(obs[1]["value"]) if len(obs) > 1 else None
    except Exception as e:
        macro["fed_rate_error"] = str(e)

    try:
        # Inflação CPI via FRED
        r = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": "CPIAUCSL",
                "api_key": "4a91b29932e776f7d4d73b7d70c37ec5",
                "file_type": "json",
                "limit": 13,
                "sort_order": "desc"
            },
            headers=HEADERS, timeout=10
        )
        if r.status_code == 200:
            obs = r.json().get("observations", [])
            if len(obs) >= 13:
                cpi_now  = float(obs[0]["value"])
                cpi_year = float(obs[12]["value"])
                macro["cpi_yoy"] = round((cpi_now - cpi_year) / cpi_year * 100, 2)
                macro["cpi_date"] = obs[0]["date"]
    except Exception as e:
        macro["cpi_error"] = str(e)

    try:
        # Desemprego via FRED
        r = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": "UNRATE",
                "api_key": "4a91b29932e776f7d4d73b7d70c37ec5",
                "file_type": "json",
                "limit": 2,
                "sort_order": "desc"
            },
            headers=HEADERS, timeout=10
        )
        if r.status_code == 200:
            obs = r.json().get("observations", [])
            if obs:
                macro["unemployment"] = float(obs[0]["value"])
                macro["unemployment_prev"] = float(obs[1]["value"]) if len(obs) > 1 else None
    except Exception as e:
        macro["unemployment_error"] = str(e)

    try:
        # DXY (Dólar Index) via alternativa gratuita
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB",
            params={"interval": "1d", "range": "5d"},
            headers=HEADERS, timeout=10
        )
        if r.status_code == 200:
            d = r.json()
            closes = d["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            closes = [c for c in closes if c is not None]
            if closes:
                macro["dxy"] = round(closes[-1], 2)
                macro["dxy_change"] = round(closes[-1] - closes[0], 2) if len(closes) > 1 else None
    except Exception as e:
        macro["dxy_error"] = str(e)

    try:
        # Treasury 10Y yield via Yahoo Finance
        r = requests.get(
            "https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX",
            params={"interval": "1d", "range": "5d"},
            headers=HEADERS, timeout=10
        )
        if r.status_code == 200:
            d = r.json()
            closes = d["chart"]["result"][0]["indicators"]["quote"][0]["close"]
            closes = [c for c in closes if c is not None]
            if closes:
                macro["treasury_10y"] = round(closes[-1], 3)
                macro["treasury_change"] = round(closes[-1] - closes[0], 3) if len(closes) > 1 else None
    except Exception as e:
        macro["treasury_error"] = str(e)

    return macro

# ── Dados de derivativos: liquidações e long/short ratio ────────────────────
@st.cache_data(ttl=300)
def get_derivatives():
    deriv = {}
    try:
        # Long/short ratio via Binance (endpoint público)
        r = requests.get(
            "https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
            params={"symbol": "BTCUSDT", "period": "1h", "limit": 2},
            headers=HEADERS, timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            if data and len(data) > 0:
                deriv["long_short_ratio"] = round(float(data[0]["longShortRatio"]), 3)
                deriv["long_pct"] = round(float(data[0]["longAccount"]) * 100, 1)
                deriv["short_pct"] = round(float(data[0]["shortAccount"]) * 100, 1)
    except Exception as e:
        deriv["ls_error"] = str(e)

    try:
        # Open Interest via Binance
        r = requests.get(
            "https://fapi.binance.com/fapi/v1/openInterest",
            params={"symbol": "BTCUSDT"},
            headers=HEADERS, timeout=10
        )
        if r.status_code == 200:
            d = r.json()
            deriv["open_interest"] = round(float(d["openInterest"]) * float(d.get("price", 80000)) / 1e9, 2)
    except Exception as e:
        deriv["oi_error"] = str(e)

    try:
        # Funding rate via Binance
        r = requests.get(
            "https://fapi.binance.com/fapi/v1/fundingRate",
            params={"symbol": "BTCUSDT", "limit": 3},
            headers=HEADERS, timeout=10
        )
        if r.status_code == 200:
            data = r.json()
            if data:
                deriv["funding_rate"] = round(float(data[-1]["fundingRate"]) * 100, 4)
    except Exception as e:
        deriv["funding_error"] = str(e)

    try:
        # Liquidações via CoinGlass (alternativa pública)
        r = requests.get(
            "https://open-api.coinglass.com/public/v2/liquidation_history",
            params={"symbol": "BTC", "time_type": "h4"},
            headers=HEADERS, timeout=10
        )
        if r.status_code == 200:
            d = r.json()
            if d.get("data") and len(d["data"]) > 0:
                latest = d["data"][0]
                deriv["liq_long_4h"] = round(float(latest.get("longLiquidationUsd", 0)) / 1e6, 2)
                deriv["liq_short_4h"] = round(float(latest.get("shortLiquidationUsd", 0)) / 1e6, 2)
    except Exception as e:
        deriv["liq_error"] = str(e)

    return deriv

# ── Dados BTC + indicadores ──────────────────────────────────────────────────
@st.cache_data(ttl=1800)
def get_indicators():
    errors = []
    price, change_24h, volume_24h = None, None, None

    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin", "vs_currencies": "usd",
                    "include_24hr_change": "true", "include_24hr_vol": "true"},
            headers=HEADERS, timeout=15
        )
        if r.status_code == 200:
            d = r.json()["bitcoin"]
            price      = float(d["usd"])
            change_24h = round(float(d["usd_24h_change"]), 2)
            volume_24h = round(float(d.get("usd_24h_vol", 0)) / 1e9, 2)
        else:
            errors.append(f"CoinGecko price: {r.status_code}")
    except Exception as e:
        errors.append(f"CoinGecko: {e}")

    if price is None:
        try:
            r = requests.get(
                "https://api.binance.com/api/v3/ticker/24hr",
                params={"symbol": "BTCUSDT"},
                headers=HEADERS, timeout=15
            )
            if r.status_code == 200:
                d = r.json()
                price      = float(d["lastPrice"])
                change_24h = round(float(d["priceChangePercent"]), 2)
                volume_24h = round(float(d["quoteVolume"]) / 1e9, 2)
        except Exception as e:
            errors.append(f"Binance price: {e}")

    if price is None:
        return {"error": "Não foi possível obter preço. " + " | ".join(errors)}

    closes_d, vols_d, closes_w = [], [], []

    try:
        r = requests.get(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": "BTCUSDT", "interval": "1d", "limit": 220},
            headers=HEADERS, timeout=20
        )
        if r.status_code == 200:
            raw = r.json()
            if isinstance(raw, list) and len(raw) > 0 and isinstance(raw[0], list):
                closes_d = [float(c[4]) for c in raw]
                vols_d   = [float(c[7]) for c in raw]
    except Exception as e:
        errors.append(f"Binance klines diário: {e}")

    if len(closes_d) < 50:
        try:
            r = requests.get(
                "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
                params={"vs_currency": "usd", "days": "220", "interval": "daily"},
                headers=HEADERS, timeout=20
            )
            if r.status_code == 200:
                d = r.json()
                closes_d = [p[1] for p in d.get("prices", [])]
                vols_d   = [v[1] for v in d.get("total_volumes", [])]
        except Exception as e:
            errors.append(f"CoinGecko market_chart: {e}")

    # Candles semanais — busca diários da Binance com startTime para ter histórico longo
    # Binance diário funciona, então buscamos múltiplos lotes de 1000 dias
    import time as _time
    all_daily = []
    try:
        end_ms = int(_time.time() * 1000)
        for _ in range(5):  # até 5000 dias = ~13 anos
            r = requests.get(
                "https://api.binance.com/api/v3/klines",
                params={"symbol": "BTCUSDT", "interval": "1d", "limit": 1000, "endTime": end_ms},
                headers=HEADERS, timeout=20
            )
            if r.status_code == 200:
                raw = r.json()
                if isinstance(raw, list) and len(raw) > 0 and isinstance(raw[0], list):
                    batch = [(int(c[0]), float(c[4])) for c in raw]
                    all_daily = batch + all_daily
                    end_ms = batch[0][0] - 1
                    if len(all_daily) >= 2000:
                        break
                else:
                    break
            else:
                break
    except Exception as e:
        errors.append(f"Binance diario lote: {e}")

    # Agrupa em semanais: pega o fechamento de domingo (último dia da semana ISO)
    if len(all_daily) > 200:
        from datetime import datetime as _dt
        weekly_map = {}
        for ts, close in all_daily:
            d = _dt.utcfromtimestamp(ts / 1000)
            # Semana ISO: segunda=0, domingo=6
            # Agrupamos pelo número da semana do ano
            week_key = (d.isocalendar()[0], d.isocalendar()[1])
            weekly_map[week_key] = close  # sobrescreve com o último dia da semana
        closes_w = [v for k, v in sorted(weekly_map.items())]
    
    # Fallback: CoinGecko reamostrado
    if len(closes_w) < 50:
        try:
            r = requests.get(
                "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
                params={"vs_currency": "usd", "days": "2000"},
                headers=HEADERS, timeout=30
            )
            if r.status_code == 200:
                d = r.json()
                prices_daily = [p[1] for p in d.get("prices", [])]
                closes_w = [prices_daily[i] for i in range(6, len(prices_daily), 7)]
        except Exception as e:
            errors.append(f"CoinGecko semanal fallback: {e}")

    daily = {}
    if len(closes_d) >= 9:
        daily = {
            "EMA9":   calc_ema(closes_d, 9),
            "EMA21":  calc_ema(closes_d, 21),
            "EMA50":  calc_ema(closes_d, 50),
            "EMA100": calc_ema(closes_d, 100),
            "EMA200": calc_ema(closes_d, 200),
            "SMA50":  calc_sma(closes_d, 50),
            "SMA200": calc_sma(closes_d, 200),
        }
    weekly = {}
    if len(closes_w) >= 9:
        weekly = {
            "EMA9":   calc_ema(closes_w, 9),
            "EMA21":  calc_ema(closes_w, 21),
            "EMA50":  calc_ema(closes_w, 50),
            "EMA100": calc_ema(closes_w, 100),
            "SMA20":  calc_sma(closes_w, 20),
            "SMA50":  calc_sma(closes_w, 50),
            "SMA200": calc_sma(closes_w, 200),
        }

    vol_avg_30d = round(sum(vols_d[-30:]) / 30 / 1e9, 2) if len(vols_d) >= 30 else None
    vol_ratio   = round(volume_24h / vol_avg_30d, 2) if (volume_24h and vol_avg_30d) else None

    dominance = None
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/global",
            headers=HEADERS, timeout=10
        )
        if r.status_code == 200:
            d = r.json().get("data", {})
            dominance = round(d.get("market_cap_percentage", {}).get("btc", 0), 1)
    except Exception as e:
        errors.append(f"Dominância: {e}")

    ATH = 126198
    halving = date(2024, 4, 19)
    days_post = (date.today() - halving).days
    dist_ath  = round((price - ATH) / ATH * 100, 1)

    if days_post < 180:   phase = "Pós-halving inicial (0-6m)"
    elif days_post < 365: phase = "Acumulação pré-bull (6-12m)"
    elif days_post < 548: phase = "Bull market histórico (12-18m)"
    else:                 phase = "Fase avançada pós-halving (18m+)"

    ema50d  = daily.get("EMA50")
    ema200d = daily.get("EMA200")
    cross = "Golden Cross ativo" if (ema50d and ema200d and ema50d > ema200d) else \
            "Death Cross ativo" if (ema50d and ema200d) else "Indefinido"

    return {
        "price": price, "change_24h": change_24h,
        "volume_24h": volume_24h, "vol_avg_30d": vol_avg_30d, "vol_ratio": vol_ratio,
        "ATH": ATH, "dist_ath": dist_ath, "days_post": days_post,
        "phase": phase, "cross": cross,
        "daily": daily, "weekly": weekly,
        "candles_d": len(closes_d), "candles_w": len(closes_w),
        "dominance": dominance,
        "errors": errors,
        "updated": datetime.now().strftime("%H:%M:%S")
    }

# ── Prompt de sistema ────────────────────────────────────────────────────────
def build_prompt(ind, macro, deriv):
    if not ind or "error" in ind:
        data_ctx = "Dados em tempo real indisponíveis."
    else:
        d = ind["daily"]
        w = ind["weekly"]
        p = ind["price"]

        def fmt(name, val):
            if not val: return ""
            diff = round((p - val) / val * 100, 1)
            pos = "suporte" if p > val else "resistência"
            return f"  {name}: ${val:,.0f} ({pos}, {diff:+.1f}%)"

        daily_lines  = "\n".join([fmt(k, v) for k, v in d.items() if v])
        weekly_lines = "\n".join([fmt(k, v) for k, v in w.items() if v])

        # Volume
        vol_ctx = ""
        if ind.get("vol_ratio"):
            vr = ind["vol_ratio"]
            if vr > 1.5:   vs = "muito acima da média — evento de inflexão possível"
            elif vr > 1.2: vs = "acima da média — pressão compradora"
            elif vr < 0.6: vs = "muito abaixo — mercado apático/acumulação silenciosa"
            elif vr < 0.8: vs = "abaixo da média — baixa convicção"
            else:          vs = "dentro da média — neutro"
            vol_ctx = f"\nVolume 24h: ${ind['volume_24h']}B | Ratio 30d: {vr}x ({vs})"

        # Dominância
        dom_ctx = ""
        if ind.get("dominance"):
            dom = ind["dominance"]
            if dom > 60:   ds = "muito alta — capital concentrado em BTC, altseason distante"
            elif dom > 55: ds = "alta — BTC liderando, altcoins paradas"
            elif dom > 50: ds = "neutra-alta — início de possível rotação"
            elif dom > 45: ds = "neutra-baixa — rotação para altcoins em curso"
            elif dom > 40: ds = "baixa — altseason ativa"
            else:          ds = "muito baixa — euforia de altcoins, topo próximo historicamente"
            dom_ctx = f"\nDominância BTC: {dom}% ({ds})"

        # Macro
        macro_lines = []
        if macro:
            if macro.get("fed_rate") is not None:
                prev = macro.get("fed_rate_prev")
                trend = ""
                if prev is not None:
                    if macro["fed_rate"] > prev: trend = " (subindo — hawkish, pressão sobre BTC)"
                    elif macro["fed_rate"] < prev: trend = " (caindo — dovish, favorável ao BTC)"
                    else: trend = " (estável)"
                macro_lines.append(f"  Taxa Fed Funds: {macro['fed_rate']}%{trend}")
            if macro.get("cpi_yoy") is not None:
                cpi = macro["cpi_yoy"]
                cpi_signal = "acima da meta do Fed (2%) — pressão hawkish" if cpi > 3 else \
                             "próxima da meta — ambiente mais dovish" if cpi > 2 else \
                             "abaixo da meta — Fed pode cortar juros (favorável ao BTC)"
                macro_lines.append(f"  Inflação CPI (YoY): {cpi}% ({cpi_signal})")
            if macro.get("unemployment") is not None:
                ue = macro["unemployment"]
                ue_prev = macro.get("unemployment_prev")
                ue_trend = ""
                if ue_prev:
                    if ue > ue_prev: ue_trend = " (subindo — economia enfraquecendo, Fed pode cortar)"
                    elif ue < ue_prev: ue_trend = " (caindo — economia forte, Fed pode manter juros altos)"
                macro_lines.append(f"  Desemprego EUA: {ue}%{ue_trend}")
            if macro.get("treasury_10y") is not None:
                t10 = macro["treasury_10y"]
                tc = macro.get("treasury_change", 0)
                t_signal = "yield subindo — pressão sobre ativos de risco incluindo BTC" if tc and tc > 0.05 else \
                           "yield caindo — favorável para BTC" if tc and tc < -0.05 else "yield estável"
                macro_lines.append(f"  Treasury 10Y yield: {t10}% ({t_signal})")
            if macro.get("dxy") is not None:
                dxy = macro["dxy"]
                dc = macro.get("dxy_change", 0)
                d_signal = "dólar fortalecendo — pressão sobre BTC" if dc and dc > 0.5 else \
                           "dólar enfraquecendo — favorável ao BTC" if dc and dc < -0.5 else "dólar estável"
                macro_lines.append(f"  DXY (Dólar Index): {dxy} ({d_signal})")

        macro_ctx = "\nDADOS MACRO EUA EM TEMPO REAL:\n" + "\n".join(macro_lines) if macro_lines else ""

        # Derivativos
        deriv_lines = []
        if deriv:
            if deriv.get("long_short_ratio") is not None:
                ls = deriv["long_short_ratio"]
                lp = deriv.get("long_pct", 50)
                sp = deriv.get("short_pct", 50)
                if ls > 1.5:   ls_signal = "excesso de longs — risco de short squeeze ou correção"
                elif ls > 1.2: ls_signal = "maioria long — mercado otimista"
                elif ls < 0.8: ls_signal = "maioria short — risco de short squeeze altista"
                elif ls < 0.67: ls_signal = "excesso de shorts — short squeeze provável"
                else:          ls_signal = "equilibrado"
                deriv_lines.append(f"  Long/Short Ratio: {ls} (Longs: {lp}% | Shorts: {sp}%) — {ls_signal}")
            if deriv.get("funding_rate") is not None:
                fr = deriv["funding_rate"]
                if fr > 0.05:   fr_signal = "muito positivo — excesso de longs, correção iminente provável"
                elif fr > 0.01: fr_signal = "positivo — mercado otimista, longs dominando"
                elif fr < -0.05: fr_signal = "muito negativo — excesso de shorts, short squeeze provável"
                elif fr < -0.01: fr_signal = "negativo — pessimismo, shorts dominando"
                else:           fr_signal = "neutro — mercado equilibrado"
                deriv_lines.append(f"  Funding Rate: {fr}% ({fr_signal})")
            if deriv.get("open_interest") is not None:
                deriv_lines.append(f"  Open Interest: ${deriv['open_interest']}B")
            if deriv.get("liq_long_4h") is not None:
                total_liq = deriv["liq_long_4h"] + deriv.get("liq_short_4h", 0)
                dominant = "longs liquidados" if deriv["liq_long_4h"] > deriv.get("liq_short_4h", 0) else "shorts liquidados"
                deriv_lines.append(f"  Liquidações 4h: ${total_liq}M total ({dominant} dominando)")

        deriv_ctx = "\nDADOS DE DERIVATIVOS EM TEMPO REAL:\n" + "\n".join(deriv_lines) if deriv_lines else ""

        data_ctx = f"""DADOS EM TEMPO REAL — USE APENAS ESSES VALORES:

Preço: ${p:,.0f} | Variação 24h: {ind['change_24h']}%
ATH: $126.198 (out/2025) | Distância: {ind['dist_ath']}%
Dias pós-halving abr/2024: {ind['days_post']} | Fase: {ind['phase']}
Tendência MA: {ind['cross']}{vol_ctx}{dom_ctx}
{macro_ctx}
{deriv_ctx}

MÉDIAS MÓVEIS DIÁRIAS (de {ind['candles_d']} candles reais):
{daily_lines if daily_lines else "  Dados insuficientes"}

MÉDIAS MÓVEIS SEMANAIS (de {ind['candles_w']} candles reais):
{weekly_lines if weekly_lines else "  Dados insuficientes"}

REGRA CRÍTICA: Use APENAS esses valores. Nunca cite médias que não estejam listadas acima."""

    fb = ""
    if st.session_state.feedbacks:
        fb = "\n\nFEEDBACKS REGISTRADOS (aprenda com eles):\n"
        for f in st.session_state.feedbacks[-15:]:
            s = "ACERTOU" if f["result"] == "correct" else "ERROU"
            fb += f"- {f['date']}: \"{f['query']}\" → {s}: {f['note']}\n"

    return f"""Você é um agente quantitativo especializado em Bitcoin com conhecimento histórico completo desde 2011.

{data_ctx}

{BTC_HISTORICAL_CONTEXT}

REGRAS DE ANÁLISE:
1. Use os dados em tempo real como ponto de partida — nunca invente valores
2. Cruze BTC + macro + derivativos simultaneamente — são interdependentes
3. Compare com análogos históricos específicos com datas e números exatos
4. Dê probabilidades numéricas baseadas na frequência histórica real
5. Identifique a fase do ciclo e o que aconteceu nela nos ciclos anteriores
6. Quando funding rate, long/short e volume contradizem o preço — destaque isso
7. Quando macro (Fed, inflação, DXY) contradiz a análise técnica — destaque isso
8. Seja direto — diga o que os dados sugerem, não o que o usuário quer ouvir
9. Se uma média não está na lista, diga que não foi calculada — nunca invente{fb}"""

# ── Enviar para Claude API ───────────────────────────────────────────────────
def send_message(api_key, user_msg, ind, macro, deriv):
    try:
        msgs = [{"role": m["role"], "content": m["content"]}
                for m in st.session_state.messages]
        msgs.append({"role": "user", "content": user_msg})

        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 1500,
                "system": build_prompt(ind, macro, deriv),
                "messages": msgs
            },
            timeout=60
        )
        if r.status_code == 200:
            return r.json()["content"][0]["text"], None
        elif r.status_code == 401:
            return None, "API key inválida. Crie uma nova em console.anthropic.com/settings/keys"
        elif r.status_code == 429:
            return None, "Limite atingido. Aguarde alguns segundos."
        else:
            return None, f"Erro {r.status_code}: {r.text[:300]}"
    except Exception as e:
        return None, f"Erro: {str(e)}"

# ── Interface ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuração")
    api_key = st.text_input("API Key da Anthropic", type="password",
                            placeholder="sk-ant-...",
                            help="console.anthropic.com/settings/keys")
    if api_key and not api_key.startswith("sk-ant-"):
        st.error("Deve começar com sk-ant-")
        api_key = ""
    elif api_key:
        st.success("✓ Key configurada")
    st.divider()
    st.markdown("""**Como usar:**
1. Cole sua API key acima
2. Pergunte qualquer coisa sobre BTC
3. Avalie acertou/errou
4. O agente aprende com os feedbacks""")
    st.divider()
    if st.button("🔄 Atualizar dados"):
        st.cache_data.clear()
        st.rerun()
    if st.button("🗑️ Limpar conversa"):
        st.session_state.messages = []
        st.rerun()

st.title("₿ Agente BTC")
st.caption("Análise quantitativa — histórico completo desde 2011 + dados macro + derivativos em tempo real")

ind   = get_indicators()
macro = get_macro_data()
deriv = get_derivatives()

if ind and "error" not in ind:
    # Row 1 — BTC
    st.markdown("**Bitcoin**")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Preço", f"${ind['price']:,.0f}", f"{ind['change_24h']}% 24h")
    c2.metric("Dist. ATH", f"{ind['dist_ath']}%", "de $126.198")
    c3.metric("Pós-halving", f"{ind['days_post']}d", "abr/2024")
    c4.metric("MA Trend", ind['cross'].split()[0], ind['cross'].split()[-1])
    if ind.get("dominance"):
        c5.metric("Dominância", f"{ind['dominance']}%", "BTC/mercado")

    # Row 2 — Macro
    st.markdown("**Macro EUA**")
    m1, m2, m3, m4, m5 = st.columns(5)
    if macro.get("fed_rate") is not None:
        delta = round(macro["fed_rate"] - macro["fed_rate_prev"], 2) if macro.get("fed_rate_prev") else None
        m1.metric("Fed Rate", f"{macro['fed_rate']}%", f"{delta:+.2f}%" if delta else None)
    if macro.get("cpi_yoy") is not None:
        m2.metric("Inflação CPI", f"{macro['cpi_yoy']}%", "YoY")
    if macro.get("unemployment") is not None:
        delta_ue = round(macro["unemployment"] - macro["unemployment_prev"], 1) if macro.get("unemployment_prev") else None
        m3.metric("Desemprego", f"{macro['unemployment']}%", f"{delta_ue:+.1f}%" if delta_ue else None)
    if macro.get("treasury_10y") is not None:
        m4.metric("Treasury 10Y", f"{macro['treasury_10y']}%",
                  f"{macro['treasury_change']:+.3f}%" if macro.get("treasury_change") else None)
    if macro.get("dxy") is not None:
        m5.metric("DXY", str(macro["dxy"]),
                  f"{macro['dxy_change']:+.2f}" if macro.get("dxy_change") else None)

    # Row 3 — Derivativos
    st.markdown("**Derivativos**")
    d1, d2, d3, d4 = st.columns(4)
    if deriv.get("long_short_ratio") is not None:
        d1.metric("Long/Short", str(deriv["long_short_ratio"]),
                  f"L:{deriv['long_pct']}% S:{deriv['short_pct']}%")
    if deriv.get("funding_rate") is not None:
        d2.metric("Funding Rate", f"{deriv['funding_rate']}%",
                  "positivo" if deriv["funding_rate"] > 0 else "negativo")
    if deriv.get("open_interest") is not None:
        d3.metric("Open Interest", f"${deriv['open_interest']}B")
    if deriv.get("liq_long_4h") is not None:
        total = deriv["liq_long_4h"] + deriv.get("liq_short_4h", 0)
        d4.metric("Liquidações 4h", f"${total}M",
                  f"L:${deriv['liq_long_4h']}M S:${deriv.get('liq_short_4h',0)}M")

    # Médias móveis expandível
    with st.expander("📊 Médias móveis reais (Binance)"):
        col1, col2 = st.columns(2)
        p = ind["price"]
        with col1:
            st.markdown("**Diárias**")
            for name, val in ind["daily"].items():
                if val:
                    diff = round((p - val) / val * 100, 1)
                    icon = "🟢" if p > val else "🔴"
                    pos  = "suporte" if p > val else "resistência"
                    st.markdown(f"{icon} **{name}:** ${val:,.0f} ({pos}, {diff:+.1f}%)")
        with col2:
            st.markdown("**Semanais**")
            for name, val in ind["weekly"].items():
                if val:
                    diff = round((p - val) / val * 100, 1)
                    icon = "🟢" if p > val else "🔴"
                    pos  = "suporte" if p > val else "resistência"
                    st.markdown(f"{icon} **{name}:** ${val:,.0f} ({pos}, {diff:+.1f}%)")

    st.caption(f"Atualizado às {ind['updated']} | {ind['candles_d']} candles diários, {ind['candles_w']} semanais")

elif ind and "error" in ind:
    st.error(f"Erro: {ind['error']}")

st.divider()

st.markdown("**Perguntas rápidas:**")
perguntas = [
    "Qual a situação atual do BTC?",
    "O macro atual é favorável ou desfavorável ao BTC?",
    "Os derivativos indicam alta ou queda iminente?",
    "Esse drawdown lembra qual período histórico?",
    "Onde estamos no ciclo do halving?",
    "É um bom momento para comprar?"
]
cols = st.columns(3)
triggered = None
for i, q in enumerate(perguntas):
    if cols[i % 3].button(q, key=f"q{i}", use_container_width=True):
        triggered = q

for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
    if msg["role"] == "assistant" and i == len(st.session_state.messages) - 1:
        ca, cb = st.columns([1, 1])
        if ca.button("✓ Acertou", key=f"ok{i}"):
            uq = st.session_state.messages[i-1]["content"][:80] if i > 0 else ""
            st.session_state.feedbacks.append({
                "date": datetime.now().strftime("%d/%m/%Y"),
                "query": uq, "result": "correct", "note": "confirmado"
            })
            save_feedbacks()
            st.success("Registrado!")
        if cb.button("✗ Errou", key=f"no{i}"):
            st.session_state[f"fb{i}"] = True
        if st.session_state.get(f"fb{i}"):
            note = st.text_input("O que aconteceu diferente?", key=f"note{i}")
            if st.button("Salvar", key=f"sv{i}"):
                uq = st.session_state.messages[i-1]["content"][:80] if i > 0 else ""
                st.session_state.feedbacks.append({
                    "date": datetime.now().strftime("%d/%m/%Y"),
                    "query": uq, "result": "wrong", "note": note or "sem detalhe"
                })
                save_feedbacks()
                st.session_state[f"fb{i}"] = False
                st.error("Registrado!")

if st.session_state.feedbacks:
    with st.expander(f"🧠 Memória — {len(st.session_state.feedbacks)} feedbacks"):
        for fb in reversed(st.session_state.feedbacks[-8:]):
            icon = "✓" if fb["result"] == "correct" else "✗"
            cor = "green" if fb["result"] == "correct" else "red"
            st.markdown(f":{cor}[{icon}] **{fb['date']}** — _{fb['query']}_ → {fb['note']}")

prompt = st.chat_input("Pergunte qualquer coisa sobre o BTC...")
final_prompt = triggered or prompt

if final_prompt:
    if not api_key:
        st.error("Cole sua API key da Anthropic na barra lateral.")
        st.stop()

    with st.chat_message("user"):
        st.markdown(final_prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analisando..."):
            reply, err = send_message(api_key, final_prompt, ind, macro, deriv)
        if err:
            st.error(err)
        else:
            st.markdown(reply)
            st.session_state.messages.append({"role": "user", "content": final_prompt})
            st.session_state.messages.append({"role": "assistant", "content": reply})
            st.rerun()
