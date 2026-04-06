import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import re
import io
import zipfile
import random

# --- CONFIGURAÇÃO E ESTILO (DESIGN UNIFICADO E TRAVADO) ---
st.set_page_config(page_title="MERCADOR", layout="wide", page_icon="🗺️")

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
CUF_PARA_UF = {
    '11': 'RO', '12': 'AC', '13': 'AM', '14': 'RR', '15': 'AP', '16': 'TO', '17': 'PA',
    '21': 'MA', '22': 'PI', '23': 'CE', '24': 'RN', '25': 'PB', '26': 'PE', '27': 'AL', '28': 'SE', '29': 'BA',
    '31': 'MG', '32': 'ES', '33': 'RJ', '35': 'SP', '41': 'PR', '42': 'SC', '43': 'RS',
    '50': 'MS', '51': 'MT', '52': 'GO', '53': 'DF',
}
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

def _tag_local(elemento):
    if elemento is None: return ""
    return elemento.tag.split('}')[-1]

_NS_NFE = 'http://www.portalfiscal.inf.br/nfe'

def _filho_direto_tag(pai, nome_local):
    if pai is None: return None
    for ch in pai:
        if _tag_local(ch) == nome_local: return ch
    return None

def _listar_dets(root):
    dets = root.findall(f'.//{{{_NS_NFE}}}det')
    if dets: return dets
    return root.findall('.//det')

def _normalizar_cuf(val):
    if not val: return ""
    d = re.sub(r'\D', '', str(val))
    if not d: return ""
    return str(int(d))

def _uf_de_cuf_no_imposto(imp):
    c = buscar_tag_recursiva('cUFDest', imp)
    k = _normalizar_cuf(c)
    return CUF_PARA_UF.get(k, '') if k else ''

def uf_fiscal_por_item(tipo, emit, dest, imp):
    ue = (buscar_tag_recursiva('UF', emit) or '').strip().upper()
    ud = (buscar_tag_recursiva('UF', dest) or '').strip().upper()
    if tipo == 'SAIDA':
        if ud: return ud
        return (_uf_de_cuf_no_imposto(imp) or '').upper()
    if ue == 'SP' and ud: return ud
    if ue: return ue
    u = _uf_de_cuf_no_imposto(imp)
    return (u or ud or '').upper()

def _iest_unicos_ordenados(imp):
    vals = []
    if imp is None: return vals
    for el in imp.iter():
        if _tag_local(el) != 'IEST' or not el.text: continue
        t = el.text.strip()
        if t and t not in vals: vals.append(t)
    return vals

def coletar_iests_imposto(imp, iest_cabecalho):
    vals = _iest_unicos_ordenados(imp)
    if vals: return ' | '.join(vals)
    return (iest_cabecalho or '').strip()

def _grupos_icmsufdest(imp):
    if imp is None: return []
    return [el for el in imp.iter() if _tag_local(el) == 'ICMSUFDest']

def _soma_difal_dentro_icmsufdest(imp):
    t = 0.0
    for g in _grupos_icmsufdest(imp):
        t += safe_float(buscar_tag_recursiva('vICMSUFDest', g))
        t += safe_float(buscar_tag_recursiva('vFCPUFDest', g))
    return t

def alerta_difal_devolucao_iest(imp, tipo, cfop, iest_doc):
    if tipo != "ENTRADA" or cfop not in CFOP_DEVOLUCAO: return ""
    if not str(iest_doc).strip(): return ""
    if imp is None: return "Devolução com IEST: item sem bloco <imposto>"
    grupos = _grupos_icmsufdest(imp)
    soma_grupo = _soma_difal_dentro_icmsufdest(imp)
    soma_global = safe_float(buscar_tag_recursiva('vICMSUFDest', imp)) + safe_float(buscar_tag_recursiva('vFCPUFDest', imp))
    eps = 0.02
    if not grupos:
        if soma_global > eps: return "DIFAL informado fora do grupo ICMSUFDest (tag incorreta)"
        return "Sem grupo ICMSUFDest no XML (DIFAL não destacado na tag oficial)"
    if soma_grupo <= eps and soma_global > eps: return "DIFAL aparece no XML mas não dentro de ICMSUFDest (revisar emissão)"
    if soma_grupo <= eps: return "ICMSUFDest presente porém vICMSUFDest/vFCPUFDest zerados"
    if abs(soma_grupo - soma_global) > eps: return "Valores de DIFAL divergem entre ICMSUFDest e outras tags do item"
    return ""

