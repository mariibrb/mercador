import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import re
import io
import zipfile

st.set_page_config(page_title="Auditoria DIFAL ST FECP - Sentinela", layout="wide")

UFS_BRASIL = ['AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS', 'MT', 'PA', 'PB', 'PE', 'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO']

CFOP_DEVOLUCAO = [
    '1201', '1202', '1203', '1204', '1410', '1411', '1660', '1661', '1662',
    '2201', '2202', '2203', '2204', '2410', '2411', '2660', '2661', '2662',
    '3201', '3202', '3411'
]

def safe_float(v):
    if v is None: return 0.0
    try:
        return float(str(v).replace(',', '.'))
    except:
        return 0.0

def buscar_tag_recursiva(tag_alvo, no):
    if no is None: return ""
    for elemento in no.iter():
        tag_nome = elemento.tag.split('}')[-1]
        if tag_nome == tag_alvo:
            return elemento.text if elemento.text else ""
    return ""

def processar_xml(content, cnpj_auditado, chaves_processadas, chaves_canceladas):
    try:
        xml_str = re.sub(r'\sxmlns(:\w+)?="[^"]+"', '', content.decode('utf-8', errors='ignore'))
        root = ET.fromstring(xml_str)
        infNFe = root.find('.//infNFe')
        chave = infNFe.attrib.get('Id', '')[3:] if infNFe is not None else ""
        
        if not chave or chave in chaves_processadas or chave in chaves_canceladas:
            return []
        
        chaves_processadas.add(chave)
        emit, dest, ide = root.find('.//emit'), root.find('.//dest'), root.find('.//ide')
        cnpj_emit = re.sub(r'\D', '', buscar_tag_recursiva('CNPJ', emit) or "")
        cnpj_alvo = re.sub(r'\D', '', cnpj_auditado)
        tp_nf = buscar_tag_recursiva('tpNF', ide)

        detalhes = []
        for det in root.findall('.//det'):
            prod = det.find('prod')
            cfop = buscar_tag_recursiva('CFOP', prod)

            if cnpj_emit == cnpj_alvo and tp_nf == "1":
                tipo = "SAIDA"
            elif cfop in CFOP_DEVOLUCAO:
                tipo = "ENTRADA"
            else:
                continue 

            icms, imp = det.find('.//ICMS'), det.find('.//imposto')
            iest_doc = buscar_tag_recursiva('IEST', emit) if tipo == "SAIDA" else buscar_tag_recursiva('IEST', dest)
            uf_fiscal = buscar_tag_recursiva('UF', dest) if tipo == "SAIDA" else (buscar_tag_recursiva('UF', dest) if buscar_tag_recursiva('UF', emit) == 'SP' else buscar_tag_recursiva('UF', emit))
            
            detalhes.append({
                "CHAVE": chave,
                "NUM_NF": buscar_tag_recursiva('nNF', ide),
                "TIPO": tipo,
                "UF_FISCAL": uf_fiscal,
                "IEST_DOC": str(iest_doc).strip(),
                "CFOP": cfop,
                "VPROD": safe_float(buscar_tag_recursiva('vProd', prod)),
                "ST": safe_float(buscar_tag_recursiva('vICMSST', icms)) + safe_float(buscar_tag_recursiva('vFCPST', icms)),
                "DIFAL": safe_float(buscar_tag_recursiva('vICMSUFDest', imp)) + safe_float(buscar_tag_recursiva('vFCPUFDest', imp)),
                "FCP": safe_float(buscar_tag_recursiva('vFCPUFDest', imp)),
                "FCPST": safe_float(buscar_tag_recursiva('vFCPST', icms))
            })
        return detalhes
    except: return []

st.title("🛡️ Sentinela: Auditoria com Regra RJ")

st.sidebar.subheader("1. Lista de Status (SIEG)")
file_status = st.sidebar.file_uploader("Suba o relatório CSV/XLSX da SIEG", type=['csv', 'xlsx'])
cnpj_empresa = st.sidebar.text_input("CNPJ Auditado (apenas números)")
uploaded_files = st.file_uploader("Suba seus XMLs ou ZIP", accept_multiple_files=True)

chaves_canceladas = set()

if file_status:
    try:
        if file_status.name.endswith('.csv'):
            df_status = pd.read_csv(file_status, skiprows=2, sep=',', encoding='utf-8')
        else:
            df_status = pd.read_excel(file_status, skiprows=2)
        col_chave, col_situacao = df_status.columns[10], df_status.columns[14]
        mask_cancel = df_status[col_situacao].astype(str).str.upper().str.contains("CANCEL", na=False)
        canceladas = df_status[mask_cancel]
        chaves_canceladas = set(canceladas[col_chave].astype(str).str.replace('NFe', '').str.strip())
        if len(chaves_canceladas) > 0:
            st.sidebar.warning(f"🚫 {len(chaves_canceladas)} notas canceladas detectadas.")
    except Exception as e:
        st.sidebar.error(f"Erro no arquivo SIEG: {e}")

