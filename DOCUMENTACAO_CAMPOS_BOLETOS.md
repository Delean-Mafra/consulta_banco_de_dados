# Documentação: Campos de Boletos e Atualização SQL

## Resumo Rápido

✅ **DATA DE EMISSÃO**: Sempre extraída e atualizada como `DATA_EMISSAO` na tabela LANC_FINANCEIRO  
✅ **VALOR DO BOLETO**: Sempre extraído e atualizado em 4 campos SQL  
✅ **PDF DESBLOQUEADO**: Automaticamente desbloqueado antes do processamento

---

## 1. ONDE ESTÃO OS DADOS?

### Boleto de Condomínio

| Campo | Onde Vem | Campo SQL |
|-------|----------|-----------|
| **Data de Emissão** | `data_documento` (ou `data_emissao`) | `DATA_EMISSAO` |
| **Valor** | `valor_documento` | Vários campos (ver abaixo) |
| **Data de Vencimento** | `data_vencimento` | `DATA_VENCIMENTO` |
| **Número do Doc** | `numero_documento` | `NUM_DOC` |
| **Nosso Número** | `nosso_numero` | `NOSSO_NUMERO` |
| **Linha Digitável** | `linha_digitavel` | `LINHA_DIGITAVEL` |

**Exemplo de saída:**
```
Linha Digitável: 12345.67890 12345.678901 12345.678901 1 12345678901234
Data do Documento: 10/01/2026
Data de Vencimento: 25/02/2026
Nosso Número: 12/123456-7
Valor Documento: 1.234,56
Número do documento: 123456
```

---

### Boleto de Faculdade

**Mesmes campos que condomínio**, apenas layout do PDF diferente.

---

### Boleto de Gás (Ultragaz)

| Campo | Onde Vem | Campo SQL |
|-------|----------|-----------|
| **Data de Emissão** | `data_emissao` | `DATA_EMISSAO` |
| **Valor** | `valor_total` | Vários campos (ver abaixo) |
| **Data de Vencimento** | `data_vencimento` | `DATA_VENCIMENTO` |
| **Número do Doc** | `demonstrativo_numero` | `NUM_DOC` |
| **Linha Digitável** | `linha_digitavel` | `LINHA_DIGITAVEL` |
| **Código Cliente** | `codigo_cliente` | (armazenado em sessão) |
| **Consumo (m³)** | `consumo_gas['volume_m3']` | (info adicional) |
| **Consumo (kg)** | `consumo_gas['volume_kg']` | (info adicional) |

**Exemplo de saída:**
```
Demonstrativo Nro.: 1001474144
Data de Emissão: 16/01/2026
Mês de Referência: 01/2026
Data de Vencimento: 25/02/2026
Valor Total a Pagar: 44,69
Código do Cliente: 3017482
Código para Débito Autom.: 10000030174820016
Linha Digitável: 836800000009446901372024602251001478414400302462

Consumo Atual:
  Volume (m³): 2,763
  Volume (kg): 6,355
```

---

## 2. CAMPOS SQL ATUALIZADOS

Quando você clica em "Atualizar Banco", o sistema executa um UPDATE na tabela `LANC_FINANCEIRO`:

```sql
UPDATE LANC_FINANCEIRO SET
    LINHA_DIGITAVEL = ?,           -- 837 (todos)
    DATA_VENCIMENTO = ?,            -- 373 (todos)
    DATA_EMISSAO = ?,               -- 376 (todos)
    VALOR_PREVISTO = ?,             -- 380
    VALOR_PREVISTO_RESTANTE = ?,   -- 383
    VALOR_A_AMORTIZAR = ?,          -- 386
    VALOR_PRESENTE = ?,             -- 389
    NUM_DOC = ?,                    -- 390
    NOSSO_NUMERO = ?                -- 394
WHERE COD_FIN = ?
```

### Detalhes de cada campo:

1. **LINHA_DIGITAVEL** (linha 368-370)
   - Vem de: `linha_digitavel`
   - Presente em: todos os 3 tipos

2. **DATA_VENCIMENTO** (linha 373-375)
   - Vem de: `data_vencimento`
   - Presente em: todos os 3 tipos

3. **DATA_EMISSAO** (linha 376-378) ⭐ **DATA DE EMISSÃO**
   - Vem de: `data_documento` (condomínio/faculdade) ou `data_emissao` (gás)
   - **Sempre atualizado**
   - Presente em: todos os 3 tipos