def processar_xml(content, cnpj_auditado, chaves_processadas, chaves_canceladas):
    try:
        xml_str = re.sub(r'\sxmlns(:\w+)?="[^"]+"', '', content.decode('utf-8', errors='ignore'))
        root = ET.fromstring(xml_str)
        infNFe = root.find('.//infNFe')
        # Limpeza rigorosa da chave
        chave_raw = infNFe.attrib.get('Id', '')[3:] if infNFe is not None else ""
        chave = re.sub(r'\D', '', chave_raw)
        
        if not chave or chave in chaves_processadas or chave in chaves_canceladas: return []
        chaves_processadas.add(chave)
        
        emit, dest, ide = root.find('.//emit'), root.find('.//dest'), root.find('.//ide')
        cnpj_emit = re.sub(r'\D', '', buscar_tag_recursiva('CNPJ', emit) or "")
        cnpj_alvo = re.sub(r'\D', '', cnpj_auditado)
        tp_nf = buscar_tag_recursiva('tpNF', ide)
        tipo = "SAIDA" if (cnpj_emit == cnpj_alvo and tp_nf == "1") else "ENTRADA"
        
        if tipo == "SAIDA":
            iest_cabecalho = (buscar_tag_recursiva("IEST", emit) or buscar_tag_recursiva("IEST", dest) or "").strip()
        else:
            iest_cabecalho = (buscar_tag_recursiva("IEST", dest) or buscar_tag_recursiva("IEST", emit) or "").strip()
            
        detalhes = []
        for det in _listar_dets(root):
            prod = _filho_direto_tag(det, 'prod')
            imp = _filho_direto_tag(det, 'imposto')
            icms = _filho_direto_tag(imp, 'ICMS') if imp is not None else None
            if icms is None and imp is not None:
                for el in imp.iter():
                    if _tag_local(el) == 'ICMS':
                        icms = el
                        break
            cfop = buscar_tag_recursiva('CFOP', prod)
            if tipo == "ENTRADA" and cfop not in CFOP_DEVOLUCAO: continue
            uf_fiscal = uf_fiscal_por_item(tipo, emit, dest, imp)
            iest_doc = coletar_iests_imposto(imp, iest_cabecalho)
            difal_val = safe_float(buscar_tag_recursiva('vICMSUFDest', imp)) + safe_float(buscar_tag_recursiva('vFCPUFDest', imp))
            
            detalhes.append({
                "CHAVE": chave, "NUM_NF": buscar_tag_recursiva('nNF', ide), "TIPO": tipo, "UF_FISCAL": uf_fiscal, "IEST_DOC": str(iest_doc).strip(), "CFOP": cfop,
                "ST": safe_float(buscar_tag_recursiva('vICMSST', icms)) + safe_float(buscar_tag_recursiva('vFCPST', icms)),
                "DIFAL": difal_val,
                "FCP": safe_float(buscar_tag_recursiva('vFCPUFDest', imp)), "FCPST": safe_float(buscar_tag_recursiva('vFCPST', icms)),
                "ALERTA_DIFAL": alerta_difal_devolucao_iest(imp, tipo, cfop, iest_doc),
            })
        return detalhes
    except: return []

# --- INTERFACE ---
st.markdown("<h1>🗺️ MERCADOR</h1>", unsafe_allow_html=True)

