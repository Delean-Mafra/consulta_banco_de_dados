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


query_select = f"""
--sql
SELECT Z.DATA_EMISSAO+1
FROM LANC_FINANCEIRO Z
WHERE Z.COD_FIN IN
(SELECT MAX(COD_FIN)
FROM LANC_FINANCEIRO X
WHERE X.VALOR_PAGO > 1
AND X.COD_PLANO_CONTA = 107
AND X.COD_HISTORICO = 104
AND X.COD_SITUACAO_TITULO = 4
);
"""

c.execute(query_select)
data_inicial = c.fetchone()[0] or 0  # Pega o resultado do SELECT


query_select = f"""
--sql
SELECT Z.DATA_PAGAMENTO
FROM LANC_FINANCEIRO Z
WHERE Z.COD_FIN IN
(SELECT MAX(COD_FIN)
FROM LANC_FINANCEIRO X
WHERE X.VALOR_PAGO > 1
AND X.COD_PLANO_CONTA = 107
AND X.COD_HISTORICO = 104
AND X.COD_SITUACAO_TITULO = 4
);
"""

c.execute(query_select)
data_final = c.fetchone()[0] or 0  # Pega o resultado do SELECT


# Query para calcular o valor
query_select = f"""
--sql
SELECT SUM(X.VALOR_PAGO) / 10
FROM LANC_FINANCEIRO X
WHERE X.DATA_PAGAMENTO BETWEEN '{data_inicial}' AND '{data_final}'
AND X.COD_CONTA_FINANCEIRA IN (25,30,4)
AND X.TIPO_LANC_FIN = 'R';
"""

c.execute(query_select)
valor_calculado = c.fetchone()[0] or 0  # Pega o resultado do SELECT
print(f"Valor calculado: {valor_calculado:.2f}")


query_select = f"""
--sql
SELECT Z.DATA_PAGAMENTO+30
FROM LANC_FINANCEIRO Z
WHERE Z.COD_FIN IN
(SELECT MAX(COD_FIN)
FROM LANC_FINANCEIRO X
WHERE X.VALOR_PAGO > 1
AND X.COD_PLANO_CONTA = 107
AND X.COD_HISTORICO = 104
AND X.COD_SITUACAO_TITULO = 4
);
"""

c.execute(query_select)
data_vencimento = c.fetchone()[0] or 0  # Pega o resultado do SELECT


def incrementar_competencia(data_competencia):
    """
    Incrementa a data de competência no formato mm/aaaa
    Exemplo: 12/2024 -> 01/2025
    
    Args:
        data_competencia (str): Data no formato 'mm/aaaa'
    
    Returns:
        str: Nova data de competência no formato 'mm/aaaa'
    """
    # Separar mês e ano
    mes, ano = data_competencia.split('/')
    
    # Converter para inteiros
    mes = int(mes)
    ano = int(ano)
    
    # Incrementar mês
    mes += 1
    
    # Se passar de dezembro, incrementa o ano
    if mes > 12:
        mes = 1
        ano += 1
    
    # Formatar mês com dois dígitos e retornar
    return f"{mes:02d}/{ano}"

# Modificar a parte do seu código que lida com a competência
query_select = """
--sql
SELECT Z.DATA_COMPETENCIA
FROM LANC_FINANCEIRO Z
WHERE Z.COD_FIN IN
(SELECT MAX(COD_FIN)
FROM LANC_FINANCEIRO X
WHERE X.VALOR_PAGO > 1
AND X.COD_PLANO_CONTA = 107
AND X.COD_HISTORICO = 104
AND X.COD_SITUACAO_TITULO = 4
);
"""

c.execute(query_select)
competencia_atual = c.fetchone()[0]  # Pega o resultado do SELECT
competencia = incrementar_competencia(competencia_atual)


query_select = f"""
--sql
SELECT Z.DATA_PAGAMENTO+1
FROM LANC_FINANCEIRO Z
WHERE Z.COD_FIN IN
(SELECT MAX(COD_FIN)
FROM LANC_FINANCEIRO X
WHERE X.VALOR_PAGO > 1
AND X.COD_PLANO_CONTA = 107
AND X.COD_HISTORICO = 104
AND X.COD_SITUACAO_TITULO = 4
);
"""

c.execute(query_select)
data_emissao = c.fetchone()[0] or 0  # Pega o resultado do SELECT


