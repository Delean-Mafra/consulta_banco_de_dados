from datetime import datetime
from db_lerconfiguracao import ler_configuracao, get_db
db = get_db()

lc = ler_configuracao()

# Configurações do banco de dados
DIR_DADOS = lc['DIR_DADOS']
USUARIO_BD = lc['USUARIO_BD']
SENHA_BD = lc['SENHA_BD']
SERVER = lc['SERVER']


# Função para calcular a data de competência correta
def calcular_data_competencia(data_vencimento):
    # Converte a data de vencimento para string no formato esperado
    data_vencimento_str = data_vencimento.strftime('%d.%m.%Y %H:%M')
    data_vencimento = datetime.strptime(data_vencimento_str, '%d.%m.%Y %H:%M')
    mes_anterior = data_vencimento.month - 1 if data_vencimento.month > 1 else 12
    ano = data_vencimento.year if mes_anterior != 12 else data_vencimento.year - 1
    return f"{mes_anterior:02d}/{ano}"

# Conectar ao banco de dados
try:
    conn = db.connect(
        host=SERVER,
        database=DIR_DADOS,
        user=USUARIO_BD,
        password=SENHA_BD
    )
    c = conn.cursor()

    # Selecionar registros a serem atualizados
    c.execute("""  --sql
        SELECT COD_FIN, DATA_VENCIMENTO, DATA_COMPETENCIA 
        FROM LANC_FINANCEIRO
        WHERE COD_HISTORICO = 64
        AND COD_PLANO_CONTA = 48
        AND ATV_LANC_FINANCEIRO = 'V'
        AND VALOR_PAGO > 1200
        AND COD_CC IN (41,48);
    """)

    # Iterar sobre os registros e atualizar se necessário
    for row in c.fetchall():
        cod_fin, data_vencimento, data_competencia = row
        data_competencia_correta = calcular_data_competencia(data_vencimento)

        if data_competencia != data_competencia_correta:
            c.execute("""--sql
                UPDATE LANC_FINANCEIRO
                SET DATA_COMPETENCIA = ?
                WHERE COD_FIN = ?;
            """, (data_competencia_correta, cod_fin))

    # Commit as mudanças
    conn.commit()

finally:
    # Fechar a conexão
    c.close()
    conn.close()

print("Atualização concluída com sucesso!")
