# app_duplicates.py
from flask import Flask, render_template, request, jsonify, send_file
from flask_wtf import FlaskForm
from wtforms import SubmitField, DateField, StringField, BooleanField
from wtforms.validators import Optional
from db_lerconfiguracao import ler_configuracao, secret_key, get_db
import threading
import webbrowser
import os
from datetime import datetime

# ---- setup ----
app = Flask(__name__)
app.config["SECRET_KEY"] = secret_key()

db = get_db()
lc = ler_configuracao()

# ensure template folder and a minimal template exist (so the app is "complete")
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
os.makedirs(TEMPLATE_DIR, exist_ok=True)

# Template será carregado do arquivo separado index_registros_duplicados.html

# ---- form ----
class DupForm(FlaskForm):
    plano_conta = StringField("Plano de Conta", validators=[Optional()])
    data_inicio = DateField("Data Início", format="%Y-%m-%d", validators=[Optional()])
    data_fim = DateField("Data Fim", format="%Y-%m-%d", validators=[Optional()])
    match_date_only = BooleanField("comparar apenas data", default=False)
    include_null_fornecedor = BooleanField("incluir fornecedor NULL como chave", default=True)
    submit = SubmitField("Buscar")

# ---- helper SQL logic ----
def _connect():
    # usa a lib db_lerconfiguracao conforme seu padrão
    conn = db.connect(
        host=lc["SERVER"],
        database=lc["DIR_DADOS"],
        user=lc["USUARIO_BD"],
        password=lc["SENHA_BD"],
    )
    return conn

def find_duplicate_groups(match_date_only=False, start_date=None, end_date=None, planos=None, include_null_fornecedor=True):
    """
    Retorna lista de grupos duplicados (cada grupo: chave + QTD).
    Plano names (planos) aceita lista de nomes (strings). start_date/end_date são objetos date ou None.
    match_date_only: se True, compara só a data (CAST(DATA_PAGAMENTO AS DATE)).
    include_null_fornecedor: se True, considera fornecedor NULL igual a NULL; caso False, trata NULL como diferente.
    """
    conn = _connect()
    c = conn.cursor()

    # escolher a expressão para agrupar: timestamp ou date
    if match_date_only:
        data_expr = "CAST(DATA_PAGAMENTO AS DATE)"
    else:
        data_expr = "DATA_PAGAMENTO"

    # montar filtro de plano (por nome) se informado
    plano_filter = ""
    if planos:
        # planos pode ser lista de nomes
        planos_escaped = ["'{}'".format(p.replace("'", "''")) for p in planos]
        plano_filter = f" AND PC.NOME_PLANO_CONTA IN ({', '.join(planos_escaped)}) "

    # montar filtro de datas
    date_filter = ""
    if start_date and end_date:
        # Firebird pode aceitar formato 'YYYY-MM-DD' como literal; seguimos seu padrão
        ds = start_date.strftime("%Y-%m-%d")
        de = end_date.strftime("%Y-%m-%d")
        # quando match_date_only usamos CAST para comparar como DATE entre limites
        if match_date_only:
            date_filter = f" AND CAST(DATA_PAGAMENTO AS DATE) BETWEEN DATE '{ds}' AND DATE '{de}' "
        else:
            date_filter = f" AND DATA_PAGAMENTO BETWEEN '{ds} 00:00:00' AND '{de} 23:59:59' "

    # montar expressão de fornecedor para GROUP BY e HAVING - aqui tratamos NULL conforme flag
    if include_null_fornecedor:
        # agrupamos diretamente por COD_FORNECEDOR (NULL = NULL)
        fornecedor_group_expr = "COD_FORNECEDOR"
        fornecedor_select_expr = "L.COD_FORNECEDOR"
    else:
        # se não incluir NULL como igual, forçamos COALESCE com um valor especial que não existe (ex: -999999)
        fornecedor_group_expr = "COALESCE(COD_FORNECEDOR, -999999999)"
        fornecedor_select_expr = "COALESCE(L.COD_FORNECEDOR, -999999999)"

    # query de grupos duplicados
    query_groups = f"""
    --sql
    SELECT {data_expr} AS DATA_KEY, L.VALOR_PAGO, L.COD_PLANO_CONTA, {fornecedor_group_expr} AS COD_FORNECEDOR_KEY, COUNT(*) AS QTD
    FROM LANC_FINANCEIRO L
    LEFT JOIN PLANO_CONTA PC ON L.COD_PLANO_CONTA = PC.COD_PLANO_CONTA
    WHERE L.COD_SITUACAO_TITULO = 4
      AND L.ATV_LANC_FINANCEIRO = 'V'
      {plano_filter}
      {date_filter}
    GROUP BY {data_expr}, L.VALOR_PAGO, L.COD_PLANO_CONTA, {fornecedor_group_expr}
    HAVING COUNT(*) > 1
    ORDER BY {data_expr}, L.VALOR_PAGO;
    """

    c.execute(query_groups)
    groups_raw = c.fetchall()
    conn.close()

    # cada linha em groups_raw: (DATA_KEY, VALOR_PAGO, COD_PLANO_CONTA, COD_FORNECEDOR_KEY, QTD)
    groups = []
    for row in groups_raw:
        groups.append({
            "DATA_KEY": row[0],
            "VALOR_PAGO": float(row[1]) if row[1] is not None else 0.0,
            "COD_PLANO_CONTA": row[2],
            "COD_FORNECEDOR_KEY": row[3],
            "QTD": row[4],
        })
    return groups

