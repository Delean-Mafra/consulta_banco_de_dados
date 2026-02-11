from flask import Flask, render_template, request, jsonify
from datetime import  date
from decimal import Decimal
import re
import os
from db_lerconfiguracao import ler_configuracao as LC, get_db as gdb, datetime



db = gdb()
lc = LC()
def conectar_bd():
    conn = db.connect(
        host=lc['SERVER'],
        database=lc['DIR_DADOS'],
        user=lc['USUARIO_BD'],
        password=lc['SENHA_BD']
    )
    return conn, conn.cursor()

app = Flask(__name__)

def parse_ofx_date(date_str):

    # Extrai apenas os primeiros 8 dígitos (AAAAMMDD)
    date_match = re.match(r'(\d{8})', date_str)
    if date_match:
        date_digits = date_match.group(1)
        year = date_digits[0:4]
        month = date_digits[4:6]
        day = date_digits[6:8]
        return {
            'display': f"{day}/{month}/{year}",  # Para mostrar na tela (dd/mm/aaaa)
            'sql': f"{year}-{month}-{day}"        # Para usar no SQL (aaaa-mm-dd)
        }
    return None

def parse_ofx_file(file_path):

    transactions = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Encontrar todas as transações <STMTTRN>...</STMTTRN>
    stmttrn_pattern = r'<STMTTRN>(.*?)</STMTTRN>'
    matches = re.findall(stmttrn_pattern, content, re.DOTALL)
    
    for match in matches:
        transaction = {}
        
        # Extrair TRNTYPE
        trntype_match = re.search(r'<TRNTYPE>(.*?)</TRNTYPE>', match)
        if trntype_match:
            transaction['trntype'] = trntype_match.group(1).strip()
        
        # Extrair DTPOSTED
        dtposted_match = re.search(r'<DTPOSTED>(.*?)</DTPOSTED>', match)
        if dtposted_match:
            transaction['dtposted'] = dtposted_match.group(1).strip()
            date_obj = parse_ofx_date(transaction['dtposted'])
            if date_obj:
                transaction['data_formatada'] = date_obj['display']  # Para exibição
                transaction['data_sql'] = date_obj['sql']             # Para consulta SQL
        
        # Extrair TRNAMT
        trnamt_match = re.search(r'<TRNAMT>(.*?)</TRNAMT>', match)
        if trnamt_match:
            transaction['trnamt'] = float(trnamt_match.group(1).strip())
        
        # Extrair FITID
        fitid_match = re.search(r'<FITID>(.*?)</FITID>', match)
        if fitid_match:
            transaction['fitid'] = fitid_match.group(1).strip()
        
        # Extrair NAME
        name_match = re.search(r'<NAME>(.*?)</NAME>', match)
        if name_match:
            transaction['name'] = name_match.group(1).strip()
        
        # Extrair MEMO
        memo_match = re.search(r'<MEMO>(.*?)</MEMO>', match)
        if memo_match:
            transaction['memo'] = memo_match.group(1).strip()
        
        # Ignorar entradas de "Saldo do dia" e "Saldo Anterior"
        if transaction.get('name') not in ['Saldo do dia', 'Saldo Anterior'] and transaction.get('trnamt', 0) != 0:
            transactions.append(transaction)
    
    return transactions


