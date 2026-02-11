# Este script extrai informações de boletos de gás (Ultragaz) em PDF.
from __future__ import annotations
import re
import sys
from pathlib import Path
from typing import List
# import copyright_delean 
# copyright_delean.copyright_delean()

try:
    import pdfplumber
except ImportError as e:
    raise SystemExit("Instale a dependência: pip install pdfplumber") from e


REGEX_LINHA_DIGITAVEL = re.compile(
    r'\b\d{12}\s+\d{12}\s+\d{12}\s+\d{12}\b'
)

REGEX_DATA = re.compile(r'\b(\d{2}/\d{2}/\d{4})\b')


def extract_all_text(pdf_path: Path) -> str:
    texts = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            # Ajustes de tolerância ajudam a juntar palavras corretamente
            txt = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            texts.append(txt)
    return "\n".join(texts)


def find_linha_digitavel(text: str) -> str | None:
    """Encontra a linha digitável no formato específico do boleto de gás."""
    m = REGEX_LINHA_DIGITAVEL.search(text)
    if not m:
        return None
    return re.sub(r'\s', '', m.group(0))


def find_dados_principais(lines: List[str]) -> dict:
    """
    Encontra os dados principais do boleto (demonstrativo, datas, valor).
    Esses dados geralmente aparecem juntos em duas linhas consecutivas.
    """
    dados = {
        "demonstrativo_numero": None,
        "data_emissao": None,
        "mes_referencia": None,
        "data_vencimento": None,
        "valor_total": None
    }
    
    for i, line in enumerate(lines):
        # Procura pela linha de cabeçalho
        if 'Demonstrativo Nro.' in line and 'Vencimento' in line:
            # A próxima linha deve ter os valores
            if i + 1 < len(lines):
                valores_line = lines[i + 1].strip()
                # Padrão: NUMERO DATA1 MESREF DATA2 VALOR
                # Exemplo: 1001474144 16/01/2026 01/2026 25/02/2026 44.69
                # Aceita tanto vírgula quanto ponto no valor
                pattern = r'(\d+)\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(\d+[.,]\d+)'
                m = re.search(pattern, valores_line)
                if m:
                    dados["demonstrativo_numero"] = m.group(1)
                    dados["data_emissao"] = m.group(2)
                    dados["mes_referencia"] = m.group(3)
                    dados["data_vencimento"] = m.group(4)
                    # Normalizar valor para formato brasileiro (vírgula)
                    valor = m.group(5).replace('.', ',')
                    dados["valor_total"] = valor
                    break
    
    return dados


def find_codigo_cliente(lines: List[str]) -> str | None:
    """Encontra o código do cliente."""
    for i, line in enumerate(lines):
        if 'digo do Cliente' in line:  # Captura "Código" com ou sem acento
            # Procura nas próximas linhas
            for j in range(i, min(i + 3, len(lines))):
                # Busca número que não seja muito longo (código de débito é mais longo)
                match = re.search(r'\b(\d{7,10})\b', lines[j])
                if match:
                    return match.group(1)
    return None


def find_codigo_debito_auto(lines: List[str]) -> str | None:
    """Encontra o código para débito automático."""
    for i, line in enumerate(lines):
        if 'bito Autom' in line:  # Captura "Débito Autom." com ou sem acento
            # Procura nas próximas linhas
            for j in range(i, min(i + 3, len(lines))):
                # Código de débito geralmente tem 17 dígitos
                match = re.search(r'\b(\d{15,20})\b', lines[j])
                if match:
                    return match.group(1)
    return None


def find_consumo_atual(lines: List[str]) -> tuple[str | None, str | None]:
    """
    Encontra o consumo atual (m³ e kg).
    Retorna uma tupla (volume_m3, volume_kg).
    """
    for i, line in enumerate(lines):
        # Procura pela linha que contém "Consumo Mês Atual"
        if 's Atual' in line:  # "Mês Atual" com ou sem acento
            # Nas próximas linhas, procura pelo padrão de consumo
            # Exemplo: "2.3 7.032 2.763 6.355"
            # Onde: fator_conversao valor_unit vol_m3 vol_kg
            for j in range(i, min(i + 5, len(lines))):
                # Busca 4 números decimais separados por espaços
                match = re.search(r'(\d+,\d+)\s+(\d+,\d+)\s+(\d+,\d+)\s+(\d+,\d+)', lines[j])
                if match:
                    # O terceiro e quarto valores são volume m³ e kg
                    return match.group(3), match.group(4)
    return None, None


def montar_output(dados: dict) -> str:
    partes = []
    
    if dados.get("demonstrativo_numero"):
        partes.append(f"Demonstrativo Nro.: {dados['demonstrativo_numero']}")
    if dados.get("data_emissao"):
        partes.append(f"Data de Emissão: {dados['data_emissao']}")
    if dados.get("mes_referencia"):
        partes.append(f"Mês de Referência: {dados['mes_referencia']}")
    if dados.get("data_vencimento"):
        partes.append(f"Data de Vencimento: {dados['data_vencimento']}")
    if dados.get("valor_total"):
        partes.append(f"Valor Total a Pagar: {dados['valor_total']}")
    if dados.get("codigo_cliente"):
        partes.append(f"Código do Cliente: {dados['codigo_cliente']}")
    if dados.get("codigo_debito_auto"):
        partes.append(f"Código para Débito Autom.: {dados['codigo_debito_auto']}")
    if dados.get("linha_digitavel"):
        partes.append(f"Linha Digitável: {dados['linha_digitavel']}")
    if dados.get("consumo_m3") or dados.get("consumo_kg"):
        partes.append("")  # linha em branco
        partes.append("Consumo Atual:")
        if dados.get("consumo_m3"):
            partes.append(f"  Volume (m³): {dados['consumo_m3']}")
        if dados.get("consumo_kg"):
            partes.append(f"  Volume (kg): {dados['consumo_kg']}")
    
    return "\n".join(partes)


def process_pdf(pdf_path: Path, output_path: Path | None = None) -> Path:
    text = extract_all_text(pdf_path)
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    
    # Extrair dados principais
    dados_principais = find_dados_principais(lines)
    consumo_m3, consumo_kg = find_consumo_atual(lines)
    
    dados = {
        "demonstrativo_numero": dados_principais["demonstrativo_numero"],
        "data_emissao": dados_principais["data_emissao"],
        "mes_referencia": dados_principais["mes_referencia"],
        "data_vencimento": dados_principais["data_vencimento"],
        "valor_total": dados_principais["valor_total"],
        "codigo_cliente": find_codigo_cliente(lines),
        "codigo_debito_auto": find_codigo_debito_auto(lines),
        "linha_digitavel": find_linha_digitavel(text),
        "consumo_m3": consumo_m3,
        "consumo_kg": consumo_kg,
    }

    out_text = montar_output(dados)

    if not output_path:
        output_path = pdf_path.with_suffix(".txt")
    output_path.write_text(out_text, encoding="utf-8")
    return output_path


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("Uso: python boleto_gas.py <arquivo.pdf> [saida.txt]")
        return 1
    pdf_path = Path(argv[1])
    if not pdf_path.is_file():
        print("Arquivo PDF não encontrado.")
        return 2
    out_path = Path(argv[2]) if len(argv) > 2 else None
    out = process_pdf(pdf_path, out_path)
    print(f"Arquivo gerado: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
