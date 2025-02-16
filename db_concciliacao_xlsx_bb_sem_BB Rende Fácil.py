import pandas as pd
from dateutil import parser
import warnings
from db_lerconfiguracao import ler_configuracao, get_db
db = get_db()

lc = ler_configuracao()

# Configurações do banco de dados
DIR_DADOS = lc['DIR_DADOS']
USUARIO_BD = lc['USUARIO_BD']
SENHA_BD = lc['SENHA_BD']
SERVER = lc['SERVER']


# Suprimir avisos de FutureWarning e UserWarning


warnings.simplefilter(action='ignore', category=FutureWarning)

# Filtrar especificamente os avisos do openpyxl
def custom_warning_filter(message, category, filename, lineno, file=None, line=None):
    if 'openpyxl' in filename:
        return
    else:
        return warnings.showwarning(message, category, filename, lineno, file, line)

warnings.showwarning = custom_warning_filter




# Conectar ao banco de dados
conn = db.connect(
    host=SERVER,
    database=DIR_DADOS,
    user=USUARIO_BD,
    password=SENHA_BD
)

# Cursor para executar as queries
cur = conn.cursor()

# Função para converter a data
def converter_data(data_str):
    if pd.isna(data_str):
        return pd.NaT
    try:
        data = parser.parse(str(data_str), dayfirst=True)
        return data.strftime('%d/%m/%Y')
    except:
        return str(data_str)

# Lendo o arquivo .xlsx
df_xlsx = pd.read_excel(r'D:\Python\Python_projcts\templates\extrato_conta_bb.xlsx')

# Filtrando registros para excluir "BB Rende Fácil"
#df_xlsx = df_xlsx[df_xlsx['Lançamento'] != 'BB Rende Fácil']
df_xlsx = df_xlsx[~df_xlsx['Lançamento'].isin(['BB Rende Fácil', 'Saldo Anterior', 'S A L D O'])]

# Convertendo a coluna "Valor" para números
df_xlsx['Valor'] = df_xlsx['Valor'].str.replace('.', '').str.replace(',', '.').astype(float)

# Ajustando os valores do DataFrame do XLSX
df_xlsx['Valor'] = df_xlsx.apply(
    lambda row: -row['Valor'] if row['Lançamento'] == 'Saída' else row['Valor'],
    axis=1
)

# Removendo datas inválidas e convertendo as datas
df_xlsx = df_xlsx[df_xlsx['Data'] != '00/00/0000']
df_xlsx['Data'] = df_xlsx['Data'].apply(converter_data)

def verificar_registro(data, valor, tipo):
    # Ignorando registros com datas inválidas
    if pd.isna(data) or valor is None:
        return False

    query = f"""
    --sql
    SELECT 1
    FROM LANC_CONTA_FIN LCF
    WHERE LCF.DATA_DISPONIVEL = '{data.replace("/", ".")}'
      AND LCF.COD_CONTA_FINANCEIRA = 25
      AND LCF.VALOR_LANCAMENTO_CONTA = {valor}
      AND LCF.TIPO_LANCAMENTO_CONTA = '{tipo}';
    """
    cur.execute(query)
    return cur.fetchone() is not None

# Identificar registros conciliados e não conciliados
nao_conciliados = []
conciliados = []

for _, row in df_xlsx.iterrows():
    data = row['Data']
    valor = row['Valor']
    lancamento = row['Lançamento']
    tipo = 'C' if valor >= 0 else 'D'

    if verificar_registro(data, abs(valor), tipo):
        conciliados.append(row)
    else:
        nao_conciliados.append(row)

# Convertendo listas para DataFrames
df_conciliados = pd.DataFrame(conciliados, columns=df_xlsx.columns)
df_nao_conciliados = pd.DataFrame(nao_conciliados, columns=df_xlsx.columns)

# Exibindo resultados
print("Registros não conciliados:")
print(df_nao_conciliados)
print("\nRegistros conciliados:")
print(df_conciliados)

# Fechar a conexão
cur.close()
conn.close()