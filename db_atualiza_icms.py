from db_lerconfiguracao import ler_configuracao, get_db
db = get_db()
lc = ler_configuracao()

# Configurações do banco de dados
DIR_DADOS = lc['DIR_DADOS']
USUARIO_BD = lc['USUARIO_BD']
SENHA_BD = lc['SENHA_BD']
SERVER = lc['SERVER']


conn = db.connect(
    host=SERVER,
    database=DIR_DADOS,
    user=USUARIO_BD,
    password=SENHA_BD
)
cod_compra = input('Digite o codigo da compra: ')
c = conn.cursor()

# Perguntar se deseja executar a atualização do ICMS dos itens
atualizar_icms_itens = input('Deseja atualizar o ICMS dos itens? (S/N): ')
if atualizar_icms_itens.upper() == 'S':
    update_icms_itens_query = f"""
    --sql
    UPDATE COMPRA_ITEM CI
    SET CI.VALOR_ICMS = (CI.PERCENTUAL_ICMS_ITEM * CI.VALOR_TOTAL_ITEM) / 100
    WHERE CI.COD_COMPRA = {cod_compra};
    """
    c.execute(update_icms_itens_query)
    conn.commit()

# Perguntar se deseja atualizar as informações do ICMS no total da compra
atualizar_icms_total = input('Deseja atualizar as informações do ICMS no total da compra? (S/N): ')
if atualizar_icms_total.upper() == 'S':
    update_icms_total_query = f"""
    --sql
    UPDATE COMPRA C
    SET C.VALOR_ICMS_NF = (SELECT SUM(CI.PERCENTUAL_ICMS_ITEM * CI.VALOR_TOTAL_ITEM) / 100
                           FROM COMPRA_ITEM CI
                           WHERE CI.COD_COMPRA = {cod_compra}),
        C.VALOR_BASE_ICMS = (SELECT SUM(CI.VALOR_TOTAL_ITEM)
                             FROM COMPRA_ITEM CI
                             WHERE CI.COD_COMPRA = {cod_compra}
                             AND CI.VALOR_ICMS > 0.01)
    WHERE C.COD_COMPRA = {cod_compra};
    """
    c.execute(update_icms_total_query)
    conn.commit()

conn.close()
