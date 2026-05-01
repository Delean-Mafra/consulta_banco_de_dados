from datetime import date
from flask import Flask, render_template_string

from db_lerconfiguracao import get_db, ler_configuracao

# Caminho fixo usado no projeto para o banco PROCEL
PROCEL_DB_PATH = r"D:\G3\Dados\PROCEL.FDB"
OUTPUT_SQL_FILE = "sync_estrutura_bancos.sql"
OUTPUT_SQL_TO_MAIN_FILE = "sync_para_delean.sql"
OUTPUT_SQL_TO_PROCEL_FILE = "sync_para_procel.sql"
DB_CHARSET = "ISO8859_1"

DB_MAIN_LABEL = "BASE_CONFIGURADA"
DB_PROCEL_LABEL = "PROCEL"

db = get_db()
app = Flask(__name__)


# Mapeamento dos tipos de campo do Firebird para DDL textual.
FB_TYPE_MAP = {
    7: "SMALLINT",
    8: "INTEGER",
    10: "FLOAT",
    12: "DATE",
    13: "TIME",
    14: "CHAR",
    16: "BIGINT",
    23: "BOOLEAN",
    27: "DOUBLE PRECISION",
    35: "TIMESTAMP",
    37: "VARCHAR",
    261: "BLOB",
}


def normalize_name(value):
    if value is None:
        return ""
    return str(value).strip().upper()


def quote_ident(name):
    cleaned = (name or "").strip()
    if not cleaned:
        return cleaned

    # Em Firebird, usar aspas preserva o nome exatamente como criado.
    escaped = cleaned.replace('"', '""')
    return f'"{escaped}"'


