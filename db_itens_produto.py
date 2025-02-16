from collections import defaultdict
from db_lerconfiguracao import ler_configuracao, get_db
db = get_db()

lc = ler_configuracao()

# Configurações do banco de dados
DIR_DADOS = lc['DIR_DADOS']
USUARIO_BD = lc['USUARIO_BD']
SENHA_BD = lc['SENHA_BD']
SERVER = lc['SERVER']


cod_produto = input('Digite o codigo do item: ')
# Conectar ao banco de dados
try:
    conn = db.connect(
        host=SERVER,
        database=DIR_DADOS,
        user=USUARIO_BD,
        password=SENHA_BD
    )
    c = conn.cursor()

    # Consulta SQL para obter os dados de compra de fraldas
    sql_query = f"""
    --sql
        SELECT C.DTC_COMPRA_ITEM AS "DATA DA COMPRA", C.VALOR_LIQUIDO_ITEM AS "VALOR DA COMPRA"
        FROM COMPRA_ITEM C
        WHERE C.COD_MATERIAL = {cod_produto};
    """
    c.execute(sql_query)

    # Processar os dados
    dados = c.fetchall()
    gastos_por_mes = defaultdict(float)  # Armazena o total gasto por mês

    for linha in dados:
        data_compra = linha[0]  # Data da compra
        valor_compra = float(linha[1])  # Converter para float

        # Extrair mês e ano da data
        mes_ano = data_compra.strftime("%m/%Y")
        gastos_por_mes[mes_ano] += valor_compra

    # Exibir os resultados
    print("Gastos por mês:")
    for mes_ano, total in sorted(gastos_por_mes.items()):
        print(f"{mes_ano}: {total:.2f}")

    # Calcular a média mensal
    total_gasto = sum(gastos_por_mes.values())  # Soma de todos os gastos
    media_mensal = total_gasto / len(gastos_por_mes)  # Média mensal
    print(f"\nMédia mensal de gastos: {media_mensal:.2f}")
    print(f"Gasto total: {total_gasto:.2f}")

except db.DatabaseError as e:
    print("Erro ao conectar ao banco de dados:", e)

finally:
    if 'conn' in locals() and conn:
        conn.close()
