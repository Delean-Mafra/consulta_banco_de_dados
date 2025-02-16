import re
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
c = conn.cursor()

# Lendo o arquivo de texto
with open('holerite.txt', 'r', encoding='utf-8') as file:
    lines = file.readlines()

def get_update_statements(lines, cod_fin):
    updates = []
    for line in lines:
        data = re.split(r'\s+', line.strip())  # divide a linha em campos
        if len(data) > 1 and data[0] == '2':
            if data[1] == 'DESC.MENSALIDADE PLANO' and len(data) >= 5:
                updates.append(f"UPDATE RETENCAO_TITULO SET VALOR_RETIDO = {data[4].replace(',', '.')}, VALOR_BASE = {data[4].replace(',', '.')} WHERE COD_FIN = {cod_fin} AND COD_IMPOSTO = 25")
            elif data[1] == 'INSS' and len(data) >= 5:
                valor_base_lines = [re.split(r'\s+', line.strip())[1] for line in lines if line.startswith('BASE INSS')]
                if valor_base_lines:  # verifica se a lista não está vazia
                    valor_base = valor_base_lines[0].replace(',', '.')
                    updates.append(f"UPDATE RETENCAO_TITULO SET COD_FIN = {cod_fin}, VALOR_RETIDO = {data[4].replace(',', '.')}, VALOR_BASE = {valor_base} WHERE COD_FIN = {cod_fin} AND COD_IMPOSTO = 7")
            elif data[1] == 'IRRF' and len(data) >= 5:
                valor_base_lines = [re.split(r'\s+', line.strip())[1] for line in lines if line.startswith('BASE IRRF')]
                if valor_base_lines:  # verifica se a lista não está vazia
                    valor_base = valor_base_lines[0].replace(',', '.')
                    updates.append(f"UPDATE RETENCAO_TITULO SET VALOR_RETIDO = {data[4].replace(',', '.')}, VALOR_BASE = {valor_base}, COD_IMPOSTO = 4 WHERE COD_FIN = {cod_fin} AND COD_IMPOSTO = 4")
    return updates

# Solicitando o número do título ao usuário
numero_titulo = input("Digite o número do título que deseja atualizar: ")

# Obtendo os statements de update
update_statements = get_update_statements(lines, numero_titulo)

# Executando os updates no banco de dados
for query in update_statements:
    c.execute(f"\n{query}")

# Confirmando as transações
conn.commit()
conn.close()

print("Updates realizados com sucesso!")
