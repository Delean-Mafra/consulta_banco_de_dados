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
from datetime import datetime, date
from collections import defaultdict

# Configurar o backend do Matplotlib para ambiente sem interface grafica
plt.switch_backend('Agg')

db = get_db()
key = secret_key()
lc = ler_configuracao()


def _to_float(value):
	if value is None:
		return 0.0
	return float(value)


def buscar_lancamentos(data_inicio=None, data_fim=None):
	conn = db.connect(
		host=lc['SERVER'],
		database=lc['DIR_DADOS'],
		user=lc['USUARIO_BD'],
		password=lc['SENHA_BD']
	)
	c = conn.cursor()

	query = """
	SELECT
		LF.DATA_PAGAMENTO,
		LF.TIPO_LANC_FIN,
		COALESCE(LF.VALOR_PAGO, 0) AS VALOR,
		COALESCE(CF.NOME_CONTA_FINANCEIRA, 'SEM CONTA') AS NOME_CONTA_FINANCEIRA,
		COALESCE(PC.NOME_PLANO_CONTA, 'SEM PLANO') AS NOME_PLANO_CONTA
	FROM LANC_FINANCEIRO LF
	LEFT JOIN CONTA_FINANCEIRA CF ON CF.COD_CONTA_FINANCEIRA = LF.COD_CONTA_FINANCEIRA
	LEFT JOIN PLANO_CONTA PC ON PC.COD_PLANO_CONTA = LF.COD_PLANO_CONTA
	WHERE LF.ATV_LANC_FINANCEIRO = 'V'
	  AND LF.TIPO_LANC_FIN IN ('P', 'R')
	"""

	if data_inicio and data_fim:
		query += f" AND LF.DATA_PAGAMENTO BETWEEN '{data_inicio}' AND '{data_fim}'"

	query += " ORDER BY LF.DATA_PAGAMENTO"

	c.execute(query)
	rows = c.fetchall()
	conn.close()
	return rows


def gerar_grafico_resultado_geral(meses_ordenados, recebido_mensal, pago_mensal):
	if not meses_ordenados:
		return None

	saldo_mensal = [recebido_mensal[mes] - pago_mensal[mes] for mes in meses_ordenados]
	cores = ['#1f8f4a' if saldo >= 0 else '#c62828' for saldo in saldo_mensal]

	plt.figure(figsize=(14, 6))
	barras = plt.bar(meses_ordenados, saldo_mensal, color=cores, alpha=0.9)
	plt.axhline(y=0, color='black', linewidth=1)
	plt.title('Resultado Geral por Mes (Recebido - Pago)', fontsize=16, fontweight='bold')
	plt.xlabel('Mes/Ano')
	plt.ylabel('Saldo (R$)')
	plt.xticks(rotation=45)
	plt.grid(axis='y', alpha=0.25)

	for barra, valor in zip(barras, saldo_mensal):
		desloc = 8 if valor >= 0 else -12
		plt.annotate(
			f'R$ {valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'),
			(barra.get_x() + barra.get_width() / 2, valor),
			textcoords='offset points',
			xytext=(0, desloc),
			ha='center',
			fontsize=9
		)

	plt.tight_layout()
	buf = io.BytesIO()
	plt.savefig(buf, format='png', dpi=140)
	buf.seek(0)
	encoded = base64.b64encode(buf.read()).decode('utf-8')
	plt.close()
	return encoded


def gerar_grafico_gastos_plano(plano_totais):
	if not plano_totais:
		return None

	itens = sorted(plano_totais.items(), key=lambda x: x[1], reverse=True)
	planos = [nome for nome, _ in itens]
	valores = [valor for _, valor in itens]

	plt.figure(figsize=(14, 7))
	barras = plt.bar(planos, valores, color='#d35400', alpha=0.85)
	plt.title('Gastos por Centro de Custo (Plano de Conta) - Apenas Pagar', fontsize=16, fontweight='bold')
	plt.xlabel('Plano de Conta')
	plt.ylabel('Total Gasto (R$)')
	plt.xticks(rotation=55, ha='right')
	plt.grid(axis='y', alpha=0.25)

	for barra, valor in zip(barras, valores):
		plt.annotate(
			f'R$ {valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'),
			(barra.get_x() + barra.get_width() / 2, valor),
			textcoords='offset points',
			xytext=(0, 6),
			ha='center',
			fontsize=8
		)

	plt.tight_layout()
	buf = io.BytesIO()
	plt.savefig(buf, format='png', dpi=140)
	buf.seek(0)
	encoded = base64.b64encode(buf.read()).decode('utf-8')
	plt.close()
	return encoded


