from datetime import date, datetime, time
from decimal import Decimal

from flask import Flask, render_template_string

from db_lerconfiguracao import get_db, ler_configuracao

PROCEL_DB_PATH = r"D:\G3\Dados\PROCEL.FDB"
TABLE_NAME = "PARAMETRO"
KEY_COLUMN = "NOME_PARAMETRO"
PK_COLUMN = "COD_PARAMETRO"

app = Flask(__name__)
db = get_db()


def normalize_name(value):
    if value is None:
        return ""
    return str(value).strip().upper()


def sql_literal(value):
    if value is None:
        return "NULL"

    if isinstance(value, bool):
        return "1" if value else "0"

    if isinstance(value, datetime):
        return f"'{value.strftime('%Y-%m-%d %H:%M:%S')}'"

    if isinstance(value, date):
        return f"'{value.strftime('%Y-%m-%d')}'"

    if isinstance(value, time):
        return f"'{value.strftime('%H:%M:%S')}'"

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, (int, float)):
        return str(value)

    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def connect_config_db(config):
    return db.connect(
        host=config.get("SERVER"),
        database=config["DIR_DADOS"],
        user=config["USUARIO_BD"],
        password=config["SENHA_BD"],
    )


def connect_procel_db(config):
    return db.connect(
        database=PROCEL_DB_PATH,
        user=config["USUARIO_BD"],
        password=config["SENHA_BD"],
    )


