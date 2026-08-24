import io
import re
import unicodedata
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="RFT Rolling 12", page_icon="📊", layout="wide")

MODEL_MAP = {
    "VTBAGFC": "VTBA",
    "V2MFGFC": "V2 MF",
    "V2VTGFC": "V2 VT",
    "G7GFCAN": "G7",
    "G8GFCAN": "G8",
}

ALIASES = {
    "data": ["data", "date", "data_producao", "production_date", "dt"],
    "modelo": ["modelo", "model", "produto", "product", "model_code"],
    "turno": ["turno", "shift", "turma"],
    "id": ["id", "serial", "numero_serie", "serie", "chassi", "vin", "unit_id"],
    "resultado": ["resultado", "status", "result", "situacao", "aprovacao"],
    "falha": ["falha", "defeito", "failure", "defect", "descricao_falha"],
    "quantidade": ["quantidade", "qtd", "qty", "volume", "unidades"],
    "aprovado_primeira": ["aprovado_primeira", "first_pass", "rft_ok", "pass_first_time"],
}

PASS_VALUES = {"OK", "APROVADO", "APROVADA", "PASS", "PASSOU", "CONFORME", "SEM FALHA", "RFT"}
FAIL_VALUES = {"NOK", "REPROVADO", "REPROVADA", "FAIL", "FALHA", "NAO CONFORME", "NC"}


def norm(value):
    value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def read_csv(uploaded):
    raw = uploaded.getvalue()
    attempts = []
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        for sep in (None, ";", ",", "\t"):
            try:
                kwargs = {"encoding": encoding}
                if sep is None:
                    kwargs.update({"sep": None, "engine": "python"})
                else:
                    kwargs["sep"] = sep
                df = pd.read_csv(io.BytesIO(raw), **kwargs)
                if df.shape[1] > 1:
                    return df
            except Exception as exc:
                attempts.append(str(exc))
    raise ValueError("Não foi possível identificar a codificação ou o separador do CSV.")


def guess_column(columns, role):
    normalized = {norm(c): c for c in columns}
    for alias in ALIASES[role]:
        if norm(alias) in normalized:
            return normalized[norm(alias)]
    return None


def parse_dates(series):
    parsed = pd.to_datetime(series, errors="coerce", dayfirst=True)
    if parsed.notna().mean() < 0.5:
        parsed = pd.to_datetime(series, errors="coerce")
    return parsed


def normalize_result(value):
    text = norm(value).replace("_", " ").upper()
    if text in PASS_VALUES or text in {norm(x).replace("_", " ").upper() for x in PASS_VALUES}:
        return True
    if text in FAIL_VALUES or text in {norm(x).replace("_", " ").upper() for x in FAIL_VALUES}:
        return False
    if text in {"1", "TRUE", "SIM", "YES"}:
        return True
    if text in {"0", "FALSE", "NAO", "NO"}:
        return False
    return np.nan


def month_label(period):
    names = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    return f"{names[period.month - 1]}/{str(period.year)[-2:]}"


def calculate_unit_level(df, date_col, id_col, result_col, model_col, shift_col, failure_col):
    work = df.copy()
    work["_data"] = parse_dates(work[date_col])
    work = work.dropna(subset=["_data"])
    work["_mes"] = work["_data"].dt.to_period("M")
    work["_id"] = work[id_col].astype(str).str.strip()
    work["_pass"] = work[result_col].map(normalize_result)
    work = work.dropna(subset=["_pass"])
    if model_col:
        work["_modelo"] = work[model_col].astype(str).str.strip().replace(MODEL_MAP)
    else:
        work["_modelo"] = "Todos"
    work["_turno"] = work[shift_col].astype(str).str.strip() if shift_col else "Todos"
    work["_falha"] = work[failure_col].fillna("Não informado").astype(str).str.strip() if failure_col else "Não informado"

    # Uma unidade é aprovada de primeira somente quando seu primeiro registro cronológico é aprovado.
    first = work.sort_values("_data").drop_duplicates(["_mes", "_id"], keep="first")
    return work, first


def calculate_aggregated(df, date_col, qty_col, first_pass_col, model_col, shift_col, failure_col):
    work = df.copy()
    work["_data"] = parse_dates(work[date_col])
    work = work.dropna(subset=["_data"])
    work["_mes"] = work["_data"].dt.to_period("M")
    work["_quantidade"] = pd.to_numeric(work[qty_col], errors="coerce").fillna(0)
    raw_pass = work[first_pass_col]
    numeric_pass = pd.to_numeric(raw_pass, errors="coerce")
    if numeric_pass.notna().mean() >= 0.8:
        work["_aprovadas"] = numeric_pass.fillna(0)
    else:
        work["_aprovadas"] = raw_pass.map(normalize_result).fillna(False).astype(int) * work["_quantidade"]
    work["_modelo"] = work[model_col].astype(str).str.strip().replace(MODEL_MAP) if model_col else "Todos"
    work["_turno"] = work[shift_col].astype(str).str.strip() if shift_col else "Todos"
    work["_falha"] = work[failure_col].fillna("Não informado").astype(str).str.strip() if failure_col else "Não informado"
    return work


