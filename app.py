import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import re
import io
import zipfile

st.set_page_config(page_title="Auditoria DIFAL ST FECP", layout="wide")

UFS_BRASIL = ['AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS', 'MT', 'PA', 'PB', 'PE', 'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO']

def safe_float(v):
    if v is None: return 0.0
    try:
        return float(str(v).replace(',', '.'))
    except:
        return 0.0

def buscar_tag_recursiva(tag_alvo, no):
    """Busca a tag em qualquer profundidade dentro de um bloco."""
    if no is None: return ""
    for elemento in no.iter():
        tag_nome = elemento.tag.split('}')[-1]
        if tag_nome == tag_alvo:
            return elemento.text if elemento.text else ""
    return ""

def processar_xml(content, cnpj_auditado):
    try:
        # Limpeza de Namespaces para facilitar a leitura
        xml_str = re.sub(r'\sxmlns(:\w+)?="[^"]+"', '', content.decode('utf-8', errors='ignore'))
        root = ET.fromstring(xml_str)
        
        emit = root.find('.//emit')
        dest = root.find('.//dest')
        ide = root.find('.//ide')
        
        cnpj_emit = re.sub(r'\D', '', buscar_tag_recursiva('CNPJ', emit) or "")
        cnpj_alvo = re.sub(r'\D', '', cnpj_auditado)
        
        tipo = "SAIDA" if cnpj_emit == cnpj_alvo else "ENTRADA"
        
        # --- A SACADA: Captura IEST do Emitente/Destinatário ---
        # Conforme o seu XML, a IEST está aqui no nível do grupo principal
        iest_documento = ""
        if tipo == "SAIDA":
            iest_documento = buscar_tag_recursiva('IEST', emit)
        else:
            iest_documento = buscar_tag_recursiva('IEST', dest)
        
        detalhes = []
        for det in root.findall('.//det'):
            icms = det.find('.//ICMS')
            imp = det.find('.//imposto')
            prod = det.find('prod')
            
            # Valores (Somas de FCP solicitadas)
            v_st = safe_float(buscar_tag_recursiva('vICMSST', icms))
            v_fcp_st = safe_float(buscar_tag_recursiva('vFCPST', icms))
            v_difal = safe_float(buscar_tag_recursiva('vICMSUFDest', imp))
            v_fcp_dest = safe_float(buscar_tag_recursiva('vFCPUFDest', imp))

            detalhes.append({
                "TIPO": tipo,
                "UF_EMIT": buscar_tag_recursiva('UF', emit),
                "UF_DEST": buscar_tag_recursiva('UF', dest),
                "CFOP": buscar_tag_recursiva('CFOP', prod),
                "ST_TOTAL": v_st + v_fcp_st,
                "DIFAL_TOTAL": v_difal + v_fcp_dest,
                "FCP_TOTAL": v_fcp_dest,
                "FCP_ST_TOTAL": v_fcp_st,
                "IEST": str(iest_documento).strip() # Replica a IEST da nota para os itens
            })
        return detalhes
    except:
        return []

# --- INTERFACE ---
st.title("🛡️ Sentinela: Gerador de Apuração DIFAL/ST/FECP")
cnpj_empresa = st.sidebar.text_input("CNPJ da Empresa Auditada (apenas números)")
uploaded_files = st.file_uploader("Suba seus XMLs ou ZIP", accept_multiple_files=True)

