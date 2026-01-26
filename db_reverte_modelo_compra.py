from db_lerconfiguracao import ler_configuracao, get_db
db = get_db()

lc = ler_configuracao()

# Conectar ao banco de dados
try:
    conn = db.connect(
    host=lc['SERVER'],
    database=lc['DIR_DADOS'],
    user=lc['USUARIO_BD'],
    password=lc['SENHA_BD']
    )
    c = conn.cursor()

    # Reverter as alterações indevidas
    revert_query = """
    UPDATE COMPRA X
    SET X.MODELO_NF = '65'
    WHERE CAST(X.MODELO_NF AS VARCHAR(10)) = '66'
    AND X.COD_FORNECEDOR != 22;
    """
    c.execute(revert_query)
    conn.commit()
    print("Alterações indevidas revertidas com sucesso.")
except db.fbcore.DatabaseError as e:
    print(f"Erro ao reverter as alterações: {e}")
finally:
    conn.close()
