from flask import Flask, render_template, jsonify, request
from flask_wtf import FlaskForm
from wtforms import SubmitField, DateField, StringField
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


# Função para buscar planos de conta de despesa
def buscar_planos_despesa():
    conn = db.connect(
        host=lc['SERVER'],
        database=lc['DIR_DADOS'],
        user=lc['USUARIO_BD'],
        password=lc['SENHA_BD']
    )
    c = conn.cursor()
    
    # Buscar planos de conta de despesa (TIPO_PLANO_CONTA='D')
    query = """
    --sql
    SELECT DISTINCT PC.NOME_PLANO_CONTA
    FROM PLANO_CONTA PC
    WHERE PC.TIPO_PLANO_CONTA = 'D'
    ORDER BY PC.NOME_PLANO_CONTA;
    """
    
    c.execute(query)
    results = c.fetchall()
    conn.close()
    
    # Retornar lista de tuplas (valor, label) para o SelectField
    return [(result[0], result[0]) for result in results]

# Função para conectar ao banco de dados e executar a consulta
def executar_consulta(plano_conta=None, data_inicio=None, data_fim=None):
    conn = db.connect(
        host=lc['SERVER'],
        database=lc['DIR_DADOS'],
        user=lc['USUARIO_BD'],
        password=lc['SENHA_BD']
    )
    c = conn.cursor()
    
    query = """
    --sql 
    SELECT DISTINCT LC.DATA_PAGAMENTO, LC.VALOR_PAGO, PC.NOME_PLANO_CONTA
    FROM LANC_FINANCEIRO LC
    LEFT JOIN PLANO_CONTA PC ON LC.COD_PLANO_CONTA = PC.COD_PLANO_CONTA
    WHERE LC.COD_SITUACAO_TITULO = 4
    AND LC.ATV_LANC_FINANCEIRO = 'V'
    AND PC.TIPO_PLANO_CONTA = 'D'
    """
    
    if plano_conta:
        # Suportar múltiplas categorias separadas por vírgula
        categorias = [cat.strip() for cat in plano_conta.split(',')]
        if len(categorias) == 1:
            query += f" AND PC.NOME_PLANO_CONTA = '{categorias[0]}'"
        else:
            categorias_str = "', '".join(categorias)
            query += f" AND PC.NOME_PLANO_CONTA IN ('{categorias_str}')"
    
    if data_inicio and data_fim:
        query += f" AND LC.DATA_PAGAMENTO BETWEEN '{data_inicio}' AND '{data_fim}'"
    
    query += " ORDER BY LC.DATA_PAGAMENTO;"
    
    c.execute(query)
    results = c.fetchall()
    conn.close()
    
    return results

# Configuração do Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = key

class DateForm(FlaskForm):
    plano_conta = StringField('Plano de Contas (separe múltiplas categorias com vírgula)', validators=[DataRequired()])
    data_inicio = DateField('Data Início', format='%Y-%m-%d', validators=[DataRequired()])
    data_fim = DateField('Data Fim', format='%Y-%m-%d', validators=[DataRequired()])
    submit = SubmitField('Filtrar')

@app.route('/api/buscar_planos')
def api_buscar_planos():
    termo = request.args.get('termo', '').upper()
    
    if len(termo) < 2:
        return jsonify([])
    
    conn = db.connect(
    host=lc['SERVER'],
    database=lc['DIR_DADOS'],
    user=lc['USUARIO_BD'],
    password=lc['SENHA_BD']
    )
    c = conn.cursor()
    
    query = """
    --sql
    SELECT DISTINCT PC.NOME_PLANO_CONTA
    FROM PLANO_CONTA PC
    WHERE PC.TIPO_PLANO_CONTA = 'D'
    AND UPPER(PC.NOME_PLANO_CONTA) STARTING WITH UPPER('{0}')
    ORDER BY PC.NOME_PLANO_CONTA;
    """.format(termo)
    
    c.execute(query)
    results = c.fetchall()
    conn.close()
    
    planos = [result[0] for result in results]
    return jsonify(planos)

