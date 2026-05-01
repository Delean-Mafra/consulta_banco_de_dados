from datetime import timedelta

from db_lerconfiguracao import ler_configuracao, get_db

input("Tem certeza que deseja continuar...?")


COD_FORNECEDOR = 580
TIPO_REL = "A"
TIPO_LANC_FIN = "P"
ATV_LANC_FINANCEIRO = "V"
COD_HISTORICO = 104
COD_PLANO_CONTA = 107
COD_FORMA_PAGTO = 22
COD_CONTA_FINANCEIRA = 25
COD_CENTRO_CUSTO = 3
COD_EMPRESA_FIN = 1
COD_SITUACAO_TITULO = 1
COD_USUARIO_CRIADOR = 1


def formatar_data_br(valor_data):
    if valor_data is None:
        return ""

    if hasattr(valor_data, "strftime"):
        return valor_data.strftime("%d/%m/%Y")

    valor_str = str(valor_data).split(" ")[0]
    if "-" in valor_str:
        ano, mes, dia = valor_str.split("-")
        return f"{dia}/{mes}/{ano}"

    return str(valor_data)


def incrementar_competencia(data_competencia):
    if hasattr(data_competencia, "strftime"):
        mes = data_competencia.month
        ano = data_competencia.year
    else:
        texto = str(data_competencia).strip()
        partes = texto.split("/")

        if len(partes) != 2:
            raise ValueError(f"Competência inválida: {data_competencia}")

        mes, ano = map(int, partes)

    mes += 1
    if mes > 12:
        mes = 1
        ano += 1

    return f"{mes:02d}/{ano:04d}"


def obter_ultimo_lancamento(c):
    query = """
--sql
SELECT
    Z.DATA_EMISSAO,
    Z.DATA_PAGAMENTO,
    Z.DATA_COMPETENCIA
FROM LANC_FINANCEIRO Z
WHERE Z.COD_FIN = (
    SELECT MAX(X.COD_FIN)
    FROM LANC_FINANCEIRO X
    WHERE X.VALOR_PAGO > 1
      AND X.COD_PLANO_CONTA = 107
      AND X.COD_HISTORICO = 104
      AND X.COD_SITUACAO_TITULO = 4
);
"""
    c.execute(query)
    row = c.fetchone()

    if not row:
        return None

    data_emissao_base, data_pagamento_base, competencia_base = row

    if data_emissao_base is None or data_pagamento_base is None or competencia_base is None:
        return None

    return {
        "data_emissao_base": data_emissao_base,
        "data_pagamento_base": data_pagamento_base,
        "competencia_base": competencia_base,
    }


def main():
    db = get_db()
    lc = ler_configuracao()

    conn = None
    c = None

    try:
        conn = db.connect(
            host=lc["SERVER"],
            database=lc["DIR_DADOS"],
            user=lc["USUARIO_BD"],
            password=lc["SENHA_BD"],
        )
        c = conn.cursor()

        base = obter_ultimo_lancamento(c)
        if base is None:
            print("Nenhum lançamento base encontrado. Processo encerrado.")
            return

        data_inicial = base["data_emissao_base"] + timedelta(days=1)
        data_final = base["data_pagamento_base"]
        data_vencimento = base["data_pagamento_base"] + timedelta(days=30)
        data_emissao = base["data_pagamento_base"] + timedelta(days=1)
        competencia = incrementar_competencia(base["competencia_base"])

        query_valor = """
--sql
SELECT COALESCE(SUM(X.VALOR_PAGO) / 10, 0)
FROM LANC_FINANCEIRO X
WHERE X.DATA_PAGAMENTO BETWEEN ? AND ?
  AND X.COD_CONTA_FINANCEIRA IN (25, 30, 4)
  AND X.TIPO_LANC_FIN = 'R'
  AND X.ATV_LANC_FINANCEIRO = 'V'
  AND X.COD_SITUACAO_TITULO = 4;
"""
        c.execute(query_valor, (data_inicial, data_final))
        row = c.fetchone()
        valor_calculado = row[0] if row and row[0] is not None else 0

        observacao = (
            f"{formatar_data_br(data_inicial)} a {formatar_data_br(data_final)} "
            f"Proxima referencia - {formatar_data_br(data_emissao)}"
        )
        # OBS_LANC no banco esta como BLOB nao textual; envie bytes para evitar TypeError do fdb.
        observacao_blob = observacao.encode("utf-8")

        query_insert = """
--sql
INSERT INTO LANC_FINANCEIRO (
    COD_FORNECEDOR, TIPO_REL, TIPO_LANC_FIN, ATV_LANC_FINANCEIRO, COD_HISTORICO,
    COD_PLANO_CONTA, COD_FORMA_PAGTO, COD_CONTA_FINANCEIRA, COD_CENTRO_CUSTO, COD_EMPRESA_FIN,
    COD_SITUACAO_TITULO, VALOR_PAGO, VALOR_AMORTIZADO, VALOR_A_AMORTIZAR, VALOR_PREVISTO,
    VALOR_PREVISTO_RESTANTE, DATA_VENCIMENTO, DATA_COMPETENCIA, COD_USUARIO_CRIADOR, DATA_EMISSAO, OBS_LANC
) VALUES (
    ?, ?, ?, ?, ?,
    ?, ?, ?, ?, ?,
    ?, ?, ?, ?, ?,
    ?, ?, ?, ?, ?, ?
);
"""
        parametros = (
            COD_FORNECEDOR,
            TIPO_REL,
            TIPO_LANC_FIN,
            ATV_LANC_FINANCEIRO,
            COD_HISTORICO,
            COD_PLANO_CONTA,
            COD_FORMA_PAGTO,
            COD_CONTA_FINANCEIRA,
            COD_CENTRO_CUSTO,
            COD_EMPRESA_FIN,
            COD_SITUACAO_TITULO,
            0,
            0,
            valor_calculado,
            valor_calculado,
            valor_calculado,
            data_vencimento,
            competencia,
            COD_USUARIO_CRIADOR,
            data_emissao,
            observacao_blob,
        )

        c.execute(query_insert, parametros)
        conn.commit()

        print(f"Valor calculado: {float(valor_calculado):.2f}")
        print("Insert realizado com sucesso!")

    except Exception:
        if conn is not None:
            conn.rollback()
        raise

    finally:
        if c is not None:
            c.close()
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    main()