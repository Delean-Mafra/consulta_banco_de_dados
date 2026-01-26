# Este script extrai informações de boletos de condomínio em PDF.
from __future__ import annotations
import re
import sys
from pathlib import Path
from typing import List, Tuple
import copyright_delean 
copyright_delean.copyright_delean()

try:
    import pdfplumber
except ImportError as e:
    raise SystemExit("Instale a dependência: pip install pdfplumber") from e


REGEX_LINHA_DIGITAVEL = re.compile(
    r'\b\d{5}\.\d{5}\s+\d{5}\.\d{6}\s+\d{5}\.\d{6}\s+\d\s+\d{10,}\b'
)

REGEX_DATA = re.compile(r'\b(\d{2}/\d{2}/\d{4})\b')
REGEX_NOSSO_NUMERO_LABEL = re.compile(r'^\s*Nosso Número\s*$', re.IGNORECASE)
REGEX_NOSSO_NUMERO_VALUE = re.compile(r'^\s*\d{2}/\d{6,}-\d\b')
REGEX_VALOR_DOC_LABEL = re.compile(r'^\s*Valor Documento\s*$', re.IGNORECASE)
REGEX_VALOR_RS = re.compile(r'R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})')
REGEX_NUMERO_DOC_LABEL = re.compile(r'^\s*N[úu]mero do documento\s*$', re.IGNORECASE)
REGEX_ZEROS_NUMDOC = re.compile(r'^0+(\d+)$')

# Descrições de rateio começam com estas palavras
RATEIO_PREFIXOS = ("RATEIO", "CONSUMO", "TAXA", "FUNDO", "COBRANÇA", "COBRANCA")

REGEX_LINHA_RATEIO = re.compile(
    r'(?P<desc>(?:RATEIO|CONSUMO|TAXA|FUNDO|COBRANÇA)[A-Z0-9ÁÉÍÓÚÂÊÔÃÕÇ \-\./()%:]+?)\s+R\$\s*(?P<valor>\d{1,3}(?:\.\d{3})*,\d{2})'
)


def extract_all_text(pdf_path: Path) -> str:
    texts = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            # Ajustes de tolerância ajudam a juntar palavras corretamente
            txt = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
            texts.append(txt)
    return "\n".join(texts)


def find_linha_digitavel(text: str) -> str | None:
    m = REGEX_LINHA_DIGITAVEL.search(text)
    if not m:
        return None
    return re.sub(r'[.\s]', '', m.group(0))


def find_after_label(lines: List[str], label_regex: re.Pattern, value_regex: re.Pattern | None = None) -> str | None:
    for i, line in enumerate(lines):
        if label_regex.match(line):
            # valor pode estar na linha seguinte ou própria linha (se layout variar)
            candidates = []
            if i + 1 < len(lines):
                candidates.append(lines[i + 1])
            candidates.append(line)  # fallback
            for c in candidates:
                if value_regex:
                    vm = value_regex.search(c.strip())
                    if vm:
                        return vm.group(0).strip()
                else:
                    return c.strip()
    return None


def find_data_doc(lines: List[str]) -> str | None:
    # Procura linha "Data do Documento" e pega primeira data após
    for i, l in enumerate(lines):
        if re.search(r'Data do Documento', l, re.IGNORECASE):
            # olhar mesma linha e 3 seguintes
            window = lines[i:i+4]
            for w in window:
                dm = REGEX_DATA.search(w)
                if dm:
                    return dm.group(1)
    # fallback: primeira data no documento
    m = REGEX_DATA.search("\n".join(lines))
    return m.group(1) if m else None


def find_valor_documento(lines: List[str]) -> str | None:
    # Primeiro tenta encontrar próximo ao label "Valor Documento"
    for i, l in enumerate(lines):
        if REGEX_VALOR_DOC_LABEL.match(l):
            window = lines[i:i+4]
            for w in window:
                vm = REGEX_VALOR_RS.search(w)
                if vm:
                    return vm.group(1) 
    
    # Se não encontrar, procura por valores maiores (provavelmente o valor total)
    valores_encontrados = []
    for line in lines:
        matches = REGEX_VALOR_RS.findall(line)
        for match in matches:
            # Converte para float para comparar
            valor_num = float(match.replace('.', '').replace(',', '.'))
            valores_encontrados.append((valor_num, match))
    
    # Retorna o maior valor encontrado (provavelmente o valor total do boleto)
    if valores_encontrados:
        valores_encontrados.sort(reverse=True)
        return valores_encontrados[0][1]
    
    return None


def find_numero_documento(lines: List[str]) -> str | None:
    # Busca por "Número do documento" seguido do valor na próxima linha
    for i, l in enumerate(lines):
        if REGEX_NUMERO_DOC_LABEL.match(l):
            if i + 1 < len(lines):
                raw = lines[i + 1].strip()
                raw = raw.replace(" ", "")
                m = REGEX_ZEROS_NUMDOC.match(raw)
                return m.group(1) if m else raw.lstrip("0") or raw
    
    # Fallback: busca por padrão "000000001113405" diretamente no texto
    for line in lines:
        # Procura por sequência de números com zeros à esquerda (pelo menos 10 dígitos)
        matches = re.findall(r'\b0+(\d{6,})\b', line)
        if matches:
            # Retorna o primeiro match sem os zeros à esquerda
            return matches[0]
    
    # Outro fallback: busca em linha que contém "Número do documento" na mesma linha
    for line in lines:
        if 'número do documento' in line.lower():
            # Procura por números na mesma linha
            matches = re.findall(r'\b0+(\d{6,})\b', line)
            if matches:
                return matches[0]
            # Se não encontrar com zeros, procura qualquer sequência longa de números
            matches = re.findall(r'\b(\d{10,})\b', line)
            if matches:
                return matches[0].lstrip("0") or matches[0]
    
    return None


