import streamlit as st
import requests
import json
import os
from datetime import datetime, date

st.set_page_config(page_title="Agente BTC", page_icon="₿", layout="centered")

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

@st.cache_data(ttl=1800)
def get_indicators():
    errors = []

    # ── Preço atual via CoinGecko ────────────────────────────────────────────
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
            price = float(d["usd"])
            change_24h = round(float(d["usd_24h_change"]), 2)
            volume_24h = round(float(d.get("usd_24h_vol", 0)) / 1e9, 2)
        else:
            errors.append(f"CoinGecko price: {r.status_code}")
    except Exception as e:
        errors.append(f"CoinGecko: {e}")

    # ── Fallback: Binance para preço ─────────────────────────────────────────
    if price is None:
        try:
            r = requests.get(
                "https://api.binance.com/api/v3/ticker/24hr",
                params={"symbol": "BTCUSDT"},
                headers=HEADERS, timeout=15
            )
            if r.status_code == 200:
                d = r.json()
                price = float(d["lastPrice"])
                change_24h = round(float(d["priceChangePercent"]), 2)
                volume_24h = round(float(d["quoteVolume"]) / 1e9, 2)
            else:
                errors.append(f"Binance price: {r.status_code}")
        except Exception as e:
            errors.append(f"Binance price: {e}")

    if price is None:
        return {"error": "Não foi possível obter preço. Erros: " + " | ".join(errors)}

    # ── Candles diários via Binance ──────────────────────────────────────────
    closes_d, vols_d = [], []
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
        else:
            errors.append(f"Binance klines diário: {r.status_code}")
    except Exception as e:
        errors.append(f"Binance klines: {e}")

    # ── Fallback candles: CoinGecko market_chart ─────────────────────────────
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

    # ── Candles semanais via Binance ─────────────────────────────────────────
    closes_w = []
    try:
        r = requests.get(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": "BTCUSDT", "interval": "1w", "limit": 60},
            headers=HEADERS, timeout=20
        )
        if r.status_code == 200:
            raw = r.json()
            if isinstance(raw, list) and len(raw) > 0 and isinstance(raw[0], list):
                closes_w = [float(c[4]) for c in raw]
    except Exception as e:
        errors.append(f"Binance klines semanal: {e}")

    # ── Calcular indicadores ─────────────────────────────────────────────────
    daily = {}
    if len(closes_d) >= 9:
        daily["EMA9"]   = calc_ema(closes_d, 9)
        daily["EMA21"]  = calc_ema(closes_d, 21)
        daily["EMA50"]  = calc_ema(closes_d, 50)
        daily["EMA100"] = calc_ema(closes_d, 100)
        daily["EMA200"] = calc_ema(closes_d, 200)
        daily["SMA50"]  = calc_sma(closes_d, 50)
        daily["SMA200"] = calc_sma(closes_d, 200)

    weekly = {}
    if len(closes_w) >= 9:
        weekly["EMA9"]  = calc_ema(closes_w, 9)
        weekly["EMA20"] = calc_ema(closes_w, 20)
        weekly["EMA21"] = calc_ema(closes_w, 21)
        weekly["EMA50"] = calc_ema(closes_w, 50)
        weekly["SMA20"] = calc_sma(closes_w, 20)

    vol_avg_30d = round(sum(vols_d[-30:]) / 30 / 1e9, 2) if len(vols_d) >= 30 else None
    vol_ratio   = round(volume_24h / vol_avg_30d, 2) if (volume_24h and vol_avg_30d) else None

    ATH = 126198
    halving = date(2024, 4, 19)
    days_post = (date.today() - halving).days
    dist_ath  = round((price - ATH) / ATH * 100, 1)

    if days_post < 180:   phase = "Pós-halving inicial (0-6m)"
    elif days_post < 365: phase = "Acumulação pré-bull (6-12m)"
    elif days_post < 548: phase = "Bull market histórico (12-18m)"
    else:                 phase = "Topo / bear territory (18m+)"

    ema50d  = daily.get("EMA50")
    ema200d = daily.get("EMA200")
    if ema50d and ema200d:
        cross = "Golden Cross ativo" if ema50d > ema200d else "Death Cross ativo"
    else:
        cross = "Indefinido"

    return {
        "price": price, "change_24h": change_24h,
        "volume_24h": volume_24h, "vol_avg_30d": vol_avg_30d, "vol_ratio": vol_ratio,
        "ATH": ATH, "dist_ath": dist_ath, "days_post": days_post,
        "phase": phase, "cross": cross,
        "daily": daily, "weekly": weekly,
        "candles_d": len(closes_d), "candles_w": len(closes_w),
        "errors": errors,
        "updated": datetime.now().strftime("%H:%M:%S")
    }

