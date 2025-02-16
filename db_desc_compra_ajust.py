from db_lerconfiguracao import ler_configuracao, get_db
db = get_db()

lc = ler_configuracao()

# Configurações do banco de dados
DIR_DADOS = lc['DIR_DADOS']
USUARIO_BD = lc['USUARIO_BD']
SENHA_BD = lc['SENHA_BD']
SERVER = lc['SERVER']


# Conectar ao banco de dados
conn = db.connect(
    host=SERVER,
    database=DIR_DADOS,
    user=USUARIO_BD,
    password=SENHA_BD
)

# Cursor para executar as queries
cur = conn.cursor()

# Parte 1: Identificar as compras com discrepância
cur.execute("""
--sql
SELECT 
    C.COD_COMPRA,
    C.VALOR_DESCONTO_TOTAL,
    SUM(CI.VALOR_DESCONTO_ITEM) AS SOMA_DESCONTO_ITENS,
    COUNT(*) AS QUANTIDADE_ITENS
FROM COMPRA C
JOIN COMPRA_ITEM CI ON C.COD_COMPRA = CI.COD_COMPRA
WHERE C.COD_NATUREZA_OPER IN (34, 36, 39, 40, 41, 42)
GROUP BY C.COD_COMPRA, C.VALOR_DESCONTO_TOTAL
HAVING ABS(C.VALOR_DESCONTO_TOTAL - SUM(CI.VALOR_DESCONTO_ITEM)) > 0.00;
""")

compras_com_discrepancia = cur.fetchall()

# Parte 2: Atualizar os valores de desconto dos itens
for compra in compras_com_discrepancia:
    cod_compra = compra[0]
    valor_desconto_total = compra[1]
    quantidade_itens = compra[3]
    desconto_por_item = valor_desconto_total / quantidade_itens

    cur.execute("""
    --sql
    UPDATE COMPRA_ITEM
    SET VALOR_DESCONTO_ITEM = ?
    WHERE COD_COMPRA = ?;
    """, (desconto_por_item, cod_compra)) 

# Commit the transaction
conn.commit()

# Fechar a conexão
cur.close()
conn.close()

print("Atualização concluída com sucesso.")