if uploaded_files and cnpj_empresa:
    dados_totais, chaves_unicas = [], set()
    for f in uploaded_files:
        if f.name.endswith('.xml'):
            dados_totais.extend(processar_xml(f.read(), cnpj_empresa, chaves_unicas, chaves_canceladas))
        elif f.name.endswith('.zip'):
            with zipfile.ZipFile(f) as z:
                for n in z.namelist():
                    if n.lower().endswith('.xml'):
                        dados_totais.extend(processar_xml(z.open(n).read(), cnpj_empresa, chaves_unicas, chaves_canceladas))
    
    if dados_totais:
        df_listagem = pd.DataFrame(dados_totais)
        st.success(f"✅ {len(chaves_unicas)} XMLs processados.")

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_listagem.to_excel(writer, sheet_name='LISTAGEM_XML', index=False)
            ws_l = writer.sheets['LISTAGEM_XML']
            ws_l.set_column('A:A', 50)
            
            workbook, ws = writer.book, writer.book.add_worksheet('DIFAL_ST_FECP')
            fmt_tit = workbook.add_format({'bold':True, 'bg_color':'#FCD5B4', 'border':1, 'align':'center'})
            fmt_head = workbook.add_format({'bold':True, 'bg_color':'#D7E4BC', 'border':1, 'align':'center'})
            fmt_num = workbook.add_format({'num_format':'#,##0.00', 'border':1})
            fmt_uf = workbook.add_format({'border':1, 'align':'center'})
            fmt_orange_uf = workbook.add_format({'bg_color': '#FFDAB9', 'border': 1, 'align':'center'})
            fmt_total = workbook.add_format({'bold':True, 'bg_color':'#F2F2F2', 'border':1, 'num_format':'#,##0.00'})

            ws.merge_range('A1:F1', '1. SAÍDAS', fmt_tit)
            ws.merge_range('H1:M1', '2. ENTRADAS (DEV)', fmt_tit)
            ws.merge_range('O1:T1', '3. SALDO', fmt_tit)

            heads = ['UF', 'IEST', 'ST TOTAL', 'DIFAL TOTAL', 'FCP TOTAL', 'FCPST TOTAL']
            for i, h in enumerate(heads):
                ws.write(1, i, h, fmt_head); ws.write(1, i + 7, h, fmt_head); ws.write(1, i + 14, h, fmt_head)

            for r, uf in enumerate(UFS_BRASIL):
                row = r + 2 
                ws.write(row, 0, uf, fmt_uf)
                ws.write_formula(row, 1, f'=IFERROR(INDEX(LISTAGEM_XML!E:E, MATCH("{uf}", LISTAGEM_XML!D:D, 0)) & "", "")', fmt_uf)
                
                for i, col_let in enumerate(['H', 'I', 'J', 'K']): 
                    ws.write_formula(row, i+2, f'=SUMIFS(LISTAGEM_XML!{col_let}:{col_let}, LISTAGEM_XML!D:D, "{uf}", LISTAGEM_XML!C:C, "SAIDA")', fmt_num)
                    ws.write_formula(row, i+9, f'=SUMIFS(LISTAGEM_XML!{col_let}:{col_let}, LISTAGEM_XML!D:D, "{uf}", LISTAGEM_XML!C:C, "ENTRADA")', fmt_num)
                    
                    col_s, col_e = chr(65 + i + 2), chr(65 + i + 9)
                    
                    # --- AJUSTE FINO RJ (Coluna R é a i=1 no loop de Saldo) ---
                    if i == 1: # Coluna DIFAL
                        # Se UF for RJ, faz (Saída - Entrada - FCP Saída). Se não, (Saída - Entrada)
                        # Onde S_DIFAL é col_s, E_DIFAL é col_e, S_FCP é a coluna J da listagem (col_s do loop i=2)
                        # No resumo: DIFAL_TOTAL_S é col_s, FCP_TOTAL_S é Coluna E do resumo (índice 4)
                        formula_saldo = f'=IF(B{row+1}<>"", IF(A{row+1}="RJ", {col_s}{row+1}-{col_e}{row+1}-E{row+1}, {col_s}{row+1}-{col_e}{row+1}), {col_s}{row+1})'
                    else:
                        formula_saldo = f'=IF(B{row+1}<>"", {col_s}{row+1}-{col_e}{row+1}, {col_s}{row+1})'
                    
                    ws.write_formula(row, i+16, formula_saldo, fmt_num)
                
                ws.write(row, 14, uf, fmt_uf); ws.write_formula(row, 15, f'=B{row+1}', fmt_uf)

            ws.conditional_format(f'A3:F{len(UFS_BRASIL)+2}', {'type':'formula', 'criteria':'=LEN($B3)>0', 'format':fmt_orange_uf})
            ws.conditional_format(f'O3:T{len(UFS_BRASIL)+2}', {'type':'formula', 'criteria':'=LEN($P3)>0', 'format':fmt_orange_uf})

            total_row = len(UFS_BRASIL) + 2
            ws.write(total_row, 0, "TOTAL GERAL", fmt_total)
            for c in [2,3,4,5, 9,10,11,12, 16,17,18,19]:
                col_let = chr(65 + c) if c < 26 else f"A{chr(65 + c - 26)}"
                ws.write_formula(total_row, c, f'=SUM({col_let}3:{col_let}{total_row})', fmt_total)

        st.download_button("💾 BAIXAR AUDITORIA COM REGRA RJ", output.getvalue(), "Auditoria_SIEG_RJ.xlsx")
