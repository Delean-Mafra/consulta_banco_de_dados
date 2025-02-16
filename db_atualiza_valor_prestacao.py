from decimal import Decimal
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

# Seleciona os registros que atendem às condições especificadas
cur.execute(""" --sql
    SELECT COD_FIN, VALOR_A_AMORTIZAR FROM LANC_FINANCEIRO
    WHERE COD_PLANO_CONTA = 122 AND COD_FORNECEDOR = 15 AND 
    ATV_LANC_FINANCEIRO = 'V' AND COD_SITUACAO_TITULO = 1 AND 
    COD_FIN < 2393 AND COD_FIN > 1156 ORDER BY COD_FIN;
""")

# Lista para armazenar os registros
registros = cur.fetchall()

# Verifica se existem registros e realiza o update
if registros:
    valor_anterior = registros[0][1] # Valor do primeiro registro

    for registro in registros[1:]: # Começa do segundo registro
        novo_valor = valor_anterior + Decimal('0.50')  # Converte 0.50 para Decimal
        cur.execute(""" --sql
            UPDATE LANC_FINANCEIRO 
            SET VALOR_A_AMORTIZAR = ?
            WHERE COD_FIN = ?;
        """, (novo_valor, registro[0]))
        valor_anterior = novo_valor

    # Commit das alterações
    conn.commit()

# Fecha as conexões
cur.close()
conn.close()
