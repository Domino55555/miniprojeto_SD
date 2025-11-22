# aviso: as mensagens são feias de ler, temos que melhorar no futuro

from flask import Flask, request, jsonify
import mysql.connector
import os
import random

app = Flask(__name__)

# Configuração DB
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "grupo3")
DB_PASSWORD = os.getenv("DB_PASSWORD", "baguette")
DB_NAME = os.getenv("DB_NAME", "servicos")

def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

print("Serviço de notificações online com DB.")

# ------------------------------
#     PAYMENT NOTIFICATION
# ------------------------------
@app.route("/notifications/payment", methods=["POST"])
def payment_notification():
    data = request.get_json()
    print("Requisição recebida:", data)

    if not data or "username" not in data or "password" not in data:
        response = {"error": "Missing fields"}
        print("Erro:", response)
        return jsonify(response), 400

    username = data["username"]
    password = data["password"]
    print(f"A pesquisar utilizador: {username}")

    # conectar DB
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT user_id, username, password, wallet FROM GW WHERE username = %s", (username,))
    user_row = cursor.fetchone()
    print(f"Resultado da pesquisa na DB: {user_row}")

    if not user_row:
        cursor.close()
        conn.close()
        response = {"error": "User not found"}
        print("Erro:", response)
        return jsonify(response), 404

    # verificar password
    if password != user_row["password"]:
        cursor.close()
        conn.close()
        response = {"error": "Invalid password"}
        print("Erro:", response)
        return jsonify(response), 401

    print("Password correta inserida.")

    # roll the dice!
    status = "success" if random.random() < 0.5 else "failed"
    print(f"Status do pagamento decidido internamente: {status}")

    amount = float(user_row["wallet"])
    print(f"Valor do pagamento retirado da wallet: {amount}")

    if status == "success":
        message = f"Pagamento de {amount} realizado com sucesso para {username} (Account ID: {user_row['user_id']})."
    else:
        message = f"Pagamento de {amount} falhou para {username} (Account ID: {user_row['user_id']})."

    print(f"Mensagem final gerada: {message}")

    response = {
        "notification": message,
        "status": status
    }

    cursor.close()
    conn.close()

    print("Resposta enviada:", response, "\n")
    return jsonify(response)


# ------------------------------
#       LIST ACCOUNTS (DEBUG)
# ------------------------------
@app.route("/notifications/contas", methods=["GET"])
def list_accounts():
    print("[LIST ACCOUNTS] Fetching all accounts from DB")
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT user_id, username, wallet FROM GW")
    accounts = cursor.fetchall()

    cursor.close()
    conn.close()
    print(f"[LIST ACCOUNTS] Retrieved {len(accounts)} accounts:", accounts, "\n")
    return jsonify(accounts)


# ------------------------------
#           RUN
# ------------------------------
if __name__ == "__main__":
    print("Servidor de notificações a correr em http://0.0.0.0:5800\n")
    app.run(host="0.0.0.0", port=5800)
