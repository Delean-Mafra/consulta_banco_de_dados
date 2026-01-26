from db_lerconfiguracao import ler_configuracao, get_db
db = get_db()
lc = ler_configuracao()


# Conectar ao banco de dados
try:
    conn = db.connect(
    host=lc['SERVER'],
    database=lc['DIR_DADOS'],
    user=lc['USUARIO_BD'],
    password=lc['SENHA_BD']
    )
    c = conn.cursor()

    c.execute("""  
              --sql
        SELECT C.NFE_CHAVE_ACESSO, G.NOME_FORNECEDOR, C.DATA_COMPRA
        FROM COMPRA C
        LEFT JOIN GERFORNECEDOR G ON C.COD_FORNECEDOR = G.COD_FORNECEDOR
        WHERE C.MODELO_NF = '65'
        AND C.NFE_CHAVE_ACESSO IS NOT NULL
        ORDER BY C.DATA_COMPRA DESC
        ;
    """)

    # Obter todos os resultados
    results = c.fetchall()

    # Formatar os resultados
    formatted_results = []
    for row in results:
        formatted_date = row[2].strftime('%d/%m/%Y')
        formatted_row = f"{row[0]};{row[1]};{formatted_date}"
        formatted_results.append(formatted_row)

    # Exibir os resultados formatados
    for result in formatted_results:
        print(result)

finally:
    c.close()
    conn.close()
