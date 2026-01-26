# Teste para identificar o problema real
from db_lerconfiguracao import ler_configuracao, get_db

db = get_db()
lc = ler_configuracao()


def testar_parametros():
    conn = db.connect(
    host=lc['SERVER'],
    database=lc['DIR_DADOS'],
    user=lc['USUARIO_BD'],
    password=lc['SENHA_BD']
    )
    cursor = conn.cursor()
    
    print("=" * 80)
    print("TESTE DE PARÂMETROS")
    print("=" * 80)
    
    # Teste 1: Apenas VALOR_SAIDA
    print("\n[TESTE 1] Apenas VALOR_SAIDA = 156.64")
    try:
        query = "SELECT * FROM LANC_CONTA_FIN WHERE VALOR_SAIDA = ?"
        cursor.execute(query, (156.64,))
        results = cursor.fetchall()
        print(f"Encontrado {len(results)} registros")
        if len(results) > 0:
            print(f"Primeiro registro: {results[0]}")
    except Exception as e:
        print(f"Erro: {e}")
    
    # Teste 2: VALOR_SAIDA + COD_CONTA
    print("\n[TESTE 2] VALOR_SAIDA = 156.64 AND COD_CONTA_FINANCEIRA = 25")
    try:
        query = "SELECT * FROM LANC_CONTA_FIN WHERE VALOR_SAIDA = ? AND COD_CONTA_FINANCEIRA = ?"
        cursor.execute(query, (156.64, 25))
        results = cursor.fetchall()
        print(f"Encontrado {len(results)} registros")
        if len(results) > 0:
            print(f"Primeiro registro: {results[0]}")
    except Exception as e:
        print(f"Erro: {e}")
    
    # Teste 3: Ver estrutura da tabela
    print("\n[TESTE 3] Listando colunas da tabela LANC_CONTA_FIN")
    try:
        cursor.execute("SELECT FIRST 1 * FROM LANC_CONTA_FIN")
        result = cursor.fetchone()
        if result:
            print(f"Número de colunas: {len(result)}")
            print(f"Descrição cursor: {cursor.description}")
    except Exception as e:
        print(f"Erro: {e}")
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    testar_parametros()
