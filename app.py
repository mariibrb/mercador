import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import re
import io
import zipfile

# --- CONFIGURAÇÃO VISUAL RIHANNA STYLE ---
st.set_page_config(page_title="Sentinela | Premium Audit", layout="wide", initial_sidebar_state="expanded")

# CSS para customização de luxo
st.markdown("""
    <style>
    /* Fundo e Texto Principal */
    .stApp {
        background-color: #0f0f0f;
        color: #e0e0e0;
    }
    
    /* Sidebar com tom grafite */
    [data-testid="stSidebar"] {
        background-color: #1a1a1a;
        border-right: 1px solid #d4af37;
    }

    /* Títulos em Dourado (Gold Leaf) */
    h1, h2, h3 {
        color: #d4af37 !important;
        font-family: 'Playfair Display', serif;
        text-transform: uppercase;
        letter-spacing: 2px;
    }

    /* Botões Estilo Rihanna (Preto e Dourado) */
    .stButton>button {
        background-color: #d4af37;
        color: black;
        border-radius: 20px;
        border: none;
        font-weight: bold;
        transition: 0.3s;
        width: 100%;
    }
    .stButton>button:hover {
        background-color: #fff;
        transform: scale(1.02);
    }

    /* Estilo para os inputs */
    .stTextInput>div>div>input {
        background-color: #262626;
        color: #d4af37;
        border: 1px solid #404040;
    }
    
    /* Sucesso e Alertas */
    .stSuccess {
        background-color: #1b2e1b;
        color: #9cdb9c;
        border: 1px solid #2e5c2e;
    }
    </style>
    """, unsafe_allow_html=True)

# --- LÓGICA DO SISTEMA (MANTIDA INTEGRALMENTE) ---
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

# --- INTERFACE RIHANNA ---
st.title("💎 SENTINELA | AUDITORIA DE LUXO")

with st.sidebar:
    st.markdown("### ⚜️ PAINEL DE CONTROLE")
    file_status = st.file_uploader("RELATÓRIO SIEG", type=['csv', 'xlsx'])
    cnpj_empresa = st.text_input("CNPJ DA EMPRESA")
    st.markdown("---")

uploaded_files = st.file_uploader("ARQUIVOS XML OU ZIP", accept_multiple_files=True)

chaves_canceladas = set()
if file_status:
    try:
        skip = 0 if file_status.name.endswith('.csv') else 2
        df_status = pd.read_csv(file_status, skiprows=skip, sep=',', encoding='utf-8') if file_status.name.endswith('.csv') else pd.read_excel(file_status, skiprows=2)
        col_ch, col_sit = df_status.columns[10], df_status.columns[14]
        mask = df_status[col_sit].astype(str).str.upper().str.contains("CANCEL", na=False)
        chaves_canceladas = set(df_status[mask][col_ch].astype(str).str.replace('NFe', '').str.strip())
        if chaves_canceladas: st.sidebar.info(f"✨ {len(chaves_canceladas)} Notas canceladas filtradas.")
    except: pass

if uploaded_files and cnpj_empresa:
    dados_totais, chaves_unicas = [], set()
    for f in uploaded_files:
        if f.name.endswith('.xml'): dados_totais.extend(processar_xml(f.read(), cnpj_empresa, chaves_unicas, chaves_canceladas))
        elif f.name.endswith('.zip'):
            with zipfile.ZipFile(f) as z:
                for n in z.namelist():
                    if n.lower().endswith('.xml'): dados_totais.extend(processar_xml(z.open(n).read(), cnpj_empresa, chaves_unicas, chaves_canceladas))
    
    if dados_totais:
        df_base = pd.DataFrame(dados_totais)
        st.success("💎 AUDITORIA CONCLUÍDA COM SUCESSO")

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_base.to_excel(writer, sheet_name='LISTAGEM_XML', index=False)
            workbook, ws = writer.book, writer.book.add_worksheet('DIFAL_ST_FECP')
            
            # FORMATOS EXCEL (MANTIDOS PARA CLAREZA)
            f_tit = workbook.add_format({'bold':True, 'bg_color':'#000000', 'font_color':'#d4af37', 'border':1, 'align':'center'})
            f_head = workbook.add_format({'bold':True, 'bg_color':'#1a1a1a', 'font_color':'#ffffff', 'border':1, 'align':'center'})
            f_num = workbook.add_format({'num_format':'#,##0.00', 'border':1})
            f_orange = workbook.add_format({'bg_color': '#FFDAB9', 'border': 1, 'align':'center'})

            ws.merge_range('A1:F1', '1. SAÍDAS', f_tit)
            ws.merge_range('H1:M1', '2. ENTRADAS (DEV)', f_tit)
            ws.merge_range('O1:T1', '3. SALDO', f_tit)

            heads = ['UF', 'IEST', 'ST TOTAL', 'DIFAL TOTAL', 'FCP TOTAL', 'FCPST TOTAL']
            for i, h in enumerate(heads):
                ws.write(1, i, h, f_head); ws.write(1, i + 7, h, f_head); ws.write(1, i + 14, h, f_head)

            for r, uf in enumerate(UFS_BRASIL):
                row = r + 2 
                ws.write(row, 0, uf); ws.write_formula(row, 1, f'=IFERROR(INDEX(LISTAGEM_XML!E:E, MATCH("{uf}", LISTAGEM_XML!D:D, 0)) & "", "")')
                for i, col_let in enumerate(['H', 'I', 'J', 'K']): 
                    ws.write_formula(row, i+2, f'=SUMIFS(LISTAGEM_XML!{col_let}:{col_let}, LISTAGEM_XML!D:D, "{uf}", LISTAGEM_XML!C:C, "SAIDA")', f_num)
                    ws.write_formula(row, i+9, f'=SUMIFS(LISTAGEM_XML!{col_let}:{col_let}, LISTAGEM_XML!D:D, "{uf}", LISTAGEM_XML!C:C, "ENTRADA")', f_num)
                    col_s, col_e = chr(65 + i + 2), chr(65 + i + 9)
                    if i == 1: # REGRA RJ NO SALDO DIFAL
                        f_sal = f'=IF(B{row+1}<>"", IF(A{row+1}="RJ", ({col_s}{row+1}-{col_e}{row+1})-(E{row+1}-L{row+1}), {col_s}{row+1}-{col_e}{row+1}), IF(A{row+1}="RJ", {col_s}{row+1}-E{row+1}, {col_s}{row+1}))'
                    else:
                        f_sal = f'=IF(B{row+1}<>"", {col_s}{row+1}-{col_e}{row+1}, {col_s}{row+1})'
                    ws.write_formula(row, i+16, f_sal, f_num)
                ws.write(row, 14, uf); ws.write_formula(row, 15, f'=B{row+1}')

            ws.conditional_format(f'A3:F29', {'type':'formula', 'criteria':'=LEN($B3)>0', 'format':f_orange})
            ws.conditional_format(f'O3:T29', {'type':'formula', 'criteria':'=LEN($P3)>0', 'format':f_orange})

        st.download_button("👑 BAIXAR AUDITORIA DIAMOND", output.getvalue(), "Auditoria_Sentinela_Premium.xlsx")
