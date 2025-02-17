import pandas as pd
from db_lerconfiguracao import ler_configuracao, get_db
db = get_db()

lc = ler_configuracao()

# Configurações do banco de dados
DIR_DADOS = lc['DIR_DADOS']
USUARIO_BD = lc['USUARIO_BD']
SENHA_BD = lc['SENHA_BD']
SERVER = lc['SERVER']


# Conectar ao banco de dados
conexao = db.connect(
    host=SERVER,
    database=DIR_DADOS,
    user=USUARIO_BD,
    password=SENHA_BD
)

# Exemplo de consulta ao banco de dados
cursor = conexao.cursor()
cursor.execute("""
               SELECT * 
               FROM GERFORNECEDOR
               WHERE COD_FORNECEDOR = 1;
               """)

# Obter os nomes das colunas
colunas = [desc[0] for desc in cursor.description]

# Imprimir os resultados formatados
for row in cursor.fetchall():
    resultado_formatado = {coluna: valor for coluna, valor in zip(colunas, row)}
    print(resultado_formatado)

# Fechar a conexão
conexao.close()

# PANDAS:

print("\n")

# Conectar ao banco de dados novamente para usar com pandas
conexao = db.connect(
    host=SERVER,
    database=DIR_DADOS,
    user=USUARIO_BD,
    password=SENHA_BD
)

# Exemplo de consulta ao banco de dados
cursor = conexao.cursor()
cursor.execute("""
               SELECT * 
               FROM GERFORNECEDOR
               WHERE COD_FORNECEDOR = 1;
               """)

# Obter os nomes das colunas
colunas = [desc[0] for desc in cursor.description]

# Obter os resultados
resultados = cursor.fetchall()

# Fechar a conexão
conexao.close()

# Criar um DataFrame do pandas
df = pd.DataFrame(resultados, columns=colunas)

# Imprimir o DataFrame
print(df)
