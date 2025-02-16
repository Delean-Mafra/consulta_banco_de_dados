from flask import Flask, render_template
from flask_wtf import FlaskForm
from wtforms import SubmitField, DateField
from wtforms.validators import DataRequired
from db_lerconfiguracao import ler_configuracao, secret_key, get_db
import webbrowser
import threading

db = get_db()
key = secret_key()

# Carregar configurações do banco de dados
config = ler_configuracao()
SERVER = config['SERVER']
DIR_DADOS = config['DIR_DADOS']
USUARIO_BD = config['USUARIO_BD']
SENHA_BD = config['SENHA_BD']

# Função para conectar ao banco de dados e executar a consulta
def executar_consulta(data_inicio, data_fim):
    conn = db.connect(
        host=SERVER,
        database=DIR_DADOS,
        user=USUARIO_BD,
        password=SENHA_BD
    )
    c = conn.cursor()
    
    query = f"""
    SELECT PC.NOME_PLANO_CONTA, SUM(LF.VALOR_PAGO) AS "VALOR"
    FROM LANC_FINANCEIRO LF
    LEFT JOIN PLANO_CONTA PC ON PC.COD_PLANO_CONTA = LF.COD_PLANO_CONTA
    WHERE LF.COD_CONTA_FINANCEIRA = 25
    AND LF.COD_SITUACAO_TITULO = 4
    AND (LF.DATA_PAGAMENTO BETWEEN '{data_inicio}' AND '{data_fim}' OR LF.DATA_DISPONIVEL_TEF BETWEEN '{data_inicio}' AND '{data_fim}')
    AND LF.TIPO_LANC_FIN = 'P'
    AND LF.ATV_LANC_FINANCEIRO = 'V'
    GROUP BY PC.NOME_PLANO_CONTA
    ORDER BY "VALOR" DESC;
    """
    
    c.execute(query)
    results = c.fetchall()
    conn.close()
    
    return results

# Configuração do Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = key

class DateForm(FlaskForm):
    data_inicio = DateField('Data Início', format='%Y-%m-%d', validators=[DataRequired()])
    data_fim = DateField('Data Fim', format='%Y-%m-%d', validators=[DataRequired()])
    submit = SubmitField('Executar Consulta')

@app.route('/', methods=['GET', 'POST'])
def index():
    form = DateForm()
    results = None
    if form.validate_on_submit():
        data_inicio = form.data_inicio.data.strftime('%Y-%m-%d')
        data_fim = form.data_fim.data.strftime('%Y-%m-%d')
        results = executar_consulta(data_inicio, data_fim)
    return render_template('index.html', form=form, results=results)

def open_browser():
    webbrowser.open_new('http://127.0.0.1:5000')

if __name__ == '__main__':
    threading.Timer(1.25, open_browser).start()  # Abre o navegador após 1.25 segundos
    app.run(debug=False)