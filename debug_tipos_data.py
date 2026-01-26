# Teste mais detalhado para entender o tipo de dados
from db_lerconfiguracao import ler_configuracao, get_db, datetime
from datetime import date

db = get_db()
lc = ler_configuracao()


def testar_tipos_data():
    conn = db.connect(
    host=lc['SERVER'],
    database=lc['DIR_DADOS'],
    user=lc['USUARIO_BD'],
    password=lc['SENHA_BD']
    )
    cursor = conn.cursor()
    
    print("=" * 80)
    print("TESTE DE TIPOS DE DATA")
    print("=" * 80)
    
    valor = 156.64
    cod_conta = 25
    
    # Teste 1: String no formato YYYY-MM-DD
    print("\n[TESTE 1] Usando string '2025-06-02'")
    try:
        query = "SELECT * FROM LANC_CONTA_FIN WHERE VALOR_SAIDA = ? AND COD_CONTA_FINANCEIRA = ? AND DATA_DISPONIVEL = ?"
        cursor.execute(query, (valor, cod_conta, '2025-06-02'))
        result = cursor.fetchone()
        print(f"Resultado: {result}")
    except Exception as e:
        print(f"Erro: {e}")
    
    # Teste 2: Objeto datetime.date
    print("\n[TESTE 2] Usando datetime.date(2025, 6, 2)")
    try:
        query = "SELECT * FROM LANC_CONTA_FIN WHERE VALOR_SAIDA = ? AND COD_CONTA_FINANCEIRA = ? AND DATA_DISPONIVEL = ?"
        cursor.execute(query, (valor, cod_conta, date(2025, 6, 2)))
        result = cursor.fetchone()
        print(f"Resultado: {result}")
    except Exception as e:
        print(f"Erro: {e}")
    
    # Teste 3: Objeto datetime.datetime
    print("\n[TESTE 3] Usando datetime.datetime(2025, 6, 2)")
    try:
        query = "SELECT * FROM LANC_CONTA_FIN WHERE VALOR_SAIDA = ? AND COD_CONTA_FINANCEIRA = ? AND DATA_DISPONIVEL = ?"
        cursor.execute(query, (valor, cod_conta, datetime(2025, 6, 2)))
        result = cursor.fetchone()
        print(f"Resultado: {result}")
    except Exception as e:
        print(f"Erro: {e}")
    
    # Teste 4: Comparação com BETWEEN
    print("\n[TESTE 4] Usando BETWEEN para o mesmo dia")
    try:
        query = """SELECT * FROM LANC_CONTA_FIN 
                   WHERE VALOR_SAIDA = ? 
                   AND COD_CONTA_FINANCEIRA = ? 
                   AND DATA_DISPONIVEL BETWEEN ? AND ?"""
        data_inicio = datetime(2025, 6, 2, 0, 0, 0)
        data_fim = datetime(2025, 6, 2, 23, 59, 59)
        cursor.execute(query, (valor, cod_conta, data_inicio, data_fim))
        result = cursor.fetchone()
        print(f"Resultado: {result}")
    except Exception as e:
        print(f"Erro: {e}")
    
    # Teste 5: Ver o tipo exato do campo DATA_DISPONIVEL
    print("\n[TESTE 5] Verificando tipo e valor real do campo DATA_DISPONIVEL")
    try:
        query = "SELECT DATA_DISPONIVEL, DATA_EFETIVACAO FROM LANC_CONTA_FIN WHERE VALOR_SAIDA = ? AND COD_CONTA_FINANCEIRA = ?"
        cursor.execute(query, (valor, cod_conta))
        result = cursor.fetchone()
        if result:
            print(f"DATA_DISPONIVEL: {result[0]} | Tipo: {type(result[0])}")
            print(f"DATA_EFETIVACAO: {result[1]} | Tipo: {type(result[1])}")
        else:
            print("Nenhum resultado")
    except Exception as e:
        print(f"Erro: {e}")
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    testar_tipos_data()