def apply_filters(df, model_values, shift_values):
    result = df.copy()
    if model_values:
        result = result[result["_modelo"].isin(model_values)]
    if shift_values:
        result = result[result["_turno"].isin(shift_values)]
    return result


st.markdown("""
<style>
.stApp { background: linear-gradient(145deg, #07111f 0%, #0b1729 55%, #081421 100%); }
[data-testid="stMetric"] { background: rgba(15,23,42,.88); border: 1px solid #23324a; padding: 18px; border-radius: 16px; }
[data-testid="stMetricLabel"] { color: #94a3b8; }
[data-testid="stMetricValue"] { color: #f8fafc; }
.block-container { max-width: 1500px; padding-top: 2rem; }
h1, h2, h3 { color: #f8fafc !important; }
</style>
""", unsafe_allow_html=True)

st.title("RFT Rolling 12")
st.caption("Faça upload do CSV para calcular o RFT mensal e o resultado ponderado dos 12 meses mais recentes.")

uploaded = st.file_uploader("Arquivo CSV", type=["csv"], help="O processamento ocorre durante a sessão do aplicativo.")

with st.sidebar:
    st.header("Configuração")
    target = st.number_input("Meta de RFT (%)", min_value=0.0, max_value=100.0, value=95.0, step=0.1)
    mode = st.radio("Estrutura dos dados", ["Uma linha por inspeção/unidade", "Dados mensais ou agregados"])

if uploaded is None:
    st.info("Anexe um CSV para iniciar. O sistema tentará reconhecer automaticamente as colunas.")
    st.markdown("""
### Formatos aceitos
**Por unidade/inspeção:** data, identificação da unidade e resultado (aprovado/reprovado).  
**Agregado:** data/mês, quantidade produzida e quantidade aprovada de primeira.

Campos opcionais: modelo, turno e falha/defeito.
""")
    st.stop()

try:
    raw_df = read_csv(uploaded)
except Exception as exc:
    st.error(str(exc))
    st.stop()

st.success(f"CSV carregado: {len(raw_df):,} linhas e {len(raw_df.columns)} colunas".replace(",", "."))

with st.expander("Mapeamento das colunas", expanded=True):
    cols = ["— Não utilizar —"] + list(raw_df.columns)
    def selector(label, role, required=False):
        guessed = guess_column(raw_df.columns, role)
        index = cols.index(guessed) if guessed in cols else 0
        selected = st.selectbox(label + (" *" if required else ""), cols, index=index, key=f"map_{role}")
        return None if selected == cols[0] else selected

    c1, c2, c3 = st.columns(3)
    with c1:
        date_col = selector("Data ou mês", "data", True)
        model_col = selector("Modelo", "modelo")
    with c2:
        shift_col = selector("Turno", "turno")
        failure_col = selector("Falha/defeito", "falha")
    with c3:
        if mode == "Uma linha por inspeção/unidade":
            id_col = selector("Identificação da unidade", "id", True)
            result_col = selector("Resultado da inspeção", "resultado", True)
            qty_col = first_pass_col = None
        else:
            qty_col = selector("Quantidade produzida", "quantidade", True)
            first_pass_col = selector("Aprovadas de primeira", "aprovado_primeira", True)
            id_col = result_col = None

required = [date_col, id_col, result_col] if mode.startswith("Uma") else [date_col, qty_col, first_pass_col]
if any(x is None for x in required):
    st.warning("Selecione todas as colunas obrigatórias marcadas com *.")
    st.stop()

try:
    if mode.startswith("Uma"):
        detailed, units = calculate_unit_level(raw_df, date_col, id_col, result_col, model_col, shift_col, failure_col)
        filter_source = units
    else:
        detailed = calculate_aggregated(raw_df, date_col, qty_col, first_pass_col, model_col, shift_col, failure_col)
        filter_source = detailed
except Exception as exc:
    st.error(f"Erro ao preparar os dados: {exc}")
    st.stop()

with st.sidebar:
    st.header("Filtros")
    model_options = sorted(filter_source["_modelo"].dropna().unique().tolist())
    shift_options = sorted(filter_source["_turno"].dropna().unique().tolist())
    selected_models = st.multiselect("Modelo", model_options, default=model_options)
    selected_shifts = st.multiselect("Turno", shift_options, default=shift_options)

filtered = apply_filters(filter_source, selected_models, selected_shifts)
if filtered.empty:
    st.warning("Nenhum registro encontrado para os filtros selecionados.")
    st.stop()

last_month = filtered["_mes"].max()
first_month = last_month - 11
rolling = filtered[(filtered["_mes"] >= first_month) & (filtered["_mes"] <= last_month)].copy()

if mode.startswith("Uma"):
    monthly = rolling.groupby("_mes").agg(produzidas=("_id", "nunique"), aprovadas=("_pass", "sum")).reset_index()
else:
    monthly = rolling.groupby("_mes").agg(produzidas=("_quantidade", "sum"), aprovadas=("_aprovadas", "sum")).reset_index()