def build_prompt(ind):
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

        vol_ctx = ""
        if ind.get("vol_ratio"):
            sentiment = "acima da média (pressão compradora)" if ind["vol_ratio"] > 1.2 else \
                        "abaixo da média (mercado apático)" if ind["vol_ratio"] < 0.8 else "dentro da média"
            vol_ctx = f"\nVolume 24h: ${ind['volume_24h']}B (ratio {ind['vol_ratio']}x vs média 30d — {sentiment})"

        data_ctx = f"""DADOS REAIS EM TEMPO REAL (calculados dos candles da Binance/CoinGecko):

Preço: ${p:,.0f} | Variação 24h: {ind['change_24h']}%
ATH: $126.198 (out/2025) | Distância: {ind['dist_ath']}%
Dias pós-halving abr/2024: {ind['days_post']} | Fase: {ind['phase']}
Tendência MA: {ind['cross']}{vol_ctx}

MÉDIAS MÓVEIS DIÁRIAS (calculadas de {ind['candles_d']} candles reais):
{daily_lines if daily_lines else "Insuficiente de dados"}

MÉDIAS MÓVEIS SEMANAIS (calculadas de {ind['candles_w']} candles reais):
{weekly_lines if weekly_lines else "Insuficiente de dados"}

REGRA CRÍTICA: Use APENAS esses valores de médias. Nunca cite valores que não estejam acima."""

    fb = ""
    if st.session_state.feedbacks:
        fb = "\n\nFEEDBACKS REGISTRADOS (aprenda com eles):\n"
        for f in st.session_state.feedbacks[-10:]:
            s = "ACERTOU" if f["result"] == "correct" else "ERROU"
            fb += f"- {f['date']}: \"{f['query']}\" → {s}: {f['note']}\n"

    return f"""Você é um agente quantitativo especializado em Bitcoin com conhecimento histórico completo desde 2011.

{data_ctx}

CICLOS HISTÓRICOS:
- 2011: ATH $32 → queda 94%
- 2013a: ATH $266 → queda 83%
- 2013b: ATH $1.163 → queda 86%, bear 14 meses
- 2017: ATH $19.891 → queda 84%, bear até dez/2018
- 2019: rally falso $13.800 → queda 52%
- 2020-21: halving mai/2020, ATH $69k nov/2021 → queda 77%
- 2022: mínima $15.476 (FTX), bear completo
- 2023: recuperação +155%
- 2024: halving abril, ETFs janeiro, ATH $108k dezembro
- 2025: ATH $126.198 outubro, correção em curso

PADRÕES PÓS-HALVING (média 3 ciclos anteriores):
- 0-6m: lateralização, retorno médio +40%
- 6-12m: aceleração bullish, retorno médio +120%
- 12-18m: bull market principal, retorno médio +200%
- 18-24m: euforia e topo, risco máximo
- Pós-topo: bear 12-14 meses, queda média 80%

REGRAS:
1. Use sempre os dados em tempo real — nunca invente valores
2. Compare com análogos históricos com datas e números reais
3. Probabilidades numéricas baseadas em frequência histórica
4. Identifique a fase e o que aconteceu nela nos ciclos anteriores
5. Seja direto — diga o que os dados sugerem
6. Se uma média não está na lista, diga que não foi calculada{fb}"""

def send_message(api_key, user_msg, ind):
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
                "max_tokens": 1200,
                "system": build_prompt(ind),
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
st.caption("Médias calculadas dos candles reais — sem valores inventados")

ind = get_indicators()

if ind and "error" not in ind:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Preço", f"${ind['price']:,.0f}", f"{ind['change_24h']}% 24h")
    c2.metric("Dist. ATH", f"{ind['dist_ath']}%", "de $126.198")
    c3.metric("Pós-halving", f"{ind['days_post']}d", "abr/2024")
    c4.metric("MA Trend", ind['cross'].split()[0], ind['cross'].split()[-1])

    with st.expander("📊 Médias móveis reais"):
        col1, col2 = st.columns(2)
        p = ind["price"]
        with col1:
            st.markdown("**Diárias**")
            for name, val in ind["daily"].items():
                if val:
                    diff = round((p - val) / val * 100, 1)
                    pos = "suporte" if p > val else "resistência"
                    icon = "🟢" if p > val else "🔴"
                    st.markdown(f"{icon} **{name}:** ${val:,.0f} ({pos}, {diff:+.1f}%)")
        with col2:
            st.markdown("**Semanais**")
            for name, val in ind["weekly"].items():
                if val:
                    diff = round((p - val) / val * 100, 1)
                    pos = "suporte" if p > val else "resistência"
                    icon = "🟢" if p > val else "🔴"
                    st.markdown(f"{icon} **{name}:** ${val:,.0f} ({pos}, {diff:+.1f}%)")

    info = f"Atualizado às {ind['updated']} | {ind['candles_d']} candles diários, {ind['candles_w']} semanais"
    if ind.get("vol_ratio"):
        info += f" | Volume ratio: {ind['vol_ratio']}x"
    st.caption(info)

    if ind.get("errors"):
        with st.expander("⚠️ Avisos"):
            for e in ind["errors"]:
                st.warning(e)
elif ind and "error" in ind:
    st.error(f"Erro ao carregar dados: {ind['error']}")

st.divider()

st.markdown("**Perguntas rápidas:**")
perguntas = [
    "Qual a situação atual do BTC?",
    "Chances de romper $90k em 60 dias?",
    "Esse drawdown lembra qual período histórico?",
    "O volume indica acumulação ou distribuição?",
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
            reply, err = send_message(api_key, final_prompt, ind)
        if err:
            st.error(err)
        else:
            st.markdown(reply)
            st.session_state.messages.append({"role": "user", "content": final_prompt})
            st.session_state.messages.append({"role": "assistant", "content": reply})
            st.rerun()