def get_table_columns(connection, table_name):
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT TRIM(rf.RDB$FIELD_NAME)
        FROM RDB$RELATION_FIELDS rf
        WHERE TRIM(rf.RDB$RELATION_NAME) = ?
        ORDER BY rf.RDB$FIELD_POSITION
        """,
        (table_name,),
    )
    columns = [row[0] for row in cursor.fetchall()]
    cursor.close()
    return columns


def get_parametro_rows(connection, columns):
    select_sql = f"SELECT {', '.join(columns)} FROM {TABLE_NAME}"

    cursor = connection.cursor()
    cursor.execute(select_sql)
    rows = cursor.fetchall()
    cursor.close()

    mapped = {}
    key_idx = columns.index(KEY_COLUMN)

    for row in rows:
        key = normalize_name(row[key_idx])
        if not key:
            continue

        if key in mapped:
            continue

        mapped[key] = {columns[i]: row[i] for i in range(len(columns))}

    return mapped


def mount_insert(table_name, columns, row_dict):
    values_sql = ", ".join(sql_literal(row_dict.get(col)) for col in columns)
    columns_sql = ", ".join(columns)
    return f"INSERT INTO {table_name} ({columns_sql}) VALUES ({values_sql});"


def compare_parametros():
    config = ler_configuracao()
    required = ["USUARIO_BD", "SENHA_BD", "DIR_DADOS"]
    missing_cfg = [k for k in required if not config.get(k)]
    if missing_cfg:
        raise RuntimeError(
            "Configuração incompleta no Servidor.conf. Faltando: "
            + ", ".join(missing_cfg)
        )

    conn_main = None
    conn_procel = None

    try:
        conn_main = connect_config_db(config)
        conn_procel = connect_procel_db(config)

        cols_main = get_table_columns(conn_main, TABLE_NAME)
        cols_procel = get_table_columns(conn_procel, TABLE_NAME)

        if KEY_COLUMN not in cols_main or KEY_COLUMN not in cols_procel:
            raise RuntimeError(
                f"Campo {KEY_COLUMN} não encontrado na tabela {TABLE_NAME} em um dos bancos."
            )

        if PK_COLUMN in cols_main:
            cols_main_non_pk = [c for c in cols_main if c != PK_COLUMN]
        else:
            cols_main_non_pk = cols_main[:]

        if PK_COLUMN in cols_procel:
            cols_procel_non_pk = [c for c in cols_procel if c != PK_COLUMN]
        else:
            cols_procel_non_pk = cols_procel[:]

        rows_main = get_parametro_rows(conn_main, cols_main_non_pk)
        rows_procel = get_parametro_rows(conn_procel, cols_procel_non_pk)

        names_main = set(rows_main.keys())
        names_procel = set(rows_procel.keys())

        missing_in_procel = sorted(names_main - names_procel)
        missing_in_main = sorted(names_procel - names_main)

        insert_cols_to_procel = [
            col for col in cols_procel_non_pk if col in set(cols_main_non_pk)
        ]
        insert_cols_to_main = [
            col for col in cols_main_non_pk if col in set(cols_procel_non_pk)
        ]

        if KEY_COLUMN not in insert_cols_to_procel or KEY_COLUMN not in insert_cols_to_main:
            raise RuntimeError(
                f"Não foi possível montar INSERT sem o campo obrigatório {KEY_COLUMN}."
            )

        inserts_to_procel = [
            mount_insert(TABLE_NAME, insert_cols_to_procel, rows_main[name])
            for name in missing_in_procel
        ]

        inserts_to_main = [
            mount_insert(TABLE_NAME, insert_cols_to_main, rows_procel[name])
            for name in missing_in_main
        ]

        return {
            "main_db": config["DIR_DADOS"],
            "procel_db": PROCEL_DB_PATH,
            "total_main": len(names_main),
            "total_procel": len(names_procel),
            "missing_in_procel": missing_in_procel,
            "missing_in_main": missing_in_main,
            "inserts_to_procel": inserts_to_procel,
            "inserts_to_main": inserts_to_main,
            "insert_cols_to_procel": insert_cols_to_procel,
            "insert_cols_to_main": insert_cols_to_main,
        }

    finally:
        if conn_main:
            conn_main.close()
        if conn_procel:
            conn_procel.close()


@app.route("/")
def index():
    try:
        result = compare_parametros()

        html = """
        <!doctype html>
        <html lang="pt-br">
        <head>
            <meta charset="utf-8">
            <title>Comparador PARAMETRO</title>
            <style>
                body { font-family: Segoe UI, Arial, sans-serif; margin: 24px; background: #f5f7fb; color: #1f2a37; }
                h1 { margin-bottom: 8px; }
                .card { background: white; border-radius: 10px; padding: 16px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
                .muted { color: #4b5563; }
                .ok { color: #0f766e; }
                .warn { color: #b45309; }
                textarea { width: 100%; min-height: 260px; font-family: Consolas, monospace; font-size: 12px; }
                ul { margin-top: 8px; }
                code { background: #eef2ff; padding: 2px 6px; border-radius: 6px; }
            </style>
        </head>
        <body>
            <h1>Comparacao da tabela PARAMETRO</h1>
            <div class="card muted">
                <div><strong>Base configurada (Servidor.conf):</strong> {{ result.main_db }}</div>
                <div><strong>Base fixa PROCEL:</strong> {{ result.procel_db }}</div>
                <div><strong>Total nomes base configurada:</strong> {{ result.total_main }}</div>
                <div><strong>Total nomes PROCEL:</strong> {{ result.total_procel }}</div>
                <div><strong>Regra:</strong> comparacao feita somente por <code>NOME_PARAMETRO</code>. <code>COD_PARAMETRO</code> nao e usado.</div>
            </div>

            <div class="card">
                <h2>Nomes que existem na base configurada e faltam na PROCEL: {{ result.missing_in_procel|length }}</h2>
                {% if result.missing_in_procel %}
                    <ul>
                    {% for name in result.missing_in_procel %}
                        <li>{{ name }}</li>
                    {% endfor %}
                    </ul>
                    <p class="warn">SQL para inserir na PROCEL (sem COD_PARAMETRO, deixando auto incremento do banco):</p>
                    <textarea readonly>{{ result.inserts_to_procel|join('\n') }}</textarea>
                {% else %}
                    <p class="ok">Nenhum nome faltando na PROCEL.</p>
                {% endif %}
            </div>

            <div class="card">
                <h2>Nomes que existem na PROCEL e faltam na base configurada: {{ result.missing_in_main|length }}</h2>
                {% if result.missing_in_main %}
                    <ul>
                    {% for name in result.missing_in_main %}
                        <li>{{ name }}</li>
                    {% endfor %}
                    </ul>
                    <p class="warn">SQL para inserir na base configurada (sem COD_PARAMETRO, deixando auto incremento do banco):</p>
                    <textarea readonly>{{ result.inserts_to_main|join('\n') }}</textarea>
                {% else %}
                    <p class="ok">Nenhum nome faltando na base configurada.</p>
                {% endif %}
            </div>
        </body>
        </html>
        """

        return render_template_string(html, result=result)

    except Exception as exc:
        return (
            "<h2>Erro ao comparar PARAMETRO</h2>"
            f"<pre>{str(exc)}</pre>",
            500,
        )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5007, debug=False)