observacao =(f'{data_inicial} a {data_final} Proxima referencia -  {data_emissao}' )


# Query para o INSERT
query_insert = f"""
--sql
INSERT INTO LANC_FINANCEIRO (
    COD_FORNECEDOR, TIPO_REL, TIPO_LANC_FIN, ATV_LANC_FINANCEIRO, COD_HISTORICO, 
    COD_PLANO_CONTA, COD_FORMA_PAGTO, COD_CONTA_FINANCEIRA, COD_CENTRO_CUSTO, COD_EMPRESA_FIN, 
    COD_SITUACAO_TITULO, VALOR_PAGO, VALOR_AMORTIZADO, VALOR_A_AMORTIZAR, VALOR_PREVISTO, 
    VALOR_PREVISTO_RESTANTE, DATA_VENCIMENTO, DATA_COMPETENCIA, COD_USUARIO_CRIADOR, DATA_EMISSAO, OBS_LANC
) VALUES (
    580, 'A', 'P', 'V', 104, 107, 22, 25, 3, 1, 1, 0, 0, {valor_calculado:.2f}, {valor_calculado:.2f}, {valor_calculado:.2f},
    '{data_vencimento}', '{competencia}', 1, '{data_emissao}', '{observacao}'
);
"""

# Executar o INSERT
c.execute(query_insert)
conn.commit()
print("Insert realizado com sucesso!")

# Fechar a conexão
c.close()
conn.close()




# # import fdb
# # from db_lerconfiguracao import ler_configuracao

# # lc = ler_configuracao()

# # # Configurações do banco de dados
# # DIR_DADOS = lc['DIR_DADOS']
# # USUARIO_BD = lc['USUARIO_BD']
# # SENHA_BD = lc['SENHA_BD']
# # SERVER = lc['SERVER']


# # # Conectar ao banco de dados
# # conn = fdb.connect(
# #     host=SERVER,
# #     database=DIR_DADOS,
# #     user=USUARIO_BD,
# #     password=SENHA_BD
# # )
# # c = conn.cursor()

# # # Solicitar datas do usuário
# # data_inicial = input("Insira a data inicial (dd.mm.yyyy): ")
# # data_final = input("Insira a data final (dd.mm.yyyy): ")

# # # Query para calcular o valor
# # query_select = f"""
# # --sql
# # SELECT SUM(X.VALOR_PAGO) / 10
# # FROM LANC_FINANCEIRO X
# # WHERE X.DATA_PAGAMENTO BETWEEN '{data_inicial}' AND '{data_final}'
# # AND X.COD_CONTA_FINANCEIRA IN (25,30,4)
# # AND X.TIPO_LANC_FIN = 'R';
# # """

# # c.execute(query_select)
# # valor_calculado = c.fetchone()[0] or 0  # Pega o resultado do SELECT
# # print(f"Valor calculado: {valor_calculado:.2f}")

# # # Solicitar mais dados do usuário
# # data_vencimento = input("Insira a data de vencimento (dd.mm.yyyy): ")
# # competencia = input("Insira a competência (mm/yyyy): ")

# # # Query para o INSERT
# # query_insert = f"""
# # --sql
# # INSERT INTO LANC_FINANCEIRO (
# #     COD_FORNECEDOR, TIPO_REL, TIPO_LANC_FIN, ATV_LANC_FINANCEIRO, COD_HISTORICO, 
# #     COD_PLANO_CONTA, COD_FORMA_PAGTO, COD_CONTA_FINANCEIRA, COD_CENTRO_CUSTO, COD_EMPRESA_FIN, 
# #     COD_SITUACAO_TITULO, VALOR_PAGO, VALOR_AMORTIZADO, VALOR_A_AMORTIZAR, VALOR_PREVISTO, 
# #     VALOR_PREVISTO_RESTANTE, DATA_VENCIMENTO, DATA_COMPETENCIA, COD_USUARIO_CRIADOR
# # ) VALUES (
# #     580, 'A', 'P', 'V', 104, 107, 22, 25, 3, 1, 1, 0, 0, {valor_calculado:.2f}, {valor_calculado:.2f}, {valor_calculado:.2f},
# #     '{data_vencimento}', '{competencia}', 1
# # );
# # """

# # # Executar o INSERT
# # c.execute(query_insert)
# # conn.commit()
# # print("Insert realizado com sucesso!")

# # # Fechar a conexão
# # c.close()
# # conn.close()
