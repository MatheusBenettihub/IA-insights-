import streamlit as st
import requests
import json
import os
from datetime import datetime, date
from anthropic import Anthropic

st.set_page_config(
    page_title="Agente BTC",
    page_icon="₿",
    layout="centered"
)

st.markdown("""
<style>
    .main { max-width: 780px; }
    .stTextInput > div > div > input { font-size: 15px; }
    .metric-row { display: flex; gap: 12px; margin-bottom: 1rem; }
    div[data-testid="metric-container"] {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 12px 16px;
        border: 1px solid #eee;
    }
    .feedback-box {
        background: #f0fdf4;
        border-left: 3px solid #22c55e;
        padding: 10px 14px;
        border-radius: 6px;
        font-size: 14px;
        margin-top: 8px;
    }
    .feedback-box.wrong {
        background: #fff1f2;
        border-left-color: #ef4444;
    }
    .chat-msg-user {
        background: #eff6ff;
        border-radius: 12px;
        padding: 12px 16px;
        margin: 8px 0;
        font-size: 15px;
    }
    .chat-msg-ai {
        background: #f9fafb;
        border-radius: 12px;
        padding: 12px 16px;
        margin: 8px 0;
        font-size: 15px;
        border: 1px solid #e5e7eb;
    }
</style>
""", unsafe_allow_html=True)

# ── Inicialização do estado ──────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []
if "feedbacks" not in st.session_state:
    st.session_state.feedbacks = []
if "btc" not in st.session_state:
    st.session_state.btc = None

FEEDBACK_FILE = "feedbacks.json"

def load_feedbacks():
    if os.path.exists(FEEDBACK_FILE):
        with open(FEEDBACK_FILE) as f:
            st.session_state.feedbacks = json.load(f)

def save_feedbacks():
    with open(FEEDBACK_FILE, "w") as f:
        json.dump(st.session_state.feedbacks, f, ensure_ascii=False, indent=2)

load_feedbacks()

# ── Dados em tempo real ──────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_btc_data():
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": "bitcoin", "vs_currencies": "usd",
                    "include_24hr_change": "true", "include_24hr_vol": "true"},
            timeout=8
        )
        d = r.json()["bitcoin"]
        price = d["usd"]
        change = d["usd_24h_change"]
        ATH = 126198
        halving = date(2024, 4, 19)
        days_post = (date.today() - halving).days
        dist_ath = round((price - ATH) / ATH * 100, 1)

        if days_post < 180:
            phase = "Pós-halving inicial"
        elif days_post < 365:
            phase = "Acumulação pré-bull"
        elif days_post < 548:
            phase = "Bull market histórico"
        else:
            phase = "Topo / bear territory"

        return {
            "price": price,
            "change": round(change, 2),
            "dist_ath": dist_ath,
            "days_post": days_post,
            "phase": phase,
            "ATH": ATH
        }
    except Exception as e:
        return None

# ── Prompt de sistema ────────────────────────────────────────────────────────
def build_system_prompt(btc):
    price_ctx = f"""
DADOS EM TEMPO REAL:
- Preço atual: ${btc['price']:,.0f}
- Variação 24h: {btc['change']}%
- ATH histórico: $126.198 (outubro/2025)
- Distância do ATH: {btc['dist_ath']}%
- Dias desde o halving de abril/2024: {btc['days_post']} dias
- Fase atual: {btc['phase']}
""" if btc else "Dados em tempo real indisponíveis no momento."

    fb_ctx = ""
    if st.session_state.feedbacks:
        fb_ctx = "\n\nHISTÓRICO DE FEEDBACKS — aprenda com esses registros:\n"
        for f in st.session_state.feedbacks[-15:]:
            status = "ACERTOU" if f["result"] == "correct" else "ERROU"
            fb_ctx += f"- {f['date']}: \"{f['query']}\" → {status}: {f['note']}\n"

    return f"""Você é um agente quantitativo especializado em Bitcoin, com conhecimento do histórico completo desde 2011.

{price_ctx}

CICLOS HISTÓRICOS DO BTC:
- 2011: ATH ~$32. Queda 94%. Recuperação em 2 anos.
- 2013 (jan): ATH ~$266. Queda 83%.
- 2013 (nov): ATH ~$1.163. Queda 86%. Bear 14 meses.
- 2017: ATH ~$19.891. Queda 84%. Bear até dez/2018.
- 2019: Rally falso até $13.800. Queda 52%.
- 2020-2021: Halving mai/2020. ATH $69k em nov/2021. Queda 77%.
- 2022: Mínima $15.476 (colapso FTX). Bear market completo.
- 2023: Recuperação +155% no ano.
- 2024: Halving abril. ETFs aprovados janeiro. ATH $108k em dezembro.
- 2025: ATH $126.198 em outubro. Correção em curso.

PADRÕES PÓS-HALVING (histórico dos 3 ciclos anteriores):
- 0-6 meses: lateralização. Retorno médio: +40%
- 6-12 meses: aceleração bullish. Retorno médio: +120%
- 12-18 meses: bull market principal. Retorno médio: +200%
- 18-24 meses: euforia e topo. Risco máximo.
- Pós-topo: bear médio de 12-14 meses, queda média 80%.

REGRAS DE ANÁLISE:
1. Use sempre os dados em tempo real como ponto de partida
2. Compare com análogos históricos específicos — cite datas e números reais
3. Dê probabilidades numéricas baseadas em frequência histórica
4. Identifique a fase do ciclo e o que aconteceu nas fases equivalentes anteriores
5. Seja direto — diga o que os dados sugerem, não o que o usuário quer ouvir
6. Quantifique incertezas quando existirem
7. Nunca invente dados históricos — se não tiver certeza, diga claramente
8. Formato de resposta: situação atual → análogos históricos → probabilidades → conclusão{fb_ctx}"""

