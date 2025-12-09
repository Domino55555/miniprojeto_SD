from flask import Flask, request, jsonify
import mysql.connector
import json
import os
import requests
from prometheus_flask_exporter import PrometheusMetrics
from prometheus_client import Summary, Gauge
import time
# Metrica de latencia: medida em segundos
REQUEST_LATENCY_GAUGE = Gauge('request_latency_seconds', 'Latência da última request', ['endpoint'])
app = Flask(__name__)
metrics = PrometheusMetrics(app)  # adiciona métricas automaticamente

# URL do serviço de notificações
NOTIFICATIONS_URL = os.getenv("NOTIFICATIONS_URL", "http://notifications:5800")

# Configuração da Base de Dados
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "grupo3")
DB_PASSWORD = os.getenv("DB_PASSWORD", "baguette")
DB_NAME = os.getenv("DB_NAME", "servicos")

@app.before_request
def before_request():
    request.start_time = time.time()

@app.after_request
def after_request(response):
    endpoint = request.endpoint or "unknown"
    REQUEST_LATENCY_GAUGE.labels(endpoint=endpoint).set(time.time() - request.start_time)
    return response

# Função para conectar à base de dados MySQL
def obter_conexao_bd():
    print("[BD] A abrir ligação à base de dados")
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

# Carregar ficheiro de produtos e preços
with open("Listas/produtos.json", "r") as f:
    precos_produtos = json.load(f)

# Converter para lower-case para facilitar matching
precos_itens = {}
for nome, preco in precos_produtos.items():
    nome_lower = nome.lower()
    precos_itens[nome_lower] = preco


# -------------------------------
#   ROTA: Criar nova encomenda
# -------------------------------
@app.route("/orders", methods=["POST"])
def criar_encomenda():
    dados = request.get_json()
    print(f"[CRIAR ENCOMENDA] Dados recebidos: {dados}")

    if not dados or "items" not in dados:
        print("[CRIAR ENCOMENDA] Falta o campo 'items'")
        return jsonify({"erro": "Falta o campo 'items'"}), 400

    itens_recebidos = dados["items"]

    # Transformar string "item1, item2" numa lista limpa
    if isinstance(itens_recebidos, str):
        itens_separados = itens_recebidos.split(",")
        lista_itens = [item.strip() for item in itens_separados]
    else:
        lista_itens = itens_recebidos

    user_id = dados.get("user_id")
    if not user_id:
        print("[CRIAR ENCOMENDA] Falta o campo 'user_id'")
        return jsonify({"erro": "Falta o campo 'user_id'"}), 400

    conn = obter_conexao_bd()
    cursor = conn.cursor(dictionary=True)

    print(f"[CRIAR ENCOMENDA] A obter username e email do user_id: {user_id}")
    cursor.execute("SELECT username, email FROM GW WHERE user_id=%s", (user_id,))
    utilizador = cursor.fetchone()

    if not utilizador:
        print("[CRIAR ENCOMENDA] Utilizador não encontrado")
        cursor.close()
        conn.close()
        return jsonify({"erro": "Utilizador não encontrado"}), 404

    username = utilizador["username"]
    email = utilizador["email"]
    print(f"[CRIAR ENCOMENDA] Utilizador encontrado → {username} ({email})")

    total = 0
    itens_invalidos = []

    for item in lista_itens:
        item_lower = item.lower().strip()
        if item_lower in precos_itens:
            total += precos_itens[item_lower]
        else:
            itens_invalidos.append(item)

    if itens_invalidos:
        print(f"[CRIAR ENCOMENDA] Itens desconhecidos: {itens_invalidos}")
        cursor.close()
        conn.close()
        return jsonify({"erro": "Itens desconhecidos", "itens": itens_invalidos}), 400

    cursor.execute(
        "INSERT INTO Orders (user_id, items, total, status) VALUES (%s, %s, %s, %s)",
        (user_id, ",".join(lista_itens), total, "pendente")
    )
    conn.commit()

    order_id = cursor.lastrowid
    cursor.close()
    conn.close()

    print(f"[CRIAR ENCOMENDA] Encomenda criada com sucesso. ID = {order_id}")

    # Enviar notificação
    try:
        resposta = requests.post(
            f"{NOTIFICATIONS_URL}/notifications/order_created",
            json={
                "email": email,
                "username": username,
                "order_id": order_id,
                "items": lista_itens,
                "total": total,
                "user_id": user_id
            },
            timeout=5
        )
        resposta.raise_for_status()
        print("[CRIAR ENCOMENDA] Notificação enviada com sucesso")
    except Exception as e:
        print(f"[CRIAR ENCOMENDA] Erro ao contactar Notifications: {e}")

    return jsonify({
        "order_id": order_id,
        "username": username,
        "items": lista_itens,
        "total": total,
        "status": "pendente"
    }), 201


