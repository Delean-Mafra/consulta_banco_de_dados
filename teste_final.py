# Teste FINAL com Decimal e date corretos
from db_lerconfiguracao import ler_configuracao, get_db
from decimal import Decimal
from datetime import date

db = get_db()
lc = ler_configuracao()


def teste_final():
    conn = db.connect(
    host=lc['SERVER'],
    database=lc['DIR_DADOS'],
    user=lc['USUARIO_BD'],
    password=lc['SENHA_BD']
    )
    cursor = conn.cursor()
    
    print("=" * 80)
    print("TESTE FINAL - COM DECIMAL E DATE")
    print("=" * 80)
    
    # Teste com Decimal e date
    print("\n[TESTE] VALOR_SAIDA = Decimal('156.64'), DATA = date(2025, 6, 2), CONTA = 25")
    print("-" * 80)
    
    valor = Decimal('156.64')
    cod_conta = 25
    data_obj = date(2025, 6, 2)
    
    query = """
        SELECT '-' || CAST(LCF.VALOR_LANCAMENTO_CONTA AS VARCHAR(30)) AS VALOR, 
               LCF.DATA_DISPONIVEL,
               LCF.DATA_EFETIVACAO,
               LCF.VALOR_SAIDA,
               LCF.COD_CONTA_FINANCEIRA
        FROM LANC_CONTA_FIN LCF
        WHERE LCF.VALOR_SAIDA = ?
        AND LCF.COD_CONTA_FINANCEIRA = ?
        AND (LCF.DATA_DISPONIVEL = ? OR CAST(LCF.DATA_EFETIVACAO AS DATE) = ?)
    """
    
    print(f"Parâmetros:")
    print(f"  valor = {valor} (tipo: {type(valor)})")
    print(f"  conta = {cod_conta} (tipo: {type(cod_conta)})")
    print(f"  data = {data_obj} (tipo: {type(data_obj)})")
    
    try:
        cursor.execute(query, (valor, cod_conta, data_obj, data_obj))
        result = cursor.fetchone()
        
        if result:
            print(f"\n✅ SUCESSO! REGISTRO ENCONTRADO:")
            print(f"  Valor: {result[0]}")
            print(f"  Data Disponível: {result[1]}")
            print(f"  Data Efetivação: {result[2]}")
            print(f"  Valor Saída: {result[3]}")
            print(f"  Conta: {result[4]}")
        else:
            print("\n❌ FALHA: Nenhum resultado encontrado")
    except Exception as e:
        print(f"\n❌ ERRO: {str(e)}")
        import traceback
        traceback.print_exc()
    
    cursor.close()
    conn.close()
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    teste_final()