# ── Interface ────────────────────────────────────────────────────────────────
st.title("₿ Agente BTC")
st.caption("Análise quantitativa — histórico desde 2011 + dados em tempo real")

# API key
with st.sidebar:
    st.header("Configuração")
    api_key = st.text_input("API Key da Anthropic", type="password",
                            placeholder="sk-ant-...",
                            help="Obtenha em console.anthropic.com/settings/keys")
    st.divider()
    st.subheader("Como usar")
    st.markdown("""
1. Cole sua API key acima
2. Faça qualquer pergunta sobre BTC
3. Avalie as respostas (acertou/errou)
4. O agente aprende com os feedbacks
    """)
    st.divider()
    if st.button("🔄 Atualizar dados BTC"):
        st.cache_data.clear()
        st.rerun()

# Dados em tempo real
btc = get_btc_data()
st.session_state.btc = btc

if btc:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        delta_color = "normal" if btc["change"] >= 0 else "inverse"
        st.metric("Preço", f"${btc['price']:,.0f}", f"{btc['change']}% 24h")
    with col2:
        st.metric("Dist. ATH", f"{btc['dist_ath']}%", "de $126.198")
    with col3:
        st.metric("Pós-halving", f"{btc['days_post']} dias", "abr/2024")
    with col4:
        st.metric("Fase", btc["phase"])
else:
    st.warning("Não foi possível carregar dados em tempo real. Verifique sua conexão.")

st.divider()

# Perguntas rápidas
st.markdown("**Perguntas rápidas:**")
cols = st.columns(3)
quick = [
    "Qual a situação atual do BTC?",
    "Chances de romper $90k em 60 dias?",
    "Esse drawdown se parece com qual período histórico?",
    "O volume indica acumulação ou distribuição?",
    "Onde estamos no ciclo do halving?",
    "É um bom momento para comprar?"
]
for i, q in enumerate(quick):
    with cols[i % 3]:
        if st.button(q, key=f"quick_{i}", use_container_width=True):
            st.session_state.pending_question = q

# Histórico do chat
for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

    # Feedback após resposta do assistente
    if msg["role"] == "assistant" and i == len(st.session_state.messages) - 1:
        col_a, col_b, col_c = st.columns([2, 1, 1])
        with col_b:
            if st.button("✓ Acertou", key=f"correct_{i}", type="secondary"):
                user_q = st.session_state.messages[i-1]["content"] if i > 0 else ""
                st.session_state.feedbacks.append({
                    "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "query": user_q[:80],
                    "result": "correct",
                    "note": "análise confirmada"
                })
                save_feedbacks()
                st.success("Registrado! O agente aprenderá com isso.")
        with col_c:
            if st.button("✗ Errou", key=f"wrong_{i}", type="secondary"):
                st.session_state[f"show_fb_note_{i}"] = True

        if st.session_state.get(f"show_fb_note_{i}"):
            note = st.text_input("O que aconteceu de diferente?", key=f"fb_note_{i}")
            if st.button("Salvar feedback", key=f"save_fb_{i}"):
                user_q = st.session_state.messages[i-1]["content"] if i > 0 else ""
                st.session_state.feedbacks.append({
                    "date": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "query": user_q[:80],
                    "result": "wrong",
                    "note": note or "sem detalhe"
                })
                save_feedbacks()
                st.session_state[f"show_fb_note_{i}"] = False
                st.error("Registrado! O agente vai considerar isso.")

# Memória de feedbacks
if st.session_state.feedbacks:
    with st.expander(f"🧠 Memória do agente — {len(st.session_state.feedbacks)} feedbacks registrados"):
        for fb in reversed(st.session_state.feedbacks[-10:]):
            icon = "✓" if fb["result"] == "correct" else "✗"
            color = "green" if fb["result"] == "correct" else "red"
            st.markdown(f":{color}[{icon}] **{fb['date']}** — _{fb['query']}_ → {fb['note']}")

# Input
prompt = st.chat_input("Pergunte qualquer coisa sobre o BTC...")

# Processa pergunta rápida
if "pending_question" in st.session_state:
    prompt = st.session_state.pending_question
    del st.session_state.pending_question

if prompt:
    if not api_key:
        st.error("Cole sua API key da Anthropic na barra lateral para continuar.")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analisando..."):
            try:
                client = Anthropic(api_key=api_key)
                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=1200,
                    system=build_system_prompt(btc),
                    messages=st.session_state.messages
                )
                reply = response.content[0].text
                st.markdown(reply)
                st.session_state.messages.append({"role": "assistant", "content": reply})
            except Exception as e:
                err = str(e)
                if "401" in err or "authentication" in err.lower():
                    st.error("API key inválida. Verifique em console.anthropic.com/settings/keys")
                elif "429" in err:
                    st.error("Limite de requisições atingido. Aguarde alguns segundos.")
                else:
                    st.error(f"Erro: {err}")

    st.rerun()
