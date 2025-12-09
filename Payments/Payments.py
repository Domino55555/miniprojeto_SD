from flask import Flask, request, jsonify
import mysql.connector
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

# Função para ligar à base de dados MySQL
def obter_conexao_bd():
    print("[BD] A abrir ligação à base de dados")
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

# Rota para obter os pagamentos de um cliente
@app.route("/payments/<username>", methods=["GET"])
def pagamentos_do_cliente(username):
    print(f"[PAGAMENTOS] Requisição recebida para username: {username}")

    if not username:
        return jsonify({"erro": "Username não fornecido"}), 400

    conn = obter_conexao_bd()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT user_id FROM GW WHERE username=%s", (username,))
    utilizador = cursor.fetchone()
    if not utilizador:
        cursor.close()
        conn.close()
        return jsonify({"erro": "Utilizador não encontrado"}), 404

    user_id = utilizador["user_id"]

    cursor.execute("""
        SELECT 
            Orders.order_id,
            Orders.items,
            Orders.total,
            Orders.status AS order_status,
            Payments.payment_id,
            Payments.status AS payment_status,
            Payments.created_at AS payment_date
        FROM Orders
        LEFT JOIN Payments ON Orders.order_id = Payments.order_id
        WHERE Orders.user_id = %s
        ORDER BY Orders.created_at DESC
    """, (user_id,))

    pagamentos = cursor.fetchall()
    cursor.close()
    conn.close()

    return jsonify(pagamentos), 200

# Rota para processar um pagamento
@app.route("/payments", methods=["POST"])
def processar_pagamento():
    dados = request.get_json()
    print(f"[PROCESSAR PAGAMENTO] Dados recebidos: {dados}")

    if not dados or "order_id" not in dados:
        print("[PROCESSAR PAGAMENTO] order_id obrigatório")
        return jsonify({"erro": "Falta o campo order_id"}), 400

    order_id = dados["order_id"]

    conn = obter_conexao_bd()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            Orders.order_id, Orders.total, Orders.status,
            GW.user_id, GW.wallet, GW.email, Orders.items
        FROM Orders
        JOIN GW ON Orders.user_id = GW.user_id
        WHERE Orders.order_id = %s
    """, (order_id,))
    
    ordem = cursor.fetchone()

    if not ordem:
        cursor.close()
        conn.close()
        return jsonify({"erro": "Encomenda não encontrada"}), 404

    total = float(ordem["total"])
    saldo = float(ordem["wallet"])
    user_id = ordem["user_id"]
    email = ordem["email"]
    estado_atual = ordem["status"]

    print(f"[PROCESSAR PAGAMENTO] Estado atual da encomenda: {estado_atual}")

    # Se a encomenda já foi processada
    if estado_atual != "pendente":
        print(f"[PROCESSAR PAGAMENTO] Encomenda {order_id} já processada anteriormente com estado '{estado_atual}'. Nenhum email enviado.")

        if estado_atual.lower() == "cancelada":
            mensagem = "A encomenda foi cancelada anteriormente. Nenhum pagamento foi processado."
        else:
            mensagem = "O pagamento já tinha sido processado anteriormente. Nenhum email enviado."

        return jsonify({
            "order_id": order_id,
            "status": estado_atual,
            "mensagem": mensagem
        }), 200

    # Pagamento com sucesso
    elif saldo >= total:
        estado_pagamento = "completa"
        novo_saldo = saldo - total

        cursor.execute("UPDATE GW SET wallet=%s WHERE user_id=%s",
                       (novo_saldo, user_id))
        cursor.execute("UPDATE Orders SET status='completa' WHERE order_id=%s",
                       (order_id,))
    else:
        # Saldo insuficiente
        estado_pagamento = "falhada"
        cursor.execute("UPDATE Orders SET status='cancelada' WHERE order_id=%s",
                       (order_id,))

    cursor.execute(
        "INSERT INTO Payments (order_id, amount, status) VALUES (%s, %s, %s)",
        (order_id, total, estado_pagamento)
    )

    payment_id = cursor.lastrowid
    conn.commit()

    cursor.close()
    conn.close()

    # Enviar notificação
    try:
        requests.post(
            f"{NOTIFICATIONS_URL}/notifications/status",
            json={
                "email": email,
                "order_id": order_id,
                "status": estado_pagamento,
                "total": total,
                "user_id": user_id
            },
            timeout=5
        )
        print("[NOTIFICAÇÃO] Enviada com sucesso")
    except Exception as e:
        print(f"[ERRO NOTIFICAÇÃO] {e}")

    return jsonify({
        "order_id": order_id,
        "payment_id": payment_id,
        "status": estado_pagamento
    }), 200

# Correr a aplicação Flask
if __name__ == "__main__":
    print("[SERVIDOR] Serviço de Payments a correr na porta 5700")
    app.run(host="0.0.0.0", port=5700)