def gerar_grafico_contas_financeiras(conta_totais):
	if not conta_totais:
		return None

	itens = sorted(conta_totais.items(), key=lambda x: abs(x[1]['saldo']), reverse=True)
	contas = [nome for nome, _ in itens]
	entradas = [dados['entrada'] for _, dados in itens]
	saidas = [dados['saida'] for _, dados in itens]
	saldos = [dados['saldo'] for _, dados in itens]
	cores_saldo = ['#2e7d32' if s >= 0 else '#b71c1c' for s in saldos]

	fig, axs = plt.subplots(3, 1, figsize=(15, 12), sharex=True)

	axs[0].bar(contas, entradas, color='#1565c0', alpha=0.9)
	axs[0].set_title('Entradas por Conta Financeira (R)')
	axs[0].set_ylabel('R$')
	axs[0].grid(axis='y', alpha=0.25)

	axs[1].bar(contas, saidas, color='#ef6c00', alpha=0.9)
	axs[1].set_title('Saidas por Conta Financeira (P)')
	axs[1].set_ylabel('R$')
	axs[1].grid(axis='y', alpha=0.25)

	axs[2].bar(contas, saldos, color=cores_saldo, alpha=0.9)
	axs[2].axhline(y=0, color='black', linewidth=1)
	axs[2].set_title('Saldo Final por Conta (Entradas - Saidas)')
	axs[2].set_ylabel('R$')
	axs[2].grid(axis='y', alpha=0.25)

	plt.xticks(rotation=55, ha='right')
	plt.tight_layout()
	buf = io.BytesIO()
	plt.savefig(buf, format='png', dpi=140)
	buf.seek(0)
	encoded = base64.b64encode(buf.read()).decode('utf-8')
	plt.close()
	return encoded


def gerar_grafico_movimento_mensal(meses_ordenados, recebido_mensal, pago_mensal):
	if not meses_ordenados:
		return None

	recebidos = [recebido_mensal[mes] for mes in meses_ordenados]
		
	pagos = [pago_mensal[mes] for mes in meses_ordenados]
	saldo_acumulado = []
	saldo_corrente = 0.0
	for recebido, pago in zip(recebidos, pagos):
		saldo_corrente += (recebido - pago)
		saldo_acumulado.append(saldo_corrente)

	x = list(range(len(meses_ordenados)))
	width = 0.38

	fig, ax1 = plt.subplots(figsize=(16, 7))
	barras_recebido = ax1.bar([i - width / 2 for i in x], recebidos, width=width, color='#1976d2', alpha=0.9, label='Recebido (R)')
	barras_pago = ax1.bar([i + width / 2 for i in x], pagos, width=width, color='#ef6c00', alpha=0.85, label='Pago (P)')

	ax1.set_title('Movimento Mensal: Recebimentos, Pagamentos e Saldo Acumulado', fontsize=16, fontweight='bold')
	ax1.set_xlabel('Mes/Ano')
	ax1.set_ylabel('Valores Mensais (R$)')
	ax1.set_xticks(x)
	ax1.set_xticklabels(meses_ordenados, rotation=45, ha='right')
	ax1.grid(axis='y', alpha=0.25)

	ax2 = ax1.twinx()
	linha_saldo, = ax2.plot(x, saldo_acumulado, color='#2e7d32', marker='o', linewidth=2.4, label='Saldo Acumulado')
	ax2.set_ylabel('Saldo Acumulado (R$)', color='#2e7d32')
	ax2.tick_params(axis='y', labelcolor='#2e7d32')

	for barra in list(barras_recebido) + list(barras_pago):
		valor = barra.get_height()
		if valor <= 0:
			continue
		ax1.annotate(
			f'{valor:,.0f}'.replace(',', '.'),
			(barra.get_x() + barra.get_width() / 2, valor),
			textcoords='offset points',
			xytext=(0, 5),
			ha='center',
			fontsize=8,
			color='#334155'
		)

	for idx, valor in enumerate(saldo_acumulado):
		ax2.annotate(
			f'R$ {valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'),
			(x[idx], valor),
			textcoords='offset points',
			xytext=(0, 10 if valor >= 0 else -14),
			ha='center',
			fontsize=8,
			color='#1b5e20'
		)

	handles_1, labels_1 = ax1.get_legend_handles_labels()
	handles_2, labels_2 = ax2.get_legend_handles_labels()
	ax1.legend(handles_1 + [linha_saldo], labels_1 + labels_2, loc='upper left')

	plt.tight_layout()
	buf = io.BytesIO()
	plt.savefig(buf, format='png', dpi=140)
	buf.seek(0)
	encoded = base64.b64encode(buf.read()).decode('utf-8')
	plt.close()
	return encoded


def montar_tabela_mensal(meses_ordenados, recebido_mensal, pago_mensal):
	tabela_mensal = []
	gasto_anterior = None

	for mes in meses_ordenados:
		recebido = recebido_mensal[mes]
		pago = pago_mensal[mes]
		saldo = recebido - pago
		variacao_pct = None

		if gasto_anterior is not None and gasto_anterior > 0:
			variacao_pct = ((pago - gasto_anterior) / gasto_anterior) * 100

		tabela_mensal.append(
			{
				'mes': mes,
				'recebido': recebido,
				'pago': pago,
				'saldo': saldo,
				'variacao_gasto': variacao_pct
			}
		)

		gasto_anterior = pago

	return tabela_mensal


