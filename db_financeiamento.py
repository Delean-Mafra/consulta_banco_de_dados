from flask import Flask, render_template
from flask_wtf import FlaskForm
from wtforms import SubmitField, DateField
from wtforms.validators import DataRequired
from db_lerconfiguracao import ler_configuracao, secret_key, get_db
import webbrowser
import threading
import matplotlib.pyplot as plt
import io
import base64
from datetime import datetime

# Configurar o backend do Matplotlib para 'Agg'
plt.switch_backend('Agg')

db = get_db()
key = secret_key()

# Carregar configurações do banco de dados
lc = ler_configuracao()

# Função para conectar ao banco de dados e executar a consulta
def executar_consulta(data_inicio=None, data_fim=None):
    conn = db.connect(
    host=lc['SERVER'],
    database=lc['DIR_DADOS'],
    user=lc['USUARIO_BD'],
    password=lc['SENHA_BD']
    )
    c = conn.cursor()
    
    query = """
    SELECT LC.DATA_PAGAMENTO, LC.VALOR_PAGO
    FROM LANC_FINANCEIRO LC
    WHERE LC.COD_PLANO_CONTA = 122
    AND LC.COD_FORNECEDOR = 15
    AND LC.COD_SITUACAO_TITULO = 4
    AND LC.ATV_LANC_FINANCEIRO = 'V'
    """
    
    if data_inicio and data_fim:
        query += f" AND LC.DATA_PAGAMENTO BETWEEN '{data_inicio}' AND '{data_fim}'"
    
    query += " ORDER BY LC.DATA_PAGAMENTO"
    
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
    submit = SubmitField('Filtrar')

@app.route('/', methods=['GET', 'POST'])
def index():
    form = DateForm()
    results = None
    graph_values = None
    graph_percentage = None

    if form.validate_on_submit():
        data_inicio = form.data_inicio.data.strftime('%d.%m.%Y')
        data_fim = form.data_fim.data.strftime('%d.%m.%Y')
        results = executar_consulta(data_inicio, data_fim)
    else:
        results = executar_consulta()

    # Gerar os gráficos
    if results:
        datas = [datetime.strptime(str(result[0]), '%Y-%m-%d %H:%M:%S') for result in results]
        valores = [float(result[1]) for result in results]
        percentuais = [0] + [(valores[i] - valores[i-1]) / valores[i-1] * 100 for i in range(1, len(valores))]

        # Gráfico de valores pagos
        plt.figure(figsize=(10, 5))
        plt.plot(datas, valores, marker='o', linestyle='-', color='b')
        plt.title('Aumento dos Juros ao Longo do Tempo')
        plt.xlabel('Data de Pagamento')
        plt.ylabel('Valor Pago (R$)')
        plt.grid(True)
        plt.xticks(rotation=45)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        graph_values = base64.b64encode(buf.read()).decode('utf-8')
        plt.close()

        # Gráfico de aumento percentual
        plt.figure(figsize=(10, 5))
        plt.plot(datas, percentuais, marker='o', linestyle='-', color='r')
        plt.title('Aumento Percentual dos Juros ao Longo do Tempo')
        plt.xlabel('Data de Pagamento')
        plt.ylabel('Aumento Percentual (%)')
        plt.grid(True)
        plt.xticks(rotation=45)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        graph_percentage = base64.b64encode(buf.read()).decode('utf-8')
        plt.close()

    return render_template('grafico_juros.html', form=form, results=results, graph_values=graph_values, graph_percentage=graph_percentage)

def open_browser():
    webbrowser.open_new('http://127.0.0.1:5000')

if __name__ == '__main__':
    threading.Timer(1.25, open_browser).start()  # Abre o navegador após 1.25 segundos
    app.run(debug=False)