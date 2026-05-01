from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from flask import Flask, render_template, request
from db_lerconfiguracao import ler_configuracao as LC, get_db as gdb


SQL_IRRF = """
SELECT
    LF.COD_FIN,
    GF.RAZAO_SOCIAL AS "EMPREGADOR",
    LF.VALOR_PREVISTO AS "VALOR BRUTO",
    LF.VALOR_PAGO AS "VALOR LIQUIDO",
    ROUND(SUM(CASE WHEN IMP.NOME_IMPOSTO LIKE '%IRRF%'
                   THEN RT.VALOR_RETIDO ELSE 0 END), 2) AS "VALOR IRRF",
    ROUND(SUM(CASE WHEN IMP.NOME_IMPOSTO LIKE '%INSS%'
                   THEN RT.VALOR_RETIDO ELSE 0 END), 2) AS "VALOR INSS",
    LF.DATA_PAGAMENTO AS "DATA DE PAGAMENTO",
    PC.NOME_PLANO_CONTA AS "TIPO DE PAGAMENTO"
FROM LANC_FINANCEIRO LF
LEFT JOIN RETENCAO_TITULO RT ON LF.COD_FIN = RT.COD_FIN
LEFT JOIN FINIMPOSTO IMP ON IMP.COD_IMPOSTO = RT.COD_IMPOSTO
LEFT JOIN PLANO_CONTA PC ON PC.COD_PLANO_CONTA = LF.COD_PLANO_CONTA
LEFT JOIN VTCENTRO_CUSTO GF ON GF.COD_CC = LF.COD_CC
WHERE
    LF.TIPO_LANC_FIN = 'R'
    AND LF.COD_CONTA_FINANCEIRA = 30
    AND LF.COD_CC = 63
    AND LF.DATA_PAGAMENTO >= ?
    AND LF.DATA_PAGAMENTO <= ?
    AND (LF.COD_EMPRESA_FIN IS NULL OR LF.COD_EMPRESA_FIN = 1)
GROUP BY
    LF.COD_FIN, GF.RAZAO_SOCIAL, LF.VALOR_PREVISTO, LF.VALOR_PAGO,
    LF.DATA_PAGAMENTO, PC.NOME_PLANO_CONTA
ORDER BY LF.COD_FIN
"""

TOLERANCIA_VALOR = Decimal("0.01")


@dataclass
class RowBanco:
    cod_fin: int
    empregador: str
    valor_bruto: Decimal
    valor_liquido: Decimal
    valor_irrf: Decimal
    valor_inss: Decimal
    data_pagamento: date
    tipo_pagamento: str


@dataclass
class RowTabela:
    mes_ref: str
    data_pagamento: date
    irrf_valor: Decimal | None
    bruto_valor: Decimal | None
    liquido_valor: Decimal | None
    inss_valor: Decimal | None
    tipo_pagamento: str
    bruto_texto: str
    linha_original: str


def _parse_data_br(texto: str) -> date | None:
    texto = (texto or "").strip()
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", texto)
    if not m:
        return None
    dia, mes, ano = map(int, m.groups())
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def _parse_valor_moeda(texto: str) -> Decimal | None:
    bruto = (texto or "").strip().replace("**", "")
    if not bruto:
        return None

    bruto_lower = bruto.lower()
    if bruto_lower in {"-", "isento", "na", "n/a", "none"}:
        return None

    # Remove texto explicativo como (PLR) e similares
    bruto = re.sub(r"\(.*?\)", "", bruto).strip()

    # Mantem apenas digitos, separadores e sinal
    bruto = re.sub(r"[^0-9,.-]", "", bruto)
    if not bruto:
        return None

    # Converte formato brasileiro para decimal
    bruto = bruto.replace(".", "").replace(",", ".")
    try:
        return Decimal(bruto)
    except InvalidOperation:
        return None


