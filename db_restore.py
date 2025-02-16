import os
import subprocess
import sys
from db_lerconfiguracao import ler_configuracao

lc = ler_configuracao()


def restore_database():
    try:
        print("Restaurador de Banco de Dados Firebird")
        print("======================================")



        # Ler configurações do arquivo

        if 'USUARIO_BD' not in lc or 'SENHA_BD' not in lc:
            raise KeyError("Usuário e/ou senha do banco de dados não encontrados no arquivo de configuração.")

        ISC_USER = lc['USUARIO_BD']
        ISC_PASSWORD = lc['SENHA_BD']
        FIREBIRD_PATH = lc['FIREBIRD_PATH']

        # Solicitar o caminho do novo banco de dados
        db_path = input("Digite o caminho do banco de dados que será criado ou sobrescrito: ").strip()
        if not db_path.strip().endswith(".FDB"):  # Remover espaços extras antes de verificar
            raise ValueError("O caminho deve terminar com '.FDB'.")

        # Solicitar o caminho do backup a ser restaurado
        bkp_path = input("Digite o caminho do arquivo de backup (FBK) a ser restaurado: ").strip()
        if not bkp_path.strip().endswith(".FBK"):  # Remover espaços extras antes de verificar
            raise ValueError("O caminho deve terminar com '.FBK'.")

        # Validar se os arquivos e caminhos existem
        if not os.path.exists(bkp_path):
            raise FileNotFoundError(f"O arquivo de backup '{bkp_path}' não foi encontrado.")
        if os.path.exists(db_path):
            overwrite = input(f"O banco de dados '{db_path}' já existe. Deseja sobrescrevê-lo? (S/N): ").strip().lower()
            if overwrite != 's':
                print("Operação cancelada pelo usuário.")
                sys.exit()
            os.remove(db_path)  # Excluir o banco de dados existente para sobrescrever

        # Comando para restaurar o banco de dados
        print("Restaurando o banco de dados...")
        subprocess.run(
            [
                os.path.join(FIREBIRD_PATH, "gbak"),
                "-c",  # Restore
                "-v",  # Verbose
                bkp_path,  # Arquivo de backup
                db_path,  # Banco de dados que será criado
                "-user", ISC_USER,
                "-pass", ISC_PASSWORD
            ],
            check=True
        )
        print(f"Banco de dados restaurado com sucesso em '{db_path}'.")

    except subprocess.CalledProcessError as e:
        print(f"Erro ao executar o comando gbak: {e}")
    except Exception as e:
        print(f"Erro: {e}")

if __name__ == "__main__":
    restore_database()
