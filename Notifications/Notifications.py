from flask import Flask, request, jsonify
import smtplib
from email.message import EmailMessage
import os
import mysql.connector
import random
import requests
from prometheus_flask_exporter import PrometheusMetrics
from prometheus_client import Summary, Gauge
import time
# Metrica de latencia: medida em segundos
REQUEST_LATENCY_GAUGE = Gauge('request_latency_seconds', 'Latência da última request', ['endpoint'])

app = Flask(__name__)
metrics = PrometheusMetrics(app)  # adiciona métricas automaticamente

ORDERS_URL = os.getenv("ORDERS_URL", "http://orders:5600")
PAYMENTS_URL = os.getenv("PAYMENTS_URL", "http://payments:5700")

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
        database=DB_NAME,
        auth_plugin="mysql_native_password"
    )

# Configuração do Email
EMAIL_REMETENTE = "weather2travel.senhas@gmail.com"
SENHA_APP = "ehbf gvdz uzbd pcuz"

# Função para enviar email
def enviar_email(destino, assunto, mensagem):
    try:
        msg = EmailMessage()
        msg["From"] = EMAIL_REMETENTE
        msg["To"] = destino
        msg["Subject"] = assunto
        msg.set_content(mensagem)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(EMAIL_REMETENTE, SENHA_APP)
            smtp.send_message(msg)

        print(f"[EMAIL ENVIADO] Para {destino} | {assunto}")
        return True

    except Exception as e:
        print(f"[ERRO EMAIL] {e}")
        return False

# Rota para enviar código de verificação por email
@app.route("/notifications/send_verification", methods=["POST"])
def enviar_codigo_verificacao():
    dados = request.get_json()
    email = dados.get("email")
    if not email:
        return {"erro": "Campo obrigatório: email"}, 400

    codigo = str(random.randint(1000, 9999))

    assunto = "Código de Verificação - Loja XPTO"
    mensagem = (
        f"Olá!\n\n"
        f"O seu código de verificação para criar conta na Loja XPTO é:\n\n{codigo}\n\n"
        f"Não partilhe este código com ninguém."
    )

    enviar_email(email, assunto, mensagem)

    return {"mensagem": "Código enviado para o email", "codigo": codigo}, 200

# Rota para obter notificações de um cliente
@app.route("/notifications/<username>", methods=["GET"])
def notificacoes_do_cliente(username):
    if not username:
        return jsonify({"erro": "Username não fornecido"}), 400

    try:
        orders_resp = requests.get(f"{ORDERS_URL}/orders/{username}", timeout=5)
        orders_data = orders_resp.json() if orders_resp.status_code == 200 else []
    except Exception as e:
        orders_data = {"erro": f"Falha ao contactar Orders: {str(e)}"}

    try:
        payments_resp = requests.get(f"{PAYMENTS_URL}/payments/{username}", timeout=5)
        payments_data = payments_resp.json() if payments_resp.status_code == 200 else []
    except Exception as e:
        payments_data = {"erro": f"Falha ao contactar Payments: {str(e)}"}

    return jsonify({
        "orders": orders_data,
        "payments": payments_data
    }), 200

# Rota para notificar criação de ordem
@app.route("/notifications/order_created", methods=["POST"])
def ordem_criada():
    dados = request.get_json()
    email = dados.get("email")
    username = dados.get("username")
    order_id = dados.get("order_id")
    items = dados.get("items", [])
    total = dados.get("total", 0.0)

    if not email or not username or not order_id:
        return {"erro": "Campos obrigatórios: email, username, order_id"}, 400

    assunto = "Encomenda Criada - Pendente de Pagamento"
    mensagem = (
        f"Olá {username},\n\n"
        f"A sua encomenda, com o número identificador {order_id}, foi criada com sucesso e está pendente de pagamento.\n"
        f"Itens: {', '.join(items)}\n"
        f"Total: {total:.2f}€\n\nObrigado por comprar connosco!"
    )

    enviar_email(email, assunto, mensagem)

    try:
        conn = obter_conexao_bd()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO Notifications (user_id, message) VALUES (%s, %s)",
            (dados.get("user_id"), mensagem)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[NOTIFICAÇÃO BD] Erro ao registar notificação: {e}")

    return {"mensagem": "Notificação de ordem enviada"}, 200

# Rota para notificar estado do pagamento
@app.route("/notifications/status", methods=["POST"])
def estado_pagamento():
    dados = request.get_json()

    email = dados.get("email")
    order_id = dados.get("order_id")
    status = dados.get("status")
    total = dados.get("total", 0.0)
    user_id = dados.get("user_id")

    if not email or not order_id or not status or not user_id:
        return {"erro": "Campos obrigatórios: email, order_id, status, user_id"}, 400

    if status == "completa":
        assunto = "Pagamento Concluído"
        mensagem = f"O pagamento da sua encomenda, com número identificador {order_id}, no valor de {total:.2f}€, foi concluído com sucesso."
    elif status == "falhada":
        assunto = "Pagamento Falhou"
        mensagem = f"O pagamento da sua encomenda, com o número identificador {order_id}, não foi concluído por saldo insuficiente."
    elif status == "cancelada":
        assunto = "Ordem Cancelada"
        mensagem = f"A sua encomenda com, o número identificador {order_id}, no valor de {total:.2f}€, foi cancelada."
    else:
        assunto = "Pagamento Pendente"
        mensagem = f"A sua encomenda, com o número identificador {order_id}, no valor de {total:.2f}€, está pendente de pagamento."

    sucesso = enviar_email(email, assunto, mensagem)
    if not sucesso:
        print(f"[ERRO EMAIL] Falha ao enviar email para {email} | status {status}")
        return {"erro": "Falha ao enviar email"}, 500

    try:
        conn = obter_conexao_bd()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO Notifications (user_id, message) VALUES (%s, %s)",
            (user_id, mensagem)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[NOTIFICAÇÃO BD] Erro ao registar notificação: {e}")

    return {"mensagem": "Notificação enviada com sucesso"}, 200

# Correr a aplicação Flask
if __name__ == "__main__":
    print("[SERVIDOR] Serviço de Notifications a correr na porta 5800")
    app.run(host="0.0.0.0", port=5800)
