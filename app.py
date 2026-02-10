import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import re
import io
import zipfile
import random

# --- CONFIGURAÇÃO E ESTILO (DESIGN UNIFICADO E TRAVADO) ---
st.set_page_config(page_title="DIAMOND TAX | Premium Audit", layout="wide", page_icon="💎")

# --- CONFIGURAÇÃO DE APARÊNCIA (COR ROSA ESPECIFICADA) ---
COR_ROSA_CLARINHO = '#FFEBFA' 

def aplicar_estilo_rihanna_original():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;800&family=Plus+Jakarta+Sans:wght@400;700&display=swap');

        header, [data-testid="stHeader"] { display: none !important; }
        .stApp { 
            background: radial-gradient(circle at top right, #FFDEEF 0%, #F8F9FA 100%) !important; 
        }

        [data-testid="stSidebar"] {
            background-color: #FFFFFF !important;
            border-right: 1px solid #FFDEEF !important;
            min-width: 400px !important;
            max-width: 400px !important;
        }

        [data-testid="stSidebar"] div.stButton > button { width: 100% !important; }

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

        div.stDownloadButton > button {
            background-color: #FF69B4 !important; 
            color: white !important; 
            border: 2px solid #FFFFFF !important;
            font-weight: 700 !important;
            border-radius: 15px !important;
            box-shadow: 0 0 15px rgba(255, 105, 180, 0.3) !important;
            text-transform: uppercase;
            width: 100% !important;
        }

        h1, h2, h3 {
            font-family: 'Montserrat', sans-serif;
            font-weight: 800;
            color: #FF69B4 !important;
            text-align: center;
        }

        .stTextInput>div>div>input {
            border: 2px solid #FFDEEF !important;
            border-radius: 10px !important;
            padding: 10px !important;
        }

        .instrucoes-card {
            background-color: rgba(255, 255, 255, 0.7);
            border-radius: 15px;
            padding: 20px;
            border-left: 5px solid #FF69B4;
            margin-bottom: 20px;
            min-height: 280px;
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

# SEÇÃO SEMPRE VISÍVEL: PASSO A PASSO E OBJETIVOS
with st.container():
    m_col1, m_col2 = st.columns(2)
    with m_col1:
        st.markdown("""
        <div class="instrucoes-card">
            <h3>📖 Passo a Passo</h3>
            <ol>
                <li><b>Relatório SIEG:</b> Suba os arquivos CSV ou XLSX de Status para filtrar notas canceladas (pode ser mais de um).</li>
                <li><b>Arquivos XML:</b> Arraste seus arquivos XML ou pastas ZIP para a área de upload.</li>
                <li><b>Processamento:</b> Clique no botão <b>"INICIAR APURAÇÃO DIAMANTE"</b>.</li>
                <li><b>Download:</b> Baixe o Excel final com as abas de listagem e resumo por estado.</li>
            </ol>
        </div>
        """, unsafe_allow_html=True)
    with m_col2:
        st.markdown("""
        <div class="instrucoes-card">
            <h3>📊 O que será obtido?</h3>
            <ul>
                <li><b>Cálculo de DIFAL/ST/FCP:</b> Apuração automática separada por UF.</li>
                <li><b>Regra Rio de Janeiro:</b> Lógica aplicada para abatimento de FCP no DIFAL (RJ).</li>
                <li><b>Relatório Inteligente:</b> Excel sem linhas de grade, com bordas e destaque Rosa nas IESTs.</li>
                <li><b>Fórmulas Vivas:</b> O arquivo gerado contém fórmulas para conferência de saldos.</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

st.markdown("---")

if 'confirmado' not in st.session_state: st.session_state['confirmado'] = False

with st.sidebar:
    st.markdown("### 🔍 Configuração")
    cnpj_input = st.text_input("CNPJ DO CLIENTE", placeholder="00.000.000/0001-00")
    cnpj_limpo = "".join(filter(str.isdigit, cnpj_input))
    if cnpj_input and len(cnpj_limpo) != 14: st.error("⚠️ O CNPJ deve ter 14 números.")
    if len(cnpj_limpo) == 14:
        if st.button("✅ LIBERAR OPERAÇÃO"): st.session_state['confirmado'] = True
    st.divider()
    if st.button("🗑️ RESETAR SISTEMA"):
        st.session_state.clear()
        st.rerun()

if st.session_state['confirmado']:
    st.info(f"🏢 Empresa: {cnpj_limpo}")
    # ALTERADO: accept_multiple_files=True para permitir vários relatórios de status
    files_status = st.file_uploader("1. Suba os relatórios de STATUS (SIEG)", type=['csv', 'xlsx'], accept_multiple_files=True)
    uploaded_files = st.file_uploader("2. Arraste seus XMLs ou ZIP aqui:", accept_multiple_files=True)
    
    chaves_canceladas = set()
    
    # Processamento de Múltiplos Arquivos de Status
    if files_status:
        for f_status in files_status:
            try:
                # O cabeçalho real está na linha 3 (índice 2)
                if f_status.name.endswith('.csv'):
                    # Lê pulando as primeiras linhas de metadados
                    df_status = pd.read_csv(f_status, header=2, sep=',', encoding='utf-8', on_bad_lines='skip')
                else:
                    df_status = pd.read_excel(f_status, header=2)
                
                # Normalizar nomes das colunas para evitar erros de case/espaço
                df_status.columns = df_status.columns.str.strip().str.upper()

                # Tenta localizar as colunas pelo nome
                col_status = next((c for c in df_status.columns if 'STATUS' in c), None)
                col_chave = next((c for c in df_status.columns if 'CHAVE' in c), None)

                if col_status and col_chave:
                    mask = df_status[col_status].astype(str).str.upper().str.contains("CANCEL", na=False)
                    # Extrai as chaves deste arquivo e adiciona ao conjunto total
                    novas_chaves = set(
                        df_status.loc[mask, col_chave]
                        .astype(str)
                        .str.replace(r'\D', '', regex=True) # Remove NFe, espaços, letras
                        .str.strip()
                    )
                    chaves_canceladas.update(novas_chaves)
                else:
                    st.warning(f"⚠️ Aviso: Colunas de 'Chave' ou 'Status' não identificadas no arquivo {f_status.name}.")

            except Exception as e: 
                st.error(f"Erro no relatório {f_status.name}: {e}")
        
        if chaves_canceladas:
            st.success(f"✅ {len(chaves_canceladas)} notas canceladas identificadas nos relatórios.")

    if uploaded_files and st.button("🚀 INICIAR APURAÇÃO DIAMANTE"):
        dados_totais, chaves_unicas = [], set()
        with st.status("💎 Analisando impostos...", expanded=True):
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
            output = io.BytesIO()
            df_listagem = pd.DataFrame(dados_totais)
            
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_listagem.to_excel(writer, sheet_name='LISTAGEM_XML', index=False)
                
                workbook = writer.book
                ws = workbook.add_worksheet('DIFAL_ST_FECP')
                ws.hide_gridlines(2)

                f_tit = workbook.add_format({'bold':True, 'bg_color':'#FF69B4', 'font_color':'#FFFFFF', 'border':1, 'align':'center'})
                f_head = workbook.add_format({'bold':True, 'bg_color':'#F8F9FA', 'font_color':'#6C757D', 'border':1, 'align':'center'})
                f_num = workbook.add_format({'num_format':'#,##0.00', 'border':1})
                f_uf = workbook.add_format({'border':1, 'align':'center'})
                f_pink_light = workbook.add_format({'bg_color': COR_ROSA_CLARINHO, 'border': 1})

                ws.merge_range('A1:F1', '1. SAÍDAS', f_tit)
                ws.merge_range('H1:M1', '2. ENTRADAS (DEV)', f_tit)
                ws.merge_range('O1:T1', '3. SALDO', f_tit)

                heads = ['UF', 'IEST', 'ST TOTAL', 'DIFAL TOTAL', 'FCP TOTAL', 'FCPST TOTAL']
                for i, h in enumerate(heads):
                    ws.write(1, i, h, f_head)
                    ws.write(1, i + 7, h, f_head)
                    ws.write(1, i + 14, h, f_head)

                for r, uf in enumerate(UFS_BRASIL):
                    row = r + 2
                    ws.write(row, 0, uf, f_uf)
                    ws.write(row, 7, uf, f_uf)
                    ws.write(row, 14, uf, f_uf)
                    
                    ws.write_formula(row, 1, f'=IFERROR(INDEX(LISTAGEM_XML!E:E, MATCH("{uf}", LISTAGEM_XML!D:D, 0)) & "", "")', f_uf)
                    ws.write_formula(row, 8, f'=B{row+1}', f_uf)
                    ws.write_formula(row, 15, f'=B{row+1}', f_uf)

                    for i, col_let in enumerate(['G', 'H', 'I', 'J']): 
                        ws.write_formula(row, i+2, f'=SUMIFS(LISTAGEM_XML!{col_let}:{col_let}, LISTAGEM_XML!D:D, "{uf}", LISTAGEM_XML!C:C, "SAIDA")', f_num)
                        ws.write_formula(row, i+9, f'=SUMIFS(LISTAGEM_XML!{col_let}:{col_let}, LISTAGEM_XML!D:D, "{uf}", LISTAGEM_XML!C:C, "ENTRADA")', f_num)
                        col_s, col_e = chr(65 + i + 2), chr(65 + i + 9)
                        if i == 1: 
                            f_sal = f'=IF(B{row+1}<>"", IF(A{row+1}="RJ", ({col_s}{row+1}-{col_e}{row+1})-(E{row+1}-L{row+1}), {col_s}{row+1}-{col_e}{row+1}), {col_s}{row+1})'
                        else:
                            f_sal = f'=IF(B{row+1}<>"", {col_s}{row+1}-{col_e}{row+1}, {col_s}{row+1})'
                        ws.write_formula(row, i+16, f_sal, f_num)

                ws.conditional_format('A3:F29', {'type':'formula', 'criteria':'=LEN($B3)>0', 'format':f_pink_light})
                ws.conditional_format('H3:M29', {'type':'formula', 'criteria':'=LEN($I3)>0', 'format':f_pink_light})
                ws.conditional_format('O3:T29', {'type':'formula', 'criteria':'=LEN($P3)>0', 'format':f_pink_light})

            st.success("💎 Apuração Concluída!")
            st.download_button("📥 BAIXAR RELATÓRIO DIAMANTE", output.getvalue(), "Diamond_Tax_Audit.xlsx")
else:
    st.warning("👈 Insira o CNPJ na barra lateral para começar.")