def find_nosso_numero(lines: List[str]) -> str | None:
    for i, l in enumerate(lines):
        if REGEX_NOSSO_NUMERO_LABEL.match(l):
            if i + 1 < len(lines):
                val_line = lines[i + 1].strip()
                if REGEX_NOSSO_NUMERO_VALUE.match(val_line):
                    return val_line
    # fallback: busca padrão genérico  dd/dddddd-d
    pattern = re.compile(r'\b\d{2}/\d{6,}-\d\b')
    for l in lines:
        m = pattern.search(l)
        if m:
            return m.group(0)
    return None


def find_rateios(lines: List[str]) -> List[Tuple[str, str]]:
    rateios = []
    
    # Buscar todas as ocorrências de R$ seguido de valor na mesma linha que contém rateios
    for line in lines:
        # Busca todos os valores R$ na linha
        valores_encontrados = re.finditer(r'R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})', line)
        
        for valor_match in valores_encontrados:
            valor = valor_match.group(1)
            valor_pos = valor_match.start()
            
            # Busca a descrição antes do valor na mesma linha
            texto_antes = line[:valor_pos]
            
            # Procura por descrições de rateio no texto antes do valor
            for prefix in RATEIO_PREFIXOS:
                # Busca a última ocorrência do prefixo antes do valor
                prefix_matches = list(re.finditer(re.escape(prefix), texto_antes, re.IGNORECASE))
                if prefix_matches:
                    ultimo_match = prefix_matches[-1]
                    inicio_desc = ultimo_match.start()
                    
                    # Extrai a descrição do prefixo até antes do valor
                    descricao = texto_antes[inicio_desc:].strip()
                    
                    # Limpa a descrição removendo números negativos e outras sujeiras
                    descricao = re.sub(r'\s*-\d+[.,]\d+.*$', '', descricao).strip()
                    descricao = re.sub(r'\s+', ' ', descricao)  # normaliza espaços
                    
                    if descricao and len(descricao) > 3:  # só aceita descrições com pelo menos 4 caracteres
                        rateios.append((descricao, valor))
                        break
    
    # Se não encontrou, tenta a estratégia anterior
    if len(rateios) < 3:
        # Primeiro tenta capturar rateios em uma linha com regex original
        for l in lines:
            line = " ".join(l.strip().split())  # normaliza múltiplos espaços
            m = REGEX_LINHA_RATEIO.search(line)
            if m:
                desc = m.group('desc').strip()
                val = m.group('valor').strip()
                rateios.append((desc, val))
        
        # Se ainda não encontrou muitos, tenta estratégia linha por linha
        if len(rateios) < 3:
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                # Verifica se linha começa com prefixo de rateio
                if any(line.startswith(prefix) for prefix in RATEIO_PREFIXOS):
                    desc = line
                    # Procura valor nas próximas 3 linhas
                    for j in range(i+1, min(i+4, len(lines))):
                        next_line = lines[j].strip()
                        valor_match = re.search(r'R\$\s*(\d{1,3}(?:\.\d{3})*,\d{2})', next_line)
                        if valor_match:
                            valor = valor_match.group(1)
                            rateios.append((desc, valor))
                            i = j  # pula para depois do valor encontrado
                            break
                i += 1
    
    # Remover duplicados mantendo ordem
    seen = set()
    unique = []
    for d, v in rateios:
        key = (d, v)
        if key not in seen:
            seen.add(key)
            unique.append((d, v))
    return unique


def montar_output(dados: dict) -> str:
    partes = []
    if dados.get("linha_digitavel"):
        partes.append(f"Linha Digitável: {dados['linha_digitavel']}")
    if dados.get("data_documento"):
        partes.append(f"Data do Documento: {dados['data_documento']}")
    if dados.get("nosso_numero"):
        partes.append(f"Nosso Número: {dados['nosso_numero']}")
    if dados.get("valor_documento"):
        partes.append(f"Valor Documento: {dados['valor_documento']}")
    if dados.get("numero_documento"):
        partes.append(f"Número do documento: {dados['numero_documento']}")
    if dados.get("rateios"):
        partes.append("")  # linha em branco
        for desc, val in dados["rateios"]:
            partes.append(f"{desc}")
            partes.append(f"R$ {val}")
            partes.append("")  # linha em branco entre itens
        if partes[-1] == "":
            partes.pop()
    return "\n".join(partes)


def process_pdf(pdf_path: Path, output_path: Path | None = None) -> Path:
    text = extract_all_text(pdf_path)
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]

    dados = {
        "linha_digitavel": find_linha_digitavel(text),
        "data_documento": find_data_doc(lines),
        "nosso_numero": find_nosso_numero(lines),
        "valor_documento": find_valor_documento(lines),
        "numero_documento": find_numero_documento(lines),
        "rateios": find_rateios(lines),
    }

    out_text = montar_output(dados)

    if not output_path:
        output_path = pdf_path.with_suffix(".txt")
    output_path.write_text(out_text, encoding="utf-8")
    return output_path


def main(argv: List[str]) -> int:
    if len(argv) < 2:
        print("Uso: python boleto_condominio.py <arquivo.pdf> [saida.txt]")
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