@app.route('/', methods=['GET', 'POST'])
def index():
    form = DateForm()
    
    results = None
    graph_values = None
    graph_percentage = None
    plano_selecionado = None

    if form.validate_on_submit():
        plano_selecionado = form.plano_conta.data
        data_inicio = form.data_inicio.data.strftime('%d.%m.%Y')
        data_fim = form.data_fim.data.strftime('%d.%m.%Y')
        results = executar_consulta(plano_selecionado, data_inicio, data_fim)
    elif request.method == 'GET':
        # Carregar dados padrão (ex: Combustível) quando acessar pela primeira vez
        plano_selecionado = "Combustível"
        results = executar_consulta(plano_selecionado)

    # Gerar os gráficos
    total_meses = 0
    media_mensal = 0
    if results:
        # Agrupar dados por mês/ano
        gastos_mensais = {}
        for result in results:
            data = datetime.strptime(str(result[0]), '%Y-%m-%d %H:%M:%S')
            mes_ano = data.strftime('%m/%Y')
            valor = float(result[1])
            
            if mes_ano in gastos_mensais:
                gastos_mensais[mes_ano] += valor
            else:
                gastos_mensais[mes_ano] = valor
        
        # Ordenar por data
        meses_ordenados = sorted(gastos_mensais.keys(), key=lambda x: datetime.strptime(x, '%m/%Y'))
        valores_mensais = [gastos_mensais[mes] for mes in meses_ordenados]
        
        # Calcular média mensal (total dividido pela quantidade de meses)
        total_meses = len(meses_ordenados)
        media_mensal = sum(valores_mensais) / total_meses if total_meses > 0 else 0
        
        # Calcular variação percentual mensal
        percentuais = [0] + [(valores_mensais[i] - valores_mensais[i-1]) / valores_mensais[i-1] * 100 for i in range(1, len(valores_mensais))]

        # Gráfico de valores gastos com combustível (agrupado por mês)
        plt.figure(figsize=(14, 7))
        plt.plot(meses_ordenados, valores_mensais, marker='o', linestyle='-', color='orange', linewidth=3, markersize=8)
        plt.title(f'Gastos Mensais - {plano_selecionado}', fontsize=18, fontweight='bold', pad=20)
        plt.xlabel('Mês/Ano', fontsize=14)
        plt.ylabel('Valor Total Gasto (R$)', fontsize=14)
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        
        # Adicionar valores sobre os pontos
        for i, valor in enumerate(valores_mensais):
            plt.annotate(f'R$ {valor:.2f}', (meses_ordenados[i], valor), 
                        textcoords="offset points", xytext=(0,10), ha='center', fontsize=10)
        
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150)
        buf.seek(0)
        graph_values = base64.b64encode(buf.read()).decode('utf-8')
        plt.close()

        # Gráfico de variação percentual dos gastos mensais
        plt.figure(figsize=(14, 7))
        colors = ['green' if p >= 0 else 'red' for p in percentuais]
        bars = plt.bar(meses_ordenados, percentuais, color=colors, alpha=0.7)
        plt.title(f'Variação Percentual dos Gastos Mensais - {plano_selecionado}', fontsize=18, fontweight='bold', pad=20)
        plt.xlabel('Mês/Ano', fontsize=14)
        plt.ylabel('Variação Percentual (%)', fontsize=14)
        plt.grid(True, alpha=0.3, axis='y')
        plt.axhline(y=0, color='black', linestyle='-', linewidth=1)
        
        # Adicionar valores sobre as barras
        for i, (bar, valor) in enumerate(zip(bars, percentuais)):
            if i > 0:  # Pular o primeiro valor (sempre 0)
                plt.annotate(f'{valor:.1f}%', (bar.get_x() + bar.get_width()/2, bar.get_height()),
                           ha='center', va='bottom' if valor >= 0 else 'top', fontsize=10)
        
        plt.xticks(rotation=45)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150)
        buf.seek(0)
        graph_percentage = base64.b64encode(buf.read()).decode('utf-8')
        plt.close()

    return render_template('grafico_gastos.html', form=form, results=results, graph_values=graph_values, graph_percentage=graph_percentage, plano_selecionado=plano_selecionado, media_mensal=media_mensal, total_meses=total_meses)

def open_browser():
    webbrowser.open_new('http://127.0.0.1:5002')

if __name__ == '__main__':
    threading.Timer(1.25, open_browser).start()  # Abre o navegador após 1.25 segundos
    app.run(debug=False, port=5002)