if uploaded_files and cnpj_empresa:
    dados = []
    for f in uploaded_files:
        if f.name.endswith('.xml'): dados.extend(processar_xml(f.read(), cnpj_empresa))
        elif f.name.endswith('.zip'):
            with zipfile.ZipFile(f) as z:
                for n in z.namelist():
                    if n.lower().endswith('.xml'): dados.extend(processar_xml(z.open(n).read(), cnpj_empresa))
    
    if dados:
        df_base = pd.DataFrame(dados)
        
        def preparar_blocos(df):
            base_uf = pd.DataFrame({'UF': UFS_BRASIL})
            
            # Saídas
            s = df[df['TIPO'] == "SAIDA"].copy()
            res_s = s.groupby('UF_DEST').agg({'ST_TOTAL':'sum', 'DIFAL_TOTAL':'sum', 'FCP_TOTAL':'sum', 'FCP_ST_TOTAL':'sum'}).reset_index().rename(columns={'UF_DEST':'UF'})
            ie_s = s[s['IEST'] != ""].groupby('UF_DEST')['IEST'].first().to_dict()
            res_s['IEST'] = res_s['UF'].map(ie_s).fillna("")
            
            # Entradas
            e = df[df['TIPO'] == "ENTRADA"].copy()
            e['UF_AGRUPAR'] = e.apply(lambda x: x['UF_DEST'] if x['UF_EMIT'] == 'SP' else x['UF_EMIT'], axis=1)
            res_e = e.groupby('UF_AGRUPAR').agg({'ST_TOTAL':'sum', 'DIFAL_TOTAL':'sum', 'FCP_TOTAL':'sum', 'FCP_ST_TOTAL':'sum'}).reset_index().rename(columns={'UF_AGRUPAR':'UF'})
            
            return base_uf.merge(res_s, on='UF', how='left').fillna(0), base_uf.merge(res_e, on='UF', how='left').fillna(0)

        df_s, df_e = preparar_blocos(df_base)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            workbook = writer.book
            ws = workbook.add_worksheet('DIFAL_ST_FECP')
            
            fmt_header = workbook.add_format({'bold':True, 'bg_color':'#D7E4BC', 'border':1, 'align':'center'})
            fmt_title = workbook.add_format({'bold':True, 'bg_color':'#FCD5B4', 'border':1, 'align':'center'})
            fmt_num = workbook.add_format({'num_format':'#,##0.00', 'border':1})
            fmt_uf = workbook.add_format({'border':1, 'align':'center'})
            fmt_orange = workbook.add_format({'bg_color': '#FFDAB9', 'border': 1, 'num_format': '#,##0.00'})

            # Títulos dos Blocos
            ws.merge_range('A1:F1', '1. SAÍDAS', fmt_title)
            ws.merge_range('H1:M1', '2. ENTRADAS', fmt_title)
            ws.merge_range('O1:T1', '3. SALDO', fmt_title)

            headers = ['UF', 'IEST', 'ST TOTAL', 'DIFAL TOTAL', 'FCP TOTAL', 'FCP-ST TOTAL']
            for i, h in enumerate(headers):
                ws.write(1, i, h, fmt_header)
                ws.write(1, i + 7, h, fmt_header)
                ws.write(1, i + 14, h, fmt_header)

            for r, uf in enumerate(UFS_BRASIL):
                row_idx = r + 2
                val_s = df_s[df_s['UF'] == uf].iloc[0]
                val_e = df_e[df_e['UF'] == uf].iloc[0]
                
                # Identifica se pinta de laranja (se tem IE na Saída)
                tem_ie = str(val_s['IEST']).strip() != ""
                fmt_atual = fmt_orange if tem_ie else fmt_num
                fmt_txt = fmt_orange if tem_ie else fmt_uf

                # Dados Saída
                ws.write(row_idx, 0, uf, fmt_txt)
                ws.write(row_idx, 1, str(val_s['IEST']), fmt_txt)
                cols_data = ['ST_TOTAL', 'DIFAL_TOTAL', 'FCP_TOTAL', 'FCP_ST_TOTAL']
                for i, c in enumerate(cols_data): ws.write(row_idx, i + 2, val_s[c], fmt_atual)
                
                # Dados Entrada
                ws.write(row_idx, 7, uf, fmt_uf)
                ws.write(row_idx, 8, "", fmt_uf) # IEST da entrada não impacta o layout da imagem
                for i, c in enumerate(cols_data): ws.write(row_idx, i + 9, val_e[c], fmt_num)

                # SALDO (Cálculo com Regra IEST)
                ws.write(row_idx, 14, uf, fmt_txt)
                ws.write(row_idx, 15, str(val_s['IEST']), fmt_txt)
                for i, c in enumerate(cols_data):
                    v_s = val_s[c]
                    v_e = val_e[c]
                    saldo = (v_s - v_e) if tem_ie else v_s
                    ws.write(row_idx, i + 16, saldo, fmt_atual)

        st.success("✅ Relatório gerado com sucesso!")
        st.download_button("💾 BAIXAR APURAÇÃO CONSOLIDADA", output.getvalue(), "Analise_DIFAL_ST_FECP.xlsx")
