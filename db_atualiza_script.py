import os
import time
from db_lerconfiguracao import ler_configuracao, get_db
db = get_db()

lc = ler_configuracao()

# Configurações do banco de dados
DIR_DADOS = lc['DIR_DADOS']
USUARIO_BD = lc['USUARIO_BD']
SENHA_BD = lc['SENHA_BD']
SERVER = lc['SERVER']


# Função para validar tabelas no banco de dados
def tabela_existe(cursor, tabela):
    query = "SELECT 1 FROM RDB$RELATIONS WHERE RDB$RELATION_NAME = ?"
    cursor.execute(query, (tabela.upper(),))
    return cursor.fetchone() is not None

# Função para ler o arquivo de configuração


# Função para executar o script SQL
def executar_script(cursor, script_path):
    try:
        with open(script_path, 'r', encoding='ISO8859_1') as arquivo_sql:
            script = arquivo_sql.readlines()
        
        comandos = []
        ignorar_proximas = {"SET SQL DIALECT", "SET NAMES", "TERM"}  # Ignorar comandos desnecessários
        for linha in script:
            linha = linha.strip()
            if any(linha.upper().startswith(ignorar) for ignorar in ignorar_proximas):
                continue
            if linha and not linha.startswith("/*") and not linha.startswith("--"):
                comandos.append(linha)

        script = ' '.join(comandos)
        comandos_individuais = [cmd.strip() for cmd in script.split(';') if cmd.strip()]

        for comando in comandos_individuais:
            # Validar tabelas antes de executar comandos que dependem delas
            if "ALTER TABLE" in comando.upper() or "DROP TABLE" in comando.upper():
                nome_tabela = comando.split()[2]  # Obtém o nome da tabela
                if not tabela_existe(cursor, nome_tabela):
                    print(f"Tabela desconhecida: {nome_tabela}. Comando ignorado.")
                    continue
            cursor.execute(comando)
        return True

    except Exception as e:
        print(f"Erro ao executar script '{script_path}': {e}")
        return False

# Caminho do arquivo de configuração

# Caminho da pasta dos scripts SQL
pasta_scripts = 'C:\\caminho\\para\\os\\scripts'

# Ler configurações do arquivo



# Conectar ao banco de dados
try:
    conn = db.connect(
        host=SERVER,
        database=DIR_DADOS,
        user=USUARIO_BD,
        password=SENHA_BD
    )
    cursor = conn.cursor()

    # Iniciar uma transação explicitamente
    cursor.execute("START TRANSACTION")

    # Loop para processar scripts SQL
    while True:
        # Obter o valor atual do parâmetro
        cod_parametro = 1
        query_select = """
        SELECT VALOR
        FROM PARAMETRO
        WHERE COD_PARAMETRO = ?;
        """
        cursor.execute(query_select, (cod_parametro,))
        resultado = cursor.fetchone()

        if resultado is None:
            print("Parâmetro não encontrado no banco de dados. Verifique o COD_PARAMETRO.")
            break

        valor_atual = int(resultado[0])
        proximo_script = f"AtualG3_{valor_atual + 1:05d}.sql"
        caminho_script = os.path.join(pasta_scripts, proximo_script)

        if not os.path.exists(caminho_script):
            print(f"Todos os scripts até '{proximo_script}' foram processados.")
            break

        # Executar o script
        print(f"Executando script: {proximo_script}...")
        sucesso = executar_script(cursor, caminho_script)

        # Atualizar o valor no banco de dados
        novo_valor = valor_atual + 1
        query_update = """
        UPDATE PARAMETRO
        SET VALOR = ?
        WHERE COD_PARAMETRO = ?;
        """
        cursor.execute(query_update, (str(novo_valor), cod_parametro))
        conn.commit()

        if sucesso:
            print(f"Script '{proximo_script}' executado com sucesso.")
        else:
            print(f"Erro no script '{proximo_script}'. Pulando para o próximo...")

        # Garantir que o script não trave a execução
        time.sleep(2)

    # Finalizar transação
    cursor.execute("COMMIT")

except db.DatabaseError as e:
    print(f"Erro ao acessar o banco de dados: {e}")
    if conn:
        try:
            # Em caso de erro, fazer o rollback para não deixar transações abertas
            cursor.execute("ROLLBACK")
        except Exception as rollback_error:
            print(f"Erro ao reverter transação: {rollback_error}")

finally:
    if conn:
        try:
            conn.close()
        except Exception as e:
            print(f"Erro ao fechar a conexão: {e}")