def fetch_records_for_group(group, match_date_only=False, include_null_fornecedor=True):
    """
    Retorna os registros completos (tuplas/dicionários) que pertencem ao grupo informado.
    group deve ter as chaves: DATA_KEY, VALOR_PAGO, COD_PLANO_CONTA, COD_FORNECEDOR_KEY
    """
    conn = _connect()
    c = conn.cursor()

    # montar condição para data
    if match_date_only:
        cond_data = "CAST(L.DATA_PAGAMENTO AS DATE) = CAST('{0}' AS DATE)".format(group["DATA_KEY"].strftime("%Y-%m-%d"))
    else:
        # DATA_KEY é timestamp; formatamos como ISO (caso seja string no resultado, mantemos)
        if isinstance(group["DATA_KEY"], datetime):
            cond_data = "L.DATA_PAGAMENTO = '{}'".format(group["DATA_KEY"].strftime("%Y-%m-%d %H:%M:%S"))
        else:
            # pode ser string ou date
            cond_data = "L.DATA_PAGAMENTO = '{}'".format(str(group["DATA_KEY"]))

    # condição fornecedor conforme flag
    if include_null_fornecedor:
        cond_fornecedor = "((L.COD_FORNECEDOR = {0}) OR (L.COD_FORNECEDOR IS NULL AND {1} IS NULL))".format(
            "NULL" if group["COD_FORNECEDOR_KEY"] is None else str(group["COD_FORNECEDOR_KEY"]),
            "NULL" if group["COD_FORNECEDOR_KEY"] is None else str(group["COD_FORNECEDOR_KEY"])
        )
        # o above fica estranho quando formatamos NULL literal; vamos usar COALESCE para segurança:
        cond_fornecedor = "COALESCE(L.COD_FORNECEDOR, -999999999) = COALESCE({0}, -999999999)".format(
            "NULL" if group["COD_FORNECEDOR_KEY"] is None else str(group["COD_FORNECEDOR_KEY"])
        )
    else:
        cond_fornecedor = "COALESCE(L.COD_FORNECEDOR, -999999999) = {}".format(
            str(group["COD_FORNECEDOR_KEY"])
        )

    # montar query que traz os registros do grupo com detalhes e nomes
    query_records = f"""
    --sql
    SELECT L.COD_FIN, L.DATA_PAGAMENTO, L.VALOR_PAGO, L.COD_PLANO_CONTA, PC.NOME_PLANO_CONTA, L.COD_FORNECEDOR, G.NOME_FORNECEDOR
    FROM LANC_FINANCEIRO L
    LEFT JOIN PLANO_CONTA PC ON L.COD_PLANO_CONTA = PC.COD_PLANO_CONTA
    LEFT JOIN GERFORNECEDOR G ON L.COD_FORNECEDOR = G.COD_FORNECEDOR
    WHERE L.COD_SITUACAO_TITULO = 4
      AND L.ATV_LANC_FINANCEIRO = 'V'
      AND {cond_data}
      AND L.VALOR_PAGO = {group["VALOR_PAGO"]}
      AND COALESCE(L.COD_PLANO_CONTA, -999999999) = COALESCE({0}, -999999999)
      AND {cond_fornecedor}
    ORDER BY L.DATA_PAGAMENTO, L.COD_FIN;
    """.format("NULL" if group["COD_PLANO_CONTA"] is None else str(group["COD_PLANO_CONTA"]))

    c.execute(query_records)
    cols = [d[0] for d in c.description]
    rows = c.fetchall()
    conn.close()

    # converter para lista de dicts
    records = []
    for r in rows:
        rec = {cols[i]: r[i] for i in range(len(cols))}
        records.append(rec)
    return records

