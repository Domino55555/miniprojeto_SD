# notifications.py
from flask import Flask, request, jsonify
import smtplib
from email.message import EmailMessage
import os
import mysql.connector
import random
import requests

app = Flask(__name__)

ORDERS_URL = os.getenv("ORDERS_URL", "http://orders:5600")
PAYMENTS_URL = os.getenv("PAYMENTS_URL", "http://payments:5700")

# Configuração da DB
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "grupo3")
DB_PASSWORD = os.getenv("DB_PASSWORD", "baguette")
DB_NAME = os.getenv("DB_NAME", "servicos")


def get_db_connection():
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


@app.route("/notifications/send_verification", methods=["POST"])
def send_verification():
    data = request.get_json()
    email = data.get("email")
    if not email:
        return {"erro": "Campo obrigatório: email"}, 400

    codigo = str(random.randint(1000, 9999))

    assunto = "Código de Verificação - Loja XPTO"
    mensagem = f"Olá!\n\nSeu código de verificação para criar conta na Loja XPTO é:\n\n{codigo}\n\nNão compartilhe este código com ninguém."

    enviar_email(email, assunto, mensagem)

    return {"mensagem": "Código enviado para o email", "codigo": codigo}, 200
    
    
@app.route('/notifications/<username>', methods=['GET'])
def notificacoes_do_cliente(username):
    if not username:
        return jsonify({"erro": "Username não fornecido"}), 400

    # 1) Buscar orders do utilizador
    try:
        orders_resp = requests.get(f"{ORDERS_URL}/orders/{username}", timeout=5)
        orders_data = orders_resp.json() if orders_resp.status_code == 200 else []
    except Exception as e:
        orders_data = {"erro": f"Falha ao contactar Orders: {str(e)}"}

    # 2) Buscar payments do utilizador
    try:
        payments_resp = requests.get(f"{PAYMENTS_URL}/payments/{username}", timeout=5)
        payments_data = payments_resp.json() if payments_resp.status_code == 200 else []
    except Exception as e:
        payments_data = {"erro": f"Falha ao contactar Payments: {str(e)}"}

    # 3) Resposta final agregada
    return jsonify({
        "username": username,
        "orders": orders_data,
        "payments": payments_data
    }), 200


@app.route("/notifications/order_created", methods=["POST"])
def order_created():
    data = request.get_json()
    email = data.get("email")
    username = data.get("username")
    order_id = data.get("order_id")
    items = data.get("items", [])
    total = data.get("total", 0.0)

    if not email or not username or not order_id:
        return {"erro": "Campos obrigatórios: email, username, order_id"}, 400

    assunto = "Ordem Criada - Pendente de Pagamento"
    mensagem = (
        f"Olá {username},\n\n"
        f"Sua ordem {order_id} foi criada com sucesso e está pendente de pagamento.\n"
        f"Itens: {', '.join(items)}\n"
        f"Total: {total:.2f}€\n\nObrigado por comprar conosco!"
    )

    enviar_email(email, assunto, mensagem)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO Notifications (user_id, message) VALUES (%s, %s)",
            (data.get("user_id"), mensagem)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[NOTIFICATIONS DB] Erro ao registrar notificação: {e}")

    return {"mensagem": "Notificação de ordem enviada"}, 200



@app.route("/notifications/status", methods=["POST"])
def payment_status():
    data = request.get_json()

    email = data.get("email")
    order_id = data.get("order_id")
    status = data.get("status")
    total = data.get("total", 0.0)
    user_id = data.get("user_id")

    if not email or not order_id or not status or not user_id:
        return {"erro": "Campos obrigatórios: email, order_id, status, user_id"}, 400

    if status == "completed":
        assunto = "Pagamento Concluído"
        mensagem = f"O seu pagamento da ordem {order_id} no valor de {total:.2f}€ foi concluído com sucesso."
    elif status == "failed":
        assunto = "Pagamento Falhou"
        mensagem = f"O pagamento da ordem {order_id} não foi concluído por saldo insuficiente."
    elif status == "cancelled":
        assunto = "Ordem Cancelada"
        mensagem = f"A sua ordem {order_id} no valor de {total:.2f}€ foi cancelada."
    else:
        assunto = "Pagamento Pendente"
        mensagem = f"A ordem {order_id} no valor de {total:.2f}€ está pendente de pagamento."

    sucesso = enviar_email(email, assunto, mensagem)
    if not sucesso:
        print(f"[ERRO EMAIL] Falha ao enviar email para {email} status {status}")
        return {"erro": "Falha ao enviar email"}, 500

    # Registrar notificação na BD
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO Notifications (user_id, message) VALUES (%s, %s)",
            (user_id, mensagem)
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[NOTIFICATIONS DB] Erro ao registrar notificação: {e}")

    return {"mensagem": "Notificação enviada com sucesso"}, 200


@app.route("/")
def home():
    return {"message": "Notifications online"}, 200


if __name__ == "__main__":
    print("[START] Notifications service on port 5800")
    app.run(host="0.0.0.0", port=5800)
