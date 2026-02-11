from db_lerconfiguracao import ler_configuracao, get_db

db = get_db()   

def get_db_delean():
    """Conecta ao banco DELEAN usando as configurações"""
    config = ler_configuracao()
    
    if not isinstance(config, dict):
        print("Erro: Configuração não é um dicionário válido")
        return None
    
    required_keys = ['USUARIO_BD', 'SENHA_BD', 'DIR_DADOS']
    missing_keys = [key for key in required_keys if key not in config]
    
    if missing_keys:
        print(f"Erro: Chaves de configuração faltando: {missing_keys}")
        return None
    
    try:
        print(f"Conectando ao DELEAN: {config['DIR_DADOS']}")
        connection = db.connect(
            database=config['DIR_DADOS'],
            user=config['USUARIO_BD'],
            password=config['SENHA_BD']
        )
        return connection
    except Exception as e:
        print(f"Erro ao conectar no banco DELEAN: {e}")
        return None

def get_db_procel():
    """Conecta ao banco PROCEL modificando temporariamente a configuração"""
    config = ler_configuracao()
    
    if not isinstance(config, dict):
        print("Erro: Configuração não é um dicionário válido")
        return None
    
    required_keys = ['USUARIO_BD', 'SENHA_BD']
    missing_keys = [key for key in required_keys if key not in config]
    
    if missing_keys:
        print(f"Erro: Chaves de configuração faltando: {missing_keys}")
        return None
    
    try:
        procel_database = 'D:\\G3\\Dados\\PROCEL.FDB'
        print(f"Conectando ao PROCEL: {procel_database}")
        
        connection = db.connect(
            database=procel_database,
            user=config['USUARIO_BD'],
            password=config['SENHA_BD']
        )
        return connection
    except Exception as e:
        print(f"Erro ao conectar no banco PROCEL: {e}")
        return None
    except Exception as e:
        print(f"Erro ao conectar no banco PROCEL: {e}")
        return None

def test_connection(connection, name):
    """Testa a conexão e mostra informações de debug"""
    print(f"\n=== DEBUG {name} ===")
    print(f"Tipo da conexão: {type(connection)}")
    print(f"Métodos disponíveis: {[m for m in dir(connection) if not m.startswith('_')]}")
    
    # Tenta diferentes formas de obter um cursor
    cursor = None
    try:
        if hasattr(connection, 'cursor'):
            cursor = connection.cursor()
            print(f"✓ cursor() funciona - Tipo: {type(cursor)}")
        else:
            print("✗ Método cursor() não encontrado")
    except Exception as e:
        print(f"✗ Erro ao criar cursor: {e}")
    
    return cursor

