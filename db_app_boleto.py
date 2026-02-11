# Aplicação Flask para extração de dados de boletos de condomínio.
# Upload de PDF e geração de arquivo TXT com dados extraídos.

from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session, jsonify
import os
import re
import webbrowser
import threading
import time
from pathlib import Path
from werkzeug.utils import secure_filename
import pikepdf
import logging
import pdfplumber
from datetime import datetime
from boleto_condominio import process_pdf as process_pdf_condominio
from boleto_faculdade import process_pdf as process_pdf_faculdade
from boleto_gas import process_pdf as process_pdf_gas
from db_lerconfiguracao import ler_configuracao, get_db
import copyright_delean 
copyright_delean.copyright_delean()

app = Flask(__name__)
app.secret_key = 'sua_chave_secreta_aqui_boleto_2026'
app.config['SESSION_TYPE'] = 'filesystem'

# Desabilitar logs do Flask
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# Instanciar conexão com banco
db = get_db()

# Configurações
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}

# Criar pasta de uploads se não existir
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def desbloquear_pdf(input_pdf):
    """Desbloqueia PDF se estiver protegido por senha ou restrições.
    
    Usa pikepdf para remover restrições de segurança do PDF.
    O arquivo é sobrescrito com a versão desbloqueada.
    """
    try:
        # Tenta abrir o PDF com permissão para sobrescrever
        with pikepdf.open(input_pdf, allow_overwriting_input=True) as pdf:
            # Salva o PDF removendo quaisquer restrições de segurança
            pdf.save(input_pdf)
        print(f'PDF desbloqueado com sucesso: {input_pdf}')
        return True
    except pikepdf.PasswordError:
        # PDF protegido por senha que não pode ser aberta sem a senha
        print(f'PDF protegido por senha (não foi possível desbloquear): {input_pdf}')
        return False
    except Exception as e:
        # Outros erros (arquivo corrompido, não é PDF válido, etc.)
        print(f'Aviso ao processar PDF: {e}')
        return False


def detect_boleto_type(filepath):
    """
    Detecta automaticamente o tipo de boleto (condomínio ou faculdade).
    Retorna: ('condominio', 'faculdade') ou None se não conseguir detectar.
    """
    try:
        with pdfplumber.open(filepath) as pdf:
            # Extrair texto das primeiras páginas
            full_text = ""
            for page in pdf.pages[:2]:  # Verificar apenas as 2 primeiras páginas
                txt = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
                full_text += txt.lower()
        
        # Indicadores de boleto de faculdade
        indicadores_faculdade = [
            'aiua educacional',
            'matrícula',
            'nome do aluno',
            'curso/turno',
            'educacional ltda'
        ]
        
        # Indicadores de boleto de condomínio
        indicadores_condominio = [
            'condomínio',
            'condominio',
            'síndico',
            'sindico',
            'proprietário',
            'proprietario',
            'unidade',
            'bloco'
        ]
        
        # Indicadores de boleto de gás
        indicadores_gas = [
            'ultragaz',
            'demonstrativo de despesas',
            'consumo de gás',
            'consumo de gas',
            'glp granel',
            'mês de referência'
        ]
        
        # Contar indicadores encontrados
        count_faculdade = sum(1 for ind in indicadores_faculdade if ind in full_text)
        count_condominio = sum(1 for ind in indicadores_condominio if ind in full_text)
        count_gas = sum(1 for ind in indicadores_gas if ind in full_text)
        
        print(f"Indicadores faculdade encontrados: {count_faculdade}")
        print(f"Indicadores condomínio encontrados: {count_condominio}")
        print(f"Indicadores gás encontrados: {count_gas}")
        
        # Priorizar gás se tiver indicadores fortes
        if count_gas > 0 and count_gas >= max(count_faculdade, count_condominio):
            return 'gas'
        elif count_faculdade > count_condominio and count_faculdade > 0:
            return 'faculdade'
        elif count_condominio > 0:
            return 'condominio'
        else:
            # Fallback: verificar se tem "Nosso Número" que é padrão em boletos
            if 'nosso número' in full_text or 'nosso numero' in full_text:
                # Tentar ser mais específico
                if 'aluno' in full_text or 'curso' in full_text:
                    return 'faculdade'
                elif 'proprietário' in full_text or 'proprietario' in full_text:
                    return 'condominio'
            return None
    
    except Exception as e:
        print(f'Erro ao detectar tipo de boleto: {e}')
        return None

