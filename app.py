import streamlit as st
import requests
import json
import os
from datetime import datetime, date

st.set_page_config(page_title="Agente BTC", page_icon="₿", layout="centered")

FEEDBACK_FILE = "feedbacks.json"

# ── Estado inicial ───────────────────────────────────────────────────────────
for key, val in [("messages", []), ("feedbacks", []), ("waiting", False)]:
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

# ── Dados BTC ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_btc():
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids":"bitcoin","vs_currencies":"usd",
                    "include_24hr_change":"true"},
            timeout=10
        )
        d = r.json()["bitcoin"]
        price = d["usd"]
        change = round(d["usd_24h_change"], 2)
        ATH = 126198
        halving = date(2024, 4, 19)
        days = (date.today() - halving).days
        dist = round((price - ATH) / ATH * 100, 1)
        if days < 180: phase = "Pós-halving inicial"
        elif days < 365: phase = "Acumulação pré-bull"
        elif days < 548: phase = "Bull market histórico"
        else: phase = "Topo / bear territory"
        return {"price": price, "change": change, "dist": dist, "days": days, "phase": phase}
    except:
        return None

# ── Prompt de sistema ────────────────────────────────────────────────────────
def build_prompt(btc):
    if btc:
        ctx = f"""DADOS EM TEMPO REAL:
- Preço: ${btc['price']:,.0f}
- Variação 24h: {btc['change']}%
- ATH: $126.198 (out/2025) — distância: {btc['dist']}%
- Dias pós-halving abr/2024: {btc['days']}
- Fase: {btc['phase']}"""
    else:
        ctx = "Dados em tempo real indisponíveis."

    fb = ""
    if st.session_state.feedbacks:
        fb = "\n\nFEEDBACKS ANTERIORES (aprenda com eles):\n"
        for f in st.session_state.feedbacks[-10:]:
            s = "ACERTOU" if f["result"] == "correct" else "ERROU"
            fb += f"- {f['date']}: \"{f['query']}\" → {s}: {f['note']}\n"

    return f"""Você é um agente quantitativo especializado em Bitcoin com conhecimento histórico completo desde 2011.

{ctx}

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
- 2025: ATH $126.198 outubro, correção atual

PADRÕES PÓS-HALVING (média 3 ciclos):
- 0-6m: lateralização, +40% médio
- 6-12m: aceleração, +120% médio
- 12-18m: bull principal, +200% médio
- 18-24m: euforia/topo, risco máximo
- Pós-topo: bear 12-14 meses, -80% médio

REGRAS:
1. Use dados em tempo real como base
2. Compare com análogos históricos específicos com datas e números
3. Dê probabilidades numéricas baseadas em frequência histórica
4. Identifique a fase do ciclo e o que aconteceu antes nela
5. Seja direto — diga o que os dados sugerem
6. Nunca invente dados históricos{fb}"""

# ── Enviar mensagem via API ──────────────────────────────────────────────────
def send_message(api_key, user_msg, btc):
    try:
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }
        msgs = []
        for m in st.session_state.messages:
            msgs.append({"role": m["role"], "content": m["content"]})
        msgs.append({"role": "user", "content": user_msg})

        body = {
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 1024,
            "system": build_prompt(btc),
            "messages": msgs
        }
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=body,
            timeout=60
        )
        if r.status_code == 200:
            return r.json()["content"][0]["text"], None
        elif r.status_code == 401:
            return None, "API key inválida. Verifique e cole a key correta na barra lateral."
        elif r.status_code == 429:
            return None, "Limite de requisições atingido. Aguarde alguns segundos."
        else:
            return None, f"Erro {r.status_code}: {r.text[:200]}"
    except requests.Timeout:
        return None, "Tempo limite excedido. Tente novamente."
    except Exception as e:
        return None, f"Erro de conexão: {str(e)}"

# ── Interface ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuração")
    api_key = st.text_input("API Key da Anthropic", type="password",
                            placeholder="sk-ant-...",
                            help="Obtenha em console.anthropic.com/settings/keys")
    if api_key and not api_key.startswith("sk-ant-"):
        st.error("Key inválida — deve começar com sk-ant-")
        api_key = ""
    elif api_key:
        st.success("Key configurada")
    st.divider()
    st.markdown("""**Como usar:**
1. Cole sua API key acima
2. Pergunte qualquer coisa sobre BTC
3. Avalie as respostas
4. O agente aprende com os feedbacks""")
    st.divider()
    if st.button("🔄 Atualizar dados BTC"):
        st.cache_data.clear()
        st.rerun()
    if st.button("🗑️ Limpar conversa"):
        st.session_state.messages = []
        st.rerun()

st.title("₿ Agente BTC")
st.caption("Análise quantitativa — histórico desde 2011 + tempo real")

btc = get_btc()
if btc:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Preço", f"${btc['price']:,.0f}", f"{btc['change']}% 24h")
    c2.metric("Dist. ATH", f"{btc['dist']}%", "de $126.198")
    c3.metric("Pós-halving", f"{btc['days']}d", "abr/2024")
    c4.metric("Fase", btc['phase'])
else:
    st.warning("Dados em tempo real indisponíveis.")

st.divider()

# Perguntas rápidas — sem rerun, só preenche o input
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

# Histórico
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

# Input e envio
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
            reply, err = send_message(api_key, final_prompt, btc)

        if err:
            st.error(err)
        else:
            st.markdown(reply)
            st.session_state.messages.append({"role": "user", "content": final_prompt})
            st.session_state.messages.append({"role": "assistant", "content": reply})
            st.rerun()
