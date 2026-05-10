import streamlit as st
import requests
import json
import os
from datetime import datetime, date

st.set_page_config(page_title="Agente BTC", page_icon="₿", layout="centered")

FEEDBACK_FILE = "feedbacks.json"

for key, val in [("messages", []), ("feedbacks", []), ("indicators", None)]:
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

# ── Cálculo de EMA ───────────────────────────────────────────────────────────
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

# ── Buscar candles reais da Binance e calcular indicadores ───────────────────
@st.cache_data(ttl=3600)
def get_indicators():
    try:
        # Candles diários — 300 candles para ter EMA200 precisa
        r_daily = requests.get(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": "BTCUSDT", "interval": "1d", "limit": 300},
            timeout=15
        )
        daily = r_daily.json()
        closes_d = [float(c[4]) for c in daily]

        # Candles semanais — 100 semanas
        r_weekly = requests.get(
            "https://api.binance.com/api/v3/klines",
            params={"symbol": "BTCUSDT", "interval": "1w", "limit": 100},
            timeout=15
        )
        weekly = r_weekly.json()
        closes_w = [float(c[4]) for c in weekly]

        # Preço atual
        r_price = requests.get(
            "https://api.binance.com/api/v3/ticker/24hr",
            params={"symbol": "BTCUSDT"},
            timeout=10
        )
        ticker = r_price.json()
        price = float(ticker["lastPrice"])
        change_24h = float(ticker["priceChangePercent"])
        volume_24h = float(ticker["quoteVolume"])

        # Volume médio 30 dias
        vols_d = [float(c[7]) for c in daily]
        vol_avg_30 = round(sum(vols_d[-30:]) / 30, 0)
        vol_ratio = round(volume_24h / vol_avg_30, 2)

        # Indicadores diários
        ema9_d   = calc_ema(closes_d, 9)
        ema21_d  = calc_ema(closes_d, 21)
        ema50_d  = calc_ema(closes_d, 50)
        ema100_d = calc_ema(closes_d, 100)
        ema200_d = calc_ema(closes_d, 200)
        sma50_d  = calc_sma(closes_d, 50)
        sma200_d = calc_sma(closes_d, 200)

        # Indicadores semanais
        ema9_w  = calc_ema(closes_w, 9)
        ema20_w = calc_ema(closes_w, 20)
        ema21_w = calc_ema(closes_w, 21)
        ema50_w = calc_ema(closes_w, 50)
        sma20_w = calc_sma(closes_w, 20)

        # Drawdown do ATH
        ATH = 126198
        dist_ath = round((price - ATH) / ATH * 100, 1)

        # Fase do halving
        halving = date(2024, 4, 19)
        days_post = (date.today() - halving).days
        if days_post < 180:   phase = "Pós-halving inicial (0-6m)"
        elif days_post < 365: phase = "Acumulação pré-bull (6-12m)"
        elif days_post < 548: phase = "Bull market histórico (12-18m)"
        else:                 phase = "Topo / bear territory (18m+)"

        # Tendência golden/death cross
        cross = "Golden Cross ativo" if ema50_d and ema200_d and ema50_d > ema200_d else "Death Cross ativo"

        return {
            "price": price,
            "change_24h": round(change_24h, 2),
            "volume_24h": round(volume_24h / 1e6, 1),
            "vol_avg_30d": round(vol_avg_30 / 1e6, 1),
            "vol_ratio": vol_ratio,
            "ATH": ATH,
            "dist_ath": dist_ath,
            "days_post": days_post,
            "phase": phase,
            "cross": cross,
            "daily": {
                "EMA9":   ema9_d,
                "EMA21":  ema21_d,
                "EMA50":  ema50_d,
                "EMA100": ema100_d,
                "EMA200": ema200_d,
                "SMA50":  sma50_d,
                "SMA200": sma200_d,
            },
            "weekly": {
                "EMA9":  ema9_w,
                "EMA20": ema20_w,
                "EMA21": ema21_w,
                "EMA50": ema50_w,
                "SMA20": sma20_w,
            },
            "updated": datetime.now().strftime("%H:%M:%S")
        }
    except Exception as e:
        return {"error": str(e)}

