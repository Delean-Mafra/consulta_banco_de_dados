import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from db_lerconfiguracao import get_db, ler_configuracao

PROCEL_DB_PATH = r"D:\G3\Dados\PROCEL.FDB"
DEFAULT_DELEAN_SCRIPT = "sync_para_delean.sql"
DEFAULT_PROCEL_SCRIPT = "sync_para_procel.sql"


db = get_db()


def read_sql_file(script_path):
    path = Path(script_path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo SQL nao encontrado: {path}")

    # Tenta UTF-8 primeiro; se falhar, usa latin-1 para arquivos legados.
    for encoding in ("utf-8", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue

    # Ultimo fallback para nunca quebrar abertura do arquivo.
    return path.read_text(encoding="latin-1", errors="replace")


def parse_set_term_candidate(line, current_terminator):
    text = line.strip()
    if not text:
        return None

    if not text.upper().startswith("SET TERM "):
        return None

    # Aceita formatos como:
    # SET TERM ^ ;
    # SET TERM ; ^
    # SET TERM ^ ;^
    pattern = re.compile(
        rf"^\s*SET\s+TERM\s+(\S+)\s+(\S+)\s*(?:{re.escape(current_terminator)})?\s*$",
        flags=re.IGNORECASE,
    )
    match = pattern.match(text)
    if not match:
        return None

    return match.group(1), match.group(2)


def parse_firebird_script(sql_text):
    terminator = ";"
    statements = []
    buffer = []

    for raw_line in sql_text.splitlines():
        line = raw_line.rstrip("\r")
        stripped = line.strip()

        # Ignora comentarios fora de bloco de statement.
        if not buffer and (not stripped or stripped.startswith("--")):
            continue

        set_term = parse_set_term_candidate(line, terminator)
        if set_term and not buffer:
            new_term, old_term = set_term
            # Mesmo se o old_term nao bater, segue com o novo para maior tolerancia.
            terminator = new_term
            continue

        buffer.append(line)
        joined = "\n".join(buffer).rstrip()

        if joined.endswith(terminator):
            statement = joined[: -len(terminator)].rstrip()
            if statement:
                statements.append(statement)
            buffer = []

    # Se terminar sem terminador, executa o que sobrou.
    if buffer:
        leftover = "\n".join(buffer).strip()
        if leftover:
            statements.append(leftover)

    return statements


def format_exception(exc):
    base = str(exc).strip() or exc.__class__.__name__
    if hasattr(exc, "args") and exc.args:
        details = " | ".join(str(item) for item in exc.args if str(item).strip())
        if details and details not in base:
            return f"{base} | detalhes: {details}"
    return base


def extract_existing_object_name(exc_text):
    patterns = [
        r"procedure\s+([\w\$\"]+)\s+already exists",
        r"problematic key value is \(\"rdb\$trigger_name\" = '([^']+)'\)",
        r"problematic key value is \(\"rdb\$constraint_name\" = '([^']+)'\)",
    ]
    text = exc_text.lower()
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def is_already_exists_error(exc):
    text = format_exception(exc).lower()

    patterns = [
        "already exists",
        "attempt to store duplicate value",
        "unsuccessful metadata update",
        "store rdb$relation_constraints failed",
        "store rdb$relations failed",
        "store rdb$procedures failed",
        "store rdb$triggers failed",
        "store rdb$generators failed",
        "store rdb$exceptions failed",
        "duplicate value",
    ]

    return any(pattern in text for pattern in patterns)


def normalize_statement_for_firebird(statement):
    text = statement.strip()
    upper = text.upper()

    # Alguns scripts legados trazem CREATE PROCEDURE sem AS antes dos DECLARE/BEGIN.
    # Ajusta automaticamente para evitar erro de parse no Firebird.
    if upper.startswith("CREATE PROCEDURE"):
        lines = text.splitlines()
        if len(lines) >= 2:
            first_body_idx = None
            for i in range(1, len(lines)):
                stripped = lines[i].strip().upper()
                if not stripped:
                    continue
                if stripped.startswith("DECLARE") or stripped.startswith("BEGIN"):
                    first_body_idx = i
                    break

            if first_body_idx is not None:
                prev_non_empty = None
                for j in range(first_body_idx - 1, -1, -1):
                    prev = lines[j].strip().upper()
                    if prev:
                        prev_non_empty = prev
                        break

                if prev_non_empty != "AS":
                    lines.insert(first_body_idx, "AS")
                    return "\n".join(lines)

    return statement


def connect_target_db(target):
    config = ler_configuracao()
    required = ["USUARIO_BD", "SENHA_BD", "DIR_DADOS"]
    missing_cfg = [k for k in required if not config.get(k)]
    if missing_cfg:
        raise RuntimeError(
            "Configuracao incompleta no Servidor.conf. Faltando: " + ", ".join(missing_cfg)
        )

    common_kwargs = {
        "user": config["USUARIO_BD"],
        "password": config["SENHA_BD"],
        "charset": "ISO8859_1",
    }

    if target == "delean":
        return db.connect(
            host=config.get("SERVER"),
            database=config["DIR_DADOS"],
            **common_kwargs,
        ), config["DIR_DADOS"]

    if target == "procel":
        return db.connect(
            database=PROCEL_DB_PATH,
            **common_kwargs,
        ), PROCEL_DB_PATH

    raise ValueError("Destino invalido. Use: delean ou procel")


def execute_statements(connection, statements, continue_on_error=False):
    cursor = connection.cursor()
    success_count = 0
    skipped_count = 0
    skipped_existing = []
    failures = []

    for idx, statement in enumerate(statements, start=1):
        sql_to_run = normalize_statement_for_firebird(statement)
        try:
            cursor.execute(sql_to_run)
            connection.commit()
            success_count += 1
            print(f"[OK] {idx}/{len(statements)} executado")
        except Exception as exc:
            try:
                connection.rollback()
            except Exception:
                pass

            if is_already_exists_error(exc):
                skipped_count += 1
                reason = format_exception(exc)
                object_name = extract_existing_object_name(reason)
                skipped_item = {
                    "index": idx,
                    "reason": reason,
                    "object": object_name,
                    "statement": sql_to_run,
                }
                skipped_existing.append(skipped_item)
                if object_name:
                    print(f"[IGNORADO] {idx}/{len(statements)} objeto ja existe: {object_name}")
                else:
                    print(f"[IGNORADO] {idx}/{len(statements)} objeto ja existe")
                continue

            failure = {
                "index": idx,
                "error": format_exception(exc),
                "statement": sql_to_run,
            }
            failures.append(failure)

            print(f"[ERRO] {idx}/{len(statements)}")
            print(f"        Motivo: {failure['error']}")
            print("        Trecho do comando:")
            snippet = "\n".join(statement.splitlines()[:12])
            print(snippet)
            print("-" * 80)

            if not continue_on_error:
                break

    cursor.close()
    return success_count, skipped_count, skipped_existing, failures


def write_error_report(report_path, script_path, target_db, failures):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "RELATORIO DE ERROS - EXECUCAO SQL",
        f"Data/Hora: {now}",
        f"Arquivo SQL: {script_path}",
        f"Banco destino: {target_db}",
        f"Total de erros: {len(failures)}",
        "",
    ]

    for item in failures:
        lines.append(f"Erro no comando #{item['index']}")
        lines.append(f"Mensagem: {item['error']}")
        lines.append("Comando:")
        lines.append(item["statement"])
        lines.append("\n" + "=" * 90 + "\n")

    Path(report_path).write_text("\n".join(lines), encoding="utf-8")


def default_script_for_target(target):
    if target == "delean":
        return DEFAULT_DELEAN_SCRIPT
    return DEFAULT_PROCEL_SCRIPT


def infer_target_from_script_name(script_path):
    name = Path(script_path).name.lower()
    if "procel" in name:
        return "procel"
    if "delean" in name:
        return "delean"
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Executa script SQL Firebird com suporte a SET TERM e erro detalhado"
    )
    parser.add_argument(
        "--target",
        choices=["delean", "procel"],
        required=False,
        default=None,
        help="Banco destino para execucao do script",
    )
    parser.add_argument(
        "--script",
        help="Caminho do arquivo SQL a executar",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continua executando os proximos comandos mesmo apos erro",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Somente valida parse do script, sem executar no banco",
    )
    parser.add_argument(
        "--show-ignored-details",
        action="store_true",
        help="Exibe detalhes completos dos comandos ignorados por ja existirem",
    )

    args = parser.parse_args()
    target = args.target
    script_path = args.script

    if script_path and not target:
        target = infer_target_from_script_name(script_path)

    if not target:
        target = "delean"
        print("Destino nao informado. Usando padrao: delean")

    if not script_path:
        script_path = default_script_for_target(target)

    try:
        print(f"Lendo arquivo SQL: {script_path}")
        sql_text = read_sql_file(script_path)

        statements = parse_firebird_script(sql_text)
        if not statements:
            print("Nenhum comando SQL encontrado no arquivo.")
            return 2

        print(f"Comandos encontrados: {len(statements)}")

        if args.dry_run:
            print("Dry-run concluido com sucesso. Nenhum comando foi executado.")
            return 0

        connection, target_db = connect_target_db(target)
        print(f"Conectado no banco destino: {target_db}")

        try:
            success_count, skipped_count, skipped_existing, failures = execute_statements(
                connection,
                statements,
                continue_on_error=args.continue_on_error,
            )
        finally:
            connection.close()

        print("\nResumo da execucao")
        print(f"Total de comandos: {len(statements)}")
        print(f"Executados com sucesso: {success_count}")
        print(f"Ignorados (ja existiam): {skipped_count}")
        print(f"Com erro: {len(failures)}")

        if skipped_existing and args.show_ignored_details:
            print("\nComandos ignorados por ja existirem:")
            for item in skipped_existing[:20]:
                print(f"- #{item['index']}: {item['reason']}")
            if len(skipped_existing) > 20:
                print(f"... e mais {len(skipped_existing) - 20} comandos ignorados")
        elif skipped_existing:
            print(
                "\nObjetos ja existentes foram ignorados (comportamento esperado para script idempotente)."
            )
            print("Use --show-ignored-details para ver os detalhes tecnicos de cada ignorado.")

        if not failures and success_count == 0 and skipped_count > 0:
            print("Banco ja estava sincronizado: nenhuma alteracao foi necessaria.")

        if failures:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = f"erro_execucao_sql_{target}_{timestamp}.log"
            write_error_report(report_file, script_path, target_db, failures)
            print(f"Relatorio detalhado salvo em: {report_file}")
            return 1

        print("Execucao finalizada sem erros.")
        return 0

    except Exception as exc:
        print("\nFalha geral durante a execucao")
        print(f"Tipo: {exc.__class__.__name__}")
        print(f"Mensagem: {format_exception(exc)}")
        return 99


if __name__ == "__main__":
    sys.exit(main())
