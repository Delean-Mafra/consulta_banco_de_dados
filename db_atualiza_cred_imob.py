from decimal import Decimal, ROUND_HALF_UP
from db_lerconfiguracao import ler_configuracao, get_db

db = get_db()
lc = ler_configuracao()

DIR_DADOS = lc['DIR_DADOS']
USUARIO_BD = lc['USUARIO_BD']
SENHA_BD = lc['SENHA_BD']
SERVER = lc['SERVER']

MULTIPLICADOR = Decimal('1.0017')   # +0,17%
PRECISAO = Decimal('0.01')          # 2 casas

SELECT_SQL = """
SELECT X.COD_FIN, X.VALOR_A_AMORTIZAR, X.VALOR_PREVISTO, X.VALOR_PREVISTO_RESTANTE
FROM LANC_FINANCEIRO X
WHERE X.COD_SITUACAO_TITULO = 1
  AND X.COD_PLANO_CONTA = 122
  AND X.COD_FORNECEDOR = 15
  AND X.ATV_LANC_FINANCEIRO = 'V'
ORDER BY X.COD_FIN
"""

UPDATE_SQL = """
UPDATE LANC_FINANCEIRO
SET VALOR_A_AMORTIZAR = ?,
    VALOR_PREVISTO = ?,
    VALOR_PREVISTO_RESTANTE = ?
WHERE COD_FIN = ?
  AND COD_PLANO_CONTA = 122
  AND COD_FORNECEDOR = 15
  AND ATV_LANC_FINANCEIRO = 'V'
  AND COD_SITUACAO_TITULO = 1
"""

def to_decimal(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))

def round2(d):
    return d.quantize(PRECISAO, rounding=ROUND_HALF_UP)

try:
    conn = db.connect(
        host=SERVER,
        database=DIR_DADOS,
        user=USUARIO_BD,
        password=SENHA_BD
    )
    c = conn.cursor()

    c.execute(SELECT_SQL)
    rows = c.fetchall()

    if not rows:
        print("Nenhum título encontrado para atualizar.")
    else:
        prev_new_value = None
        total = 0

        for cod_fin, valor_a, valor_prev, valor_prev_rest in rows:
            base = to_decimal(valor_prev)

            # Se base for None, pular (evita transformar em zero)
            if base is None:
                print(f"Pulado COD_FIN={cod_fin} porque VALOR_PREVISTO é NULL")
                continue

            if prev_new_value is None:
                # Primeiro título: manter o valor original (apenas arredondar)
                new_value = round2(base)
            else:
                # Demais títulos: aplicar 0,17% sobre o valor já atualizado do anterior
                new_value = round2(prev_new_value * MULTIPLICADOR)

            # Enviar como string para preservar precisão no driver
            c.execute(UPDATE_SQL, (str(new_value), str(new_value), str(new_value), cod_fin))

            prev_new_value = new_value
            total += 1

        conn.commit()
        print(f"Atualização finalizada. Títulos atualizados: {total}")

except Exception as e:
    try:
        conn.rollback()
    except:
        pass
    print("Erro ao atualizar:", e)

finally:
    try:
        c.close()
        conn.close()
    except:
        pass