4. **VALOR (4 campos)** (linha 380-389)
   - Vem de: `valor_documento` (condomínio/faculdade) ou `valor_total` (gás)
   - Campos atualizados:
     - `VALOR_PREVISTO`
     - `VALOR_PREVISTO_RESTANTE`
     - `VALOR_A_AMORTIZAR`
     - `VALOR_PRESENTE`

5. **NUM_DOC** (linha 390-392)
   - Vem de: `numero_documento` (condomínio/faculdade) ou `demonstrativo_numero` (gás)
   - Presente em: todos os 3 tipos

6. **NOSSO_NUMERO** (linha 394-396)
   - Vem de: `nosso_numero`
   - Presente em: condomínio e faculdade apenas

---

## 3. FLUXO DE PROCESSAMENTO

### Quando você faz upload do PDF:

```
1. PDF é salvo temporariamente
   ↓
2. ✅ DESBLOQUEIO AUTOMÁTICO (linha 244-246)
   → desbloquear_pdf(filepath)
   → Remove proteção se houver
   ↓
3. DETECÇÃO DE TIPO (linha 250)
   → detect_boleto_type(filepath)
   → Retorna: 'condominio', 'faculdade' ou 'gas'
   ↓
4. PROCESSAMENTO (linha 256-261)
   → process_pdf_condominio() ou
   → process_pdf_faculdade() ou
   → process_pdf_gas()
   ↓
5. EXTRAÇÃO DE DADOS
   → Gera arquivo .txt com dados extraídos
   ↓
6. PARSING (linha 267)
   → parse_extracted_data()
   → Converte .txt em dicionário Python
   ↓
7. ARMAZENAMENTO (linha 271)
   → session['boleto_data'] = dados parseados
   ↓
8. EXIBIÇÃO (linha 273)
   → Mostra resultado para usuário em HTML
   ↓
9. ATUALIZAÇÃO (quando usuário clica "Atualizar")
   → atualizar_banco()
   → Usa dados da sessão
   → Executa UPDATE no SQL (linhas 317-415)
```

---

## 4. CÓDIGO-CHAVE

### Desbloqueio PDF (linhas 244-246)
```python
# Primeiro tenta desbloquear o PDF se estiver protegido
print(f"Verificando se o PDF está bloqueado...")
desbloquear_pdf(filepath)
print(f"PDF desbloqueado (se necessário)")
```

### Atualização SQL - DATA_EMISSAO (linhas 376-378)
```python
if data_emissao:
    campos_update.append('DATA_EMISSAO = ?')
    valores_update.append(data_emissao)
```

### Atualização SQL - VALOR (linhas 380-389)
```python
if valor_documento:
    campos_update.append('VALOR_PREVISTO = ?')
    valores_update.append(valor_documento)
    campos_update.append('VALOR_PREVISTO_RESTANTE = ?')
    valores_update.append(valor_documento)
    campos_update.append('VALOR_A_AMORTIZAR = ?')
    valores_update.append(valor_documento)
    campos_update.append('VALOR_PRESENTE = ?')
    valores_update.append(valor_documento)
```

---

## 5. TESTE RÁPIDO

Para verificar se tudo está funcionando:

```python
import sys
sys.path.insert(0, r'\Python\complementos\banco_de_dados')

from db_app_boleto import parse_extracted_data

# Teste com dados de condomínio
dados = """Linha Digitável: 123...
Data do Documento: 10/01/2026
Data de Vencimento: 25/02/2026
Nosso Número: 12/123456-7
Valor Documento: 1.234,56"""

resultado = parse_extracted_data(dados)
print(f"data_emissao: {resultado.get('data_emissao')}")
print(f"valor_documento: {resultado.get('valor_documento')}")
```

---

## 6. RESUMO FINAL

| Pergunta | Resposta | Linha |
|----------|----------|-------|
| Aonde está DATA_EMISSAO? | Em `data_documento` ou `data_emissao` | parse_extracted_data() |
| É atualizado no SQL? | **SIM** | 376-378 |
| Aonde está o VALOR? | Em `valor_documento` ou `valor_total` | parse_extracted_data() |
| É atualizado no SQL? | **SIM**, em 4 campos | 380-389 |
| PDF é desbloqueado automaticamente? | **SIM** | 244-246 |
| Quando é desbloqueado? | **ANTES** de processar | Ordem: desbloquear → detectar → processar |

---

**Data: 10/02/2026**  
**Status: ✅ Todos os campos implementados e testados**