# --------------------------------------------
#   ROTA: Obter encomendas por username
# --------------------------------------------
@app.route("/orders/<username>", methods=["GET"])
def obter_encomendas_por_username(username):
    print(f"[OBTER ENCOMENDAS] A procurar encomendas de '{username}'")
    conn = obter_conexao_bd()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            Orders.order_id,
            Orders.items,
            Orders.total,
            Orders.status,
            Orders.created_at,
            GW.username
        FROM Orders
        JOIN GW ON Orders.user_id = GW.user_id
        WHERE GW.username = %s
    """, (username,))

    encomendas = cursor.fetchall()
    cursor.close()
    conn.close()

    if encomendas:
        print(f"[OBTER ENCOMENDAS] Encontradas {len(encomendas)} encomendas")
        return jsonify(encomendas)

    print("[OBTER ENCOMENDAS] Nenhuma encomenda encontrada")
    return jsonify({"erro": "Nenhuma encomenda encontrada"}), 404


# ----------------------------------------
#   ROTA: Listar itens disponíveis
# ----------------------------------------
@app.route("/orders/fields", methods=["GET"])
def obter_itens_disponiveis():
    print("[ITENS DISPONÍVEIS] A enviar lista de itens disponíveis")
    return jsonify({"items": list(precos_itens.keys())})


# ----------------------------------------
#   ROTA: Cancelar encomenda
# ----------------------------------------
@app.route("/orders/cancel", methods=["POST"])
def cancelar_encomenda():
    dados = request.get_json()
    print(f"[CANCELAR ENCOMENDA] Dados recebidos: {dados}")

    if not dados or "order_id" not in dados:
        return jsonify({"erro": "Falta o campo 'order_id'"}), 400

    order_id = dados["order_id"]

    conn = obter_conexao_bd()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            Orders.order_id, Orders.total, Orders.status, Orders.items,
            GW.user_id, GW.wallet, GW.email, GW.username
        FROM Orders
        JOIN GW ON Orders.user_id = GW.user_id
        WHERE Orders.order_id = %s
    """, (order_id,))

    encomenda = cursor.fetchone()

    if not encomenda:
        cursor.close()
        conn.close()
        return jsonify({"erro": "Encomenda não encontrada"}), 404

    if encomenda["status"].lower() != "pendente":
        cursor.close()
        conn.close()
        return jsonify({"erro": f"A encomenda não pode ser cancelada porque está '{encomenda['status']}'"}), 400

    cursor.execute("UPDATE Orders SET status='cancelada' WHERE order_id=%s", (order_id,))
    conn.commit()

    email = encomenda["email"]
    user_id = encomenda["user_id"]
    total = float(encomenda["total"])

    cursor.close()
    conn.close()

    # Enviar notificação
    try:
        resposta = requests.post(
            f"{NOTIFICATIONS_URL}/notifications/status",
            json={
                "email": email,
                "order_id": order_id,
                "status": "cancelada",
                "total": total,
                "user_id": user_id
            },
            timeout=5
        )
        print(f"[CANCELAR ENCOMENDA] Notificação enviada ({resposta.status_code})")
    except Exception as e:
        print(f"[CANCELAR ENCOMENDA] Falha ao enviar notificação: {e}")

    return jsonify({
        "sucesso": True,
        "order_id": order_id,
        "status": "cancelada",
        "mensagem": "Encomenda cancelada com sucesso"
    }), 200


# ----------------------------------------
#   INICIAR SERVIÇO
# ----------------------------------------
if __name__ == "__main__":
    print("[SERVIDOR] Serviço de Orders a correr na porta 5600")
    app.run(host="0.0.0.0", port=5600)
