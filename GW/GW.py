from flask import Flask, request, jsonify, Response
import requests
import os
import uuid
import mysql.connector
from prometheus_flask_exporter import PrometheusMetrics
import time
from prometheus_client import Summary, Histogram

# Metrica de latencia: medida em segundos
REQUEST_LATENCY_HIST = Histogram('request_latency_seconds_hist', 'Latência das requests', ['endpoint'])

app = Flask(__name__)
metrics = PrometheusMetrics(app)  # adiciona métricas automaticamente

# URLs dos serviços internos
ORDERS_URL = os.getenv("ORDERS_URL", "http://orders:5600")
PAYMENTS_URL = os.getenv("PAYMENTS_URL", "http://payments:5700")
NOTIFICATIONS_URL = os.getenv("NOTIFICATIONS_URL", "http://notifications:5800")

# Armazenamento em memória dos tokens válidos
tokens_validos = {}

# Armazenamento em memória dos registos pendentes de criação de conta
pending_signups = {}


@app.before_request
def before_request():
    request.start_time = time.time()

@app.after_request
def after_request(response):
    endpoint = request.endpoint or "unknown"
    REQUEST_LATENCY_HIST.labels(endpoint=endpoint).observe(time.time() - request.start_time)
    return response


# Função para obter ligação à base de dados MySQL
def obter_conexao_bd():
    print("[BD] A abrir ligação à base de dados")
    return mysql.connector.connect(
        host="db",
        user="grupo3",
        password="baguette",
        database="servicos",
        auth_plugin='mysql_native_password'
    )

# Função para verificar se o token enviado no header é válido
def verificar_token():
    btoken = request.headers.get("Authorization")
    if not btoken or not btoken.startswith("Bearer "):
        print("[AUTENTICAÇÃO] Token ausente ou inválido no header")
        return None
    token = btoken.split()[1]
    username = tokens_validos.get(token)
    print(f"[AUTENTICAÇÃO] Token verificado para o utilizador: {username}")
    return username

# Rota de boas-vindas
@app.route("/", methods=["GET"])
def boas_vindas():
    print("[GW] Requisição de boas-vindas recebida")
    texto = (
        "=== 🛒 BEM-VINDO À XPTO STORE 🛒 ===\n\n"
        "Através deste Gateway pode criar conta, fazer login, criar encomendas,\n"
        "consultar produtos, efetuar pagamentos e ver notificações.\n\n"
        "👉 ROTAS DISPONÍVEIS:\n\n"
        "🔐 AUTENTICAÇÃO\n"
        "- [POST] /signup\n"
        "  Cria uma nova conta.\n"
        "  JSON: { \"username\": \"...\", \"password\": \"...\", \"email\": \"...\" }\n\n"
        "- [POST] /signup/confirm\n"
        "  Confirma a conta com o código enviado para o email.\n\n"
        "- [POST] /login\n"
        "  Faz login e devolve um token.\n"
        "  JSON: { \"username\": \"...\", \"password\": \"...\" }\n\n"
        "- [POST] /logout\n"
        "  Termina a sessão ativa.\n\n"
        "💰 WALLET\n"
        "- [GET] /wallet\n"
        "  Mostra o saldo da carteira.\n\n"
        "📦 ORDERS\n"
        "- [GET] /orders/fields\n"
        "  Lista os produtos disponíveis.\n\n"
        "- [POST] /orders/new\n"
        "  Cria uma nova encomenda.\n"
        "  JSON: { \"items\": \"Produto\" }\n\n"
        "- [GET] /orders/me\n"
        "  Lista as encomendas do utilizador.\n\n"
        "- [POST] /orders/cancel\n"
        "  Cancela uma encomenda.\n"
        "  JSON: { \"order_id\": ... }\n\n"
        "💳 PAYMENTS\n"
        "- [POST] /payments\n"
        "  Processa o pagamento de uma encomenda.\n\n"
        "- [GET] /payments/me\n"
        "  Lista os pagamentos do utilizador.\n\n"
        "📧 NOTIFICAÇÕES\n"
        "- [GET] /notifications/me\n"
        "  Mostra todas as notificações enviadas ao utilizador.\n\n"
        "⚠️ IMPORTANTE\n"
        "Todas as rotas protegidas devem incluir o header:\n"
        "Authorization: Bearer <token>\n\n"
        "=== XPTO STORE – Tudo num só lugar! ===\n"
    )
    return Response(texto, mimetype="text/plain")

