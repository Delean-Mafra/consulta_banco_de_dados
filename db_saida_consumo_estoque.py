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

saida_consumo = input('Digite o codigo da saida para consumo: ')
c = conn.cursor()

# Definindo a consulta de atualização
update_query = f"""
--sql
UPDATE SAIDA_CONSUMO_ITEM SCI
SET SCI.QUANTIDADE = (
    SELECT A.SALDO_ATUAL
    FROM ALMMATERIAL A
    WHERE A.COD_MATERIAL = SCI.COD_MATERIAL
)
WHERE SCI.COD_SAIDA_CONSUMO = {saida_consumo};
"""

# Executando a consulta de atualização
c.execute(update_query)

# Confirmando as alterações
conn.commit()

print("Atualização concluída com sucesso!")
