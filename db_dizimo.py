# Este código é responsável por calcular o valor do dízimo com base nos lançamentos financeiros registrados no banco de dados. Ele realiza as seguintes etapas:
# 1. Conecta ao banco de dados utilizando as configurações lidas de um arquivo de configuração.
# 2. Executa consultas SQL para obter as datas de emissão, pagamento e competência dos lançamentos financeiros relevantes.
# 3. Calcula o valor do dízimo com base nos valores pagos entre as datas obtidas.
# 4. Insere um novo registro no banco de dados com o valor calculado e as informações associadas.


from db_lerconfiguracao import ler_configuracao, get_db
db = get_db()

input("Pressione Enter para continuar...")

lc = ler_configuracao()

# Conectar ao banco de dados
conn = db.connect(
    host=lc['SERVER'],
    database=lc['DIR_DADOS'],
    user=lc['USUARIO_BD'],
    password=lc['SENHA_BD']
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
AND X.TIPO_LANC_FIN = 'R'
AND X.ATV_LANC_FINANCEIRO = 'V'
AND X.COD_SITUACAO_TITULO = 4;
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


def formatar_data_br(valor_data):
    if hasattr(valor_data, 'strftime'):
        return valor_data.strftime('%d/%m/%Y')

    valor_str = str(valor_data).split(' ')[0]
    if '-' in valor_str:
        ano, mes, dia = valor_str.split('-')
        return f"{dia}/{mes}/{ano}"

    return str(valor_data)


observacao = (
    f"{formatar_data_br(data_inicial)} a {formatar_data_br(data_final)} "
    f"Proxima referencia -  {formatar_data_br(data_emissao)}"
)


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