# Rota para criar a conta
@app.route("/signup", methods=["POST"])
def criar_conta():
    dados = request.get_json()
    print(f"[SIGNUP] Dados recebidos: {dados}")
    username = dados.get("username")
    password = dados.get("password")
    email = dados.get("email")

    if not username or not password or not email:
        print("[SIGNUP] Falta username, password ou email")
        return {"erro": "username, password e email obrigatórios"}, 400

    try:
        conn = obter_conexao_bd()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM GW WHERE username=%s OR email=%s", (username, email))
        registo_bd = cursor.fetchone()
        cursor.close()
        conn.close()
        if registo_bd:
            print(f"[SIGNUP] Username ou email já existente: {username}, {email}")
            return {"erro": "Username ou email já existente"}, 409

        try:
            resp = requests.post(
                f"{NOTIFICATIONS_URL}/notifications/send_verification",
                json={"email": email},
                timeout=5
            )
            resp.raise_for_status()
        except Exception as e:
            print(f"[ERRO NOTIFICAÇÃO] {e}")
            return {"erro": "Falha ao enviar email"}, 500

        codigo = resp.json().get("codigo")
        pending_signups[username] = {
            "password": password,
            "email": email,
            "codigo": codigo
        }

        return {"mensagem": "Código enviado para o email. Confirme em /signup/confirm."}, 200

    except Exception as e:
        return {"erro": f"Erro interno: {str(e)}"}, 500

# Rota para confirmar signup
@app.route("/signup/confirm", methods=["POST"])
def confirmar_signup():
    dados = request.get_json() or {}
    username = dados.get("username")
    codigo_recebido = dados.get("codigo")

    if not username or not codigo_recebido:
        return {"erro": "username e codigo obrigatórios"}, 400

    registo = pending_signups.get(username)
    if not registo:
        return {"erro": "Não existe registo pendente para este utilizador"}, 404

    if codigo_recebido != registo["codigo"]:
        return {"erro": "Código incorreto"}, 401

    try:
        conn = obter_conexao_bd()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO GW (username, password, email) VALUES (%s, %s, %s)",
            (username, registo["password"], registo["email"])
        )
        conn.commit()
        cursor.close()
        conn.close()

        del pending_signups[username]

        return {"mensagem": "Conta confirmada!"}, 201
    except Exception as e:
        return {"erro": f"Erro interno: {str(e)}"}, 500

# Rota de login
@app.route("/login", methods=["POST"])
def login():
    dados = request.get_json()
    print(f"[LOGIN] Dados recebidos: {dados}")
    username = dados.get("username")
    password = dados.get("password")

    if not username or not password:
        return {"erro": "username e password obrigatórios"}, 400

    try:
        conn = obter_conexao_bd()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM GW WHERE username=%s AND password=%s", (username, password))
        registo_bd = cursor.fetchone()
        cursor.close()
        conn.close()

        if not registo_bd:
            return {"erro": "Credenciais inválidas"}, 401

        token = str(uuid.uuid4())
        tokens_validos[token] = username
        print(f"[LOGIN] Login bem-sucedido. Token gerado para {username}: {token}")
        return {"token": token}, 200
    except Exception as e:
        return {"erro": str(e)}, 500

# Rota de logout
@app.route("/logout", methods=["POST"])
def logout():
    username = verificar_token()
    if not username:
        print("[LOGOUT] Token inválido")
        return {"erro": "Token inválido"}, 401
    for token, user in list(tokens_validos.items()):
        if user == username:
            del tokens_validos[token]
            print(f"[LOGOUT] Token removido para {user}")
    return {"mensagem": "Sessão terminada"}, 200

