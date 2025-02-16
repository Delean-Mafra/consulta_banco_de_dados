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

# Executar o UPDATE em LANC_FINANCEIRO
try:
    update_lanc_financeiro_query = """
    --sql
    UPDATE LANC_FINANCEIRO Z
    SET Z.CHAVE_REL = (
        SELECT FIRST 1 X.COD_COMPRA
        FROM COMPRA X
        WHERE X.COD_COMPRA > 768
        AND X.COD_FORNECEDOR = Z.COD_FORNECEDOR
        AND X.VALOR_LIQUIDO_COMPRA = Z.VALOR_PREVISTO
        AND Z.TIPO_REL = 'A'
        AND X.MODELO_NF = 65
    ), Z.TIPO_REL = 'C',
    Z.NUM_DOC = (
        SELECT FIRST 1 X.NUMERO_NF
        FROM COMPRA X
        WHERE X.COD_COMPRA > 768
        AND X.COD_FORNECEDOR = Z.COD_FORNECEDOR
        AND X.VALOR_LIQUIDO_COMPRA = Z.VALOR_PREVISTO
        AND Z.TIPO_REL = 'A'
        AND X.MODELO_NF = 65
    )
    WHERE EXISTS (
        SELECT 1
        FROM COMPRA X
        WHERE X.COD_COMPRA > 768
        AND X.COD_FORNECEDOR = Z.COD_FORNECEDOR
        AND X.VALOR_LIQUIDO_COMPRA = Z.VALOR_PREVISTO
        AND Z.TIPO_REL = 'A'
        AND X.MODELO_NF = 65
    );
    """
    c.execute(update_lanc_financeiro_query)
    conn.commit()
    print("Update em LANC_FINANCEIRO executado com sucesso.")
except db.fbcore.DatabaseError as e:
    print(f"Erro ao executar o update em LANC_FINANCEIRO: {e}")

# Identificar os códigos de compra atualizados
try:
    select_updated_cod_compra_query = """
    --sql
    SELECT DISTINCT X.COD_COMPRA
    FROM COMPRA X
    INNER JOIN LANC_FINANCEIRO Z ON X.COD_FORNECEDOR = Z.COD_FORNECEDOR
    WHERE X.COD_COMPRA >= 768
    AND X.COD_FORNECEDOR = 22
    AND X.VALOR_LIQUIDO_COMPRA = Z.VALOR_PREVISTO
    AND Z.TIPO_REL = 'C'
    AND CAST(X.MODELO_NF AS VARCHAR(10)) = '65';
    """
    c.execute(select_updated_cod_compra_query)
    updated_cod_compra = [row[0] for row in c.fetchall()]
    print(f"Códigos de compra atualizados: {updated_cod_compra}")
except db.fbcore.DatabaseError as e:
    print(f"Erro ao identificar os códigos de compra atualizados: {e}")

# Executar o UPDATE apenas para as compras específicas
try:
    if updated_cod_compra:
        update_compra_query = f"""
        --sql
        UPDATE COMPRA X
        SET X.MODELO_NF = '66'
        WHERE X.COD_COMPRA IN ({','.join(map(str, updated_cod_compra))})
        AND CAST(X.MODELO_NF AS VARCHAR(10)) = '65';
        """
        c.execute(update_compra_query)
        conn.commit()
        print("Update em COMPRA executado com sucesso.")
    else:
        print("Nenhum código de compra atualizado encontrado.")
except db.fbcore.DatabaseError as e:
    print(f"Erro ao executar o update em COMPRA: {e}")
finally:
    conn.close()