with st.container():
    m_col1, m_col2 = st.columns(2)
    with m_col1:
        st.markdown("""
        <div class="instrucoes-card">
            <h3>📖 Passo a Passo</h3>
            <ol>
                <li><b>Relatório SIEG:</b> Suba os arquivos CSV ou XLSX de Status para filtrar notas canceladas.</li>
                <li><b>Arquivos XML:</b> Arraste seus arquivos XML ou pastas ZIP.</li>
                <li><b>Processamento:</b> Clique no botão <b>"INICIAR APURAÇÃO DIAMANTE"</b>.</li>
                <li><b>Download:</b> Baixe o Excel final com os saldos apurados.</li>
            </ol>
        </div>
        """, unsafe_allow_html=True)
    with m_col2:
        st.markdown("""
        <div class="instrucoes-card">
            <h3>📊 O que será obtido?</h3>
            <ul>
                <li><b>Cálculo DIFAL/ST/FCP:</b> Apuração automática por UF.</li>
                <li><b>Regra RJ:</b> Abatimento automático de FCP no DIFAL.</li>
                <li><b>Relatório Inteligente:</b> Excel formatado com destaque Rosa nas IESTs.</li>
                <li><b>Aba CANCELADAS_SIEG:</b> Registro detalhado de todas as notas descartadas.</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

st.markdown("---")

if 'confirmado' not in st.session_state: st.session_state['confirmado'] = False

with st.sidebar:
    st.markdown("### 🔍 Configuração")
    cnpj_input = st.text_input("CNPJ DO CLIENTE", placeholder="00.000.000/0001-00")
    cnpj_limpo = "".join(filter(str.isdigit, cnpj_input))
    if cnpj_input and len(cnpj_limpo) != 14: st.error("⚠️ CNPJ inválido.")
    if len(cnpj_limpo) == 14:
        if st.button("✅ LIBERAR OPERAÇÃO"): st.session_state['confirmado'] = True
    st.divider()
    if st.button("🗑️ RESETAR SISTEMA"):
        st.session_state.clear()
        st.rerun()

if st.session_state['confirmado']:
    st.info(f"🏢 Empresa: {cnpj_limpo}")
    files_status = st.file_uploader("1. Relatórios de STATUS (SIEG)", type=['csv', 'xlsx'], accept_multiple_files=True)
    uploaded_files = st.file_uploader("2. XMLs ou ZIP:", accept_multiple_files=True)
    
    chaves_canceladas = set()
    linhas_canceladas = []
    mapa_autenticidade = {}

    if files_status:
        for f_status in files_status:
            try:
                df_status = pd.read_excel(f_status, header=1) if f_status.name.endswith('.xlsx') else pd.read_csv(f_status, header=1)
                df_status.columns = [str(c).strip().upper() for c in df_status.columns]
                
                col_status = next((c for c in df_status.columns if 'STATUS' in c), None)
                col_chave = next((c for c in df_status.columns if 'CHAVE' in c), None)

                if col_status and col_chave:
                    s_status, s_chave = df_status[col_status], df_status[col_chave]
                    for idx in df_status.index:
                        k = re.sub(r'\D', '', str(s_chave.loc[idx]))
                        if k:
                            txt_status = str(s_status.loc[idx]).strip()
                            mapa_autenticidade[k] = txt_status
                            
                            if "CANCEL" in txt_status.upper() or "REJEI" in txt_status.upper():
                                chaves_canceladas.add(k)
                                linhas_canceladas.append({
                                    'CHAVE': k, 
                                    'ARQUIVO': f_status.name, 
                                    'STATUS_SIEG': txt_status
                                })
                else:
                    st.warning(f"⚠️ Colunas não identificadas no arquivo {f_status.name}.")
            except Exception as e: st.error(f"Erro no SIEG: {e}")
            
        if chaves_canceladas:
            st.success(f"✅ {len(chaves_canceladas)} notas (Canceladas/Rejeitadas) identificadas para exclusão.")

    if uploaded_files and st.button("🚀 INICIAR APURAÇÃO DIAMANTE"):
        dados_totais, chaves_unicas = [], set()
        with st.status("💎 Analisando...", expanded=True):
            for f in uploaded_files:
                f_bytes = f.read()
                if f.name.endswith('.xml'):
                    res = processar_xml(f_bytes, cnpj_limpo, chaves_unicas, chaves_canceladas)
                    dados_totais.extend(res)
                elif f.name.endswith('.zip'):
                    with zipfile.ZipFile(io.BytesIO(f_bytes)) as z_in:
                        for n in z_in.namelist():
                            if n.lower().endswith('.xml'):
                                res = processar_xml(z_in.read(n), cnpj_limpo, chaves_unicas, chaves_canceladas)
                                dados_totais.extend(res)
        
        if dados_totais:
            output = io.BytesIO()
            df_listagem = pd.DataFrame(dados_totais)
            
            # Preenchimento garantido da coluna de Status de Autenticidade
            df_listagem['STATUS_AUTENTICIDADE'] = df_listagem['CHAVE'].map(lambda x: mapa_autenticidade.get(str(x), 'AUTORIZADA'))
            
            ufs_resumo = sorted({u for u in df_listagem['UF_FISCAL'] if u})
            iest_por_uf = {}
            for ufk, g in df_listagem.groupby('UF_FISCAL'):
                iests = g['IEST_DOC'].replace('', None).dropna().unique()
                iest_por_uf[ufk] = ' | '.join([str(i) for i in iests])

            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df_listagem.to_excel(writer, sheet_name='LISTAGEM_XML', index=False)
                
                # Aba de Canceladas preenchida rigorosamente
                df_cancel_final = pd.DataFrame(linhas_canceladas)
                if df_cancel_final.empty:
                    df_cancel_final = pd.DataFrame(columns=['CHAVE', 'ARQUIVO', 'STATUS_SIEG'])
                df_cancel_final.to_excel(writer, sheet_name='CANCELADAS_SIEG', index=False)
                
                workbook = writer.book
                ws = workbook.add_worksheet('DIFAL_ST_FECP')
                ws.hide_gridlines(2)
                f_tit = workbook.add_format({'bold':True, 'bg_color':'#FF69B4', 'font_color':'#FFFFFF', 'border':1, 'align':'center'})
                f_head = workbook.add_format({'bold':True, 'bg_color':'#F8F9FA', 'border':1, 'align':'center'})
                f_num = workbook.add_format({'num_format':'#,##0.00', 'border':1})
                f_uf = workbook.add_format({'border':1, 'align':'center'})
                f_pink = workbook.add_format({'bg_color': COR_ROSA_CLARINHO, 'border': 1})

                ws.merge_range('A1:F1', '1. SAÍDAS', f_tit)
                ws.merge_range('H1:M1', '2. ENTRADAS (DEV)', f_tit)
                ws.merge_range('O1:T1', '3. SALDO', f_tit)

                heads = ['UF', 'IEST', 'ST TOTAL', 'DIFAL TOTAL', 'FCP TOTAL', 'FCPST TOTAL']
                for i, h in enumerate(heads):
                    ws.write(1, i, h, f_head); ws.write(1, i + 7, h, f_head); ws.write(1, i + 14, h, f_head)

                for r, uf in enumerate(ufs_resumo):
                    row = r + 2
                    ws.write(row, 0, uf, f_uf); ws.write(row, 7, uf, f_uf); ws.write(row, 14, uf, f_uf)
                    ws.write_string(row, 1, iest_por_uf.get(uf, ''), f_uf)
                    ws.write_formula(row, 8, f'=B{row+1}', f_uf); ws.write_formula(row, 15, f'=B{row+1}', f_uf)

                    for i, col_let in enumerate(['G', 'H', 'I', 'J']):
                        ws.write_formula(row, i+2, f'=SUMIFS(LISTAGEM_XML!{col_let}:{col_let}, LISTAGEM_XML!D:D, "{uf}", LISTAGEM_XML!C:C, "SAIDA")', f_num)
                        ws.write_formula(row, i+9, f'=SUMIFS(LISTAGEM_XML!{col_let}:{col_let}, LISTAGEM_XML!D:D, "{uf}", LISTAGEM_XML!C:C, "ENTRADA")', f_num)
                        col_s, col_e = chr(65 + i + 2), chr(65 + i + 9)
                        if i == 1: f_sal = f'=IF(B{row+1}<>"", IF(A{row+1}="RJ", ({col_s}{row+1}-{col_e}{row+1})-(E{row+1}-L{row+1}), {col_s}{row+1}-{col_e}{row+1}), {col_s}{row+1})'
                        else: f_sal = f'=IF(B{row+1}<>"", {col_s}{row+1}-{col_e}{row+1}, {col_s}{row+1})'
                        ws.write_formula(row, i+16, f_sal, f_num)
                
                ws.conditional_format('A3:F100', {'type':'formula', 'criteria':'=LEN($B3)>0', 'format':f_pink})
                ws.conditional_format('O3:T100', {'type':'formula', 'criteria':'=LEN($P3)>0', 'format':f_pink})

            st.success("💎 Apuração Concluída!")
            st.download_button("📥 BAIXAR RELATÓRIO", output.getvalue(), "Mercador.xlsx")
        else:
            st.error("❌ Nenhuma nota válida encontrada para o CNPJ e status informados.")
else: st.warning("👈 Insira o CNPJ.")