def open_browser():
    #Abre o navegador após um pequeno delay#
    time.sleep(1.5)
    webbrowser.open('http://127.0.0.1:5000')

def parse_extracted_data(data):
    #Parseia os dados extraídos em campos individuais#
    fields = {}
    lines = data.strip().split('\n')
    
    for line in lines:
        if ':' in line:
            if line.startswith('Linha Digitável:'):
                fields['linha_digitavel'] = line.split(':', 1)[1].strip()
            elif line.startswith('Data do Documento:'):
                data_doc = line.split(':', 1)[1].strip()
                fields['data_documento'] = data_doc
                fields['data_emissao'] = data_doc  # Padronizar com o campo de gás
            elif line.startswith('Data de Vencimento:'):
                fields['data_vencimento'] = line.split(':', 1)[1].strip()
            elif line.startswith('Nosso Número:'):
                fields['nosso_numero'] = line.split(':', 1)[1].strip()
            elif line.startswith('Valor Documento:'):
                fields['valor_documento'] = line.split(':', 1)[1].strip()
            elif line.startswith('Número do documento:'):
                fields['numero_documento'] = line.split(':', 1)[1].strip()
            # Campos específicos de boleto de gás
            elif line.startswith('Demonstrativo Nro.:'):
                fields['demonstrativo_numero'] = line.split(':', 1)[1].strip()
            elif line.startswith('Data de Emissão:'):
                fields['data_emissao'] = line.split(':', 1)[1].strip()
            elif line.startswith('Mês de Referência:'):
                fields['mes_referencia'] = line.split(':', 1)[1].strip()
            elif line.startswith('Valor Total a Pagar:'):
                fields['valor_total'] = line.split(':', 1)[1].strip()
            elif line.startswith('Código do Cliente:'):
                fields['codigo_cliente'] = line.split(':', 1)[1].strip()
            elif line.startswith('Código para Débito Autom.:'):
                fields['codigo_debito_auto'] = line.split(':', 1)[1].strip()
    
    # Processar rateios (para boletos de condomínio e faculdade)
    rateios = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line and not ':' in line and (line.startswith('RATEIO') or line.startswith('CONSUMO') or 
                                        line.startswith('TAXA') or line.startswith('FUNDO') or 
                                        line.startswith('COBRANÇA')):
            if i + 1 < len(lines) and lines[i + 1].startswith('R$'):
                desc = line
                valor = lines[i + 1].replace('R$ ', '').strip()
                rateios.append({'descricao': desc, 'valor': valor})
                i += 2
            else:
                i += 1
        else:
            i += 1
    
    fields['rateios'] = rateios
    
    # Processar consumo de gás (estrutura diferente)
    consumo_gas = {}
    for i, line in enumerate(lines):
        if 'Consumo Atual:' in line:
            # Próximas linhas contêm Volume (m³) e Volume (kg)
            if i + 1 < len(lines) and 'Volume (m' in lines[i + 1]:
                # Extrair valor do volume m³
                match = re.search(r'Volume \(m.?\):\s*([\d,]+)', lines[i + 1])
                if match:
                    consumo_gas['volume_m3'] = match.group(1)
            if i + 2 < len(lines) and 'Volume (kg)' in lines[i + 2]:
                # Extrair valor do volume kg
                match = re.search(r'Volume \(kg\):\s*([\d,]+)', lines[i + 2])
                if match:
                    consumo_gas['volume_kg'] = match.group(1)
            break
    
    if consumo_gas:
        fields['consumo_gas'] = consumo_gas
    
    return fields