def consolidar_dados(rows):
	recebido_mensal = defaultdict(float)
	pago_mensal = defaultdict(float)
	plano_totais = defaultdict(float)
	conta_totais = defaultdict(lambda: {'entrada': 0.0, 'saida': 0.0, 'saldo': 0.0})

	for data_pagamento, tipo, valor, nome_conta, nome_plano in rows:
		if not data_pagamento:
			continue

		if isinstance(data_pagamento, str):
			dt = datetime.strptime(data_pagamento, '%Y-%m-%d %H:%M:%S')
		else:
			dt = data_pagamento

		mes_ano = dt.strftime('%m/%Y')
		valor_num = _to_float(valor)

		if tipo == 'R':
			recebido_mensal[mes_ano] += valor_num
			conta_totais[nome_conta]['entrada'] += valor_num
		elif tipo == 'P':
			pago_mensal[mes_ano] += valor_num
			plano_totais[nome_plano] += valor_num
			conta_totais[nome_conta]['saida'] += valor_num

	for conta in conta_totais:
		conta_totais[conta]['saldo'] = conta_totais[conta]['entrada'] - conta_totais[conta]['saida']

	meses = sorted(set(list(recebido_mensal.keys()) + list(pago_mensal.keys())), key=lambda x: datetime.strptime(x, '%m/%Y'))

	return {
		'meses': meses,
		'recebido_mensal': recebido_mensal,
		'pago_mensal': pago_mensal,
		'plano_totais': plano_totais,
		'conta_totais': conta_totais
	}


app = Flask(__name__)
app.config['SECRET_KEY'] = key


class DREForm(FlaskForm):
	data_inicio = DateField('Data Inicio', format='%Y-%m-%d', validators=[DataRequired()])
	data_fim = DateField('Data Fim', format='%Y-%m-%d', validators=[DataRequired()])
	submit = SubmitField('Gerar DRE')


@app.route('/', methods=['GET', 'POST'])
def index():
	hoje = date.today()
	primeiro_dia = date(hoje.year, 1, 1)

	form = DREForm()
	if request_method_is_get():
		form.data_inicio.data = primeiro_dia
		form.data_fim.data = hoje

	graph_geral = None
	graph_movimento_mensal = None
	graph_plano = None
	graph_conta = None
	resumo = None
	tabela_contas = []
	tabela_mensal = []

	if form.validate_on_submit() or request_method_is_get():
		data_inicio_sql = form.data_inicio.data.strftime('%d.%m.%Y')
		data_fim_sql = form.data_fim.data.strftime('%d.%m.%Y')
		rows = buscar_lancamentos(data_inicio_sql, data_fim_sql)
		dados = consolidar_dados(rows)

		graph_geral = gerar_grafico_resultado_geral(dados['meses'], dados['recebido_mensal'], dados['pago_mensal'])
		graph_movimento_mensal = gerar_grafico_movimento_mensal(dados['meses'], dados['recebido_mensal'], dados['pago_mensal'])
		graph_plano = gerar_grafico_gastos_plano(dados['plano_totais'])
		graph_conta = gerar_grafico_contas_financeiras(dados['conta_totais'])
		tabela_mensal = montar_tabela_mensal(dados['meses'], dados['recebido_mensal'], dados['pago_mensal'])

		total_recebido = sum(dados['recebido_mensal'].values())
		total_pago = sum(dados['pago_mensal'].values())
		saldo_total = total_recebido - total_pago
		media_gasto_mensal = total_pago / len(dados['meses']) if dados['meses'] else 0.0

		mes_maior_gasto = None
		valor_maior_gasto = 0.0
		if dados['meses']:
			mes_maior_gasto = max(dados['meses'], key=lambda mes: dados['pago_mensal'][mes])
			valor_maior_gasto = dados['pago_mensal'][mes_maior_gasto]

		resumo = {
			'total_recebido': total_recebido,
			'total_pago': total_pago,
			'saldo_total': saldo_total,
			'qtd_meses': len(dados['meses']),
			'media_gasto_mensal': media_gasto_mensal,
			'mes_maior_gasto': mes_maior_gasto,
			'valor_maior_gasto': valor_maior_gasto
		}

		for conta, valores in sorted(dados['conta_totais'].items(), key=lambda x: x[0]):
			tabela_contas.append(
				{
					'conta': conta,
					'entrada': valores['entrada'],
					'saida': valores['saida'],
					'saldo': valores['saldo']
				}
			)

	return render_template(
		'dre.html',
		form=form,
		graph_geral=graph_geral,
		graph_movimento_mensal=graph_movimento_mensal,
		graph_plano=graph_plano,
		graph_conta=graph_conta,
		resumo=resumo,
		tabela_contas=tabela_contas,
		tabela_mensal=tabela_mensal
	)


def request_method_is_get():
	from flask import request
	return request.method == 'GET'


def open_browser():
	webbrowser.open_new('http://127.0.0.1:5008')


if __name__ == '__main__':
	threading.Timer(1.25, open_browser).start()
	app.run(debug=False, port=5008)