def get_tables_list(connection):
    """Obtém lista de tabelas do banco"""
    try:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT RDB$RELATION_NAME 
            FROM RDB$RELATIONS 
            WHERE RDB$SYSTEM_FLAG = 0 
            AND RDB$RELATION_TYPE = 0
            ORDER BY RDB$RELATION_NAME
        """)
        tables = [row[0].strip() for row in cursor.fetchall()]
        cursor.close()
        return tables
    except Exception as e:
        print(f"Erro ao obter lista de tabelas: {e}")
        return []

def get_table_ddl(connection, table_name):
    """Gera o DDL de uma tabela específica"""
    try:
        cursor = connection.cursor()
        
        # Busca informações dos campos
        cursor.execute("""
            SELECT 
                rf.RDB$FIELD_NAME,
                rf.RDB$FIELD_SOURCE,
                rf.RDB$NULL_FLAG,
                rf.RDB$DEFAULT_SOURCE,
                f.RDB$FIELD_TYPE,
                f.RDB$FIELD_SUB_TYPE,
                f.RDB$FIELD_LENGTH,
                f.RDB$FIELD_PRECISION,
                f.RDB$FIELD_SCALE,
                f.RDB$CHARACTER_LENGTH,
                f.RDB$CHARACTER_SET_ID
            FROM RDB$RELATION_FIELDS rf
            JOIN RDB$FIELDS f ON rf.RDB$FIELD_SOURCE = f.RDB$FIELD_NAME
            WHERE rf.RDB$RELATION_NAME = ?
            ORDER BY rf.RDB$FIELD_POSITION
        """, (table_name,))
        
        fields = cursor.fetchall()
        cursor.close()
        
        if not fields:
            return None
            
        # Monta o DDL
        ddl_lines = [f"CREATE TABLE {table_name.strip()} ("]
        field_definitions = []
        
        for field in fields:
            field_name = field[0].strip()
            field_type = get_field_type_string(field)
            null_flag = field[2]
            default_source = field[3]
            
            field_def = f"    {field_name:<15} {field_type}"
            
            # Adiciona NOT NULL se necessário
            if null_flag == 1:
                field_def += " NOT NULL"
                
            # Adiciona DEFAULT se existe
            if default_source:
                default_val = default_source.strip()
                if default_val.upper().startswith('DEFAULT'):
                    field_def += f" {default_val}"
                    
            field_definitions.append(field_def)
        
        ddl_lines.append(",\n".join(field_definitions))
        ddl_lines.append(");")
        
        return "\n".join(ddl_lines)
        
    except Exception as e:
        print(f"Erro ao gerar DDL da tabela {table_name}: {e}")
        return None

def get_field_type_string(field_info):
    """Converte informações do campo para string de tipo SQL"""
    field_type = field_info[4]
    field_sub_type = field_info[5]
    field_length = field_info[6]
    field_precision = field_info[7]
    field_scale = field_info[8]
    char_length = field_info[9]
    
    # Mapeamento dos tipos
    type_map = {
        7: "SMALLINT",
        8: "INTEGER", 
        10: "FLOAT",
        12: "DATE",
        13: "TIME",
        14: "CHAR",
        16: "BIGINT",
        27: "DOUBLE PRECISION",
        35: "TIMESTAMP",
        37: "VARCHAR",
        261: "BLOB"
    }
    
    if field_type in [14, 37]:  # CHAR ou VARCHAR
        if char_length:
            length = char_length
        else:
            length = field_length
            
        if field_type == 14:
            return f"CHAR({length})"
        else:
            return f"VARCHAR({length})"
    elif field_type == 16 and field_sub_type == 1:  # NUMERIC/DECIMAL
        if field_precision and field_scale:
            return f"NUMERIC({field_precision},{abs(field_scale)})"
        else:
            return "BIGINT"
    elif field_type == 8 and field_sub_type == 1:  # NUMERIC/DECIMAL
        if field_precision and field_scale:
            return f"NUMERIC({field_precision},{abs(field_scale)})"
        else:
            return "INTEGER"
    elif field_type == 261:  # BLOB
        if field_sub_type == 1:
            return "BLOB SUB_TYPE TEXT"
        else:
            return "BLOB"
    else:
        return type_map.get(field_type, "UNKNOWN")

def execute_ddl(connection, ddl):
    """Executa um comando DDL no banco"""
    try:
        cursor = connection.cursor()
        cursor.execute(ddl)
        connection.commit()
        cursor.close()
        return True
    except Exception as e:
        print(f"Erro ao executar DDL: {e}")
        try:
            connection.rollback()
        except:
            pass
        return False

def table_exists(connection, table_name):
    """Verifica se uma tabela existe no banco"""
    try:
        cursor = connection.cursor()
        cursor.execute("""
            SELECT COUNT(*) 
            FROM RDB$RELATIONS 
            WHERE RDB$SYSTEM_FLAG = 0 
            AND RDB$RELATION_TYPE = 0
            AND UPPER(TRIM(RDB$RELATION_NAME)) = UPPER(?)
        """, (table_name.strip(),))
        
        result = cursor.fetchone()
        cursor.close()
        return result[0] > 0
    except Exception as e:
        print(f"Erro ao verificar se tabela {table_name} existe: {e}")
        return False

def comparar_e_criar_tabelas():
    """Função principal que compara os bancos e cria as tabelas faltantes"""
    print("Iniciando comparação entre bancos DELEAN e PROCEL...")
    
    # Conecta aos bancos usando as funções corretas
    conn_delean = get_db_delean()
    conn_procel = get_db_procel()
    
    if not conn_delean or not conn_procel:
        print("Erro: Não foi possível conectar aos bancos.")
        return
    
    try:
        # Obtém lista de tabelas de cada banco
        print("Obtendo lista de tabelas do DELEAN...")
        tables_delean = set(get_tables_list(conn_delean))
        print(f"DELEAN possui {len(tables_delean)} tabelas")
        
        print("Obtendo lista de tabelas do PROCEL...")
        tables_procel = set(get_tables_list(conn_procel))
        print(f"PROCEL possui {len(tables_procel)} tabelas")
        
        # Encontra tabelas que existem no PROCEL mas não no DELEAN
        tables_to_create = tables_procel - tables_delean
        
        if not tables_to_create:
            print("✓ Todas as tabelas do PROCEL já existem no DELEAN.")
            return
        
        print(f"\nEncontradas {len(tables_to_create)} tabelas para criar no DELEAN:")
        
        # Mostra apenas as primeiras 10 tabelas para não poluir o log
        tables_sorted = sorted(tables_to_create)
        for table in tables_sorted[:10]:
            print(f"  - {table}")
        
        if len(tables_to_create) > 10:
            print(f"  ... e mais {len(tables_to_create) - 10} tabelas")
        
        # Pergunta se deseja continuar
        print(f"\nDeseja continuar com a criação das {len(tables_to_create)} tabelas? (s/n)")
        resposta = input().lower().strip()
        
        if resposta not in ['s', 'sim', 'y', 'yes']:
            print("Operação cancelada pelo usuário.")
            return
        
        # Cria as tabelas faltantes
        success_count = 0
        error_count = 0
        skipped_count = 0
        
        for i, table_name in enumerate(tables_sorted, 1):
            print(f"\n[{i}/{len(tables_sorted)}] Processando tabela: {table_name}")
            
            # Verifica novamente se a tabela já existe (dupla verificação)
            if table_exists(conn_delean, table_name):
                print(f"⚠ Tabela {table_name} já existe no DELEAN, pulando...")
                skipped_count += 1
                continue
            
            # Gera DDL da tabela do PROCEL
            ddl = get_table_ddl(conn_procel, table_name)
            if ddl:
                # Executa DDL no DELEAN
                if execute_ddl(conn_delean, ddl):
                    print(f"✓ Tabela {table_name} criada com sucesso no DELEAN")
                    success_count += 1
                else:
                    print(f"✗ Erro ao criar tabela {table_name} no DELEAN")
                    error_count += 1
            else:
                print(f"✗ Erro ao gerar DDL para tabela {table_name}")
                error_count += 1
        
        print(f"\n=== RESUMO FINAL ===")
        print(f"Tabelas processadas: {len(tables_to_create)}")
        print(f"Tabelas criadas com sucesso: {success_count}")
        print(f"Tabelas com erro: {error_count}")
        print(f"Tabelas já existentes (puladas): {skipped_count}")
        
        if success_count > 0:
            print(f"✓ {success_count} tabelas foram criadas com sucesso!")
        if error_count > 0:
            print(f"⚠ {error_count} tabelas tiveram erro na criação")
        
    except Exception as e:
        print(f"Erro durante a comparação: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Fecha conexões
        try:
            if conn_delean:
                conn_delean.close()
        except:
            pass
        try:
            if conn_procel:
                conn_procel.close()
        except:
            pass
        print("Conexões fechadas.")

if __name__ == "__main__":
    comparar_e_criar_tabelas()