# ── Prompt de sistema ────────────────────────────────────────────────────────
def build_prompt(ind):
    if not ind or "error" in ind:
        data_ctx = "Dados em tempo real indisponíveis."
    else:
        d = ind["daily"]
        w = ind["weekly"]
        data_ctx = f"""DADOS EM TEMPO REAL (calculados dos candles reais da Binance — não invente outros valores):

Preço atual: ${ind['price']:,.0f}
Variação 24h: {ind['change_24h']}%
Volume 24h: ${ind['volume_24h']}M (média 30d: ${ind['vol_avg_30d']}M | ratio: {ind['vol_ratio']}x)
ATH: $126.198 (out/2025) | Distância: {ind['dist_ath']}%
Dias pós-halving abr/2024: {ind['days_post']} | Fase: {ind['phase']}
Tendência MA: {ind['cross']}

MÉDIAS MÓVEIS DIÁRIAS (calculadas dos candles reais):
- EMA9:   ${d['EMA9']:,.0f}
- EMA21:  ${d['EMA21']:,.0f}
- EMA50:  ${d['EMA50']:,.0f}
- EMA100: ${d['EMA100']:,.0f}
- EMA200: ${d['EMA200']:,.0f}
- SMA50:  ${d['SMA50']:,.0f}
- SMA200: ${d['SMA200']:,.0f}

MÉDIAS MÓVEIS SEMANAIS (calculadas dos candles reais):
- EMA9:  ${w['EMA9']:,.0f}
- EMA20: ${w['EMA20']:,.0f}
- EMA21: ${w['EMA21']:,.0f}
- EMA50: ${w['EMA50']:,.0f}
- SMA20: ${w['SMA20']:,.0f}

REGRA CRÍTICA: Use APENAS os valores de médias acima. Nunca cite valores de médias que não estejam nessa lista. Se alguém perguntar por uma média que não está aqui, diga que não foi calculada."""

    fb = ""
    if st.session_state.feedbacks:
        fb = "\n\nFEEDBACKS ANTERIORES (aprenda com eles):\n"
        for f in st.session_state.feedbacks[-10:]:
            s = "ACERTOU" if f["result"] == "correct" else "ERROU"
            fb += f"- {f['date']}: \"{f['query']}\" → {s}: {f['note']}\n"

    return f"""Você é um agente quantitativo especializado em Bitcoin com conhecimento histórico completo desde 2011.

{data_ctx}

CICLOS HISTÓRICOS DO BTC:
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

REGRAS DE ANÁLISE:
1. Use sempre os dados em tempo real como base — nunca invente valores
2. Compare com análogos históricos específicos com datas e números reais
3. Dê probabilidades numéricas baseadas em frequência histórica
4. Identifique a fase do ciclo e o que aconteceu nela nos ciclos anteriores
5. Seja direto — diga o que os dados sugerem, não o que o usuário quer ouvir
6. Quantifique incertezas quando existirem
7. Se o preço atual está acima de uma média, diga que é suporte; abaixo, resistência{fb}"""

# ── Enviar para API ──────────────────────────────────────────────────────────
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
            return None, "API key inválida. Verifique na barra lateral."
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
    if st.button("🔄 Atualizar indicadores"):
        st.cache_data.clear()
        st.rerun()
    if st.button("🗑️ Limpar conversa"):
        st.session_state.messages = []
        st.rerun()

st.title("₿ Agente BTC")
st.caption("Médias móveis calculadas dos candles reais da Binance — sem valores inventados")

# Carregar indicadores
ind = get_indicators()

if ind and "error" not in ind:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Preço", f"${ind['price']:,.0f}", f"{ind['change_24h']}% 24h")
    c2.metric("Dist. ATH", f"{ind['dist_ath']}%", "de $126.198")
    c3.metric("Pós-halving", f"{ind['days_post']}d", "abr/2024")
    c4.metric("MA Trend", ind['cross'].split()[0], ind['cross'].split()[-1] if len(ind['cross'].split()) > 1 else "")

    with st.expander("📊 Médias móveis reais (Binance)"):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Diárias**")
            d = ind["daily"]
            p = ind["price"]
            for name, val in d.items():
                if val:
                    diff = round((p - val) / val * 100, 1)
                    pos = "suporte" if p > val else "resistência"
                    icon = "🟢" if p > val else "🔴"
                    st.markdown(f"{icon} **{name}:** ${val:,.0f} ({pos}, {diff:+.1f}%)")
        with col2:
            st.markdown("**Semanais**")
            w = ind["weekly"]
            for name, val in w.items():
                if val:
                    diff = round((p - val) / val * 100, 1)
                    pos = "suporte" if p > val else "resistência"
                    icon = "🟢" if p > val else "🔴"
                    st.markdown(f"{icon} **{name}:** ${val:,.0f} ({pos}, {diff:+.1f}%)")
    st.caption(f"Dados atualizados às {ind.get('updated', '—')} | Volume 24h: ${ind['volume_24h']}M (ratio vs 30d: {ind['vol_ratio']}x)")
elif ind and "error" in ind:
    st.error(f"Erro ao carregar dados da Binance: {ind['error']}")
else:
    st.warning("Carregando dados...")

st.divider()

# Perguntas rápidas
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

# Histórico do chat
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

# Input
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
