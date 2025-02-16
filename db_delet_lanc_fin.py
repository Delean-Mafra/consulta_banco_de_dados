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

# Selecionar todos os COD_FIN dos registros que atendem aos critérios
query_select = """
--sql
SELECT COD_FIN
FROM LANC_FINANCEIRO 
WHERE TIPO_LANC_FIN = 'R'
  AND ATV_LANC_FINANCEIRO = 'F'
  AND (COD_EMPRESA_FIN IS NULL OR COD_EMPRESA_FIN = 1)
  AND COD_LANC_FINANCEIRO_AUTO = 6
ORDER BY COD_FIN;
"""

cur.execute(query_select)
cod_fin_list = cur.fetchall()

# Tentar deletar cada registro individualmente
errored_cod_fin = []

for cod_fin in cod_fin_list:
    try:
        query_delete = f"""
        --sql
        DELETE FROM LANC_FINANCEIRO WHERE COD_FIN = {cod_fin[0]};
        """
        cur.execute(query_delete)
    except db.fbcore.DatabaseError as e:
        print(f"Erro ao deletar COD_FIN = {cod_fin[0]}: {e}")
        errored_cod_fin.append(cod_fin[0])

conn.commit()

print("Deleções concluídas com exceções para os seguintes COD_FIN:", errored_cod_fin)

# Fechar conexão
cur.close()
conn.close()