# Rota para obter valor da carteira
@app.route("/wallet", methods=["GET"])
def get_wallet():
    username = verificar_token()
    if not username:
        return {"erro": "Token inválido"}, 401

    conn = obter_conexao_bd()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT wallet FROM GW WHERE username=%s", (username,))
    registo_bd = cursor.fetchone()
    cursor.close()
    conn.close()

    if not registo_bd:
        print(f"[WALLET] Utilizador não encontrado: {username}")
        return {"erro": "Utilizador não encontrado"}, 404

    print(f"[WALLET] Carteira de {username}: {registo_bd['wallet']}")
    return {"Carteira": float(registo_bd["wallet"])}, 200

# Rota para criar nova encomenda
@app.route("/orders/new", methods=["POST"])
def criar_pedido():
    username = verificar_token()
    if not username:
        return {"erro": "Token inválido"}, 401

    dados = request.get_json()
    if not dados:
        return {"erro": "Corpo da requisição vazio"}, 400

    conn = obter_conexao_bd()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT user_id FROM GW WHERE username=%s", (username,))
    registo_bd = cursor.fetchone()
    cursor.close()
    conn.close()

    if not registo_bd:
        return {"erro": "Utilizador não encontrado"}, 404

    dados['user_id'] = registo_bd['user_id']

    try:
        resp = requests.post(f"{ORDERS_URL}/orders", json=dados, timeout=5)
        return resp.json(), resp.status_code
    except Exception as e:
        return {"erro": str(e)}, 500

# Rota para listar encomendas do utilizador
@app.route("/orders/me", methods=["GET"])
def orders_do_cliente():
    username = verificar_token()
    if not username:
        return {"erro": "Token inválido"}, 401
    try:
        resp = requests.get(f"{ORDERS_URL}/orders/{username}", timeout=5)
        return resp.json(), resp.status_code
    except Exception as e:
        return {"erro": str(e)}, 500

# Rota para listar produtos disponíveis
@app.route("/orders/fields", methods=["GET"])
def produtos_disponiveis():
    username = verificar_token()
    if not username:
        return {"erro": "Token inválido"}, 401
    try:
        resp = requests.get(f"{ORDERS_URL}/orders/fields", timeout=5)
        return resp.json(), resp.status_code
    except Exception as e:
        return {"erro": str(e)}, 500

# Rota para cancelar encomenda
@app.route("/orders/cancel", methods=["POST"])
def gw_cancel_order():
    username = verificar_token()
    if not username:
        return {"erro": "Token inválido"}, 401

    dados = request.get_json()
    if not dados:
        return {"erro": "Corpo da requisição vazio"}, 400

    try:
        resp = requests.post(f"{ORDERS_URL}/orders/cancel", json=dados, timeout=5)
        return resp.json(), resp.status_code
    except Exception as e:
        return {"erro": str(e)}, 500

# Rota para processar pagamento
@app.route("/payments", methods=["POST"])
def processar_pagamento():
    username = verificar_token()
    if not username:
        return {"erro": "Token inválido"}, 401
    dados = request.get_json()
    try:
        resp = requests.post(f"{PAYMENTS_URL}/payments", json=dados, timeout=5)
        return resp.json(), resp.status_code
    except Exception as e:
        return {"erro": str(e)}, 500

# Rota para listar pagamentos do utilizador
@app.route("/payments/me", methods=["GET"])
def pagamentos_do_cliente():
    username = verificar_token()
    if not username:
        return {"erro": "Token inválido"}, 401
    try:
        resp = requests.get(f"{PAYMENTS_URL}/payments/{username}", timeout=5)
        return resp.json(), resp.status_code
    except Exception as e:
        return {"erro": str(e)}, 500

# Rota para listar notificações do utilizador
@app.route("/notifications/me", methods=["GET"])
def notificacoes_do_cliente():
    username = verificar_token()
    if not username:
        return {"erro": "Token inválido"}, 401
    try:
        resp = requests.get(f"{NOTIFICATIONS_URL}/notifications/{username}", timeout=5)
        return resp.json(), resp.status_code
    except Exception as e:
        return {"erro": str(e)}, 500

# Correr a aplicação Flask
if __name__ == "__main__":
    print("[SERVIDOR] Gateway a correr na porta 5863")
    app.run(host="0.0.0.0", port=5863)