# ---- routes ----
@app.route("/", methods=["GET", "POST"])
def index():
    form = DupForm()
    groups_output = []

    if request.method == "POST":
        # coletar filtros do form
        plano_input = request.form.get("plano_conta", "").strip()
        planos = [p.strip() for p in plano_input.split(",")] if plano_input else None

        di = request.form.get("data_inicio", "")
        df = request.form.get("data_fim", "")
        start_date = datetime.strptime(di, "%Y-%m-%d").date() if di else None
        end_date = datetime.strptime(df, "%Y-%m-%d").date() if df else None

        match_date_only = bool(request.form.get("match_date_only"))
        include_null_fornecedor = bool(request.form.get("include_null_fornecedor"))

        # buscar grupos duplicados
        groups = find_duplicate_groups(match_date_only=match_date_only, start_date=start_date, end_date=end_date, planos=planos, include_null_fornecedor=include_null_fornecedor)

        # para cada grupo, buscar os registros que pertencem
        for g in groups:
            records = fetch_records_for_group(g, match_date_only=match_date_only, include_null_fornecedor=include_null_fornecedor)

            # pegar nomes de plano/fornecedor se disponíveis
            nome_plano = records[0].get("NOME_PLANO_CONTA") if records else None
            nome_fornecedor = records[0].get("NOME_FORNECEDOR") if records else None

            key_display = None
            if match_date_only:
                # mostrar apenas data
                if isinstance(g["DATA_KEY"], datetime):
                    key_display = g["DATA_KEY"].date().isoformat()
                else:
                    # já pode vir como date
                    key_display = str(g["DATA_KEY"])
            else:
                key_display = str(g["DATA_KEY"])

            groups_output.append({
                "key_display": key_display,
                "valor": g["VALOR_PAGO"],
                "cod_plano": g["COD_PLANO_CONTA"],
                "nome_plano": nome_plano,
                "cod_fornecedor": g["COD_FORNECEDOR_KEY"],
                "nome_fornecedor": nome_fornecedor,
                "count": g["QTD"],
                "cod_fins": [r["COD_FIN"] for r in records],
                "records": records,
            })

    # popular valores no form para reuso na template
    # (não usamos form.validate_on_submit pra manter comportamento simples)
    return render_template("index_registros_duplicados.html", form=form, groups=groups_output)

@app.route("/plano_conta.json")
def plano_conta_json():
    """Servir o arquivo PLANO_CONTA.json a partir da raiz do projeto."""
    file_path = os.path.join(os.path.dirname(__file__), "PLANO_CONTA.json")
    if os.path.exists(file_path):
        return send_file(file_path)
    return jsonify({"error": "File not found"}), 404

def open_browser():
    webbrowser.open_new("http://127.0.0.1:5003")

if __name__ == "__main__":
    # inicia browser automaticamente (opcional)
    threading.Timer(1.2, open_browser).start()
    app.run(debug=False, port=5003)