def safe_strip(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return decode_db_bytes(value).strip()
    return str(value).strip()


def decode_db_bytes(raw_value):
    # Metadata de bancos legados pode vir com bytes invalidos para o codec padrao do Windows.
    # Tenta UTF-8 e depois fallback latin-1 para nunca quebrar a comparacao.
    for enc in ("utf-8", "latin-1"):
        try:
            return raw_value.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw_value.decode("latin-1", errors="replace")


def connect_main_db(config):
    return db.connect(
        host=config.get("SERVER"),
        database=config["DIR_DADOS"],
        user=config["USUARIO_BD"],
        password=config["SENHA_BD"],
        charset=DB_CHARSET,
    )


def connect_procel_db(config):
    return db.connect(
        database=PROCEL_DB_PATH,
        user=config["USUARIO_BD"],
        password=config["SENHA_BD"],
        charset=DB_CHARSET,
    )


def fetch_all(cursor, sql, params=None):
    cursor.execute(sql, params or ())
    return cursor.fetchall()


def list_user_tables(connection):
    cursor = connection.cursor()
    rows = fetch_all(
        cursor,
        """
        SELECT TRIM(r.RDB$RELATION_NAME)
        FROM RDB$RELATIONS r
        WHERE COALESCE(r.RDB$SYSTEM_FLAG, 0) = 0
          AND r.RDB$RELATION_TYPE = 0
        ORDER BY r.RDB$RELATION_NAME
        """,
    )
    cursor.close()
    return [safe_strip(row[0]) for row in rows if safe_strip(row[0])]


def list_user_procedures(connection):
    cursor = connection.cursor()
    rows = fetch_all(
        cursor,
        """
        SELECT TRIM(p.RDB$PROCEDURE_NAME)
        FROM RDB$PROCEDURES p
        WHERE COALESCE(p.RDB$SYSTEM_FLAG, 0) = 0
        ORDER BY p.RDB$PROCEDURE_NAME
        """,
    )
    cursor.close()
    return [safe_strip(row[0]) for row in rows if safe_strip(row[0])]


def list_user_generators(connection):
    cursor = connection.cursor()
    rows = fetch_all(
        cursor,
        """
        SELECT TRIM(g.RDB$GENERATOR_NAME)
        FROM RDB$GENERATORS g
        WHERE COALESCE(g.RDB$SYSTEM_FLAG, 0) = 0
          AND UPPER(TRIM(g.RDB$GENERATOR_NAME)) NOT STARTING WITH 'RDB$'
        ORDER BY g.RDB$GENERATOR_NAME
        """,
    )
    cursor.close()
    return [safe_strip(row[0]) for row in rows if safe_strip(row[0])]


def list_user_triggers(connection):
    cursor = connection.cursor()
    rows = fetch_all(
        cursor,
        """
        SELECT TRIM(t.RDB$TRIGGER_NAME)
        FROM RDB$TRIGGERS t
        WHERE COALESCE(t.RDB$SYSTEM_FLAG, 0) = 0
        ORDER BY t.RDB$TRIGGER_NAME
        """,
    )
    cursor.close()
    return [safe_strip(row[0]) for row in rows if safe_strip(row[0])]


def build_field_type(field_type, sub_type, field_length, field_precision, field_scale, char_length):
    if field_type in (14, 37):
        length = char_length or field_length or 0
        if field_type == 14:
            return f"CHAR({int(length)})"
        return f"VARCHAR({int(length)})"

    if field_type == 261:
        if sub_type == 1:
            return "BLOB SUB_TYPE TEXT"
        return "BLOB"

    # Numeric/Decimal podem ser representados em SMALLINT/INTEGER/BIGINT com sub_type 1 ou 2
    if field_type in (7, 8, 16) and sub_type in (1, 2):
        precision = int(field_precision) if field_precision else None
        scale = abs(int(field_scale)) if field_scale else 0
        base = "NUMERIC" if sub_type == 1 else "DECIMAL"
        if precision:
            return f"{base}({precision},{scale})"

    base_type = FB_TYPE_MAP.get(field_type)
    if base_type:
        return base_type

    return f"UNKNOWN_TYPE_{field_type}"


def get_table_columns_metadata(connection, table_name):
    cursor = connection.cursor()
    rows = fetch_all(
        cursor,
        """
        SELECT
            TRIM(rf.RDB$FIELD_NAME),
            COALESCE(rf.RDB$NULL_FLAG, 0),
            rf.RDB$DEFAULT_SOURCE,
            f.RDB$FIELD_TYPE,
            COALESCE(f.RDB$FIELD_SUB_TYPE, 0),
            COALESCE(f.RDB$FIELD_LENGTH, 0),
            f.RDB$FIELD_PRECISION,
            COALESCE(f.RDB$FIELD_SCALE, 0),
            COALESCE(f.RDB$CHARACTER_LENGTH, 0),
            TRIM(cs.RDB$CHARACTER_SET_NAME),
            TRIM(coll.RDB$COLLATION_NAME)
        FROM RDB$RELATION_FIELDS rf
        JOIN RDB$FIELDS f
          ON f.RDB$FIELD_NAME = rf.RDB$FIELD_SOURCE
        LEFT JOIN RDB$CHARACTER_SETS cs
          ON cs.RDB$CHARACTER_SET_ID = f.RDB$CHARACTER_SET_ID
        LEFT JOIN RDB$COLLATIONS coll
          ON coll.RDB$COLLATION_ID = f.RDB$COLLATION_ID
         AND coll.RDB$CHARACTER_SET_ID = f.RDB$CHARACTER_SET_ID
        WHERE TRIM(rf.RDB$RELATION_NAME) = ?
        ORDER BY rf.RDB$FIELD_POSITION
        """,
        (table_name,),
    )
    cursor.close()
    return rows


def get_table_constraints_metadata(connection, table_name):
    cursor = connection.cursor()
    rows = fetch_all(
        cursor,
        """
        SELECT
            TRIM(rc.RDB$CONSTRAINT_NAME),
            TRIM(rc.RDB$CONSTRAINT_TYPE),
            TRIM(i.RDB$INDEX_NAME),
            TRIM(refc.RDB$CONST_NAME_UQ),
            TRIM(refc.RDB$UPDATE_RULE),
            TRIM(refc.RDB$DELETE_RULE)
        FROM RDB$RELATION_CONSTRAINTS rc
        LEFT JOIN RDB$INDICES i
          ON i.RDB$INDEX_NAME = rc.RDB$INDEX_NAME
        LEFT JOIN RDB$REF_CONSTRAINTS refc
          ON refc.RDB$CONSTRAINT_NAME = rc.RDB$CONSTRAINT_NAME
        WHERE TRIM(rc.RDB$RELATION_NAME) = ?
        ORDER BY rc.RDB$CONSTRAINT_TYPE, rc.RDB$CONSTRAINT_NAME
        """,
        (table_name,),
    )
    cursor.close()
    return rows


def get_index_fields(connection, index_name):
    cursor = connection.cursor()
    rows = fetch_all(
        cursor,
        """
        SELECT TRIM(seg.RDB$FIELD_NAME)
        FROM RDB$INDEX_SEGMENTS seg
        WHERE TRIM(seg.RDB$INDEX_NAME) = ?
        ORDER BY seg.RDB$FIELD_POSITION
        """,
        (index_name,),
    )
    cursor.close()
    return [safe_strip(row[0]) for row in rows if safe_strip(row[0])]


def get_unique_constraint_target(connection, unique_constraint_name):
    cursor = connection.cursor()
    rows = fetch_all(
        cursor,
        """
        SELECT
            TRIM(rc.RDB$RELATION_NAME),
            TRIM(rc.RDB$INDEX_NAME)
        FROM RDB$RELATION_CONSTRAINTS rc
        WHERE TRIM(rc.RDB$CONSTRAINT_NAME) = ?
        """,
        (unique_constraint_name,),
    )
    cursor.close()
    if not rows:
        return None, None

    relation_name, index_name = rows[0]
    return safe_strip(relation_name), safe_strip(index_name)


def get_check_constraint_source(connection, constraint_name):
    cursor = connection.cursor()
    rows = fetch_all(
        cursor,
        """
        SELECT cc.RDB$TRIGGER_SOURCE
        FROM RDB$CHECK_CONSTRAINTS cc
        JOIN RDB$TRIGGERS t
          ON t.RDB$TRIGGER_NAME = cc.RDB$TRIGGER_NAME
        WHERE TRIM(cc.RDB$CONSTRAINT_NAME) = ?
        """,
        (constraint_name,),
    )
    cursor.close()
    if not rows:
        return ""

    source = rows[0][0]
    return safe_strip(source)


def build_table_ddl(connection, table_name):
    columns = get_table_columns_metadata(connection, table_name)
    if not columns:
        return ""

    lines = [f"CREATE TABLE {quote_ident(table_name)} ("]
    col_defs = []

    for row in columns:
        (
            field_name,
            null_flag,
            default_source,
            field_type,
            field_sub_type,
            field_length,
            field_precision,
            field_scale,
            char_length,
            charset_name,
            collation_name,
        ) = row

        field_type_sql = build_field_type(
            field_type,
            field_sub_type,
            field_length,
            field_precision,
            field_scale,
            char_length,
        )

        field_sql = f"    {quote_ident(field_name)} {field_type_sql}"

        default_text = safe_strip(default_source)
        if default_text:
            field_sql += f" {default_text}"

        if int(null_flag) == 1:
            field_sql += " NOT NULL"

        if field_type in (14, 37):
            if charset_name:
                field_sql += f" CHARACTER SET {quote_ident(charset_name)}"
            if collation_name and collation_name.upper() != "NONE":
                field_sql += f" COLLATE {quote_ident(collation_name)}"

        col_defs.append(field_sql)

    constraints = get_table_constraints_metadata(connection, table_name)
    for constraint in constraints:
        (
            cons_name,
            cons_type,
            index_name,
            const_name_uq,
            update_rule,
            delete_rule,
        ) = constraint

        c_name = safe_strip(cons_name)
        c_type = safe_strip(cons_type).upper()
        i_name = safe_strip(index_name)

        if c_type in ("PRIMARY KEY", "UNIQUE"):
            fields = get_index_fields(connection, i_name)
            if fields:
                fields_sql = ", ".join(quote_ident(f) for f in fields)
                col_defs.append(f"    {c_type} ({fields_sql})")

        elif c_type == "FOREIGN KEY":
            fk_fields = get_index_fields(connection, i_name)
            ref_table, ref_index = get_unique_constraint_target(connection, safe_strip(const_name_uq))
            if fk_fields and ref_table and ref_index:
                ref_fields = get_index_fields(connection, ref_index)
                if ref_fields and len(ref_fields) == len(fk_fields):
                    fk_sql = (
                        f"    FOREIGN KEY "
                        f"({', '.join(quote_ident(f) for f in fk_fields)}) "
                        f"REFERENCES {quote_ident(ref_table)} "
                        f"({', '.join(quote_ident(f) for f in ref_fields)})"
                    )
                    if update_rule and update_rule.upper() != "RESTRICT":
                        fk_sql += f" ON UPDATE {update_rule.upper()}"
                    if delete_rule and delete_rule.upper() != "RESTRICT":
                        fk_sql += f" ON DELETE {delete_rule.upper()}"
                    col_defs.append(fk_sql)

        elif c_type == "CHECK":
            check_source = get_check_constraint_source(connection, c_name)
            if check_source:
                compact = " ".join(check_source.replace("\n", " ").split())
                if "CHECK" in compact.upper():
                    check_expr = compact[compact.upper().find("CHECK"):]
                else:
                    check_expr = f"CHECK ({compact})"
                col_defs.append(f"    {check_expr}")

    lines.append(",\n".join(col_defs))
    lines.append(");")

    return "\n".join(lines)


def build_procedure_ddl(connection, procedure_name):
    cursor = connection.cursor()
    rows = fetch_all(
        cursor,
        """
        SELECT p.RDB$PROCEDURE_SOURCE, p.RDB$PROCEDURE_INPUTS, p.RDB$PROCEDURE_OUTPUTS
        FROM RDB$PROCEDURES p
        WHERE TRIM(p.RDB$PROCEDURE_NAME) = ?
        """,
        (procedure_name,),
    )
    cursor.close()

    if not rows:
        return ""

    source = safe_strip(rows[0][0])
    has_inputs = int(rows[0][1] or 0)
    has_outputs = int(rows[0][2] or 0)
    if not source:
        return ""

    params = []
    if has_inputs or has_outputs:
        cursor = connection.cursor()
        param_rows = fetch_all(
            cursor,
            """
            SELECT
                TRIM(pp.RDB$PARAMETER_NAME),
                pp.RDB$PARAMETER_TYPE,
                f.RDB$FIELD_TYPE,
                COALESCE(f.RDB$FIELD_SUB_TYPE, 0),
                COALESCE(f.RDB$FIELD_LENGTH, 0),
                f.RDB$FIELD_PRECISION,
                COALESCE(f.RDB$FIELD_SCALE, 0),
                COALESCE(f.RDB$CHARACTER_LENGTH, 0)
            FROM RDB$PROCEDURE_PARAMETERS pp
            LEFT JOIN RDB$FIELDS f ON f.RDB$FIELD_NAME = pp.RDB$FIELD_SOURCE
            WHERE TRIM(pp.RDB$PROCEDURE_NAME) = ?
            ORDER BY pp.RDB$PARAMETER_TYPE, pp.RDB$PARAMETER_NUMBER
            """,
            (procedure_name,),
        )
        cursor.close()

        for param_row in param_rows:
            param_name = safe_strip(param_row[0])
            param_type = int(param_row[1] or 0)
            field_type = param_row[2]
            field_sub_type = param_row[3]
            field_length = param_row[4]
            field_precision = param_row[5]
            field_scale = param_row[6]
            char_length = param_row[7]

            field_type_sql = build_field_type(
                field_type,
                field_sub_type,
                field_length,
                field_precision,
                field_scale,
                char_length,
            )

            param_dir = "OUT" if param_type == 1 else "IN"
            params.append(f"{param_dir} {quote_ident(param_name)} {field_type_sql}")

    upper_source = source.upper()
    if "CREATE PROCEDURE" in upper_source or "CREATE OR ALTER PROCEDURE" in upper_source:
        body = source
    else:
        params_section = ""
        if params:
            params_section = f"({', '.join(params)})\n"
        body = f"CREATE PROCEDURE {quote_ident(procedure_name)}\n{params_section}{source}"

    return "SET TERM ^ ;\n" + body + "^\nSET TERM ; ^"


def build_generator_ddl(generator_name):
    return f"CREATE SEQUENCE {quote_ident(generator_name)};"


def build_trigger_ddl(connection, trigger_name):
    cursor = connection.cursor()
    rows = fetch_all(
        cursor,
        """
        SELECT
            TRIM(t.RDB$RELATION_NAME),
            COALESCE(t.RDB$TRIGGER_SEQUENCE, 0),
            COALESCE(t.RDB$TRIGGER_INACTIVE, 0),
            t.RDB$TRIGGER_TYPE,
            t.RDB$TRIGGER_SOURCE
        FROM RDB$TRIGGERS t
        WHERE TRIM(t.RDB$TRIGGER_NAME) = ?
        """,
        (trigger_name,),
    )
    cursor.close()

    if not rows:
        return ""

    relation_name, trigger_sequence, trigger_inactive, trigger_type, trigger_source = rows[0]
    source = safe_strip(trigger_source)
    if not source:
        return ""

    upper_source = source.upper()
    if "CREATE TRIGGER" in upper_source or "CREATE OR ALTER TRIGGER" in upper_source:
        body = source
    else:
        relation = safe_strip(relation_name)
        position = int(trigger_sequence)
        active = "INACTIVE" if int(trigger_inactive) == 1 else "ACTIVE"
        trigger_event = decode_trigger_event(trigger_type)

        body = (
            f"CREATE TRIGGER {quote_ident(trigger_name)} FOR {quote_ident(relation)}\n"
            f"{active} {trigger_event} POSITION {position}\n"
            f"{source}"
        )

    return "SET TERM ^ ;\n" + body + "^\nSET TERM ; ^"


def decode_trigger_event(trigger_type):
    trigger_type = int(trigger_type or 0)

    # Mapeamento dos tipos de trigger de tabela no Firebird.
    mapping = {
        1: "BEFORE INSERT",
        2: "AFTER INSERT",
        3: "BEFORE UPDATE",
        4: "AFTER UPDATE",
        5: "BEFORE DELETE",
        6: "AFTER DELETE",
        17: "BEFORE INSERT OR UPDATE",
        18: "AFTER INSERT OR UPDATE",
        25: "BEFORE INSERT OR DELETE",
        26: "AFTER INSERT OR DELETE",
        27: "BEFORE UPDATE OR DELETE",
        28: "AFTER UPDATE OR DELETE",
        113: "BEFORE INSERT OR UPDATE OR DELETE",
        114: "AFTER INSERT OR UPDATE OR DELETE",
    }
    return mapping.get(trigger_type, "BEFORE INSERT")


def make_section_header(title):
    return [
        "",
        "-- ============================================================",
        f"-- {title}",
        "-- ============================================================",
        "",
    ]


def compare_objects(source_names, target_names):
    source_map = {normalize_name(name): name for name in source_names}
    target_keys = {normalize_name(name) for name in target_names}

    missing_keys = sorted(set(source_map.keys()) - target_keys)
    return [source_map[key] for key in missing_keys if key in source_map]


def append_ddls_for_missing(
    sql_lines,
    object_type_label,
    source_label,
    target_label,
    missing_names,
    ddl_builder,
):
    if not missing_names:
        return

    sql_lines.extend(
        make_section_header(
            f"{object_type_label}: faltando em {target_label} e existentes em {source_label}"
        )
    )

    for object_name in missing_names:
        sql_lines.append(f"-- {object_type_label}: {object_name}")
        ddl = ddl_builder(object_name)
        if ddl:
            sql_lines.append(ddl)
        else:
            sql_lines.append("-- Nao foi possivel montar DDL para este objeto.")
        sql_lines.append("")


def compare_and_generate_sql(
    output_path=OUTPUT_SQL_FILE,
    output_main_path=OUTPUT_SQL_TO_MAIN_FILE,
    output_procel_path=OUTPUT_SQL_TO_PROCEL_FILE,
):
    config = ler_configuracao()

    required = ["USUARIO_BD", "SENHA_BD", "DIR_DADOS"]
    missing_cfg = [key for key in required if not config.get(key)]
    if missing_cfg:
        raise RuntimeError(
            "Configuracao incompleta no Servidor.conf. Faltando: "
            + ", ".join(missing_cfg)
        )

    conn_main = None
    conn_procel = None

    try:
        conn_main = connect_main_db(config)
        conn_procel = connect_procel_db(config)

        tables_main = list_user_tables(conn_main)
        tables_procel = list_user_tables(conn_procel)

        procedures_main = list_user_procedures(conn_main)
        procedures_procel = list_user_procedures(conn_procel)

        generators_main = list_user_generators(conn_main)
        generators_procel = list_user_generators(conn_procel)

        triggers_main = list_user_triggers(conn_main)
        triggers_procel = list_user_triggers(conn_procel)

        missing_tables_in_procel = compare_objects(tables_main, tables_procel)
        missing_tables_in_main = compare_objects(tables_procel, tables_main)

        missing_procs_in_procel = compare_objects(procedures_main, procedures_procel)
        missing_procs_in_main = compare_objects(procedures_procel, procedures_main)

        missing_generators_in_procel = compare_objects(generators_main, generators_procel)
        missing_generators_in_main = compare_objects(generators_procel, generators_main)

        missing_triggers_in_procel = compare_objects(triggers_main, triggers_procel)
        missing_triggers_in_main = compare_objects(triggers_procel, triggers_main)

        sql_lines = [
            "-- Script gerado automaticamente",
            f"-- Data: {date.today().isoformat()}",
            f"-- Origem principal: {config['DIR_DADOS']}",
            f"-- Origem PROCEL: {PROCEL_DB_PATH}",
            "",
        ]

        sql_lines_to_main = [
            "-- Script gerado automaticamente (DESTINO: BASE_CONFIGURADA)",
            f"-- Data: {date.today().isoformat()}",
            f"-- Destino: {config['DIR_DADOS']}",
            f"-- Origem de leitura: {PROCEL_DB_PATH}",
            "",
        ]

        sql_lines_to_procel = [
            "-- Script gerado automaticamente (DESTINO: PROCEL)",
            f"-- Data: {date.today().isoformat()}",
            f"-- Destino: {PROCEL_DB_PATH}",
            f"-- Origem de leitura: {config['DIR_DADOS']}",
            "",
        ]

        append_ddls_for_missing(
            sql_lines,
            "TABLE",
            DB_MAIN_LABEL,
            DB_PROCEL_LABEL,
            missing_tables_in_procel,
            lambda name: build_table_ddl(conn_main, name),
        )
        append_ddls_for_missing(
            sql_lines,
            "TABLE",
            DB_PROCEL_LABEL,
            DB_MAIN_LABEL,
            missing_tables_in_main,
            lambda name: build_table_ddl(conn_procel, name),
        )
        append_ddls_for_missing(
            sql_lines_to_procel,
            "TABLE",
            DB_MAIN_LABEL,
            DB_PROCEL_LABEL,
            missing_tables_in_procel,
            lambda name: build_table_ddl(conn_main, name),
        )
        append_ddls_for_missing(
            sql_lines_to_main,
            "TABLE",
            DB_PROCEL_LABEL,
            DB_MAIN_LABEL,
            missing_tables_in_main,
            lambda name: build_table_ddl(conn_procel, name),
        )

        append_ddls_for_missing(
            sql_lines,
            "PROCEDURE",
            DB_MAIN_LABEL,
            DB_PROCEL_LABEL,
            missing_procs_in_procel,
            lambda name: build_procedure_ddl(conn_main, name),
        )
        append_ddls_for_missing(
            sql_lines,
            "PROCEDURE",
            DB_PROCEL_LABEL,
            DB_MAIN_LABEL,
            missing_procs_in_main,
            lambda name: build_procedure_ddl(conn_procel, name),
        )
        append_ddls_for_missing(
            sql_lines_to_procel,
            "PROCEDURE",
            DB_MAIN_LABEL,
            DB_PROCEL_LABEL,
            missing_procs_in_procel,
            lambda name: build_procedure_ddl(conn_main, name),
        )
        append_ddls_for_missing(
            sql_lines_to_main,
            "PROCEDURE",
            DB_PROCEL_LABEL,
            DB_MAIN_LABEL,
            missing_procs_in_main,
            lambda name: build_procedure_ddl(conn_procel, name),
        )

        append_ddls_for_missing(
            sql_lines,
            "GENERATOR/SEQUENCE",
            DB_MAIN_LABEL,
            DB_PROCEL_LABEL,
            missing_generators_in_procel,
            lambda name: build_generator_ddl(name),
        )
        append_ddls_for_missing(
            sql_lines,
            "GENERATOR/SEQUENCE",
            DB_PROCEL_LABEL,
            DB_MAIN_LABEL,
            missing_generators_in_main,
            lambda name: build_generator_ddl(name),
        )
        append_ddls_for_missing(
            sql_lines_to_procel,
            "GENERATOR/SEQUENCE",
            DB_MAIN_LABEL,
            DB_PROCEL_LABEL,
            missing_generators_in_procel,
            lambda name: build_generator_ddl(name),
        )
        append_ddls_for_missing(
            sql_lines_to_main,
            "GENERATOR/SEQUENCE",
            DB_PROCEL_LABEL,
            DB_MAIN_LABEL,
            missing_generators_in_main,
            lambda name: build_generator_ddl(name),
        )

        append_ddls_for_missing(
            sql_lines,
            "TRIGGER",
            DB_MAIN_LABEL,
            DB_PROCEL_LABEL,
            missing_triggers_in_procel,
            lambda name: build_trigger_ddl(conn_main, name),
        )
        append_ddls_for_missing(
            sql_lines,
            "TRIGGER",
            DB_PROCEL_LABEL,
            DB_MAIN_LABEL,
            missing_triggers_in_main,
            lambda name: build_trigger_ddl(conn_procel, name),
        )
        append_ddls_for_missing(
            sql_lines_to_procel,
            "TRIGGER",
            DB_MAIN_LABEL,
            DB_PROCEL_LABEL,
            missing_triggers_in_procel,
            lambda name: build_trigger_ddl(conn_main, name),
        )
        append_ddls_for_missing(
            sql_lines_to_main,
            "TRIGGER",
            DB_PROCEL_LABEL,
            DB_MAIN_LABEL,
            missing_triggers_in_main,
            lambda name: build_trigger_ddl(conn_procel, name),
        )

        sql_text = "\n".join(sql_lines).strip() + "\n"
        sql_text_to_main = "\n".join(sql_lines_to_main).strip() + "\n"
        sql_text_to_procel = "\n".join(sql_lines_to_procel).strip() + "\n"

        with open(output_path, "w", encoding="utf-8") as fp:
            fp.write(sql_text)
        with open(output_main_path, "w", encoding="utf-8") as fp:
            fp.write(sql_text_to_main)
        with open(output_procel_path, "w", encoding="utf-8") as fp:
            fp.write(sql_text_to_procel)

        return {
            "output_sql": output_path,
            "output_sql_to_main": output_main_path,
            "output_sql_to_procel": output_procel_path,
            "main_db": config["DIR_DADOS"],
            "procel_db": PROCEL_DB_PATH,
            "missing_tables_in_procel": len(missing_tables_in_procel),
            "missing_tables_in_main": len(missing_tables_in_main),
            "missing_procs_in_procel": len(missing_procs_in_procel),
            "missing_procs_in_main": len(missing_procs_in_main),
            "missing_generators_in_procel": len(missing_generators_in_procel),
            "missing_generators_in_main": len(missing_generators_in_main),
            "missing_triggers_in_procel": len(missing_triggers_in_procel),
            "missing_triggers_in_main": len(missing_triggers_in_main),
            "tables_missing_in_procel": missing_tables_in_procel,
            "tables_missing_in_main": missing_tables_in_main,
            "procedures_missing_in_procel": missing_procs_in_procel,
            "procedures_missing_in_main": missing_procs_in_main,
            "generators_missing_in_procel": missing_generators_in_procel,
            "generators_missing_in_main": missing_generators_in_main,
            "triggers_missing_in_procel": missing_triggers_in_procel,
            "triggers_missing_in_main": missing_triggers_in_main,
            "sql_text": sql_text,
            "sql_text_to_main": sql_text_to_main,
            "sql_text_to_procel": sql_text_to_procel,
        }

    finally:
        if conn_main:
            conn_main.close()
        if conn_procel:
            conn_procel.close()


def print_summary(result):
    print("Comparacao concluida.")
    print(f"Arquivo SQL gerado: {result['output_sql']}")
    print(f"Arquivo SQL destino DELEAN: {result['output_sql_to_main']}")
    print(f"Arquivo SQL destino PROCEL: {result['output_sql_to_procel']}")
    print("-")
    print(f"TABLES faltando na PROCEL: {result['missing_tables_in_procel']}")
    print(f"TABLES faltando na BASE_CONFIGURADA: {result['missing_tables_in_main']}")
    print(f"PROCEDURES faltando na PROCEL: {result['missing_procs_in_procel']}")
    print(f"PROCEDURES faltando na BASE_CONFIGURADA: {result['missing_procs_in_main']}")
    print(
        f"GENERATORS faltando na PROCEL: {result['missing_generators_in_procel']}"
    )
    print(
        f"GENERATORS faltando na BASE_CONFIGURADA: {result['missing_generators_in_main']}"
    )
    print(f"TRIGGERS faltando na PROCEL: {result['missing_triggers_in_procel']}")
    print(f"TRIGGERS faltando na BASE_CONFIGURADA: {result['missing_triggers_in_main']}")


@app.route("/")
def index():
    try:
        result = compare_and_generate_sql()

        html = """
        <!doctype html>
        <html lang="pt-br">
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Comparador de Estrutura Firebird</title>
            <style>
                :root {
                    --bg: #f4f7fb;
                    --card: #ffffff;
                    --text: #1f2937;
                    --muted: #4b5563;
                    --ok: #065f46;
                    --warn: #92400e;
                    --line: #dbe3ef;
                }

                * { box-sizing: border-box; }
                body {
                    margin: 0;
                    font-family: Segoe UI, Arial, sans-serif;
                    background: radial-gradient(circle at top right, #e6eefc 0%, var(--bg) 45%, #f7fafc 100%);
                    color: var(--text);
                }
                .container {
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 24px 16px 48px;
                }
                h1 {
                    margin: 0 0 8px;
                    font-size: 30px;
                    line-height: 1.1;
                }
                .subtitle {
                    color: var(--muted);
                    margin-bottom: 18px;
                }
                .card {
                    background: var(--card);
                    border: 1px solid var(--line);
                    border-radius: 14px;
                    padding: 16px;
                    margin-bottom: 14px;
                    box-shadow: 0 3px 10px rgba(0, 0, 0, 0.04);
                }
                .grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                    gap: 12px;
                }
                h2 {
                    margin: 4px 0 10px;
                    font-size: 18px;
                }
                h3 {
                    margin: 0 0 8px;
                    font-size: 16px;
                }
                .muted { color: var(--muted); }
                .ok { color: var(--ok); }
                .warn { color: var(--warn); }
                .mono {
                    background: #f8fafc;
                    border: 1px solid var(--line);
                    border-radius: 10px;
                    padding: 10px;
                    font-family: Consolas, monospace;
                    font-size: 12px;
                    white-space: pre-wrap;
                    word-break: break-word;
                }
                ul {
                    margin: 8px 0;
                    padding-left: 20px;
                    max-height: 220px;
                    overflow: auto;
                }
                li { margin-bottom: 3px; }
                textarea {
                    width: 100%;
                    min-height: 320px;
                    font-family: Consolas, monospace;
                    font-size: 12px;
                    border: 1px solid var(--line);
                    border-radius: 10px;
                    padding: 10px;
                    resize: vertical;
                    background: #f8fafc;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Comparador de Estrutura Firebird</h1>
                <div class="subtitle">Comparacao de TABLE, PROCEDURE, GENERATOR/SEQUENCE e TRIGGER entre dois bancos.</div>

                <div class="card muted">
                    <div><strong>Base configurada:</strong> {{ result.main_db }}</div>
                    <div><strong>Base PROCEL:</strong> {{ result.procel_db }}</div>
                    <div><strong>Arquivo SQL geral:</strong> {{ result.output_sql }}</div>
                    <div><strong>SQL para executar no DELEAN:</strong> {{ result.output_sql_to_main }}</div>
                    <div><strong>SQL para executar no PROCEL:</strong> {{ result.output_sql_to_procel }}</div>
                </div>

                <div class="grid">
                    <div class="card">
                        <h2>Faltando na PROCEL</h2>
                        <div>TABLES: <strong>{{ result.missing_tables_in_procel }}</strong></div>
                        <div>PROCEDURES: <strong>{{ result.missing_procs_in_procel }}</strong></div>
                        <div>GENERATORS: <strong>{{ result.missing_generators_in_procel }}</strong></div>
                        <div>TRIGGERS: <strong>{{ result.missing_triggers_in_procel }}</strong></div>
                    </div>
                    <div class="card">
                        <h2>Faltando na Base Configurada</h2>
                        <div>TABLES: <strong>{{ result.missing_tables_in_main }}</strong></div>
                        <div>PROCEDURES: <strong>{{ result.missing_procs_in_main }}</strong></div>
                        <div>GENERATORS: <strong>{{ result.missing_generators_in_main }}</strong></div>
                        <div>TRIGGERS: <strong>{{ result.missing_triggers_in_main }}</strong></div>
                    </div>
                </div>

                <div class="grid">
                    <div class="card">
                        <h3>Objetos faltando na PROCEL</h3>
                        <div class="warn">Objects listados abaixo serao criados no PROCEL.</div>
                        <ul>
                            {% for name in result.tables_missing_in_procel %}<li>TABLE: {{ name }}</li>{% endfor %}
                            {% for name in result.procedures_missing_in_procel %}<li>PROCEDURE: {{ name }}</li>{% endfor %}
                            {% for name in result.generators_missing_in_procel %}<li>GENERATOR: {{ name }}</li>{% endfor %}
                            {% for name in result.triggers_missing_in_procel %}<li>TRIGGER: {{ name }}</li>{% endfor %}
                            {% if not result.tables_missing_in_procel and not result.procedures_missing_in_procel and not result.generators_missing_in_procel and not result.triggers_missing_in_procel %}
                                <li class="ok">Nenhum objeto faltando.</li>
                            {% endif %}
                        </ul>
                    </div>

                    <div class="card">
                        <h3>Objetos faltando na Base Configurada</h3>
                        <div class="warn">Objects listados abaixo serao criados na base configurada.</div>
                        <ul>
                            {% for name in result.tables_missing_in_main %}<li>TABLE: {{ name }}</li>{% endfor %}
                            {% for name in result.procedures_missing_in_main %}<li>PROCEDURE: {{ name }}</li>{% endfor %}
                            {% for name in result.generators_missing_in_main %}<li>GENERATOR: {{ name }}</li>{% endfor %}
                            {% for name in result.triggers_missing_in_main %}<li>TRIGGER: {{ name }}</li>{% endfor %}
                            {% if not result.tables_missing_in_main and not result.procedures_missing_in_main and not result.generators_missing_in_main and not result.triggers_missing_in_main %}
                                <li class="ok">Nenhum objeto faltando.</li>
                            {% endif %}
                        </ul>
                    </div>
                </div>

                <div class="card">
                    <h2>SQL Completo Gerado</h2>
                    <div class="muted">Este mesmo conteudo foi salvo em {{ result.output_sql }}.</div>
                    <textarea readonly>{{ result.sql_text }}</textarea>
                </div>

                <div class="card">
                    <h2>SQL para Executar no DELEAN</h2>
                    <div class="muted">Contem somente objetos faltantes na base configurada (destino DELEAN).</div>
                    <div class="muted">Arquivo: {{ result.output_sql_to_main }}</div>
                    <textarea readonly>{{ result.sql_text_to_main }}</textarea>
                </div>

                <div class="card">
                    <h2>SQL para Executar no PROCEL</h2>
                    <div class="muted">Contem somente objetos faltantes no PROCEL (destino PROCEL).</div>
                    <div class="muted">Arquivo: {{ result.output_sql_to_procel }}</div>
                    <textarea readonly>{{ result.sql_text_to_procel }}</textarea>
                </div>
            </div>
        </body>
        </html>
        """

        return render_template_string(html, result=result)

    except Exception as exc:
        if isinstance(exc, UnicodeDecodeError):
            return (
                "<h2>Erro de encoding ao ler metadados do banco</h2>"
                "<p>O banco possui texto em charset legado/invalido para o decode padrao.</p>"
                f"<pre>{str(exc)}</pre>",
                500,
            )
        return (
            "<h2>Erro ao comparar estrutura</h2>"
            f"<pre>{str(exc)}</pre>",
            500,
        )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5008, debug=False)