monthly["rft"] = np.where(monthly["produzidas"] > 0, monthly["aprovadas"] / monthly["produzidas"] * 100, np.nan)
all_months = pd.DataFrame({"_mes": pd.period_range(first_month, last_month, freq="M")})
monthly = all_months.merge(monthly, on="_mes", how="left")
monthly["mes"] = monthly["_mes"].map(month_label)
monthly["meta"] = target

total_units = monthly["produzidas"].sum(skipna=True)
total_pass = monthly["aprovadas"].sum(skipna=True)
rolling_rft = total_pass / total_units * 100 if total_units else np.nan
valid_months = int(monthly["rft"].notna().sum())
months_target = int((monthly["rft"] >= target).sum())
latest_rft = monthly.loc[monthly["rft"].last_valid_index(), "rft"] if monthly["rft"].notna().any() else np.nan

m1, m2, m3, m4 = st.columns(4)
m1.metric("RFT Rolling 12", f"{rolling_rft:.2f}%" if pd.notna(rolling_rft) else "—")
m2.metric("RFT do último mês", f"{latest_rft:.2f}%" if pd.notna(latest_rft) else "—")
m3.metric("Meses na meta", f"{months_target}/{valid_months}")
m4.metric("Volume analisado", f"{int(total_units):,}".replace(",", "."))

st.caption(f"Janela automática: {month_label(first_month)} a {month_label(last_month)} • cálculo ponderado pelo volume")

fig = go.Figure()
fig.add_trace(go.Scatter(x=monthly["mes"], y=monthly["rft"], mode="lines+markers", name="RFT mensal", line=dict(color="#22d3ee", width=3), marker=dict(size=8)))
fig.add_trace(go.Scatter(x=monthly["mes"], y=monthly["meta"], mode="lines", name="Meta", line=dict(color="#f59e0b", width=2, dash="dash")))
fig.add_hline(y=rolling_rft, line_color="#a78bfa", line_dash="dot", annotation_text=f"Rolling 12: {rolling_rft:.2f}%" if pd.notna(rolling_rft) else "")
fig.update_layout(title="Evolução mensal do RFT", template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(15,23,42,.65)", yaxis_title="RFT (%)", xaxis_title="", legend_orientation="h", height=430, margin=dict(l=20, r=20, t=65, b=20))
fig.update_yaxes(range=[max(0, min(target, monthly["rft"].min(skipna=True) if monthly["rft"].notna().any() else target) - 5), 100])
st.plotly_chart(fig, use_container_width=True)

left, right = st.columns(2)
with left:
    volume = px.bar(monthly, x="mes", y="produzidas", title="Volume produzido por mês", labels={"mes": "", "produzidas": "Unidades"}, color_discrete_sequence=["#3b82f6"], template="plotly_dark")
    volume.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(15,23,42,.65)", height=360)
    st.plotly_chart(volume, use_container_width=True)
with right:
    if failure_col and mode.startswith("Uma"):
        raw_filtered = apply_filters(detailed, selected_models, selected_shifts)
        raw_rolling = raw_filtered[(raw_filtered["_mes"] >= first_month) & (raw_filtered["_mes"] <= last_month)]
        failures = raw_rolling[~raw_rolling["_pass"].astype(bool)].groupby("_falha").size().sort_values(ascending=False).head(10).reset_index(name="ocorrencias")
    elif failure_col:
        failures = rolling.groupby("_falha")["_quantidade"].sum().sort_values(ascending=False).head(10).reset_index(name="ocorrencias")
    else:
        failures = pd.DataFrame()
    if not failures.empty:
        pareto = px.bar(failures.sort_values("ocorrencias"), x="ocorrencias", y="_falha", orientation="h", title="Top falhas no Rolling 12", labels={"_falha": "", "ocorrencias": "Ocorrências"}, color_discrete_sequence=["#ef4444"], template="plotly_dark")
        pareto.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(15,23,42,.65)", height=360)
        st.plotly_chart(pareto, use_container_width=True)
    else:
        st.info("Mapeie uma coluna de falha/defeito para visualizar o Pareto.")

st.subheader("Resultado mensal")
display = monthly[["mes", "produzidas", "aprovadas", "rft"]].copy()
display.columns = ["Mês", "Produzidas", "Aprovadas de primeira", "RFT (%)"]
display["RFT (%)"] = display["RFT (%)"].round(2)
st.dataframe(display, use_container_width=True, hide_index=True)

export = display.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
st.download_button("Baixar resultado Rolling 12", export, file_name="resultado_rft_rolling12.csv", mime="text/csv")

with st.expander("Regra de cálculo"):
    st.markdown("""
- **RFT mensal:** aprovadas de primeira ÷ produzidas no mês.
- **RFT Rolling 12:** soma das aprovadas de primeira ÷ soma das produzidas nos 12 meses mais recentes.
- Em dados por unidade, é considerado o primeiro registro cronológico de cada unidade em cada mês.
- Meses sem registros permanecem visíveis, mas não entram no denominador.
""")
