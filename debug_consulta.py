# Script de DEBUG para testar a consulta específica que está falhando
from db_lerconfiguracao import ler_configuracao, get_db

db = get_db()
lc = ler_configuracao()


def testar_consulta():
    """Testa a consulta específica que deveria funcionar"""
    
    print("=" * 80)
    print("TESTE DE CONSULTA - DEBUG")
    print("=" * 80)
    
    # Conectar ao banco
    conn = db.connect(
    host=lc['SERVER'],
    database=lc['DIR_DADOS'],
    user=lc['USUARIO_BD'],
    password=lc['SENHA_BD']
    )
    cursor = conn.cursor()
    
    # Teste 1: Consulta básica COM CAST
    print("\n[TESTE 1] Consultando com CAST(DATE) - formato YYYY-MM-DD")
    print("-" * 80)
    
    query1 = """
        SELECT '-' || CAST(LCF.VALOR_LANCAMENTO_CONTA AS VARCHAR(30)) AS VALOR, 
               LCF.DATA_DISPONIVEL,
               LCF.DATA_EFETIVACAO,
               LCF.VALOR_SAIDA,
               LCF.COD_CONTA_FINANCEIRA
        FROM LANC_CONTA_FIN LCF
        WHERE LCF.VALOR_SAIDA = ?
        AND LCF.COD_CONTA_FINANCEIRA = ?
        AND CAST(LCF.DATA_DISPONIVEL AS DATE) = ?
    """
    
    valor = 156.64
    cod_conta = 25
    data_sql = '2025-06-02'  # Formato ISO: YYYY-MM-DD
    
    print(f"Parâmetros: valor={valor}, conta={cod_conta}, data={data_sql}")
    
    try:
        cursor.execute(query1, (valor, cod_conta, data_sql))
        result = cursor.fetchone()
        
        if result:
            print(f"✓ RESULTADO ENCONTRADO:")
            print(f"  Valor: {result[0]}")
            print(f"  Data Disponível: {result[1]}")
            print(f"  Data Efetivação: {result[2]}")
            print(f"  Valor Saída: {result[3]}")
            print(f"  Conta: {result[4]}")
        else:
            print("✗ NENHUM RESULTADO ENCONTRADO")
    except Exception as e:
        print(f"✗ ERRO: {str(e)}")
    
    # Teste 2: Consulta com OR (DATA_DISPONIVEL ou DATA_EFETIVACAO) COM CAST
    print("\n[TESTE 2] Consultando com OR e CAST (DATA_DISPONIVEL OU DATA_EFETIVACAO)")
    print("-" * 80)
    
    query2 = """
        SELECT '-' || CAST(LCF.VALOR_LANCAMENTO_CONTA AS VARCHAR(30)) AS VALOR, 
               LCF.DATA_DISPONIVEL,
               LCF.DATA_EFETIVACAO,
               LCF.VALOR_SAIDA,
               LCF.COD_CONTA_FINANCEIRA
        FROM LANC_CONTA_FIN LCF
        WHERE LCF.VALOR_SAIDA = ?
        AND LCF.COD_CONTA_FINANCEIRA = ?
        AND (CAST(LCF.DATA_DISPONIVEL AS DATE) = ? OR CAST(LCF.DATA_EFETIVACAO AS DATE) = ?)
    """
    
    print(f"Parâmetros: valor={valor}, conta={cod_conta}, data={data_sql}, data={data_sql}")
    
    try:
        cursor.execute(query2, (valor, cod_conta, data_sql, data_sql))
        result = cursor.fetchone()
        
        if result:
            print(f"✓ RESULTADO ENCONTRADO:")
            print(f"  Valor: {result[0]}")
            print(f"  Data Disponível: {result[1]}")
            print(f"  Data Efetivação: {result[2]}")
            print(f"  Valor Saída: {result[3]}")
            print(f"  Conta: {result[4]}")
        else:
            print("✗ NENHUM RESULTADO ENCONTRADO")
    except Exception as e:
        print(f"✗ ERRO: {str(e)}")
    
    # Teste 3: Verificar tipo de dados retornados
    print("\n[TESTE 3] Verificando tipo de cursor.fetchone()")
    print("-" * 80)
    
    try:
        cursor.execute(query2, (valor, cod_conta, data_sql, data_sql))
        result = cursor.fetchone()
        
        print(f"Tipo do resultado: {type(result)}")
        print(f"Resultado: {result}")
        print(f"Bool do resultado: {bool(result)}")
        print(f"result is not None: {result is not None}")
        
        if result:
            print("✓ O resultado é TRUTHY (será interpretado como encontrado)")
        else:
            print("✗ O resultado é FALSY (será interpretado como não encontrado)")
            
    except Exception as e:
        print(f"✗ ERRO: {str(e)}")
    
    # Teste 4: Listar todos os lançamentos próximos
    print("\n[TESTE 4] Listando lançamentos próximos da data para conferência")
    print("-" * 80)
    
    query4 = """
        SELECT LCF.VALOR_SAIDA,
               LCF.VALOR_ENTRADA,
               LCF.DATA_DISPONIVEL,
               LCF.DATA_EFETIVACAO,
               LCF.VALOR_LANCAMENTO_CONTA
        FROM LANC_CONTA_FIN LCF
        WHERE LCF.COD_CONTA_FINANCEIRA = 25
        AND (LCF.DATA_DISPONIVEL BETWEEN '01.06.2025' AND '05.06.2025'
             OR LCF.DATA_EFETIVACAO BETWEEN '01.06.2025' AND '05.06.2025')
        ORDER BY LCF.DATA_DISPONIVEL
    """
    
    try:
        cursor.execute(query4)
        results = cursor.fetchall()
        
        print(f"Encontrados {len(results)} lançamentos entre 01.06.2025 e 05.06.2025:")
        for r in results:
            print(f"  Saída: {r[0]}, Entrada: {r[1]}, Disp: {r[2]}, Efet: {r[3]}, Lanc: {r[4]}")
    except Exception as e:
        print(f"✗ ERRO: {str(e)}")
    
    # Teste 5: Verificar informações do driver
    print("\n[TESTE 5] Informações do driver de banco de dados")
    print("-" * 80)
    print(f"Tipo do DB: {type(db)}")
    print(f"Nome do módulo: {db.__module__ if hasattr(db, '__module__') else 'N/A'}")
    print(f"Tipo da conexão: {type(conn)}")
    print(f"Tipo do cursor: {type(cursor)}")
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 80)
    print("TESTE FINALIZADO")
    print("=" * 80)


if __name__ == "__main__":
    testar_consulta()
