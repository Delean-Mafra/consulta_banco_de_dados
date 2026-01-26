import subprocess
import os
import zipfile
import shutil
import webbrowser
import time
import psutil
import sys
from db_lerconfiguracao import ler_configuracao, nome_alias

lc = ler_configuracao()

apelido = nome_alias()['APELIDO_BANCO']   

def main():
    try:
        # Verifique todos os processos em execução
        for proc in psutil.process_iter(['pid', 'name']):
            # Verifique se o processo 'app' está em execução
            if proc.info['name'] == lc['APLICATIVO']:
                print("O banco de dados está em uso, por favor feche o 'app'.")
                answer = input("Deseja tentar iniciar o bkp novamente? Digite 'S' para sim ou qualquer outra tecla para 'Não': ")
                if answer.lower() == 's':
                    # Se o usuário quiser tentar novamente, termine o processo e continue com o script
                    proc.kill()
                    proc.wait()  # Aguarde o término do processo
                else:
                    # Se o usuário não quiser tentar novamente, termine o script
                    sys.exit()

        # Adicione um tempo de espera para garantir que o processo foi encerrado
        time.sleep(5)

        # Configurações do banco de dados
        DIR_DADOS = lc['DIR_DADOS']
        USUARIO_BD = lc['USUARIO_BD']
        SENHA_BD = lc['SENHA_BD']

        # Definindo as variáveis de ambiente
        os.environ['ISC_USER'] = USUARIO_BD
        os.environ['ISC_PASSWORD'] = SENHA_BD

        # Definindo o caminho para o Firebird
        firebird_path = lc['FIREBIRD_PATH']

        # Definindo o caminho para o arquivo de banco de dados
        db_path = f"{DIR_DADOS}"

        # Movendo e renomeando o arquivo de banco de dados original para a pasta de backup
        data = time.strftime('%d-%m-%Y')
        bkp_path = f"{lc['CAMINHO_BKP']}{apelido}_{data}_bkp.FDB"
        shutil.move(db_path, bkp_path)

        # Executando o GFIX
        print("Executando o GFIX...")
        subprocess.run([os.path.join(firebird_path, 'gfix'), '-v', '-f', bkp_path, '-user', os.environ['ISC_USER'], '-pass', os.environ['ISC_PASSWORD']])
        subprocess.run([os.path.join(firebird_path, 'gfix'), '-m', '-i', bkp_path, '-user', os.environ['ISC_USER'], '-pass', os.environ['ISC_PASSWORD']])

        # Fazendo backup da base de dados
        print("Fazendo backup da base de dados...")
        bkp_file = f"{lc['PASTA_DADOS']}{apelido}_{data}.FBK"
        subprocess.run([os.path.join(firebird_path, 'gbak'), '-g', '-b', '-z', '-l', '-v', bkp_path, bkp_file, '-user', os.environ['ISC_USER'], '-pass', os.environ['ISC_PASSWORD']])

        # Gerando novo banco de dados
        print("Gerando novo banco de dados...")
        new_db_path = f"{lc['PASTA_DADOS']}{apelido}_{data}_NOVO.FDB"
        subprocess.run([os.path.join(firebird_path, 'gbak'), '-g', '-c', '-z', '-v', bkp_file, new_db_path, '-user', os.environ['ISC_USER'], '-pass', os.environ['ISC_PASSWORD']])

        # Compactando o novo banco de dados
        print("Compactando o novo banco de dados...")
        with zipfile.ZipFile(f"{new_db_path}.zip", 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.write(new_db_path)

        # Renomeando o novo banco de dados para o nome original
        shutil.move(new_db_path, db_path)

        # Excluindo o arquivo de backup
        os.remove(bkp_file)

        print("Backup, restore, compactação e renomeação concluídos com sucesso!")

        # Abrindo o Google Drive no navegador
        webbrowser.open(lc['CAMINHO_NUVEM'])

        time.sleep(5)
        # Excluindo o arquivo "iphist.dat"
        try:
            os.remove("iphist.dat")
            print("Arquivo 'iphist.dat' excluído com sucesso!")
        except FileNotFoundError:
            print("Arquivo 'iphist.dat' não encontrado.")

    except Exception as e:
        print(f"Ocorreu um erro: {e}")
        answer = input("Deseja tentar executar o código novamente? Digite 'S' para sim ou qualquer outra tecla para 'Não'.")
        if answer.lower() == 's':
            main()
        else:
            sys.exit()

if __name__ == "__main__":
    main()