@app.route('/')
def index():
    return render_template('index_boleto.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('Nenhum arquivo selecionado')
        return redirect(request.url)
    
    file = request.files['file']
    
    if file.filename == '':
        flash('Nenhum arquivo selecionado')
        return redirect(request.url)
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            # Primeiro tenta desbloquear o PDF se estiver protegido
            print(f"Verificando se o PDF está bloqueado...")
            desbloquear_pdf(filepath)
            print(f"PDF desbloqueado (se necessário)")
            
            # Detectar o tipo de boleto
            print(f"Detectando tipo de boleto...")
            boleto_type = detect_boleto_type(filepath)
            
            if boleto_type is None:
                flash('Não foi possível identificar o tipo de boleto. Tente novamente.')
                os.remove(filepath)
                return redirect(url_for('index'))
            
            print(f"Tipo detectado: {boleto_type}")
            
            # Processar o PDF com a função apropriada
            pdf_path = Path(filepath)
            if boleto_type == 'faculdade':
                output_path = process_pdf_faculdade(pdf_path)
                tipo_descricao = "Boleto de Faculdade"
            elif boleto_type == 'gas':
                output_path = process_pdf_gas(pdf_path)
                tipo_descricao = "Boleto de Gás"
            else:  # condominio
                output_path = process_pdf_condominio(pdf_path)
                tipo_descricao = "Boleto de Condomínio"
            
            # Ler o conteúdo do arquivo gerado
            with open(output_path, 'r', encoding='utf-8') as f:
                extracted_data = f.read()
            
            # Processar dados para exibição individual
            processed_data = parse_extracted_data(extracted_data)
            processed_data['tipo_boleto'] = tipo_descricao
            processed_data['boleto_type'] = boleto_type
            
            # Armazenar dados na sessão para uso posterior na atualização do banco
            session['boleto_data'] = processed_data
            
            # Limpar arquivos temporários
            os.remove(filepath)
            
            return render_template('resultado_boleto_condominio.html', 
                                 data=extracted_data, 
                                 processed_data=processed_data,
                                 filename=filename,
                                 output_filename=output_path.name)
        
        except Exception as e:
            flash(f'Erro ao processar o arquivo: {str(e)}')
            import traceback
            traceback.print_exc()
            return redirect(url_for('index'))
    
    else:
        flash('Tipo de arquivo não permitido. Apenas arquivos PDF são aceitos.')
        return redirect(url_for('index'))

@app.route('/download/<filename>')
def download_file(filename):
    try:
        return send_file(filename, as_attachment=True)
    except Exception as e:
        flash(f'Erro ao baixar o arquivo: {str(e)}')
        return redirect(url_for('index'))

@app.route('/atualizar_banco', methods=['POST'])
def atualizar_banco():
    """Atualiza os dados do boleto no banco de dados Banco de Dados"""
    try:
        # Recuperar dados do boleto da sessão
        boleto_data = session.get('boleto_data')
        
        if not boleto_data:
            return jsonify({'success': False, 'message': 'Nenhum dado de boleto encontrado na sessão'}), 400
        
        # Obter COD_FIN do formulário
        cod_fin = request.form.get('cod_fin')
        
        if not cod_fin:
            return jsonify({'success': False, 'message': 'COD_FIN não fornecido'}), 400
        
        # Validar e converter COD_FIN para inteiro
        try:
            cod_fin = int(cod_fin)
        except ValueError:
            return jsonify({'success': False, 'message': 'COD_FIN deve ser um número válido'}), 400
        
        # Ler configuração do banco
        lc = ler_configuracao()
        
        # Conectar ao banco de dados
        conn = db.connect(
            host=lc['SERVER'],
            database=lc['DIR_DADOS'],
            user=lc['USUARIO_BD'],
            password=lc['SENHA_BD']
        )
        c = conn.cursor()
        
        # Preparar valores para atualização
        linha_digitavel = boleto_data.get('linha_digitavel', '')
        data_vencimento_str = boleto_data.get('data_vencimento', '')
        data_documento_str = boleto_data.get('data_documento', '') or boleto_data.get('data_emissao', '')
        numero_documento = boleto_data.get('numero_documento', '') or boleto_data.get('demonstrativo_numero', '')
        nosso_numero = boleto_data.get('nosso_numero', '')
        
        # Converter datas (apenas se tiver valor)
        data_vencimento = converter_data(data_vencimento_str) if data_vencimento_str else None
        data_emissao = converter_data(data_documento_str) if data_documento_str else None
        
        # Converter valor_documento para float (suporta ambos os formatos: condomínio/faculdade e gás)
        valor_str = boleto_data.get('valor_documento', '') or boleto_data.get('valor_total', '') or '0'
        valor_str = valor_str.replace('.', '').replace(',', '.')
        try:
            valor_documento = float(valor_str) if valor_str and valor_str != '0' else None
        except:
            valor_documento = None
        
        # Construir SQL dinamicamente apenas com campos que foram extraídos
        campos_update = []
        valores_update = []
        
        if linha_digitavel:
            campos_update.append('LINHA_DIGITAVEL = ?')
            valores_update.append(linha_digitavel)
        
        if data_vencimento:
            campos_update.append('DATA_VENCIMENTO = ?')
            valores_update.append(data_vencimento)
        
        if data_emissao:
            campos_update.append('DATA_EMISSAO = ?')
            valores_update.append(data_emissao)
        
        if valor_documento:
            campos_update.append('VALOR_PREVISTO = ?')
            valores_update.append(valor_documento)
            campos_update.append('VALOR_PREVISTO_RESTANTE = ?')
            valores_update.append(valor_documento)
            campos_update.append('VALOR_A_AMORTIZAR = ?')
            valores_update.append(valor_documento)
            campos_update.append('VALOR_PRESENTE = ?')
            valores_update.append(valor_documento)
        
        if numero_documento:
            campos_update.append('NUM_DOC = ?')
            valores_update.append(numero_documento)
        
        if nosso_numero:
            campos_update.append('NOSSO_NUMERO = ?')
            valores_update.append(nosso_numero)
        
        # Verificar se há campos para atualizar (sem PREVISTO ainda)
        if len(campos_update) == 0:
            c.close()
            conn.close()
            return jsonify({
                'success': False,
                'message': 'Nenhum dado válido foi extraído do boleto para atualização'
            }), 400
        
        # Montar SQL com campos dinâmicos (SEM PREVISTO)
        sql = f"UPDATE LANC_FINANCEIRO SET {', '.join(campos_update)} WHERE COD_FIN = ?"
        valores_update.append(cod_fin)
        
        # DEBUG: Mostrar SQL que será executado
        print(f"SQL Valores do Boleto: {sql}")
        print(f"Valores: {valores_update}")
        
        # Executar UPDATE com os dados do boleto
        c.execute(sql, tuple(valores_update))
        conn.commit()
        
        # Verificar se alguma linha foi atualizada
        # Nota: Banco de Dados retorna -1 para rowcount em UPDATEs bem-sucedidos
        linhas_afetadas = c.rowcount
        print(f"Linhas afetadas na primeira atualização: {linhas_afetadas}")
        
        # Verificar se o registro existe (rowcount=0 significa que não encontrou)
        if linhas_afetadas == 0:
            c.close()
            conn.close()
            return jsonify({
                'success': False, 
                'message': f'Nenhum registro encontrado com COD_FIN = {cod_fin}'
            }), 404
        
        # ══════════════════════════════════════════════════════════════════════════
        # ATUALIZAR PREVISTO EM UMA TRANSAÇÃO SEPARADA
        # Fazer isso separadamente ajuda a identificar se há triggers interferindo
        # ══════════════════════════════════════════════════════════════════════════
        
        # Criar um novo cursor para a segunda transação
        c2 = conn.cursor()
        
        # Primeiro, Log do valor ANTES da atualização
        c2.execute("SELECT PREVISTO FROM LANC_FINANCEIRO WHERE COD_FIN = ?", (cod_fin,))
        resultado_antes = c2.fetchone()
        previsto_antes = resultado_antes[0] if resultado_antes else None
        print(f"[PREVISTO] Valor ANTES da atualização: '{previsto_antes}'")
        
        # UPDATE do PREVISTO em transação separada
        sql_previsto = "UPDATE LANC_FINANCEIRO SET PREVISTO = ? WHERE COD_FIN = ?"
        print(f"[PREVISTO] SQL: {sql_previsto}")
        print(f"[PREVISTO] Valores: ['F', {cod_fin}]")
        
        c2.execute(sql_previsto, ('F', cod_fin))
        conn.commit()
        
        linhas_previsto = c2.rowcount
        print(f"[PREVISTO] Linhas afetadas: {linhas_previsto}")
        
        # Verificar imediatamente após o commit
        c2.execute("SELECT PREVISTO FROM LANC_FINANCEIRO WHERE COD_FIN = ?", (cod_fin,))
        resultado_apos = c2.fetchone()
        previsto_atual = resultado_apos[0] if resultado_apos else None
        print(f"[PREVISTO] Valor DEPOIS da atualização: '{previsto_atual}'")
        print(f"[PREVISTO] Valor esperado: 'F' | Valor atual: '{previsto_atual}' | Match: {previsto_atual == 'F'}")
        
        # Tentar novamente se não funcionou (possível trigger que adiciona transação implícita)
        if previsto_atual != 'F':
            print(f"[PREVISTO] AVISO: Primeira tentativa não funcionou. Tentando novamente...")
            time.sleep(0.5)  # Pequeno delay
            
            c2.execute("UPDATE LANC_FINANCEIRO SET PREVISTO = 'F' WHERE COD_FIN = ?", (cod_fin,))
            conn.commit()
            
            c2.execute("SELECT PREVISTO FROM LANC_FINANCEIRO WHERE COD_FIN = ?", (cod_fin,))
            resultado_terceira = c2.fetchone()
            previsto_atual = resultado_terceira[0] if resultado_terceira else None
            print(f"[PREVISTO] Valor após segunda tentativa: '{previsto_atual}'")
        
        c2.close()
        c.close()
        conn.close()
        
        # Retornar resultado
        if previsto_atual == 'F':
            return jsonify({
                'success': True, 
                'message': f'Registro COD_FIN {cod_fin} atualizado com sucesso! PREVISTO atualizado para F.',
                'linhas_afetadas': linhas_afetadas,
                'previsto_atual': previsto_atual
            })
        else:
            # Retorna sucesso mas avisa que PREVISTO não foi atualizado
            return jsonify({
                'success': True,
                'message': f'Registro COD_FIN {cod_fin} atualizado com sucesso! PORÉM: O campo PREVISTO permanece como "{previsto_atual}". Verifique se há um TRIGGER no banco que impede esta alteração.',
                'linhas_afetadas': linhas_afetadas,
                'previsto_atual': previsto_atual,
                'warning': True
            })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False, 
            'message': f'Erro ao atualizar banco de dados: {str(e)}'
        }), 500

def converter_data(data_str):
    """Converte string de data para formato datetime compatível com Banco de Dados"""
    if not data_str:
        return None
    
    # Formatos possíveis: DD/MM/YYYY, DD/MM/YY, YYYY-MM-DD
    formatos = ['%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d', '%d-%m-%Y']
    
    for formato in formatos:
        try:
            return datetime.strptime(data_str, formato)
        except ValueError:
            continue
    
    # Se nenhum formato funcionar, retorna None
    print(f'Aviso: Não foi possível converter a data: {data_str}')
    return None

if __name__ == '__main__':
    # Iniciar thread para abrir o navegador
    threading.Thread(target=open_browser, daemon=True).start()
    
    # Iniciar o servidor Flask
    print("🚀 Iniciando servidor...")
    print("📱 Abrindo navegador automaticamente...")
    app.run(debug=False, host='127.0.0.1', port=5000, use_reloader=False)