def buscar_lancamento_bd(valor, data_sql, cod_conta=25):

    conn, cursor = conectar_bd()
    
    try:
        # Converter data string para objeto date
        ano, mes, dia = map(int, data_sql.split('-'))
        data_obj = date(ano, mes, dia)
        
        if valor < 0:
            # Débito - buscar em VALOR_SAIDA
            # Converter para Decimal para compatibilidade com Banco de dados
            valor_decimal = Decimal(str(abs(valor)))
            
            query = """
                SELECT '-' || CAST(LCF.VALOR_LANCAMENTO_CONTA AS VARCHAR(30)) AS VALOR, 
                       LCF.DATA_DISPONIVEL,
                       LCF.DATA_EFETIVACAO,
                       LCF.VALOR_SAIDA
                FROM LANC_CONTA_FIN LCF
                WHERE LCF.VALOR_SAIDA = ?
                AND LCF.REG_ESTORNO IS NULL
                AND LCF.LANCAMENTO_ESTORNADO = 'F'
                AND LCF.COD_CONTA_FINANCEIRA = ?
                AND (LCF.DATA_DISPONIVEL = ? OR CAST(LCF.DATA_EFETIVACAO AS DATE) = ?)
            """
            
            print(f"[DEBUG] Buscando DÉBITO: valor={valor_decimal}, data={data_obj}, conta={cod_conta}")
            cursor.execute(query, (valor_decimal, cod_conta, data_obj, data_obj))
            
        else:
            # Crédito - buscar em VALOR_ENTRADA
            valor_decimal = Decimal(str(valor))
            
            query = """
                SELECT CAST(LCF.VALOR_LANCAMENTO_CONTA AS VARCHAR(30)) AS VALOR, 
                       LCF.DATA_DISPONIVEL,
                       LCF.DATA_EFETIVACAO,
                       LCF.VALOR_ENTRADA
                FROM LANC_CONTA_FIN LCF
                WHERE LCF.VALOR_ENTRADA = ?
                AND LCF.REG_ESTORNO IS NULL
                AND LCF.LANCAMENTO_ESTORNADO = 'F'
                AND LCF.COD_CONTA_FINANCEIRA = ?
                AND (LCF.DATA_DISPONIVEL = ? OR CAST(LCF.DATA_EFETIVACAO AS DATE) = ?)
            """
            
            print(f"[DEBUG] Buscando CRÉDITO: valor={valor_decimal}, data={data_obj}, conta={cod_conta}")
            cursor.execute(query, (valor_decimal, cod_conta, data_obj, data_obj))
        
        result = cursor.fetchone()
        
        if result:
            print(f"[DEBUG] ✓ Registro encontrado: {result}")
            return {'encontrado': True, 'detalhes': result}
        else:
            print(f"[DEBUG] ✗ Registro NÃO encontrado")
            return {'encontrado': False, 'detalhes': None}
    
    except Exception as e:
        print(f"[ERRO] Erro ao buscar no BD: {str(e)}")
        print(f"[ERRO] Valor: {valor}, Data: {data_sql}, Conta: {cod_conta}")
        import traceback
        traceback.print_exc()
        return {'encontrado': False, 'detalhes': None, 'erro': str(e)}
    
    finally:
        cursor.close()
        conn.close()


def conciliar_ofx(file_path, cod_conta=25):

    print(f"\n{'='*80}")
    print(f"INICIANDO CONCILIAÇÃO")
    print(f"Arquivo: {file_path}")
    print(f"Conta: {cod_conta}")
    print(f"{'='*80}\n")
    
    transactions = parse_ofx_file(file_path)
    print(f"Total de transações no OFX: {len(transactions)}\n")
    
    encontradas = []
    nao_encontradas = []
    
    for i, trans in enumerate(transactions, 1):
        valor = trans.get('trnamt', 0)
        data_formatada = trans.get('data_formatada')  # Para exibição
        data_sql = trans.get('data_sql')               # Para consulta
        
        print(f"\n[{i}/{len(transactions)}] Processando: {trans.get('name')} - R$ {valor:.2f} em {data_formatada}")
        
        if data_sql:
            resultado = buscar_lancamento_bd(valor, data_sql, cod_conta)
            
            trans['existe_bd'] = resultado['encontrado']
            trans['detalhes_bd'] = resultado.get('detalhes')
            trans['erro_bd'] = resultado.get('erro')
            
            if resultado['encontrado']:
                encontradas.append(trans)
                print(f"    ✓ ENCONTRADO no BD")
            else:
                nao_encontradas.append(trans)
                print(f"    ✗ NÃO ENCONTRADO no BD")
                if 'erro' in resultado:
                    print(f"    ERRO: {resultado['erro']}")
        else:
            nao_encontradas.append(trans)
            print(f"    ✗ Data inválida - não processado")
    
    print(f"\n{'='*80}")
    print(f"CONCILIAÇÃO FINALIZADA")
    print(f"Total OFX: {len(transactions)}")
    print(f"Encontradas: {len(encontradas)}")
    print(f"Não Encontradas: {len(nao_encontradas)}")
    print(f"{'='*80}\n")
    
    return {
        'total_ofx': len(transactions),
        'encontradas': encontradas,
        'nao_encontradas': nao_encontradas,
        'total_encontradas': len(encontradas),
        'total_nao_encontradas': len(nao_encontradas)
    }


@app.route('/')
def index():
    """Página principal"""
    return render_template('conciliacao_ofx.html')


@app.route('/conciliar', methods=['POST'])
def conciliar():
    """Endpoint para realizar a conciliação"""
    try:
        data = request.get_json()
        file_path = data.get('file_path')
        cod_conta = data.get('cod_conta', 25)
        
        if not file_path:
            return jsonify({'error': 'Caminho do arquivo não fornecido'}), 400
        
        if not os.path.exists(file_path):
            return jsonify({'error': f'Arquivo não encontrado: {file_path}'}), 404
        
        resultado = conciliar_ofx(file_path, cod_conta)
        
        return jsonify(resultado)
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000) 


