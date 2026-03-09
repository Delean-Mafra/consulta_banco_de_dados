from db_lerconfiguracao import ler_configuracao, nome_alias, get_db

# Obter configurações
config = ler_configuracao()
alias = nome_alias()
db = get_db()

try:
    # Conectar ao banco de dados Firebird
    conn = db.connect(
        host=config['SERVER'],
        database=alias['APELIDO_BANCO'],
        user=config['USUARIO_BD'],
        password=config['SENHA_BD'],
        charset='UTF8'
    )
    
    cursor = conn.cursor()
    
    # Executar o UPDATE
    query = """
    UPDATE LANC_FINANCEIRO
    SET PREVISTO = 'F'
    WHERE COD_SITUACAO_TITULO = 4
    AND ATV_LANC_FINANCEIRO = 'V'
    AND PREVISTO = 'V'
    """
    
    cursor.execute(query)
    conn.commit()
    
    print(f"✅ Update executado com sucesso!")
    print(f"📊 Registros atualizados: {cursor.rowcount}")
    
    cursor.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Erro ao executar o update: {e}")
