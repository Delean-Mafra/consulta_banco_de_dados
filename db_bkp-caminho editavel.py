import subprocess
import os
import time
from db_lerconfiguracao import ler_configuracao, nome_alias

lc = ler_configuracao()
apelido = nome_alias()['APELIDO_BANCO']

# Configurações do banco de dados
DIR_DADOS = lc['DIR_DADOS']
USUARIO_BD = lc['USUARIO_BD']
SENHA_BD = lc['SENHA_BD']

# Definindo as variáveis de ambiente
os.environ['ISC_USER'] = USUARIO_BD
os.environ['ISC_PASSWORD'] = SENHA_BD

# Definindo o caminho para o Firebird
firebird_path = lc['FIREBIRD_PATH']

# Solicitando ao usuário que insira o caminho do arquivo de banco de dados
db_path = input("Por favor, insira o caminho do arquivo de banco de dados: ")

# Executando o GFIX
print("Executando o GFIX...")
subprocess.run([os.path.join(firebird_path, 'gfix'), '-v', '-f', db_path, '-user', os.environ['ISC_USER'], '-pass', os.environ['ISC_PASSWORD']])
subprocess.run([os.path.join(firebird_path, 'gfix'), '-m', '-i', db_path, '-user', os.environ['ISC_USER'], '-pass', os.environ['ISC_PASSWORD']])

# Fazendo backup da base de dados
print("Fazendo backup da base de dados...")
data = time.strftime('%d-%m-%Y')
subprocess.run([os.path.join(firebird_path, 'gbak'), '-g', '-b', '-z', '-l', '-v', db_path, f"{lc['PASTA_DADOS']}{apelido}_{data}.FBK", '-user', os.environ['ISC_USER'], '-pass', os.environ['ISC_PASSWORD']])

# Gerando novo banco de dados
print("Gerando novo banco de dados...")
subprocess.run([os.path.join(firebird_path, 'gbak'), '-g', '-c', '-z', '-v', f"{lc['PASTA_DADOS']}{apelido}_{data}.FBK", f"{lc['PASTA_DADOS']}{apelido}_{data}_NOVO.FDB", '-user', os.environ['ISC_USER'], '-pass', os.environ['ISC_PASSWORD']])

print("Backup e restore concluídos com sucesso!")
