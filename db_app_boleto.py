# Aplicação Flask para extração de dados de boletos de condomínio.
# Upload de PDF e geração de arquivo TXT com dados extraídos.

from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session, jsonify
import os
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
    #Desbloqueia PDF se estiver protegido#
    try:
        with pikepdf.open(input_pdf, allow_overwriting_input=True) as pdf:
            pdf.save(input_pdf)
        return True
    except Exception as e:
        print(f'Erro ao desbloquear PDF: {e}')
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
        
        # Contar indicadores encontrados
        count_faculdade = sum(1 for ind in indicadores_faculdade if ind in full_text)
        count_condominio = sum(1 for ind in indicadores_condominio if ind in full_text)
        
        print(f"Indicadores faculdade encontrados: {count_faculdade}")
        print(f"Indicadores condomínio encontrados: {count_condominio}")
        
        if count_faculdade > count_condominio and count_faculdade > 0:
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
                fields['data_documento'] = line.split(':', 1)[1].strip()
            elif line.startswith('Data de Vencimento:'):
                fields['data_vencimento'] = line.split(':', 1)[1].strip()
            elif line.startswith('Nosso Número:'):
                fields['nosso_numero'] = line.split(':', 1)[1].strip()
            elif line.startswith('Valor Documento:'):
                fields['valor_documento'] = line.split(':', 1)[1].strip()
            elif line.startswith('Número do documento:'):
                fields['numero_documento'] = line.split(':', 1)[1].strip()
    
    # Processar rateios
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
    return fields

@app.route('/')
def index():
    return render_template('index_boleto_condominio.html')

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
    """Atualiza os dados do boleto no banco de dados Firebird"""
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
        data_vencimento = converter_data(boleto_data.get('data_vencimento', ''))
        data_emissao = converter_data(boleto_data.get('data_documento', ''))
        numero_documento = boleto_data.get('numero_documento', '')
        
        # Converter valor_documento para float
        valor_str = boleto_data.get('valor_documento', '0').replace('.', '').replace(',', '.')
        try:
            valor_documento = float(valor_str)
        except:
            valor_documento = 0.0
        
        # Executar UPDATE
        sql = """
            UPDATE LANC_FINANCEIRO
            SET LINHA_DIGITAVEL = ?,
                DATA_VENCIMENTO = ?,
                DATA_EMISSAO = ?,
                VALOR_PREVISTO = ?,
                VALOR_PREVISTO_RESTANTE = ?,
                VALOR_A_AMORTIZAR = ?,
                VALOR_PRESENTE = ?,
                NUM_DOC = ?
            WHERE COD_FIN = ?
        """
        
        c.execute(sql, (
            linha_digitavel,
            data_vencimento,
            data_emissao,
            valor_documento,
            valor_documento,
            valor_documento,
            valor_documento,
            numero_documento,
            cod_fin
        ))
        
        # Verificar se alguma linha foi atualizada
        if c.rowcount == 0:
            conn.rollback()
            c.close()
            conn.close()
            return jsonify({
                'success': False, 
                'message': f'Nenhum registro encontrado com COD_FIN = {cod_fin}'
            }), 404
        
        # Commit das alterações
        conn.commit()
        
        # Fechar conexão
        c.close()
        conn.close()
        
        return jsonify({
            'success': True, 
            'message': f'Registro COD_FIN {cod_fin} atualizado com sucesso!',
            'linhas_afetadas': c.rowcount
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False, 
            'message': f'Erro ao atualizar banco de dados: {str(e)}'
        }), 500

def converter_data(data_str):
    """Converte string de data para formato datetime compatível com Firebird"""
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