def _normalizar_data_banco(valor: Any) -> date | None:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor

    # Alguns exports podem trazer epoch em milissegundos
    if isinstance(valor, (int, float)):
        if valor > 1_000_000_000_000:
            return datetime.fromtimestamp(valor / 1000).date()
        if valor > 1_000_000_000:
            return datetime.fromtimestamp(valor).date()

    if isinstance(valor, str):
        valor = valor.strip()

        dt_br = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", valor)
        if dt_br:
            d, m, y = map(int, dt_br.groups())
            try:
                return date(y, m, d)
            except ValueError:
                pass

        dt_iso = re.search(r"(\d{4})-(\d{2})-(\d{2})", valor)
        if dt_iso:
            y, m, d = map(int, dt_iso.groups())
            try:
                return date(y, m, d)
            except ValueError:
                pass

        if valor.isdigit():
            inteiro = int(valor)
            if inteiro > 1_000_000_000_000:
                return datetime.fromtimestamp(inteiro / 1000).date()
            if inteiro > 1_000_000_000:
                return datetime.fromtimestamp(inteiro).date()

    return None


def _fmt_data(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def _fmt_money(d: Decimal | None) -> str:
    if d is None:
        return "-"
    s = f"{d:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


def _fmt_data_sql_firebird(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def _normalizar_header_coluna(texto: str) -> str:
    t = (texto or "").strip().lower()
    trocas = {
        "á": "a",
        "à": "a",
        "â": "a",
        "ã": "a",
        "é": "e",
        "ê": "e",
        "í": "i",
        "ó": "o",
        "ô": "o",
        "õ": "o",
        "ú": "u",
        "ç": "c",
    }
    for k, v in trocas.items():
        t = t.replace(k, v)
    return re.sub(r"\s+", " ", t)


def _tipo_pagamento_tabela(bruto_texto: str) -> str:
    t = _normalizar_header_coluna(bruto_texto)
    if "participacao" in t or "resultado" in t or "plr" in t or "comiss" in t:
        return "Comissões (PLR)"
    if "13" in t:
        return "13º Salário"
    if "ferias" in t:
        return "Pag. Ferias"
    return "Salários"


def _find_col_index(headers: list[str], aliases: list[str], allow_partial: bool = True) -> int | None:
    for alias in aliases:
        alias_n = _normalizar_header_coluna(alias)
        for idx, h in enumerate(headers):
            if h == alias_n:
                return idx
    if allow_partial:
        for alias in aliases:
            alias_n = _normalizar_header_coluna(alias)
            for idx, h in enumerate(headers):
                if alias_n in h:
                    return idx
    return None


def _sum_dec(*vals: Decimal | None) -> Decimal | None:
    nums = [v for v in vals if v is not None]
    if not nums:
        return None
    return sum(nums, Decimal("0.00"))


def _melhor_diff_bruto_liquido(row_banco: RowBanco, row_tabela: RowTabela) -> Decimal | None:
    diffs: list[Decimal] = []
    if row_tabela.bruto_valor is not None:
        diffs.append(abs(row_banco.valor_bruto - row_tabela.bruto_valor))
    if row_tabela.liquido_valor is not None:
        diffs.append(abs(row_banco.valor_liquido - row_tabela.liquido_valor))
    if not diffs:
        return None
    return min(diffs)


def _match_info_bruto_liquido(row_banco: RowBanco, row_tabela: RowTabela) -> tuple[str, Decimal, Decimal, Decimal] | None:
    opcoes: list[tuple[str, Decimal, Decimal, Decimal]] = []

    if row_tabela.bruto_valor is not None:
        diff_bruto = abs(row_banco.valor_bruto - row_tabela.bruto_valor)
        opcoes.append(("Bruto", row_tabela.bruto_valor, row_banco.valor_bruto, diff_bruto))

    if row_tabela.liquido_valor is not None:
        diff_liquido = abs(row_banco.valor_liquido - row_tabela.liquido_valor)
        opcoes.append(("Liquido", row_tabela.liquido_valor, row_banco.valor_liquido, diff_liquido))

    if not opcoes:
        return None

    return min(opcoes, key=lambda x: x[3])


def localizar_sem_irrf_por_data_valor(
    dados_banco: list[RowBanco], usados: set[int], row: RowTabela
) -> tuple[int | None, RowBanco | None, int | None]:
    # So tenta localizar se houver pelo menos um valor de referencia na linha da tabela.
    if row.bruto_valor is None and row.liquido_valor is None:
        return None, None, None

    # 1) Prioriza mesma data e valor bruto/liquido igual (com tolerancia monetaria)
    candidatos_mesma_data: list[tuple[int, RowBanco, Decimal]] = []
    for idx, b in enumerate(dados_banco):
        if idx in usados:
            continue
        data_b = _normalizar_data_banco(b.data_pagamento)
        if data_b != row.data_pagamento:
            continue
        diff = _melhor_diff_bruto_liquido(b, row)
        if diff is None:
            continue
        candidatos_mesma_data.append((idx, b, diff))

    if candidatos_mesma_data:
        idx, b, diff = min(candidatos_mesma_data, key=lambda x: x[2])
        if diff <= TOLERANCIA_VALOR:
            return idx, b, 0

    # 2) Nao achou na mesma data: busca por valor mais proximo + data mais proxima
    candidatos_gerais: list[tuple[int, RowBanco, Decimal, int]] = []
    for idx, b in enumerate(dados_banco):
        if idx in usados:
            continue
        diff = _melhor_diff_bruto_liquido(b, row)
        if diff is None:
            continue
        data_b = _normalizar_data_banco(b.data_pagamento)
        dias = abs((data_b - row.data_pagamento).days) if data_b and row.data_pagamento else 99999
        candidatos_gerais.append((idx, b, diff, dias))

    if not candidatos_gerais:
        return None, None, None

    idx, b, diff, dias = min(candidatos_gerais, key=lambda x: (x[2], x[3]))
    if diff <= TOLERANCIA_VALOR:
        return idx, b, dias

    return None, None, None


def _tipo_pagamento_banco(tipo: str) -> str:
    t = _normalizar_header_coluna(tipo)
    if "comiss" in t:
        return "Comissões (PLR)"
    if "ferias" in t:
        return "Pag. Ferias"
    if "13" in t:
        return "13º Salário"
    if "salario" in t:
        return "Salários"
    return "Outros"


def gerar_sql_correcao_datas(dados_tabela: list[RowTabela], resultado_comparacao: dict[str, Any] | None) -> str:
    if not resultado_comparacao:
        return ""

    tabela_por_mes_data: dict[tuple[str, str], RowTabela] = {
        (r.mes_ref, _fmt_data(r.data_pagamento)): r for r in dados_tabela
    }

    blocos: list[str] = []
    for linha in resultado_comparacao.get("linhas", []):
        if linha.get("status") not in {
            "Valor correto, data errada",
            "Localizado por Bruto/Liquido (data divergente)",
        }:
            continue

        cod_fin = linha.get("cod_fin")
        mes_ref = linha.get("mes_ref", "")
        data_tabela_txt = linha.get("data_tabela", "")
        ref = tabela_por_mes_data.get((mes_ref, data_tabela_txt))
        if not cod_fin or not ref:
            continue

        data_sql = _fmt_data_sql_firebird(ref.data_pagamento)
        bloco = (
            f"-- Correção automática para {mes_ref} | COD_FIN {cod_fin}\n"
            "-- Atualiza a data disponível na tabela LANC_CONTA_FIN\n"
            "UPDATE LANC_CONTA_FIN\n"
            f"SET DATA_DISPONIVEL = DATE '{data_sql}'\n"
            f"WHERE COD_FIN = {cod_fin};\n"
            "COMMIT;\n\n"
            "-- Atualiza a data de pagamento na tabela LANC_FINANCEIRO\n"
            "UPDATE LANC_FINANCEIRO\n"
            f"SET DATA_PAGAMENTO = DATE '{data_sql}'\n"
            f"WHERE COD_FIN = {cod_fin};\n"
            "COMMIT;"
        )
        blocos.append(bloco)

    return "\n\n".join(blocos)


def carregar_banco(data_ini: date, data_fim: date) -> tuple[list[RowBanco], str | None]:
    db = gdb()
    lc = LC()

    conn = None
    cursor = None
    try:
        conn = db.connect(
            host=lc["SERVER"],
            database=lc["DIR_DADOS"],
            user=lc["USUARIO_BD"],
            password=lc["SENHA_BD"],
        )
        cursor = conn.cursor()
        data_ini_dt = datetime.combine(data_ini, datetime.min.time())
        data_fim_dt = datetime.combine(data_fim, datetime.max.time().replace(microsecond=0))
        cursor.execute(SQL_IRRF, (data_ini_dt, data_fim_dt))

        rows: list[RowBanco] = []
        for item in cursor.fetchall():
            data_pg = _normalizar_data_banco(item[6])
            rows.append(
                RowBanco(
                    cod_fin=int(item[0]),
                    empregador=str(item[1] or ""),
                    valor_bruto=Decimal(str(item[2] or 0)),
                    valor_liquido=Decimal(str(item[3] or 0)),
                    valor_irrf=Decimal(str(item[4] or 0)),
                    valor_inss=Decimal(str(item[5] or 0)),
                    data_pagamento=data_pg,
                    tipo_pagamento=str(item[7] or ""),
                )
            )
        return rows, None
    except Exception as exc:
        return [], f"Erro ao consultar banco: {exc}"
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def parse_tabela_colada(texto: str) -> tuple[list[RowTabela], list[str]]:
    linhas = [l.strip() for l in (texto or "").splitlines() if l.strip()]
    erros: list[str] = []
    resultado: list[RowTabela] = []

    if not linhas:
        return resultado, ["Cole uma tabela para comparar."]

    # Aceita tabela markdown com | e ignorar linha separadora :---
    linhas_tabela = [l for l in linhas if "|" in l]
    if not linhas_tabela:
        return resultado, ["Nao foi encontrada estrutura de tabela com '|'."]

    header_idx = None
    header_cols: list[str] = []
    for idx, linha in enumerate(linhas_tabela):
        cols = [_normalizar_header_coluna(c) for c in linha.strip("|").split("|")]
        if (
            _find_col_index(cols, ["pagamento", "data pagto", "data pagamento"]) is not None
            and (
                _find_col_index(cols, ["irrf", "ir", "irrf salario", "irrf ferias"]) is not None
                or _find_col_index(cols, ["inss", "inss salario", "inss ferias"]) is not None
            )
        ):
            header_idx = idx
            header_cols = cols
            break

    if header_idx is None:
        return resultado, ["Cabecalho nao encontrado para o formato esperado da tabela."]

    idx_mes = _find_col_index(header_cols, ["mes ref.", "competencia"])
    idx_pg = _find_col_index(header_cols, ["pagamento", "data pagto", "data pagamento"])
    idx_tipo = _find_col_index(header_cols, ["tipo de holerite", "tipo holerite", "tipo de pagamento"])
    idx_bruto = _find_col_index(header_cols, ["rend. tributavel (bruto)", "bruto (r$)", "bruto"])
    idx_liquido = _find_col_index(header_cols, ["liquido (r$)", "liquido"])

    idx_irrf_total = _find_col_index(header_cols, ["irrf", "ir"], allow_partial=False)
    idx_inss_total = _find_col_index(header_cols, ["inss"], allow_partial=False)

    idx_irrf_sal = _find_col_index(header_cols, ["irrf salario"])
    idx_irrf_fer = _find_col_index(header_cols, ["irrf ferias"])
    idx_irrf_13 = _find_col_index(header_cols, ["irrf 13", "irrf 13º", "irrf 13o"])
    idx_inss_sal = _find_col_index(header_cols, ["inss salario"])
    idx_inss_fer = _find_col_index(header_cols, ["inss ferias"])
    idx_inss_13 = _find_col_index(header_cols, ["inss 13", "inss 13º", "inss 13o"])

    if idx_pg is None:
        return resultado, ["Coluna de data de pagamento nao encontrada."]

    for linha in linhas_tabela[header_idx + 1 :]:
        if re.search(r"^\|\s*:?-+", linha):
            continue

        cols = [c.strip() for c in linha.strip("|").split("|")]
        if len(cols) <= idx_pg:
            continue

        data_pg = _parse_data_br(cols[idx_pg].replace("**", ""))
        if not data_pg:
            continue

        irrf_total = _parse_valor_moeda(cols[idx_irrf_total]) if idx_irrf_total is not None and idx_irrf_total < len(cols) else None
        inss_total = _parse_valor_moeda(cols[idx_inss_total]) if idx_inss_total is not None and idx_inss_total < len(cols) else None

        irrf_sal = _parse_valor_moeda(cols[idx_irrf_sal]) if idx_irrf_sal is not None and idx_irrf_sal < len(cols) else None
        irrf_fer = _parse_valor_moeda(cols[idx_irrf_fer]) if idx_irrf_fer is not None and idx_irrf_fer < len(cols) else None
        irrf_13 = _parse_valor_moeda(cols[idx_irrf_13]) if idx_irrf_13 is not None and idx_irrf_13 < len(cols) else None
        inss_sal = _parse_valor_moeda(cols[idx_inss_sal]) if idx_inss_sal is not None and idx_inss_sal < len(cols) else None
        inss_fer = _parse_valor_moeda(cols[idx_inss_fer]) if idx_inss_fer is not None and idx_inss_fer < len(cols) else None
        inss_13 = _parse_valor_moeda(cols[idx_inss_13]) if idx_inss_13 is not None and idx_inss_13 < len(cols) else None

        irrf = irrf_total if irrf_total is not None else _sum_dec(irrf_sal, irrf_fer, irrf_13)
        inss = inss_total if inss_total is not None else _sum_dec(inss_sal, inss_fer, inss_13)

        mes = cols[idx_mes].replace("**", "") if idx_mes is not None and idx_mes < len(cols) else ""
        bruto = cols[idx_bruto].replace("**", "") if idx_bruto is not None and idx_bruto < len(cols) else ""
        liquido_txt = cols[idx_liquido].replace("**", "") if idx_liquido is not None and idx_liquido < len(cols) else ""
        bruto_valor = _parse_valor_moeda(bruto)
        liquido_valor = _parse_valor_moeda(liquido_txt)
        tipo_raw = cols[idx_tipo].replace("**", "") if idx_tipo is not None and idx_tipo < len(cols) else ""
        tipo_base = tipo_raw if tipo_raw else bruto
        if irrf_13 is not None or inss_13 is not None:
            tipo_pag = "13º Salário"
        elif irrf_fer is not None or inss_fer is not None:
            tipo_pag = "Pag. Ferias"
        else:
            tipo_pag = _tipo_pagamento_tabela(tipo_base)

        resultado.append(
            RowTabela(
                mes_ref=mes,
                data_pagamento=data_pg,
                irrf_valor=irrf,
                bruto_valor=bruto_valor,
                liquido_valor=liquido_valor,
                inss_valor=inss,
                tipo_pagamento=tipo_pag,
                bruto_texto=bruto,
                linha_original=linha,
            )
        )

    if not resultado:
        erros.append("Nenhuma linha valida encontrada na tabela colada.")

    return resultado, erros


def parse_tabela_markdown_preview(texto: str) -> tuple[list[str], list[list[str]]]:
    linhas = [l.strip() for l in (texto or "").splitlines() if l.strip() and "|" in l]
    if not linhas:
        return [], []

    headers: list[str] = []
    rows: list[list[str]] = []

    for linha in linhas:
        # Ignora separador markdown: | :--- | :--- |
        if re.search(r"^\|\s*:?-+", linha):
            continue

        cols = [c.strip().replace("**", "") for c in linha.strip("|").split("|")]
        if not any(cols):
            continue

        if not headers:
            headers = cols
            continue

        # Ajusta tamanho da linha para bater com cabecalho
        if len(cols) < len(headers):
            cols += [""] * (len(headers) - len(cols))
        elif len(cols) > len(headers):
            cols = cols[: len(headers)]

        rows.append(cols)

    return headers, rows


def calcular_totalizadores(dados_banco: list[RowBanco], dados_tabela: list[RowTabela]) -> dict[str, str]:
    total_bruto_banco = sum((b.valor_bruto for b in dados_banco), Decimal("0.00"))
    total_liquido_banco = sum((b.valor_liquido for b in dados_banco), Decimal("0.00"))
    total_irrf_banco = sum((b.valor_irrf for b in dados_banco), Decimal("0.00"))
    total_inss_banco = sum((b.valor_inss for b in dados_banco), Decimal("0.00"))

    total_bruto_tabela = sum((r.bruto_valor or Decimal("0.00") for r in dados_tabela), Decimal("0.00"))
    total_irrf_tabela = sum((r.irrf_valor or Decimal("0.00") for r in dados_tabela), Decimal("0.00"))
    total_inss_tabela = sum((r.inss_valor or Decimal("0.00") for r in dados_tabela), Decimal("0.00"))

    total_bruto_sem_inss_banco = total_bruto_banco - total_inss_banco
    total_bruto_sem_inss_tabela = total_bruto_tabela - total_inss_tabela

    total_ferias_banco = sum(
        (b.valor_bruto for b in dados_banco if _tipo_pagamento_banco(b.tipo_pagamento) == "Pag. Ferias"),
        Decimal("0.00"),
    )
    total_irrf_ferias_banco = sum(
        (b.valor_irrf for b in dados_banco if _tipo_pagamento_banco(b.tipo_pagamento) == "Pag. Ferias"),
        Decimal("0.00"),
    )
    total_comissoes_banco = sum(
        (b.valor_bruto for b in dados_banco if _tipo_pagamento_banco(b.tipo_pagamento) == "Comissões (PLR)"),
        Decimal("0.00"),
    )
    total_salarios_banco = sum(
        (b.valor_bruto for b in dados_banco if _tipo_pagamento_banco(b.tipo_pagamento) == "Salários"),
        Decimal("0.00"),
    )
    total_irrf_salarios_banco = sum(
        (b.valor_irrf for b in dados_banco if _tipo_pagamento_banco(b.tipo_pagamento) == "Salários"),
        Decimal("0.00"),
    )
    total_irrf_decimo_banco = sum(
        (b.valor_irrf for b in dados_banco if _tipo_pagamento_banco(b.tipo_pagamento) == "13º Salário"),
        Decimal("0.00"),
    )

    total_ferias_tabela = sum(
        (r.bruto_valor or Decimal("0.00") for r in dados_tabela if r.tipo_pagamento == "Pag. Ferias"),
        Decimal("0.00"),
    )
    total_comissoes_tabela = sum(
        (r.bruto_valor or Decimal("0.00") for r in dados_tabela if r.tipo_pagamento == "Comissões (PLR)"),
        Decimal("0.00"),
    )
    total_salarios_tabela = sum(
        (r.bruto_valor or Decimal("0.00") for r in dados_tabela if r.tipo_pagamento == "Salários"),
        Decimal("0.00"),
    )
    total_decimo_tabela = sum(
        (r.bruto_valor or Decimal("0.00") for r in dados_tabela if r.tipo_pagamento == "13º Salário"),
        Decimal("0.00"),
    )

    return {
        "banco_valor_liquido": _fmt_money(total_liquido_banco),
        "banco_valor_bruto": _fmt_money(total_bruto_banco),
        "banco_bruto_sem_inss": _fmt_money(total_bruto_sem_inss_banco),
        "banco_valor_irrf": _fmt_money(total_irrf_banco),
        "banco_valor_inss": _fmt_money(total_inss_banco),
        "tabela_bruto": _fmt_money(total_bruto_tabela),
        "tabela_bruto_sem_inss": _fmt_money(total_bruto_sem_inss_tabela),
        "tabela_irrf": _fmt_money(total_irrf_tabela),
        "tabela_inss": _fmt_money(total_inss_tabela),
        "banco_ferias": _fmt_money(total_ferias_banco),
        "banco_irrf_ferias": _fmt_money(total_irrf_ferias_banco),
        "banco_irrf_decimo": _fmt_money(total_irrf_decimo_banco),
        "banco_irrf_salarios": _fmt_money(total_irrf_salarios_banco),
        "banco_comissoes": _fmt_money(total_comissoes_banco),
        "banco_salarios": _fmt_money(total_salarios_banco),
        "tabela_ferias": _fmt_money(total_ferias_tabela),
        "tabela_comissoes": _fmt_money(total_comissoes_tabela),
        "tabela_salarios": _fmt_money(total_salarios_tabela),
        "tabela_decimo": _fmt_money(total_decimo_tabela),
    }


def comparar(dados_banco: list[RowBanco], dados_tabela: list[RowTabela]) -> dict[str, Any]:
    usados: set[int] = set()
    comparados: list[dict[str, Any]] = []

    total_divergencia = Decimal("0.00")
    total_iguais = 0
    total_data_errada = 0
    total_divergente = 0

    for row in dados_tabela:
        if row.irrf_valor is None:
            idx_alt, banco_alt, dias_alt = localizar_sem_irrf_por_data_valor(dados_banco, usados, row)

            if idx_alt is not None and banco_alt is not None:
                usados.add(idx_alt)
                data_banco_alt = _normalizar_data_banco(banco_alt.data_pagamento)
                info_match = _match_info_bruto_liquido(banco_alt, row)
                criterio = info_match[0] if info_match else "Bruto/Liquido"
                valor_ref_tabela = _fmt_money(info_match[1]) if info_match else "-"
                valor_ref_banco = _fmt_money(info_match[2]) if info_match else "-"
                if dias_alt == 0:
                    status_alt = "Localizado por Bruto/Liquido (IRRF vazio/isento)"
                    obs_alt = (
                        f"Linha sem IRRF localizada por {criterio}. "
                        "Valores exibidos sao do criterio de localizacao."
                    )
                else:
                    status_alt = "Localizado por Bruto/Liquido (data divergente)"
                    obs_alt = (
                        f"Linha sem IRRF localizada por {criterio}, "
                        f"com diferenca de {dias_alt} dia(s)."
                    )

                comparados.append(
                    {
                        "mes_ref": row.mes_ref,
                        "data_tabela": _fmt_data(row.data_pagamento),
                        "valor_tabela": valor_ref_tabela,
                        "status": status_alt,
                        "cod_fin": banco_alt.cod_fin,
                        "data_banco": _fmt_data(data_banco_alt),
                        "valor_banco": valor_ref_banco,
                        "diferenca": "-",
                        "dias_diff": dias_alt if dias_alt is not None else "-",
                        "obs": obs_alt,
                    }
                )
                continue

            comparados.append(
                {
                    "mes_ref": row.mes_ref,
                    "data_tabela": _fmt_data(row.data_pagamento),
                    "valor_tabela": _fmt_money(row.irrf_valor),
                    "status": "Ignorado (IRRF vazio/isento)",
                    "cod_fin": "",
                    "data_banco": "",
                    "valor_banco": "",
                    "diferenca": "-",
                    "dias_diff": "-",
                    "obs": "Linha sem IRRF e sem correspondencia por data + bruto/liquido.",
                }
            )
            continue

        candidatos_mesma_data = [
            (idx, b)
            for idx, b in enumerate(dados_banco)
            if idx not in usados and _normalizar_data_banco(b.data_pagamento) == row.data_pagamento
        ]

        escolhido_idx = None
        escolhido_row = None

        if candidatos_mesma_data:
            escolhido_idx, escolhido_row = min(
                candidatos_mesma_data,
                key=lambda item: abs(item[1].valor_irrf - row.irrf_valor),
            )
        else:
            candidatos_valor = [
                (idx, b)
                for idx, b in enumerate(dados_banco)
                if idx not in usados
            ]
            if candidatos_valor:
                escolhido_idx, escolhido_row = min(
                    candidatos_valor,
                    key=lambda item: (
                        abs(item[1].valor_irrf - row.irrf_valor),
                        abs((_normalizar_data_banco(item[1].data_pagamento) - row.data_pagamento).days)
                        if _normalizar_data_banco(item[1].data_pagamento) and row.data_pagamento
                        else 99999,
                    ),
                )

        if escolhido_idx is None or escolhido_row is None:
            comparados.append(
                {
                    "mes_ref": row.mes_ref,
                    "data_tabela": _fmt_data(row.data_pagamento),
                    "valor_tabela": _fmt_money(row.irrf_valor),
                    "status": "Sem correspondencia",
                    "cod_fin": "",
                    "data_banco": "",
                    "valor_banco": "",
                    "diferenca": _fmt_money(row.irrf_valor),
                    "dias_diff": "-",
                    "obs": "Nao foi encontrado registro no banco para confronto.",
                }
            )
            total_divergente += 1
            total_divergencia += abs(row.irrf_valor)
            continue

        usados.add(escolhido_idx)
        data_banco = _normalizar_data_banco(escolhido_row.data_pagamento)
        diff_valor = escolhido_row.valor_irrf - row.irrf_valor
        abs_diff = abs(diff_valor)
        dias_diff_num = (data_banco - row.data_pagamento).days if data_banco else 99999

        if data_banco == row.data_pagamento:
            if abs_diff <= TOLERANCIA_VALOR:
                status = "OK"
                obs = "Data e valor de IRRF conferem."
                total_iguais += 1
            else:
                status = "Divergencia de valor"
                obs = "Data igual, mas valor de IRRF diferente."
                total_divergente += 1
                total_divergencia += abs_diff
        else:
            if abs_diff <= TOLERANCIA_VALOR:
                status = "Valor correto, data errada"
                obs = (
                    "Valor de IRRF confere, mas a data diverge. "
                    f"Diferenca de {abs(dias_diff_num)} dia(s)."
                )
                total_data_errada += 1
            else:
                status = "Data e valor divergentes"
                obs = (
                    "Nao havia data igual; confrontado pelo valor mais proximo."
                )
                total_divergente += 1
                total_divergencia += abs_diff

        comparados.append(
            {
                "mes_ref": row.mes_ref,
                "data_tabela": _fmt_data(row.data_pagamento),
                "valor_tabela": _fmt_money(row.irrf_valor),
                "status": status,
                "cod_fin": escolhido_row.cod_fin,
                "data_banco": _fmt_data(data_banco),
                "valor_banco": _fmt_money(escolhido_row.valor_irrf),
                "diferenca": _fmt_money(diff_valor),
                "dias_diff": abs(dias_diff_num) if data_banco else "-",
                "obs": obs,
            }
        )

    sobrou_banco = [
        {
            "cod_fin": b.cod_fin,
            "data_pagamento": _fmt_data(b.data_pagamento),
            "valor_irrf": _fmt_money(b.valor_irrf),
            "valor_inss": _fmt_money(b.valor_inss),
            "tipo_pagamento": b.tipo_pagamento,
        }
        for idx, b in enumerate(dados_banco)
        if idx not in usados
    ]

    return {
        "linhas": comparados,
        "sobrou_banco": sobrou_banco,
        "resumo": {
            "total_tabela": len(dados_tabela),
            "total_banco": len(dados_banco),
            "total_ok": total_iguais,
            "total_data_errada": total_data_errada,
            "total_divergente": total_divergente,
            "total_divergencia": _fmt_money(total_divergencia),
            "nao_usados_banco": len(sobrou_banco),
        },
    }


app = Flask(__name__)


@app.route("/", methods=["GET", "POST"])
def index() -> str:
    inicio_default = "01/01/2025"
    fim_default = "31/12/2025"

    tabela_colada = ""
    tabela_preview_headers: list[str] = []
    tabela_preview_rows: list[list[str]] = []
    erros: list[str] = []
    resultado = None
    sql_correcao_datas = ""
    totalizadores = None
    dados_banco_view: list[dict[str, Any]] = []

    data_ini = _parse_data_br(request.form.get("data_inicio", inicio_default)) if request.method == "POST" else _parse_data_br(inicio_default)
    data_fim = _parse_data_br(request.form.get("data_fim", fim_default)) if request.method == "POST" else _parse_data_br(fim_default)

    if request.method == "POST":
        tabela_colada = request.form.get("tabela_colada", "")
        tabela_preview_headers, tabela_preview_rows = parse_tabela_markdown_preview(tabela_colada)

        if not data_ini or not data_fim:
            erros.append("Datas invalidas. Use dd/mm/aaaa.")
        elif data_ini > data_fim:
            erros.append("Data inicial maior que data final.")

        dados_banco: list[RowBanco] = []
        if not erros:
            dados_banco, erro_banco = carregar_banco(data_ini, data_fim)
            if erro_banco:
                erros.append(erro_banco)

        if not erros:
            dados_tabela, erros_tabela = parse_tabela_colada(tabela_colada)
            erros.extend(erros_tabela)

        if not erros:
            resultado = comparar(dados_banco, dados_tabela)
            sql_correcao_datas = gerar_sql_correcao_datas(dados_tabela, resultado)
            totalizadores = calcular_totalizadores(dados_banco, dados_tabela)

        dados_banco_view = [
            {
                "cod_fin": b.cod_fin,
                "empregador": b.empregador,
                "valor_bruto": _fmt_money(b.valor_bruto),
                "valor_liquido": _fmt_money(b.valor_liquido),
                "valor_irrf": _fmt_money(b.valor_irrf),
                "valor_inss": _fmt_money(b.valor_inss),
                "data_pagamento": _fmt_data(b.data_pagamento),
                "tipo_pagamento": b.tipo_pagamento,
            }
            for b in dados_banco
        ]

    return render_template(
        "irrf_confronto.html",
        erros=erros,
        resultado=resultado,
        tabela_colada=tabela_colada,
        tabela_preview_headers=tabela_preview_headers,
        tabela_preview_rows=tabela_preview_rows,
        sql_correcao_datas=sql_correcao_datas,
        totalizadores=totalizadores,
        dados_banco=dados_banco_view,
        data_inicio=request.form.get("data_inicio", inicio_default),
        data_fim=request.form.get("data_fim", fim_default),
    )


if __name__ == "__main__":
    app.run(debug=True, port=5012)
