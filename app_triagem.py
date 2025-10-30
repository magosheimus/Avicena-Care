import os
import html
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
from datetime import datetime
import numpy as np
import time

# Configuração da página (precisa vir ANTES de qualquer saída visual)
st.set_page_config(
    page_title="Avicena Care - Sistema de Triagem",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ========================= GUARDA DE EXECUÇÃO =========================
# Se o arquivo antigo reaparecer por sincronização (OneDrive) avisa o usuário.
if os.path.exists("app_triagem_profissional.py"):
    st.warning(
        'Arquivo legado "app_triagem_profissional.py" detectado. Apenas "app_triagem.py" deve ser usado. Você pode deletá-lo com segurança.'
    )
# ======================================================================


def calcular_score_clinico(temp, pa_sist, pa_diast, fr, fc, idade):
    """
    Calcula um score clínico baseado em MEWS (Modified Early Warning Score)
    adaptado para triagem hospitalar.

    Retorna: (score, classificacao_risco, alertas_clinicos)
    """
    score = 0
    alertas = []

    # Ajustes por idade
    if idade < 16:
        # Pediatria - limites ajustados
        fc_normal_max = 100 if idade > 12 else 120
        fr_normal_max = 20 if idade > 12 else 25
    elif idade > 65:
        # Idosos - tolerância menor
        fc_normal_max = 95
        fr_normal_max = 18
    else:
        # Adultos
        fc_normal_max = 100
        fr_normal_max = 20

    # TEMPERATURA
    if temp >= 39.0:
        score += 3
        alertas.append("Febre alta (≥39°C)")
    elif temp >= 38.5:
        score += 2
        alertas.append("Febre moderada")
    elif temp >= 37.5:
        score += 1
        alertas.append("Febrícula")
    elif temp <= 35.0:
        score += 3
        alertas.append("Hipotermia grave")
    elif temp <= 35.5:
        score += 2
        alertas.append("Hipotermia")

    # PRESSÃO ARTERIAL
    if pa_sist >= 180 or pa_diast >= 110:
        score += 3
        alertas.append("Hipertensão severa")
    elif pa_sist >= 160 or pa_diast >= 100:
        score += 2
        alertas.append("Hipertensão moderada")
    elif pa_sist < 90 or pa_diast < 60:
        score += 3
        alertas.append("Hipotensão")
    elif pa_sist < 100:
        score += 1
        alertas.append("PA sistólica baixa")

    # FREQUÊNCIA CARDÍACA
    if fc >= 130:
        score += 3
        alertas.append("Taquicardia severa")
    elif fc >= 110:
        score += 2
        alertas.append("Taquicardia moderada")
    elif fc >= fc_normal_max:
        score += 1
        alertas.append("Taquicardia leve")
    elif fc <= 40:
        score += 3
        alertas.append("Bradicardia severa")
    elif fc <= 50:
        score += 2
        alertas.append("Bradicardia")

    # FREQUÊNCIA RESPIRATÓRIA
    if fr >= 30:
        score += 3
        alertas.append("Taquipneia severa")
    elif fr >= 25:
        score += 2
        alertas.append("Taquipneia moderada")
    elif fr >= fr_normal_max:
        score += 1
        alertas.append("Taquipneia leve")
    elif fr <= 8:
        score += 3
        alertas.append("Bradipneia severa")
    elif fr <= 10:
        score += 1
        alertas.append("Bradipneia")

    # CLASSIFICAÇÃO DE RISCO
    if score >= 7:
        classificacao = ("CRÍTICO", "🔴", "Risco muito alto - Atenção imediata")
    elif score >= 5:
        classificacao = ("ALTO", "🟠", "Risco alto - Avaliação urgente")
    elif score >= 3:
        classificacao = ("MODERADO", "🟡", "Risco moderado - Monitorização")
    elif score >= 1:
        classificacao = ("BAIXO", "🔵", "Risco baixo - Observação")
    else:
        classificacao = ("NORMAL", "🟢", "Parâmetros normais")

    # PADRÕES CLÍNICOS ESPECÍFICOS
    padroes_clinicos = []

    # Possível sepse: febre + taquicardia + taquipneia
    if temp >= 38.0 and fc >= 100 and fr >= 22:
        padroes_clinicos.append("⚠️ Padrão sugestivo de sepse")

    # Choque compensado: taquicardia + hipotensão
    if fc >= 110 and pa_sist < 100:
        padroes_clinicos.append("⚠️ Possível choque compensado")

    # Instabilidade cardiocirculatória: bradicardia + hipotensão
    if fc <= 60 and pa_sist < 90:
        padroes_clinicos.append("🚨 Instabilidade cardiocirculatória")

    # Descompensação em idoso
    if idade > 65 and score >= 3:
        padroes_clinicos.append("👴 Idoso com sinais de descompensação")

    alertas.extend(padroes_clinicos)

    return score, classificacao, alertas


# Função para calcular urgência baseada em sinais vitais
def calcular_urgencia(
    temperatura,
    pa_sistolica,
    pa_diastolica,
    freq_respiratoria,
    freq_cardiaca,
    idade,
    spo2=None,
    nivel_consciencia="Alerta",
):
    """
    Triagem por pontos ampliada, conforme parâmetros e faixas sugeridas pelo usuário.
    Retorna: (nivel, cor, emoji, descricao, pontuacao, alertas)
    """
    pontos = 0
    alertas = []

    # FR
    if freq_respiratoria <= 8 or freq_respiratoria >= 25:
        pontos += 3
        alertas.append("FR crítica")
    elif 9 <= freq_respiratoria <= 11:
        pontos += 1
        alertas.append("FR levemente alterada")
    elif 21 <= freq_respiratoria <= 24:
        pontos += 2
        alertas.append("FR moderada")
    # 12-20 = 0 ponto

    # SpO2
    if spo2 is not None:
        if spo2 <= 91:
            pontos += 3
            alertas.append("SpO₂ crítica")
        elif 92 <= spo2 <= 93:
            pontos += 2
            alertas.append("SpO₂ moderada")
        elif 94 <= spo2 <= 95:
            pontos += 1
            alertas.append("SpO₂ levemente alterada")
        # >=96 = 0 ponto

    # PA sistólica
    if pa_sistolica <= 90 or pa_sistolica >= 220:
        pontos += 3
        alertas.append("PA sistólica crítica")
    elif 91 <= pa_sistolica <= 100:
        pontos += 2
        alertas.append("PA sistólica moderada")
    elif 101 <= pa_sistolica <= 110:
        pontos += 1
        alertas.append("PA sistólica levemente alterada")
    # 111-219 = 0 ponto

    # FC
    if freq_cardiaca <= 40 or freq_cardiaca >= 131:
        pontos += 3
        alertas.append("FC crítica")
    elif 41 <= freq_cardiaca <= 50:
        pontos += 1
        alertas.append("FC levemente alterada")
    elif 51 <= freq_cardiaca <= 90:
        pontos += 0
    elif 91 <= freq_cardiaca <= 110:
        pontos += 1
        alertas.append("FC levemente alterada")
    elif 111 <= freq_cardiaca <= 130:
        pontos += 2
        alertas.append("FC moderada")

    # Temperatura
    if temperatura <= 35.0:
        pontos += 3
        alertas.append("Hipotermia grave")
    elif 35.1 <= temperatura <= 36.0:
        pontos += 1
        alertas.append("Temperatura levemente baixa")
    elif 36.1 <= temperatura <= 37.0:
        pontos += 0
    elif 37.1 <= temperatura <= 39.0:
        pontos += 1
        alertas.append("Temperatura levemente elevada")
    elif temperatura >= 39.1:
        pontos += 2
        alertas.append("Febre alta")

    # Nível de consciência
    if nivel_consciencia.lower() == "alerta":
        pontos += 0
    else:
        pontos += 3
        alertas.append("Alteração de consciência")

    # Regra de exceção: parâmetro crítico extremo
    if (
        freq_respiratoria <= 8
        or freq_respiratoria >= 25
        or spo2 is not None
        and spo2 <= 85
        or pa_sistolica < 80
        or freq_cardiaca < 40
        or freq_cardiaca > 150
        or nivel_consciencia.lower() != "alerta"
    ):
        return (
            "PRIORIDADE MÁXIMA",
            "#dc2626",
            "🔴",
            "Atendimento imediato",
            pontos,
            alertas,
        )

    # Classificação por faixas de pontos
    if pontos >= 7:
        return (
            "PRIORIDADE MÁXIMA",
            "#dc2626",
            "�",
            "Atendimento imediato",
            pontos,
            alertas,
        )
    elif pontos >= 5:
        return ("ALTA PRIORIDADE", "#ea580c", "�", "Muito urgente", pontos, alertas)
    elif pontos >= 3:
        return ("MÉDIA PRIORIDADE", "#eab308", "🟡", "Urgente", pontos, alertas)
    elif pontos >= 1:
        return ("BAIXA PRIORIDADE", "#16a34a", "🟢", "Pouco urgente", pontos, alertas)
    else:
        return (
            "MÍNIMA (ELETIVA)",
            "#2563eb",
            "🔵",
            "Sem sinais agudos",
            pontos,
            alertas,
        )


###############################
# UTIL: CSS CRÍTICO (fallback)
###############################
CRITICAL_CSS = """
<style id='critical-ac'>
.ac-global-header{width:100vw;margin-left:calc(50% - 50vw);margin-right:calc(50% - 50vw);background:linear-gradient(90deg,#036672 0%,#057c7d 50%,#059669 100%);padding:26px 54px 24px 54px;position:relative;z-index:130;box-shadow:0 2px 6px rgba(0,0,0,.18)}
.ac-header-wrap{max-width:1500px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;gap:34px;flex-wrap:wrap}
.ac-brand{display:flex;align-items:center;gap:18px}
.ac-logo{width:58px;height:58px;display:grid;place-items:center;background:rgba(255,255,255,0.16);border:1px solid rgba(255,255,255,0.35);backdrop-filter:blur(4px);border-radius:18px;font-size:1.55rem;font-weight:800;color:#fff;box-shadow:0 4px 10px -2px rgba(0,0,0,.35)}
.ac-title{ft-size:2.05rem;font-weight:800;color:#fff;line-height:1;letter-spacing:.5px;text-shadow:0 3px 6px rgba(0,0,0,.35)}
.ac-sub{font-size:.8rem;font-weight:600;letter-spacing:.5px;color:#d1faf5;display:inline-flex;align-items:center;gap:6px}
.ac-status-pill{display:inline-flex;align-items:center;gap:8px;background:rgba(255,255,255,0.14);border:1px solid rgba(255,255,255,0.4);padding:10px 22px;border-radius:999px;font-weight:600;font-size:.75rem;color:#f0fdfa;box-shadow:0 2px 8px -2px rgba(0,0,0,.35)}
.ac-status-pill span{width:10px;height:10px;background:#10f0b3;border-radius:50%;box-shadow:0 0 0 4px rgba(16,240,179,0.25)}
.pcacr-wrapper{max-width:1500px;margin:0 auto 18px auto;padding:0 54px}
.pcacr-box{background:#ffffff;border:1px solid #e2e8f0;border-radius:28px;padding:30px 38px 26px 38px;box-shadow:0 4px 12px -2px rgba(15,23,42,0.08),0 2px 4px rgba(15,23,42,0.05);position:relative}
.pcacr-legend{display:flex;flex-wrap:wrap;gap:14px;margin-top:4px}
/* estilo legacy .pcacr-pillx removido (agora em styles.css com versão elegante) */
.pcacr-dot{width:12px;height:12px;border-radius:50%}
.d-max{background:#dc2626}.d-alta{background:#ea580c}.d-media{background:#eab308}.d-baixa{background:#16a34a}.d-min{background:#2563eb}
.kpi-band{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:28px;margin:30px 0 6px 0}
.kpi-box{background:#ffffff;border:1px solid #e2e8f0;border-radius:20px;padding:24px 22px 22px 22px;position:relative;display:flex;flex-direction:column;align-items:flex-start;gap:4px;box-shadow:0 2px 6px -1px rgba(15,23,42,0.08)}
.kpi-box:before{content:"";position:absolute;top:0;left:0;right:0;height:12px;border-top-left-radius:20px;border-top-right-radius:20px}
.kpi-box.total:before{background:#1d4ed8}.kpi-box.max:before{background:#dc2626}.kpi-box.alta:before{background:#ea580c}.kpi-box.media:before{background:#eab308}.kpi-box.baixa:before{background:#16a34a}.kpi-box.min:before{background:#2563eb}
.kpi-value2{font-size:2.05rem;font-weight:800;line-height:1;color:#0f172a;letter-spacing:.5px;margin-top:2px}
.kpi-label2{font-size:.70rem;font-weight:700;letter-spacing:.8px;color:#334155;margin-top:2px}
.kpi-meta2{font-size:.6rem;font-weight:600;letter-spacing:.6px;color:#64748b;margin-top:2px}
</style>
"""


# Função para carregar CSS externo (sem cache para garantir atualização imediata)
def load_css():
    path = "styles.css"
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        # Anexar comentário com timestamp de modificação para bust cache do navegador
        try:
            mtime = os.path.getmtime(path)
            content += f"\n/* v:{mtime} */\n"
        except Exception:
            pass
        return content
    except FileNotFoundError:
        st.warning("⚠️ Arquivo styles.css não encontrado. Usando estilos padrão.")
        return ""


# Aplicar CSS personalizado
css_content = load_css()
if css_content:
    st.markdown(f"<style>{css_content}</style>", unsafe_allow_html=True)
else:
    # Fallback emergencial
    st.markdown(CRITICAL_CSS, unsafe_allow_html=True)

from datetime import datetime as _dt

_now = _dt.now().strftime("%d/%m %H:%M")
# Header principal (estilos movidos para styles.css)
brand_header = """
<div class='ac-global-header'>
    <div class='ac-header-wrap'>
            <div class='ac-brand'>
                    <div class='ac-logo'>🏥</div>
                    <div class='ac-text'>
                                <div class='ac-title'>Avicena Care</div>
                                <div class='ac-sub'>Protocolo Catarinense de Acolhimento (PCACR)</div>
                    </div>
            </div>
            <div class='ac-status-pill'><span></span> PCACR Ativo</div>
    </div>
</div>
"""
st.markdown(brand_header, unsafe_allow_html=True)

###############################
# BANCO DE DADOS / SEED INICIAL
###############################


@st.cache_resource
def init_connection():
    return sqlite3.connect(":memory:", check_same_thread=False)


conn = init_connection()


def create_schema():
    conn.execute(
        """CREATE TABLE IF NOT EXISTS triagem (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            Nome TEXT,
            Idade INTEGER,
            PA TEXT,
            FC INTEGER,
            FR INTEGER,
            Temp REAL,
            Comorbidade TEXT,
            Alergia TEXT,
            Queixa_Principal TEXT,
            urgencia_automatica TEXT,
            urgencia_manual TEXT,
            status TEXT DEFAULT 'AGUARDANDO',
            data_cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            data_atendimento TIMESTAMP,
            atendido_por TEXT
        )"""
    )
    conn.commit()


def load_initial_data():
    create_schema()
    cur = conn.execute("SELECT COUNT(*) FROM triagem")
    if cur.fetchone()[0] == 0:
        # Dados base (Nome, Idade, PA, FC, FR, Temp, Comorbidade, Alergia, Queixa)
        dados_iniciais = [
            (
                "João Silva",
                45,
                "130/85",
                78,
                18,
                37.2,
                "Hipertensão",
                "Nenhuma",
                "Dor torácica intermitente",
            ),
            (
                "Maria Souza",
                67,
                "150/95",
                90,
                22,
                38.4,
                "Diabetes",
                "Dipirona",
                "Mal-estar e febre",
            ),
            (
                "Carlos Pereira",
                29,
                "118/76",
                72,
                16,
                36.8,
                "Nenhuma",
                "Nenhuma",
                "Cefaleia leve",
            ),
            (
                "Ana Costa",
                54,
                "165/102",
                88,
                20,
                37.9,
                "Hipertensão",
                "AAS",
                "Dispneia leve",
            ),
            (
                "Bruno Lima",
                38,
                "125/80",
                110,
                24,
                39.2,
                "Asma",
                "Nenhuma",
                "Febre alta e tosse",
            ),
        ]
        for nome, idade, pa, fc, fr, temp, comorb, alergia, queixa in dados_iniciais:
            pa_sist, pa_diast = map(int, pa.split("/"))
            urg = calcular_urgencia(temp, pa_sist, pa_diast, fr, fc, idade)[0]
            conn.execute(
                """INSERT INTO triagem
                (Nome, Idade, PA, FC, FR, Temp, Comorbidade, Alergia, Queixa_Principal, urgencia_automatica, urgencia_manual, status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    nome,
                    idade,
                    pa,
                    fc,
                    fr,
                    temp,
                    comorb,
                    alergia,
                    queixa,
                    urg,
                    urg,
                    "AGUARDANDO",
                ),
            )
        conn.commit()


def get_data(incluir_atendidos: bool = False):
    if incluir_atendidos:
        return pd.read_sql_query(
            "SELECT * FROM triagem ORDER BY data_cadastro DESC", conn
        )
    return pd.read_sql_query(
        "SELECT * FROM triagem WHERE status='AGUARDANDO' ORDER BY data_cadastro DESC",
        conn,
    )


def get_atendidos():
    return pd.read_sql_query(
        "SELECT * FROM triagem WHERE status='ATENDIDO' ORDER BY data_atendimento DESC",
        conn,
    )


load_initial_data()

# (Header antigo removido – substituído pelo brand_header acima)

df = get_data()
if df.empty:
    st.error("⚠️ Nenhum dado encontrado no banco de dados!")
    st.stop()

total_pacientes = len(df)
qtd_pacientes_febre = len(df[df["Temp"] > 37.5])
pressao_alta = len(
    df[
        df["PA"].apply(
            lambda x: int(x.split("/")[0]) >= 140 if "/" in str(x) else False
        )
    ]
)
temp_media = df["Temp"].mean()
urgencia_critica = (
    len(df[df["urgencia_manual"] == "CRÍTICA"])
    if "urgencia_manual" in df.columns
    else 0
)
urgencia_alta = (
    len(df[df["urgencia_manual"] == "ALTA"]) if "urgencia_manual" in df.columns else 0
)
urgencia_moderada = (
    len(df[df["urgencia_manual"] == "MODERADA"])
    if "urgencia_manual" in df.columns
    else 0
)
urgencia_baixa = (
    len(df[df["urgencia_manual"] == "BAIXA"]) if "urgencia_manual" in df.columns else 0
)
urgencia_normal = (
    len(df[df["urgencia_manual"] == "NORMAL"]) if "urgencia_manual" in df.columns else 0
)

protocol_html = f"""
<div class='pcacr-wrapper'>
  <div class='pcacr-box'>
     <div class='pcacr-status-inline'><span></span> PCACR Ativo</div>
     <h2>📋 Protocolo PCACR Ativo</h2>
     <p>Classificação de risco por cores e tempos alvo</p>
     <div class='pcacr-legend'>
        <div class='pcacr-pillx'><span class='pcacr-dot d-max'></span>Máxima (0min)</div>
        <div class='pcacr-pillx'><span class='pcacr-dot d-alta'></span>Alta (15min)</div>
        <div class='pcacr-pillx'><span class='pcacr-dot d-media'></span>Média (60min)</div>
        <div class='pcacr-pillx'><span class='pcacr-dot d-baixa'></span>Baixa (120min)</div>
        <div class='pcacr-pillx'><span class='pcacr-dot d-min'></span>Mínima (240min)</div>
     </div>
     <div class='kpi-band'>
        <div class='kpi-box total'>
            <div class='kpi-icon'>📊</div>
            <div class='kpi-value2'>{total_pacientes}</div>
            <div class='kpi-label2'>TOTAL DE PACIENTES</div>
            <div class='kpi-meta2'>Atual</div>
        </div>
        <div class='kpi-box max'>
            <div class='kpi-icon'>🔴</div>
            <div class='kpi-value2'>{urgencia_critica}</div>
            <div class='kpi-label2'>PRIORIDADE MÁXIMA</div>
            <div class='kpi-meta2'>0 minutos</div>
        </div>
        <div class='kpi-box alta'>
            <div class='kpi-icon'>🟠</div>
            <div class='kpi-value2'>{urgencia_alta}</div>
            <div class='kpi-label2'>PRIORIDADE ALTA</div>
            <div class='kpi-meta2'>15 minutos</div>
        </div>
        <div class='kpi-box media'>
            <div class='kpi-icon'>🟡</div>
            <div class='kpi-value2'>{urgencia_moderada}</div>
            <div class='kpi-label2'>PRIORIDADE MÉDIA</div>
            <div class='kpi-meta2'>60 minutos</div>
        </div>
        <div class='kpi-box baixa'>
            <div class='kpi-icon'>🟢</div>
            <div class='kpi-value2'>{urgencia_baixa}</div>
            <div class='kpi-label2'>PRIORIDADE BAIXA</div>
            <div class='kpi-meta2'>120 minutos</div>
        </div>
        <div class='kpi-box min'>
            <div class='kpi-icon'>🔵</div>
            <div class='kpi-value2'>{urgencia_normal}</div>
            <div class='kpi-label2'>PRIORIDADE MÍNIMA</div>
            <div class='kpi-meta2'>240 minutos</div>
        </div>
     </div>
  </div>
</div>
"""

st.markdown(protocol_html, unsafe_allow_html=True)

# Espaço suave antes das tabs
st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# Criar tabs reorganizadas para melhor UX
tab_dashboard, tab_fila, tab_clinico, tab_analytics, tab_novo = st.tabs(
    [
        "📊 Dashboard",
        "🧾 Fila de Atendimento",
        "🧠 Análise Clínica",
        "📈 Relatórios",
        "➕ Novo Paciente",
    ]
)
with tab_novo:
    st.markdown(
        """
        <style>
        /* For Streamlit selectbox dropdowns */
        .stSelectbox div[data-baseweb="select"] * {
            color: #222 !important;
        }
        .stSelectbox input {
            color: #222 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="form-card"><div class="form-card-title">👤 Dados do Paciente</div>',
        unsafe_allow_html=True,
    )
    cols_dados = st.columns([2, 1, 1, 1])
    with cols_dados[0]:
        nome_novo = st.text_input("Nome do paciente *", key="novo_nome_novo")
    with cols_dados[1]:
        idade_novo = st.number_input(
            "Idade *", min_value=0, max_value=120, value=30, key="novo_idade_novo"
        )
    with cols_dados[2]:
        altura_novo = st.number_input(
            "Altura (cm)",
            min_value=40,
            max_value=250,
            value=170,
            key="novo_altura_novo",
        )
    with cols_dados[3]:
        peso_novo = st.number_input(
            "Peso (kg)", min_value=2, max_value=300, value=70, key="novo_peso_novo"
        )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        '<div class="form-card"><div class="form-card-title">🫁 Saturação de O₂ e Estado Mental</div>',
        unsafe_allow_html=True,
    )
    spo2_novo = st.number_input(
        "Saturação de O₂ (%)",
        min_value=70,
        max_value=100,
        value=98,
        key="novo_spo2_novo",
    )
    estado_mental_novo = st.selectbox(
        "Estado mental",
        [
            "Alerta",
            "Confuso",
            "Sonolento",
            "Resposta ao estímulo de voz",
            "Resposta ao estímulo de dor",
            "Sem resposta",
        ],
        key="novo_estado_mental_novo",
    )
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="form-card"><div class="form-card-title">🩺 Sinais Vitais</div>',
        unsafe_allow_html=True,
    )
    cols_sv1 = st.columns([1, 1])
    with cols_sv1[0]:
        freq_cardiaca_novo = st.number_input(
            "Frequência Cardíaca (bpm) *",
            min_value=30,
            max_value=200,
            value=70,
            key="novo_fc_novo",
        )
    with cols_sv1[1]:
        freq_respiratoria_novo = st.number_input(
            "Frequência Respiratória (rpm) *",
            min_value=5,
            max_value=50,
            value=18,
            key="novo_fr_novo",
        )

    st.markdown('<div class="pa-group">', unsafe_allow_html=True)
    cols_pa = st.columns([1, 0.2, 1])
    with cols_pa[0]:
        pa_sistolica_novo = st.number_input(
            "Pressão Sistólica *",
            min_value=60,
            max_value=250,
            value=120,
            key="novo_pa_sist_novo",
        )
    with cols_pa[1]:
        st.markdown('<div class="pa-slash">/</div>', unsafe_allow_html=True)
    with cols_pa[2]:
        pa_diastolica_novo = st.number_input(
            "Pressão Diastólica *",
            min_value=40,
            max_value=150,
            value=80,
            key="novo_pa_diast_novo",
        )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        '<div class="form-card"><div class="form-card-title">⚕️ Condições Clínicas</div>',
        unsafe_allow_html=True,
    )
    comorbidades_opcoes = [
        "Nenhuma",
        "Hipertensão",
        "Diabetes",
        "Asma",
        "Hipotireoidismo",
        "Obesidade",
        "Dislipidemia",
        "Cardiopatia",
        "DPOC",
        "Outra",
    ]
    comorbidade_selecionada_novo = st.selectbox(
        "Comorbidade", comorbidades_opcoes, key="novo_comorb_novo"
    )
    comorbidade_customizada_novo = ""
    if comorbidade_selecionada_novo == "Outra":
        comorbidade_customizada_novo = st.text_input(
            "Especifique a comorbidade",
            placeholder="Ex: Fibromialgia, Artrite reumatoide, Lúpus, Epilepsia...",
            key="novo_comorb_outra_novo",
        )
    comorbidade_novo = (
        f"Outra: {comorbidade_customizada_novo}"
        if comorbidade_selecionada_novo == "Outra"
        and comorbidade_customizada_novo.strip()
        else (
            "Outra (não especificada)"
            if comorbidade_selecionada_novo == "Outra"
            else comorbidade_selecionada_novo
        )
    )

    alergias_opcoes = [
        "Nenhuma",
        "Dipirona",
        "Amoxicilina",
        "Penicilina",
        "AAS",
        "Lactose",
        "Glúten",
        "Frutos do mar",
        "Iodo",
        "Outra",
    ]
    alergia_selecionada_novo = st.selectbox(
        "Alergias conhecidas", alergias_opcoes, key="novo_alergia_novo"
    )
    alergia_customizada_novo = ""
    if alergia_selecionada_novo == "Outra":
        alergia_customizada_novo = st.text_input(
            "Especifique a alergia",
            placeholder="Ex: Aspirina, Látex, Poeira, Amendoim, Sulfito...",
            key="novo_alergia_outra_novo",
        )
    alergia_novo = (
        f"Outra: {alergia_customizada_novo}"
        if alergia_selecionada_novo == "Outra" and alergia_customizada_novo.strip()
        else (
            "Outra (não especificada)"
            if alergia_selecionada_novo == "Outra"
            else alergia_selecionada_novo
        )
    )
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        '<div class="form-card"><div class="form-card-title">📝 Queixa Principal</div>',
        unsafe_allow_html=True,
    )
    queixa_principal_novo = st.text_area(
        "Descreva a principal queixa do paciente *",
        placeholder="Ex: Dor de cabeça há 3 dias, febre desde ontem, dificuldade para respirar...",
        height=110,
        key="novo_queixa_novo",
    )
    st.caption("Dica: inclua duração, intensidade e fatores de melhora/piora.")
    st.markdown("</div>", unsafe_allow_html=True)

    col_submit, col_clear = st.columns([2, 1])
    with col_submit:
        submit_clicked_novo = st.button(
            "💾 Cadastrar Paciente",
            type="primary",
            use_container_width=True,
            key="submit_novo_paciente_novo",
        )
    with col_clear:
        clear_clicked_novo = st.button(
            "🧹 Limpar",
            type="secondary",
            use_container_width=True,
            key="limpar_form_novo",
        )

    # Limpar formulário
    if clear_clicked_novo:
        for k in [
            "novo_nome_novo",
            "novo_idade_novo",
            "novo_pa_sist_novo",
            "novo_pa_diast_novo",
            "novo_temp_novo",
            "novo_fc_novo",
            "novo_fr_novo",
            "novo_comorb_novo",
            "novo_comorb_outra_novo",
            "novo_alergia_novo",
            "novo_alergia_outra_novo",
            "novo_queixa_novo",
            "novo_spo2_novo",
            "novo_estado_mental_novo",
        ]:
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()

    # Validação e submissão
    nome_novo = st.session_state.get("novo_nome_novo", "")
    idade_novo = st.session_state.get("novo_idade_novo", 0)
    temperatura_novo = st.session_state.get("novo_temp_novo", 36.5)
    if submit_clicked_novo:
        if not nome_novo or not nome_novo.strip():
            st.error("❌ Nome é obrigatório!")
        elif len(nome_novo.strip()) < 2:
            st.error("❌ Nome deve ter pelo menos 2 caracteres!")
        elif idade_novo <= 0:
            st.error("❌ Idade deve ser maior que zero!")
        elif temperatura_novo < 30 or temperatura_novo > 45:
            st.error("❌ Temperatura deve estar entre 30°C e 45°C!")
        elif pa_sistolica_novo <= pa_diastolica_novo:
            st.error("❌ Pressão sistólica deve ser maior que a diastólica!")
        elif freq_respiratoria_novo < 5 or freq_respiratoria_novo > 50:
            st.error("❌ Frequência respiratória deve estar entre 5 e 50 rpm!")
        elif not queixa_principal_novo or not queixa_principal_novo.strip():
            st.error("❌ Queixa principal é obrigatória!")
        elif len(queixa_principal_novo.strip()) < 5:
            st.error("❌ Queixa principal deve ter pelo menos 5 caracteres!")
        elif (
            comorbidade_selecionada_novo == "Outra"
            and not (comorbidade_customizada_novo or "").strip()
        ):
            st.error("❌ Por favor, especifique a comorbidade no campo 'Outra'!")
        elif (
            alergia_selecionada_novo == "Outra"
            and not (alergia_customizada_novo or "").strip()
        ):
            st.error("❌ Por favor, especifique a alergia no campo 'Outra'!")
        else:
            pa_formatada_novo = f"{pa_sistolica_novo}/{pa_diastolica_novo}"
            urgencia_auto_novo = calcular_urgencia(
                temperatura_novo,
                pa_sistolica_novo,
                pa_diastolica_novo,
                freq_respiratoria_novo,
                freq_cardiaca_novo,
                idade_novo,
                spo2_novo,
                estado_mental_novo,
            )
            urgencia_nivel_novo = urgencia_auto_novo[0]
            try:
                conn.execute(
                    """
                    INSERT INTO triagem (Nome, Idade, PA, FC, FR, Temp, Comorbidade, Alergia, Queixa_Principal, urgencia_automatica, urgencia_manual, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        nome_novo.strip(),
                        idade_novo,
                        pa_formatada_novo,
                        freq_cardiaca_novo,
                        freq_respiratoria_novo,
                        temperatura_novo,
                        comorbidade_novo,
                        alergia_novo,
                        queixa_principal_novo.strip(),
                        urgencia_nivel_novo,
                        urgencia_nivel_novo,
                        "AGUARDANDO",
                    ),
                )
                conn.commit()
                st.success(f"✅ Paciente {nome_novo} cadastrado com sucesso!")

                # Resumo cadastrado
                dados_paciente_novo = pd.DataFrame(
                    {
                        "Nome": [nome_novo],
                        "Idade": [idade_novo],
                        "PA": [pa_formatada_novo],
                        "FC": [freq_cardiaca_novo],
                        "FR": [freq_respiratoria_novo],
                        "Temp": [temperatura_novo],
                        "SpO₂": [spo2_novo],
                        "Estado mental": [estado_mental_novo],
                        "Comorbidade": [comorbidade_novo],
                        "Alergia": [alergia_novo],
                        "Queixa Principal": [queixa_principal_novo.strip()],
                        "Urgência": [f"{urgencia_auto_novo[2]} {urgencia_nivel_novo}"],
                        "Pontuação": [urgencia_auto_novo[4]],
                    }
                )
                st.dataframe(dados_paciente_novo, use_container_width=True)

                # Auto-refresh: marcar que dados foram atualizados
                st.session_state["patient_list_updated"] = True
                st.info("🔄 A lista de pacientes será atualizada automaticamente.")
                time.sleep(2)
                st.rerun()
            except Exception as e:
                st.error(f"❌ Erro ao cadastrar paciente: {str(e)}")

# ---------------- DASHBOARD ----------------
with tab_dashboard:
    st.markdown("### 📊 Visão Geral do Sistema")

    # Métricas principais
    df_total = get_data()
    df_atendidos = get_atendidos()

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        total_pacientes = len(df_total)
        st.markdown(
            f"""
        <div class="metric-card-modern">
            <div class="metric-header">
                <div class="metric-icon">👥</div>
                <div class="metric-title">Total Pacientes</div>
            </div>
            <div class="metric-value">{total_pacientes}</div>
            <div class="metric-change">Na fila + atendidos</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col2:
        aguardando = (
            len(df_total[df_total["status"] == "AGUARDANDO"])
            if not df_total.empty
            else 0
        )
        st.markdown(
            f"""
        <div class="metric-card-modern">
            <div class="metric-header">
                <div class="metric-icon">⏳</div>
                <div class="metric-title">Aguardando</div>
            </div>
            <div class="metric-value">{aguardando}</div>
            <div class="metric-change">Em atendimento</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col3:
        total_atendidos_dash = len(df_atendidos) if not df_atendidos.empty else 0
        st.markdown(
            f"""
        <div class="metric-card-modern">
            <div class="metric-header">
                <div class="metric-icon">✅</div>
                <div class="metric-title">Atendidos</div>
            </div>
            <div class="metric-value">{total_atendidos_dash}</div>
            <div class="metric-change">Finalizados</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    with col4:
        if not df_total.empty:
            urgentes = (
                len(df_total[df_total["urgencia_manual"].isin(["CRÍTICA", "ALTA"])])
                if "urgencia_manual" in df_total.columns
                else 0
            )
        else:
            urgentes = 0
        st.markdown(
            f"""
        <div class="metric-card-modern">
            <div class="metric-header">
                <div class="metric-icon">🚨</div>
                <div class="metric-title">Urgentes</div>
            </div>
            <div class="metric-value">{urgentes}</div>
            <div class="metric-change">Alta prioridade</div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # Gráfico de distribuição de urgências
    if not df_total.empty and "urgencia_manual" in df_total.columns:
        st.markdown("### 📈 Distribuição por Urgência")

        urgencia_dist = df_total["urgencia_manual"].value_counts()

        fig_dist = px.pie(
            values=urgencia_dist.values,
            names=urgencia_dist.index,
            title="Distribuição de Pacientes por Nível de Urgência",
            color_discrete_map={
                "CRÍTICA": "#ef4444",
                "ALTA": "#f59e0b",
                "MODERADA": "#eab308",
                "BAIXA": "#3b82f6",
                "NORMAL": "#10b981",
            },
        )
        fig_dist.update_layout(height=400)
        st.plotly_chart(fig_dist, use_container_width=True)

# --- Fila de Atendimento (pré-processamento de filtros) ---
with tab_fila:
    # Recarregar dados frescos automaticamente
    df = get_data()
    df_filtered = df.copy()
    total_aguardando = len(df)
    total_filtrado = len(df_filtered)

    # Header da Fila com visual hospitalar clean
    st.markdown(
        """
    <div class="fila-header">
        <div class="fila-header-left">
            <div class="fila-icon">🏥</div>
            <div class="fila-info">
                <h3>Fila de Atendimento</h3>
                <p><span class="patient-count">{}</span> pacientes aguardando</p>
            </div>
        </div>
        <div class="fila-header-right">
            <div class="fila-status">
                <span class="status-dot active"></span>
                <span>Sistema Ativo</span>
            </div>
        </div>
    </div>
    """.format(
            total_filtrado
        ),
        unsafe_allow_html=True,
    )

    # Controles de ação em linha limpa
    col_refresh, col_urgencia_manual = st.columns([1, 2])

    with col_refresh:
        if st.button("🔄 Atualizar Lista", type="secondary", use_container_width=True):
            st.rerun()

    with col_urgencia_manual:
        # Botão para alterar urgência em lote
        if not df_filtered.empty:
            if st.button(
                "⚕️ Gerenciar Paciente", type="primary", use_container_width=True
            ):
                st.session_state.show_patient_manager = True

    # Gerenciador de Paciente (urgência, edição e atendimento)
    if not df_filtered.empty and st.session_state.get("show_patient_manager", False):
        with st.expander("⚕️ Gerenciar Paciente", expanded=True):
            st.markdown("**Selecione um paciente para gerenciar:**")

            # Seletor de paciente
            nomes_pacientes = [
                f"{row['Nome']} (#{int(row.get('id', 0)):04d})"
                for _, row in df_filtered.iterrows()
            ]
            if nomes_pacientes:
                paciente_selecionado = st.selectbox(
                    "Paciente:",
                    nomes_pacientes,
                    help="Escolha o paciente para gerenciar",
                )

            if paciente_selecionado:
                # Extrair ID do paciente selecionado
                patient_id = int(paciente_selecionado.split("#")[1].split(")")[0])
                patient_name = paciente_selecionado.split(" (#")[0]

                # Buscar dados do paciente pelo ID
                dados_paciente = df_filtered[df_filtered["id"] == patient_id].iloc[0]

                # Layout em abas para gerenciamento completo do paciente
                tab_info, tab_edit, tab_urgency, tab_action = st.tabs(
                    ["📋 Info", "✏️ Editar", "🎯 Urgência", "✅ Ações"]
                )

                # Calcular urgência automática para uso em todas as abas
                pa_parts = dados_paciente["PA"].split("/")
                pa_sist, pa_diast = int(pa_parts[0]), int(pa_parts[1])
                fc = dados_paciente.get("FC", 70)
                urgencia_calc = calcular_urgencia(
                    dados_paciente["Temp"],
                    pa_sist,
                    pa_diast,
                    dados_paciente["FR"],
                    fc,
                    dados_paciente["Idade"],
                )

                with tab_info:
                    st.markdown(f"### 📋 {patient_name}")

                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown("**📊 Dados Pessoais:**")
                        st.markdown(f"• **ID:** #{patient_id:04d}")
                        st.markdown(f"• **Nome:** {dados_paciente['Nome']}")
                        st.markdown(f"• **Idade:** {dados_paciente['Idade']} anos")
                        st.markdown(
                            f"• **Comorbidade:** {dados_paciente.get('Comorbidade', 'Nenhuma')}"
                        )

                    with col2:
                        st.markdown("**🩺 Sinais Vitais:**")
                        st.markdown(f"• **Temperatura:** {dados_paciente['Temp']}°C")
                        st.markdown(f"• **PA:** {dados_paciente['PA']} mmHg")
                        st.markdown(f"• **FC:** {fc} bpm")
                        st.markdown(f"• **FR:** {dados_paciente['FR']} rpm")

                        urgencia_atual = dados_paciente.get(
                            "urgencia_manual", urgencia_calc[0]
                        )
                        st.markdown(
                            f"• **Urgência:** {urgencia_calc[2]} {urgencia_atual}"
                        )

                    if urgencia_calc[5]:  # Alertas
                        st.markdown("**⚠️ Alertas dos Sinais Vitais:**")
                        for alerta in urgencia_calc[5]:
                            st.markdown(f"• {alerta}")

                with tab_edit:
                    st.markdown(f"### ✏️ Editar - {patient_name}")

                    col1, col2 = st.columns(2)
                    with col1:
                        novo_nome = st.text_input(
                            "Nome:", value=dados_paciente.get("Nome", "")
                        )
                        nova_idade = st.number_input(
                            "Idade:",
                            value=int(dados_paciente.get("Idade", 0)),
                            min_value=0,
                            max_value=120,
                        )
                        nova_temp = st.number_input(
                            "Temperatura (°C):",
                            value=float(dados_paciente.get("Temp", 36.5)),
                            min_value=30.0,
                            max_value=45.0,
                            step=0.1,
                        )
                        nova_pa = st.text_input(
                            "PA:", value=dados_paciente.get("PA", "120/80")
                        )

                    with col2:
                        nova_fc = st.number_input(
                            "FC (bpm):",
                            value=int(dados_paciente.get("FC", 70)),
                            min_value=30,
                            max_value=200,
                        )
                        nova_fr = st.number_input(
                            "FR (rpm):",
                            value=int(dados_paciente.get("FR", 16)),
                            min_value=8,
                            max_value=60,
                        )
                        nova_comorbidade = st.text_area(
                            "Comorbidade:", value=dados_paciente.get("Comorbidade", "")
                        )
                        nova_queixa = st.text_area(
                            "Queixa:", value=dados_paciente.get("Queixa_Principal", "")
                        )

                    if st.button(
                        "💾 Salvar Alterações", type="primary", use_container_width=True
                    ):
                        try:
                            conn.execute(
                                """
                                UPDATE triagem SET Nome = ?, Idade = ?, Temp = ?, PA = ?, FC = ?, FR = ?, 
                                Comorbidade = ?, Queixa_Principal = ? WHERE id = ?
                            """,
                                (
                                    novo_nome,
                                    nova_idade,
                                    nova_temp,
                                    nova_pa,
                                    nova_fc,
                                    nova_fr,
                                    nova_comorbidade,
                                    nova_queixa,
                                    patient_id,
                                ),
                            )
                            conn.commit()
                            st.success("✅ Dados atualizados!")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erro: {str(e)}")

                with tab_urgency:
                    st.markdown(f"### 🎯 Alterar Urgência - {patient_name}")

                    # Urgência atual
                    urgencia_atual = dados_paciente.get(
                        "urgencia_manual", urgencia_calc[0]
                    )
                    st.markdown(
                        f"**Urgência Atual:** {urgencia_calc[2]} {urgencia_atual}"
                    )

                    # Seletor de nova urgência
                    opcoes_urgencia = ["NORMAL", "BAIXA", "MODERADA", "ALTA", "CRÍTICA"]
                    cores_urgencia = {
                        "NORMAL": "🟢",
                        "BAIXA": "🔵",
                        "MODERADA": "🟡",
                        "ALTA": "🟠",
                        "CRÍTICA": "🔴",
                    }

                    nova_urgencia = st.selectbox(
                        "Nova Urgência:",
                        opcoes_urgencia,
                        index=(
                            opcoes_urgencia.index(urgencia_atual)
                            if urgencia_atual in opcoes_urgencia
                            else 0
                        ),
                        format_func=lambda x: f"{cores_urgencia[x]} {x}",
                    )

                    # Motivo da alteração
                    motivo = st.text_area(
                        "Motivo:", placeholder="Ex: Observação clínica...", height=80
                    )

                    if st.button(
                        "🎯 Alterar Urgência", type="primary", use_container_width=True
                    ):
                        if motivo.strip():
                            try:
                                conn.execute(
                                    "UPDATE triagem SET urgencia_manual = ? WHERE id = ?",
                                    (nova_urgencia, patient_id),
                                )
                                conn.commit()
                                st.success(
                                    f"✅ Urgência alterada para {cores_urgencia[nova_urgencia]} {nova_urgencia}"
                                )
                                st.info(f"**Motivo:** {motivo}")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Erro: {str(e)}")
                        else:
                            st.warning("⚠️ Informe o motivo da alteração.")

                with tab_action:
                    st.markdown(f"### ✅ Ações - {patient_name}")

                    if st.button(
                        "✅ Marcar como Atendido",
                        type="primary",
                        use_container_width=True,
                    ):
                        try:
                            conn.execute(
                                "INSERT INTO historico_atendimentos SELECT *, datetime('now') as data_atendimento FROM triagem WHERE id = ?",
                                (patient_id,),
                            )
                            conn.execute(
                                "DELETE FROM triagem WHERE id = ?", (patient_id,)
                            )
                            conn.commit()
                            st.success(f"✅ {patient_name} marcado como atendido!")
                            st.session_state.show_patient_manager = False
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erro: {str(e)}")

                # Botão para fechar o gerenciador
                if st.button("❌ Fechar Gerenciador", use_container_width=True):
                    st.session_state.show_patient_manager = False
                    st.rerun()

    if df_filtered.empty:
        st.info("Nenhum paciente aguardando.")
    else:
        # Montar tabela estilizada (sem título visível)
        # Mapas
        mapa_prioridade = {
            "CRÍTICA": ("PRIORIDADE MÁXIMA", "maxima"),
            "PRIORIDADE MÁXIMA": ("PRIORIDADE MÁXIMA", "maxima"),
            "ALTA": ("ALTA", "alta"),
            "ALTA PRIORIDADE": ("ALTA", "alta"),
            "MODERADA": ("MÉDIA", "media"),
            "MÉDIA PRIORIDADE": ("MÉDIA", "media"),
            "BAIXA": ("BAIXA", "baixa"),
            "BAIXA PRIORIDADE": ("BAIXA", "baixa"),
            "NORMAL": ("MÍNIMA", "minima"),
            "MÍNIMA (ELETIVA)": ("MÍNIMA", "minima"),
        }
        # Ordenar por prioridade (tipo Excel) antes de renderizar
        ordem_urgencia = {
            "CRÍTICA": 0,
            "ALTA": 1,
            "MODERADA": 2,
            "BAIXA": 3,
            "NORMAL": 4,
        }
        df_sorted = df_filtered.copy()
        base_urg = df_sorted["urgencia_manual"].fillna(
            df_sorted.get("urgencia_automatica", "NORMAL")
        )
        df_sorted = (
            df_sorted.assign(_ordem=base_urg.map(ordem_urgencia).fillna(999))
            .sort_values(["_ordem", "data_cadastro"])
            .drop(columns=["_ordem"])
        )
        linhas = []
        for pos, (_, row) in enumerate(df_sorted.iterrows(), start=1):
            urg_raw = row.get("urgencia_manual", "NORMAL")
            urg_label, urg_class = mapa_prioridade.get(urg_raw, ("MÍNIMA", "minima"))
            temp_val = float(row["Temp"]) if pd.notnull(row["Temp"]) else 0.0
            temp_fmt = f"{temp_val:.1f}°C"
            chegada = (
                row.get("data_cadastro", "")[11:16]
                if row.get("data_cadastro")
                else "--:--"
            )
            sintomas_full = row.get("Queixa_Principal", "") or ""
            sintomas = sintomas_full[:45] + ("…" if len(sintomas_full) > 45 else "")

            # Comorbidade
            comorbidade_full = row.get("Comorbidade", "") or "Nenhuma"
            comorbidade_short = comorbidade_full[:25] + (
                "…" if len(comorbidade_full) > 25 else ""
            )

            # Cores tipo Excel para valores vitais
            # Temperatura
            if temp_val >= 39.0:
                temp_cls = "val-red"
            elif temp_val >= 37.5:
                temp_cls = "val-orange"
            else:
                temp_cls = "val-green"
            temp_html = f"<span class='vital-badge {temp_cls}'>{temp_fmt}</span>"

            # Pressão Arterial
            pa_text = row["PA"]
            try:
                pa_sist, pa_diast = map(int, str(pa_text).split("/"))
                if pa_sist >= 180 or pa_diast >= 110:
                    pa_cls = "val-red"
                elif pa_sist >= 140 or pa_diast >= 90:
                    pa_cls = "val-orange"
                else:
                    pa_cls = "val-green"
            except Exception:
                pa_cls = "val-green"
            pa_html = f"<span class='vital-badge {pa_cls}'>{pa_text}</span>"

            # Frequência Cardíaca
            fc_val = row.get("FC", None)
            try:
                fc_val = int(fc_val)
            except Exception:
                fc_val = None
            if fc_val is None:
                fc_html = f"<span class='vital-badge val-green'>--</span>"
            else:
                if fc_val >= 120:
                    fc_cls = "val-red"
                elif fc_val >= 100:
                    fc_cls = "val-orange"
                else:
                    fc_cls = "val-green"
                fc_html = f"<span class='vital-badge {fc_cls}'>{fc_val}</span>"

            # Frequência Respiratória
            fr_val = row.get("FR", None)
            try:
                fr_val = int(fr_val)
            except Exception:
                fr_val = None
            if fr_val is None:
                fr_html = f"<span class='vital-badge val-green'>--</span>"
            else:
                if fr_val >= 30:
                    fr_cls = "val-red"
                elif fr_val >= 22:
                    fr_cls = "val-orange"
                else:
                    fr_cls = "val-green"
                fr_html = f"<span class='vital-badge {fr_cls}'>{fr_val}</span>"

            id_fmt = (
                f"#{int(row.get('id', 0)):04d}"
                if pd.notnull(row.get("id", None))
                else "#----"
            )

            linhas.append(
                f"<tr class='patient-row priority-row-{urg_class}'>\n"
                f"  <td class='col-pos'>{pos}</td>\n"
                f"  <td class='col-priority'><span class='priority-badge priority-{urg_class}'>{urg_label}</span></td>\n"
                f"  <td class='col-patient'><strong>{html.escape(row['Nome'])}</strong></td>\n"
                f"  <td class='col-id'><span class='patient-id'>{id_fmt}</span></td>\n"
                f"  <td class='col-age'>{row['Idade']}a</td>\n"
                f"  <td class='col-time'>{chegada}</td>\n"
                f"  <td class='col-temp'>{temp_html}</td>\n"
                f"  <td class='col-bp'>{pa_html}</td>\n"
                f"  <td class='col-hr'>{fc_html}</td>\n"
                f"  <td class='col-rr'>{fr_html}</td>\n"
                f"  <td class='col-comorbidity' title='{html.escape(comorbidade_full)}'>{html.escape(comorbidade_short)}</td>\n"
                f"  <td class='col-symptoms' title='{html.escape(sintomas_full)}'>{html.escape(sintomas)}</td>\n"
                f"</tr>\n"
            )

        tabela_html = (
            "<div class='hospital-table-container'>\n"
            "<table class='hospital-table'>\n"
            "<thead>\n"
            "<tr>\n"
            "<th class='th-pos'>#</th>\n"
            "<th class='th-priority'>Prioridade</th>\n"
            "<th class='th-patient'>Paciente</th>\n"
            "<th class='th-id'>ID</th>\n"
            "<th class='th-age'>Idade</th>\n"
            "<th class='th-time'>Chegada</th>\n"
            "<th class='th-temp'>Temp</th>\n"
            "<th class='th-bp'>PA</th>\n"
            "<th class='th-hr'>FC</th>\n"
            "<th class='th-rr'>FR</th>\n"
            "<th class='th-comorbidity'>Comorbidade</th>\n"
            "<th class='th-symptoms'>Sintomas</th>\n"
            "</tr>\n"
            "</thead>\n"
            "<tbody>\n"
            f"{''.join(linhas)}"
            "</tbody>\n"
            "</table>\n"
            "</div>"
        )
        st.markdown(tabela_html, unsafe_allow_html=True)

        # Legenda e controles em layout hospitalar
        st.markdown(
            """
        <div class="table-footer">
            <div class="legend-section">
                <div class="legend-title">📊 Legenda Clínica:</div>
                <div class="legend-items">
                    <span class="legend-item">🔴 Crítico: Temp ≥39°C, PA ≥180/110</span>
                    <span class="legend-item">🟠 Atenção: Temp ≥37.5°C, PA ≥140/90</span>
                    <span class="legend-item">🟢 Normal: Dentro dos parâmetros</span>
                </div>
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

        # Ações em layout hospitalar clean
        col_export, col_summary = st.columns([1, 2])

        with col_export:
            # Preparar CSV do relatório exportável (ordenado por prioridade)
            export_rows = []
            for pos, (_, row) in enumerate(df_sorted.iterrows(), start=1):
                urg_raw = row.get("urgencia_manual", "NORMAL")
                urg_label, _urg_class = mapa_prioridade.get(
                    urg_raw, ("MÍNIMA", "minima")
                )
                chegada = (
                    row.get("data_cadastro", "")[11:16]
                    if row.get("data_cadastro")
                    else "--:--"
                )
                export_rows.append(
                    {
                        "Pos": pos,
                        "Prioridade": urg_label,
                        "Paciente": row["Nome"],
                        "ID": (
                            f"#{int(row.get('id', 0)):04d}"
                            if pd.notnull(row.get("id", None))
                            else ""
                        ),
                        "Idade": f"{row['Idade']}a",
                        "Chegada": chegada,
                        "Temp": (
                            f"{float(row['Temp']):.1f}°C"
                            if pd.notnull(row["Temp"])
                            else ""
                        ),
                        "PA": row["PA"],
                        "FC": (
                            f"{int(row['FC'])}bpm" if pd.notnull(row.get("FC")) else ""
                        ),
                        "FR": (
                            f"{int(row['FR'])}rpm" if pd.notnull(row.get("FR")) else ""
                        ),
                        "Comorbidade": row.get("Comorbidade", "") or "Nenhuma",
                        "Sintomas": row.get("Queixa_Principal", "") or "",
                    }
                )
            df_export = pd.DataFrame(export_rows)
            csv_bytes = df_export.to_csv(index=False).encode("utf-8")
            st.download_button(
                "📋 Exportar Lista",
                data=csv_bytes,
                file_name="fila_atendimento.csv",
                mime="text/csv",
                use_container_width=True,
            )

        with col_summary:
            # Resumo rápido por prioridade
            priority_counts = (
                df_sorted["urgencia_manual"]
                .fillna(df_sorted.get("urgencia_automatica", "NORMAL"))
                .value_counts()
            )
            summary_badges = []
            for prio, count in priority_counts.items():
                color_map = {
                    "CRÍTICA": "#dc2626",
                    "PRIORIDADE MÁXIMA": "#b91c1c",
                    "ALTA": "#ea580c",
                    "MODERADA": "#eab308",
                    "BAIXA": "#16a34a",
                    "NORMAL": "#2563eb",
                }
                color = color_map.get(prio, "#64748b")
                summary_badges.append(
                    f'<span class="summary-badge" style="background: {color}; color: white;">{prio}: {count}</span>'
                )

            st.markdown(
                f"""
            <div class="priority-summary">
                <span class="summary-title">Distribuição por Prioridade:</span>
                {' '.join(summary_badges)}
            </div>
            """,
                unsafe_allow_html=True,
            )

    st.markdown("</div>", unsafe_allow_html=True)

# ---------------- ANÁLISE CLÍNICA ----------------
with tab_clinico:
    st.markdown('<div class="fade-in">', unsafe_allow_html=True)
    st.subheader("🧠 Insights Clínicos - Análise Correlacional")

    # Combinar dados atuais e histórico
    df_atual = get_data()
    df_atendidos = get_atendidos()
    df_completo = (
        pd.concat([df_atual, df_atendidos], ignore_index=True)
        if not df_atendidos.empty
        else df_atual
    )

    if df_completo.empty:
        st.markdown(
            """
        <div class="alert-modern alert-info">
            <div style="font-size: 1.5rem;">🧠</div>
            <div>
                <strong>Dados insuficientes para análise</strong><br>
                <small>Cadastre alguns pacientes para ver insights clínicos correlacionais</small>
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )
    else:
        # Calcular scores clínicos para todos os pacientes
        scores_clinicos = []
        for _, row in df_completo.iterrows():
            try:
                pa_parts = str(row["PA"]).split("/")
                pa_sist, pa_diast = int(pa_parts[0]), int(pa_parts[1])
                score, classificacao, alertas = calcular_score_clinico(
                    float(row["Temp"]),
                    pa_sist,
                    pa_diast,
                    int(row["FR"]),
                    int(row["FC"]),
                    int(row["Idade"]),
                )
                scores_clinicos.append(
                    {
                        "Nome": row["Nome"],
                        "Idade": row["Idade"],
                        "Temp": row["Temp"],
                        "PA_Sist": pa_sist,
                        "PA_Diast": pa_diast,
                        "FC": row["FC"],
                        "FR": row["FR"],
                        "Score": score,
                        "Classificacao": classificacao[0],
                        "Risco_Icon": classificacao[1],
                        "Descricao": classificacao[2],
                        "Alertas": "; ".join(alertas) if alertas else "Nenhum",
                    }
                )
            except Exception:
                continue
        if not scores_clinicos:
            st.error("❌ Erro ao processar dados dos pacientes")
            st.stop()
        df_scores = pd.DataFrame(scores_clinicos)

        # Resumo Clínico
        st.markdown("### 🧠 Resumo Clínico")
        col1, col2, col3 = st.columns(3)
        sepse_pattern = df_scores[
            (df_scores["Temp"] >= 38.0)
            & (df_scores["FC"] >= 100)
            & (df_scores["FR"] >= 22)
        ]
        choque_pattern = df_scores[
            (df_scores["FC"] >= 110) & (df_scores["PA_Sist"] < 100)
        ]
        with col1:
            score_medio = df_scores["Score"].mean()
            if score_medio < 3:
                status = "🟢 Estável"
                cor = "#10b981"
            elif score_medio < 6:
                status = "🟡 Moderado"
                cor = "#eab308"
            else:
                status = "🔴 Crítico"
                cor = "#ef4444"
            st.markdown(
                f"""
            <div style="background: linear-gradient(135deg, {cor}20, {cor}10); border-left: 4px solid {cor}; padding: 15px; border-radius: 8px;">
                <h3 style="margin: 0; color: {cor};">Score Médio: {score_medio:.1f}</h3>
                <p style="margin: 5px 0 0 0; color: #666;">{status} - {len(df_scores)} pacientes analisados</p>
            </div>
            """,
                unsafe_allow_html=True,
            )
        with col2:
            padroes_detectados = len(sepse_pattern) + len(choque_pattern)
            if padroes_detectados == 0:
                alert_msg = "✅ Nenhum padrão crítico detectado"
                alert_color = "#10b981"
            else:
                alert_msg = f"⚠️ {padroes_detectados} padrão(s) crítico(s)"
                alert_color = "#ef4444"
            st.markdown(
                f"""
            <div style="background: linear-gradient(135deg, {alert_color}20, {alert_color}10); border-left: 4px solid {alert_color}; padding: 15px; border-radius: 8px;">
                <h3 style="margin: 0; color: {alert_color};">Alertas Clínicos</h3>
                <p style="margin: 5px 0 0 0; color: #666;">{alert_msg}</p>
            </div>
            """,
                unsafe_allow_html=True,
            )
        with col3:
            padroes_criticos = (
                len(pd.concat([sepse_pattern, choque_pattern]).drop_duplicates())
                if (len(sepse_pattern) + len(choque_pattern)) > 0
                else 0
            )
            st.markdown(
                f"""
            <div class="metric-card-modern">
                <div class="metric-header">
                    <div class="metric-icon">🚑</div>
                    <div class="metric-title">Padrões Críticos</div>
                </div>
                <div class="metric-value">{padroes_criticos}</div>
                <div class="metric-change">Sepse/Choque detectados</div>
            </div>
            """,
                unsafe_allow_html=True,
            )
        st.markdown("---")
        if len(sepse_pattern) > 0 or len(choque_pattern) > 0:
            st.markdown("### 🚨 Alertas Críticos")
            if len(sepse_pattern) > 0:
                with st.expander(
                    f"🦠 **Padrão Séptico Detectado** ({len(sepse_pattern)} paciente(s))",
                    expanded=True,
                ):
                    st.markdown("**Critérios:** Febre ≥38°C + FC ≥100bpm + FR ≥22rpm")
                    if not sepse_pattern.empty:
                        st.dataframe(
                            sepse_pattern[
                                ["Nome", "Idade", "Temp", "FC", "FR", "Score"]
                            ],
                            use_container_width=True,
                        )
            if len(choque_pattern) > 0:
                with st.expander(
                    f"💔 **Possível Choque** ({len(choque_pattern)} paciente(s))",
                    expanded=True,
                ):
                    st.markdown("**Critérios:** FC ≥110bpm + PA Sistólica <100mmHg")
                    if not choque_pattern.empty:
                        st.dataframe(
                            choque_pattern[["Nome", "Idade", "PA_Sist", "FC", "Score"]],
                            use_container_width=True,
                        )
        st.markdown("### 📊 Visão Geral dos Riscos")
        # Grid 2x2 para gráficos principais
        grid_col1, grid_col2 = st.columns(2)
        with grid_col1:
            # Gráfico 1: Barras por prioridade
            prioridade_order = ["Mínima", "Baixa", "Média", "Alta", "Máxima"]
            prioridade_labels = {
                "MÍNIMA": "Mínima",
                "BAIXA": "Baixa",
                "MÉDIA PRIORIDADE": "Média",
                "MODERADA": "Média",
                "ALTA PRIORIDADE": "Alta",
                "ALTA": "Alta",
                "PRIORIDADE MÁXIMA": "Máxima",
                "CRÍTICA": "Máxima",
                "NORMAL": "Mínima",
            }
            try:
                prioridades_raw = (
                    df_atual["urgencia_manual"]
                    .fillna(df_atual.get("urgencia_automatica", "NORMAL"))
                    .tolist()
                )
            except Exception:
                prioridades_raw = []
            prioridades = (
                pd.Series(prioridades_raw).map(prioridade_labels).fillna("Mínima")
            )
            prioridade_counts = prioridades.value_counts().reindex(
                prioridade_order, fill_value=0
            )
            fig_bar_prioridade = px.bar(
                x=prioridade_counts.index,
                y=prioridade_counts.values,
                title="Pacientes por Prioridade de Triagem",
                labels={"x": "Prioridade", "y": "Número de Pacientes"},
                color=prioridade_counts.index,
                color_discrete_map={
                    "Mínima": "#10b981",
                    "Baixa": "#3b82f6",
                    "Média": "#eab308",
                    "Alta": "#f59e0b",
                    "Máxima": "#ef4444",
                },
            )
            fig_bar_prioridade.update_layout(
                height=400, xaxis_title="Prioridade", yaxis_title="Número de Pacientes"
            )
            st.plotly_chart(fig_bar_prioridade, use_container_width=True)
            # Gráfico 2: Radar chart para paciente individual
            st.markdown("#### Parâmetros Vitais - Radar Chart")
            nomes_pacientes = df_atual["Nome"].tolist() if not df_atual.empty else []
            paciente_selecionado = st.selectbox(
                "Selecione o paciente para análise clínica:",
                nomes_pacientes,
                key="radar_paciente",
            )
            if paciente_selecionado:
                dados_paciente = df_atual[
                    df_atual["Nome"] == paciente_selecionado
                ].iloc[0]
                parametros = ["FR", "FC", "PA", "SpO₂", "Temp", "Consciência"]
                valores = []
                valores.append(float(dados_paciente.get("FR", 0)))
                valores.append(float(dados_paciente.get("FC", 0)))
                try:
                    pa_sist = float(str(dados_paciente.get("PA", "0/0")).split("/")[0])
                except Exception:
                    pa_sist = 0
                valores.append(pa_sist)
                valores.append(
                    float(dados_paciente.get("SpO2", dados_paciente.get("SpO₂", 0)))
                )
                valores.append(float(dados_paciente.get("Temp", 0)))
                consciencia = dados_paciente.get(
                    "Estado_Mental", dados_paciente.get("Consciência", "Alerta")
                )
                valores.append(1 if str(consciencia).lower() == "alerta" else 0)
                normais = [18, 80, 120, 98, 36.5, 1]
                valores_norm = [v / n if n else 0 for v, n in zip(valores, normais)]
                fig_radar = go.Figure()
                fig_radar.add_trace(
                    go.Scatterpolar(
                        r=valores_norm,
                        theta=parametros,
                        fill="toself",
                        name=paciente_selecionado,
                    )
                )
                fig_radar.update_layout(
                    polar=dict(radialaxis=dict(visible=True)),
                    showlegend=False,
                    title="Radar de Parâmetros Vitais",
                )
                st.plotly_chart(fig_radar, use_container_width=True)
        with grid_col2:
            # Gráfico 3: Matriz de risco 2D (PA Sistólica vs FC)
            st.markdown("#### Matriz de Risco: PA Sistólica vs FC")
            if not df_atual.empty:
                fig_matriz = px.scatter(
                    df_atual,
                    x=df_atual["PA"].apply(
                        lambda x: int(str(x).split("/")[0]) if "/" in str(x) else 0
                    ),
                    y="FC",
                    color=df_atual["urgencia_manual"]
                    .map(prioridade_labels)
                    .fillna("Mínima"),
                    title="Matriz de Risco: PA Sistólica vs FC",
                    labels={"x": "PA Sistólica", "y": "Frequência Cardíaca"},
                    color_discrete_map={
                        "Mínima": "#10b981",
                        "Baixa": "#3b82f6",
                        "Média": "#eab308",
                        "Alta": "#f59e0b",
                        "Máxima": "#ef4444",
                    },
                )
                fig_matriz.update_layout(height=400)
                st.plotly_chart(fig_matriz, use_container_width=True)
            # Gráfico 4: Pizza das prioridades
            st.markdown("#### Proporção de Prioridades - Gráfico de Pizza")
            prioridades_raw = (
                df_atual["urgencia_manual"]
                .fillna(df_atual.get("urgencia_automatica", "NORMAL"))
                .tolist()
                if not df_atual.empty
                else []
            )
            prioridades = (
                pd.Series(prioridades_raw).map(prioridade_labels).fillna("Mínima")
            )
            prioridade_counts = prioridades.value_counts().reindex(
                prioridade_order, fill_value=0
            )
            fig_pie = px.pie(
                names=prioridade_counts.index,
                values=prioridade_counts.values,
                title="Proporção de Pacientes por Prioridade",
                color=prioridade_counts.index,
                color_discrete_map={
                    "Mínima": "#10b981",
                    "Baixa": "#3b82f6",
                    "Média": "#eab308",
                    "Alta": "#f59e0b",
                    "Máxima": "#ef4444",
                },
            )
            fig_pie.update_layout(height=400)
            st.plotly_chart(fig_pie, use_container_width=True)



    # ...existing code...
with tab_analytics:
    st.subheader("⚕️ Análise de Comorbidades e Alergias")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### 📊 Comorbidades")
        comorb_df = df["Comorbidade"].value_counts().reset_index()
        comorb_df.columns = ["Comorbidade", "Quantidade"]

        fig_comorb_bar = px.bar(
            comorb_df,
            x="Quantidade",
            y="Comorbidade",
            orientation="h",
            title="Distribuição de Comorbidades",
            color="Quantidade",
            color_continuous_scale="Blues",
        )
        fig_comorb_bar.update_layout(height=400)
        st.plotly_chart(fig_comorb_bar, use_container_width=True)

        # Tabela de comorbidades
        st.dataframe(comorb_df, use_container_width=True)

    with col2:
        st.markdown("### 🚨 Alergias")
        alergia_df = df["Alergia"].value_counts().reset_index()
        alergia_df.columns = ["Alergia", "Quantidade"]

        fig_alergia_bar = px.bar(
            alergia_df,
            x="Quantidade",
            y="Alergia",
            orientation="h",
            title="Distribuição de Alergias",
            color="Quantidade",
            color_continuous_scale="Reds",
        )
        fig_alergia_bar.update_layout(height=400)
        st.plotly_chart(fig_alergia_bar, use_container_width=True)

        # Tabela de alergias
        st.dataframe(alergia_df, use_container_width=True)

    # Análise cruzada

    st.subheader("🔗 Análise Cruzada: Comorbidades vs Temperatura")
    # Gráfico de dispersão
    fig_scatter = px.scatter(
        df,
        x="Temp",
        y="Comorbidade",
        title="Dispersão: Temperatura vs Comorbidade",
        color="Temp",
        color_continuous_scale="RdYlBu",
    )
    fig_scatter.update_layout(height=400)
    st.plotly_chart(fig_scatter, use_container_width=True)
    # Estatísticas de temperatura
    st.subheader("📊 Estatísticas de Temperatura")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        temp_normal = len(df[df["Temp"] <= 37.0])
        st.metric("🟢 Normal (≤37°C)", temp_normal, f"{temp_normal/len(df)*100:.1f}%")

    with col2:
        temp_elevada = len(df[(df["Temp"] > 37.0) & (df["Temp"] <= 37.5)])
        st.metric(
            "🟡 Elevada (37-37.5°C)", temp_elevada, f"{temp_elevada/len(df)*100:.1f}%"
        )

    with col3:
        temp_febre = len(df[(df["Temp"] > 37.5) & (df["Temp"] < 39.0)])
        st.metric("🔴 Febre (37.5-39°C)", temp_febre, f"{temp_febre/len(df)*100:.1f}%")

    with col4:
        temp_alta = len(df[df["Temp"] >= 39.0])
        st.metric("🔥 Febre Alta (≥39°C)", temp_alta, f"{temp_alta/len(df)*100:.1f}%")
    # Formulário de cadastro de paciente

    # Prévia de urgência (lado direito) – atualiza em tempo real conforme campos
    # ...prévia de urgência removida...

    # Instruções
    st.markdown("---")
    st.markdown(
        """
    ### 📝 Instruções de Uso
    - Campos marcados com (*) são obrigatórios
    - Pressão Arterial no formato Sistólica/Diastólica (Ex: 120/80)
    - Sistema calcula a urgência automaticamente conforme os sinais vitais
    - Use descrições claras e objetivas na Queixa Principal
    """
    )

# Footer substituído por marca discreta
st.markdown(
    """
<div style='text-align:center;margin:40px 0 10px 0;opacity:0.6;font-size:12px;'>
🏥 <strong>Avicena Care</strong> · Sistema de Triagem Médica · Versão 2.0 | 2025
</div>
""",
    unsafe_allow_html=True,
)
