from db_lerconfiguracao import ler_configuracao, get_db
db = get_db()
lc = ler_configuracao()

# Configurações do banco de dados
DIR_DADOS = lc['DIR_DADOS']
USUARIO_BD = lc['USUARIO_BD']
SENHA_BD = lc['SENHA_BD']
SERVER = lc['SERVER']


# Conectar ao banco de dados
try:
    conn = db.connect(
        host=SERVER,
        database=DIR_DADOS,
        user=USUARIO_BD,
        password=SENHA_BD
    )
    c = conn.cursor() 

    # Buscar o valor atual do parâmetro
    cod_parametro = 1  # Substitua pelo código do parâmetro que deseja atualizar
    query_select = """
    --sql
    SELECT VALOR
    FROM PARAMETRO
    WHERE COD_PARAMETRO = ?;
    """
    c.execute(query_select, (cod_parametro,))
    resultado = c.fetchone()

    if resultado is not None:
        valor_atual = resultado[0]

        try:
            # Converter o valor para inteiro
            valor_numerico = int(valor_atual)

            # Incrementar o valor
            valor_incrementado = valor_numerico + 1

            # Atualizar o valor no banco de dados
            query_update = """
            --sql
            UPDATE PARAMETRO
            SET VALOR = ?
            WHERE COD_PARAMETRO = ?;
            """
            c.execute(query_update, (str(valor_incrementado), cod_parametro))
            conn.commit()
            print(f"Parâmetro atualizado com sucesso! Novo valor: {valor_incrementado}")

        except ValueError:
            print(f"Erro: o valor atual '{valor_atual}' não pode ser convertido para inteiro.")
    else:
        print(f"Parâmetro com COD_PARAMETRO = {cod_parametro} não encontrado.")

except db.DatabaseError as e:
    print(f"Erro ao acessar o banco de dados: {e}")

finally:
    # Fechar conexão com o banco de dados
    if conn:
        conn.close()