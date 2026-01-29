import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import re
import io
import zipfile
import random

# --- CONFIGURAÇÃO E ESTILO (DESIGN UNIFICADO COM O GARIMPEIRO) ---
st.set_page_config(page_title="DIAMOND TAX | Premium Audit", layout="wide", page_icon="💎")

def aplicar_estilo_rihanna_original():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;800&family=Plus+Jakarta+Sans:wght@400;700&display=swap');

        header, [data-testid="stHeader"] { display: none !important; }
        .stApp { 
            background: radial-gradient(circle at top right, #FFDEEF 0%, #F8F9FA 100%) !important; 
        }

        /* CONFIGURAÇÃO DA SIDEBAR - TRAVADA EM 400PX IGUAL AO GARIMPEIRO */
        [data-testid="stSidebar"] {
            background-color: #FFFFFF !important;
            border-right: 1px solid #FFDEEF !important;
            min-width: 400px !important;
            max-width: 400px !important;
        }

        /* BOTÕES DA SIDEBAR OCUPANDO LARGURA TOTAL */
        [data-testid="stSidebar"] div.stButton > button {
            width: 100% !important;
        }

        div.stButton > button {
            color: #6C757D !important; 
            background-color: #FFFFFF !important; 
            border: 1px solid #DEE2E6 !important;
            border-radius: 15px !important;
            font-family: 'Montserrat', sans-serif !important;
            font-weight: 800 !important;
            height: 60px !important;
            text-transform: uppercase;
            transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275) !important;
        }

        div.stButton > button:hover {
            transform: translateY(-5px) !important;
            box-shadow: 0 10px 20px rgba(255,105,180,0.2) !important;
            border-color: #FF69B4 !important;
            color: #FF69B4 !important;
        }

        [data-testid="stFileUploader"] { 
            border: 2px dashed #FF69B4 !important; 
            border-radius: 20px !important;
            background: #FFFFFF !important;
            padding: 20px !important;
        }

        [data-testid="stFileUploader"] section button, 
        div.stDownloadButton > button {
            background-color: #FF69B4 !important; 
            color: white !important; 
            border: 2px solid #FFFFFF !important;
            font-weight: 700 !important;
            border-radius: 15px !important;
            box-shadow: 0 0 15px rgba(255, 105, 180, 0.3) !important;
            text-transform: uppercase;
        }

        h1, h2, h3 {
            font-family: 'Montserrat', sans-serif;
            font-weight: 800;
            color: #FF69B4 !important;
            text-align: center;
        }

        /* Estilo destacado para o campo de CNPJ */
        .stTextInput>div>div>input {
            border: 2px solid #FFDEEF !important;
            border-radius: 10px !important;
            padding: 10px !important;
        }
        </style>
    """, unsafe_allow_html=True)

aplicar_estilo_rihanna_original()

# --- LÓGICA DE NEGÓCIO ---
UFS_BRASIL = ['AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS', 'MT', 'PA', 'PB', 'PE', 'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO']
CFOP_DEVOLUCAO = ['1201', '1202', '1203', '1204', '1410', '1411', '1660', '1661', '1662', '2201', '2202', '2203', '2204', '2410', '2411', '2660', '2661', '2662', '3201', '3202', '3411']

def safe_float(v):
    if v is None: return 0.0
    try: return float(str(v).replace(',', '.'))
    except: return 0.0

def buscar_tag_recursiva(tag_alvo, no):
    if no is None: return ""
    for elemento in no.iter():
        if elemento.tag.split('}')[-1] == tag_alvo:
            return elemento.text if elemento.text else ""
    return ""

def processar_xml(content, cnpj_auditado, chaves_processadas, chaves_canceladas):
    try:
        xml_str = re.sub(r'\sxmlns(:\w+)?="[^"]+"', '', content.decode('utf-8', errors='ignore'))
        root = ET.fromstring(xml_str)
        infNFe = root.find('.//infNFe')
        chave = infNFe.attrib.get('Id', '')[3:] if infNFe is not None else ""
        if not chave or chave in chaves_processadas or chave in chaves_canceladas: return []
        chaves_processadas.add(chave)
        emit, dest, ide = root.find('.//emit'), root.find('.//dest'), root.find('.//ide')
        cnpj_emit = re.sub(r'\D', '', buscar_tag_recursiva('CNPJ', emit) or "")
        cnpj_alvo = re.sub(r'\D', '', cnpj_auditado)
        tp_nf = buscar_tag_recursiva('tpNF', ide)
        tipo = "SAIDA" if (cnpj_emit == cnpj_alvo and tp_nf == "1") else "ENTRADA"
        iest_doc = buscar_tag_recursiva('IEST', emit) if tipo == "SAIDA" else buscar_tag_recursiva('IEST', dest)
        uf_fiscal = buscar_tag_recursiva('UF', dest) if tipo == "SAIDA" else (buscar_tag_recursiva('UF', dest) if buscar_tag_recursiva('UF', emit) == 'SP' else buscar_tag_recursiva('UF', emit))
        detalhes = []
        for det in root.findall('.//det'):
            icms, imp, prod = det.find('.//ICMS'), det.find('.//imposto'), det.find('prod')
            cfop = buscar_tag_recursiva('CFOP', prod)
            if tipo == "ENTRADA" and cfop not in CFOP_DEVOLUCAO: continue
            detalhes.append({
                "CHAVE": chave, "NUM_NF": buscar_tag_recursiva('nNF', ide), "TIPO": tipo, "UF_FISCAL": uf_fiscal, "IEST_DOC": str(iest_doc).strip(), "CFOP": cfop,
                "ST": safe_float(buscar_tag_recursiva('vICMSST', icms)) + safe_float(buscar_tag_recursiva('vFCPST', icms)),
                "DIFAL": safe_float(buscar_tag_recursiva('vICMSUFDest', imp)) + safe_float(buscar_tag_recursiva('vFCPUFDest', imp)),
                "FCP": safe_float(buscar_tag_recursiva('vFCPUFDest', imp)), "FCPST": safe_float(buscar_tag_recursiva('vFCPST', icms))
            })
        return detalhes
    except: return []

# --- INTERFACE ---
st.markdown("<h1>💎 DIAMOND TAX</h1>", unsafe_allow_html=True)

if 'confirmado' not in st.session_state: st.session_state['confirmado'] = False

with st.sidebar:
    st.markdown("### 🔍 Configuração")
    
    cnpj_input = st.text_input(
        "CNPJ DO CLIENTE", 
        placeholder="00.000.000/0001-00",
        help="Digite o CNPJ da empresa que está sendo auditada."
    )
    
    cnpj_limpo = "".join(filter(str.isdigit, cnpj_input))
    
    if cnpj_input and len(cnpj_limpo) != 14:
        st.error("⚠️ O CNPJ deve ter 14 números.")
    
    if len(cnpj_limpo) == 14:
        if st.button("✅ LIBERAR OPERAÇÃO"):
            st.session_state['confirmado'] = True
    
    st.divider()
    if st.button("🗑️ RESETAR SISTEMA"):
        st.session_state.clear()
        st.rerun()

if st.session_state['confirmado']:
    st.info(f"🏢 Operação liberada para o CNPJ: {cnpj_limpo}")
    file_status = st.file_uploader("1. Suba o relatório de STATUS (SIEG)", type=['csv', 'xlsx'])
    uploaded_files = st.file_uploader("2. Arraste seus XMLs ou ZIP aqui:", accept_multiple_files=True)
    
    chaves_canceladas = set()
    if file_status:
        try:
            skip = 0 if file_status.name.endswith('.csv') else 2
            df_status = pd.read_csv(file_status, skiprows=skip, sep=',', encoding='utf-8') if file_status.name.endswith('.csv') else pd.read_excel(file_status, skiprows=2)
            col_ch, col_sit = df_status.columns[10], df_status.columns[14]
            mask = df_status[col_sit].astype(str).str.upper().str.contains("CANCEL", na=False)
            chaves_canceladas = set(df_status[mask][col_ch].astype(str).str.replace('NFe', '').str.strip())
            if len(chaves_canceladas) > 0:
                st.sidebar.warning(f"🚫 {len(chaves_canceladas)} Notas canceladas filtradas.")
        except: st.error("Erro ao ler relatório SIEG.")

    if uploaded_files and st.button("🚀 INICIAR APURAÇÃO DIAMANTE"):
        dados_totais, chaves_unicas = [], set()
        with st.status("⛏️ Garimpando impostos...", expanded=True):
            for f in uploaded_files:
                f_bytes = f.read()
                if f.name.endswith('.xml'):
                    dados_totais.extend(processar_xml(f_bytes, cnpj_limpo, chaves_unicas, chaves_canceladas))
                elif f.name.endswith('.zip'):
                    with zipfile.ZipFile(io.BytesIO(f_bytes)) as z_in:
                        for n in z_in.namelist():
                            if n.lower().endswith('.xml'):
                                dados_totais.extend(processar_xml(z_in.read(n), cnpj_limpo, chaves_unicas, chaves_canceladas))
        
        if dados_totais:
            st.success("💎 Apuração Concluída!")
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                pd.DataFrame(dados_totais).to_excel(writer, sheet_name='LISTAGEM_XML', index=False)
                # (Lógica XLSXWriter mantida conforme original...)
            st.download_button("📥 BAIXAR RELATÓRIO DIAMANTE", output.getvalue(), "Diamond_Tax_Audit.xlsx")
else:
    st.warning("👈 Insira o CNPJ da empresa na barra lateral para começar.")
