from flask import Flask, request, jsonify
import mysql.connector
import os
import requests

app = Flask(__name__)

NOTIFICATIONS_URL = os.getenv("NOTIFICATIONS_URL", "http://notifications:5800")

# ---- DB CONFIG ----
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "grupo3")
DB_PASSWORD = os.getenv("DB_PASSWORD", "baguette")
DB_NAME = os.getenv("DB_NAME", "servicos")

def get_db_connection():
    print("[DB] Abrindo conexão com a base de dados")
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

# ------------------------------
# GET PAYMENTS DO CLIENTE
# ------------------------------
@app.route("/payments/<username>", methods=["GET"])
def pagamentos_do_cliente(username):
    print(f"[PAYMENTS ME] Requisição recebida para username: {username}")

    if not username:
        return jsonify({"erro": "Username não fornecido"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Buscar o user_id do username
    cursor.execute("SELECT user_id FROM GW WHERE username=%s", (username,))
    row = cursor.fetchone()
    if not row:
        cursor.close()
        conn.close()
        return jsonify({"erro": "Utilizador não encontrado"}), 404

    user_id = row["user_id"]

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

# ------------------------------
# PROCESS PAYMENT
# ------------------------------
@app.route("/payments", methods=["POST"])
def process_payment():
    data = request.get_json()
    print(f"[PROCESS PAYMENT] Dados recebidos: {data}")

    if not data or "order_id" not in data:
        print("[CANCEL ORDER] order_id obrigatório")
        return jsonify({"error": "Missing order_id"}), 400

    order_id = data["order_id"]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Buscar ordem + utilizador + email
    cursor.execute("""
        SELECT 
            Orders.order_id, Orders.total, Orders.status,
            GW.user_id, GW.wallet, GW.email, Orders.items
        FROM Orders
        JOIN GW ON Orders.user_id = GW.user_id
        WHERE Orders.order_id = %s
    """, (order_id,))
    
    row = cursor.fetchone()

    if not row:
        cursor.close()
        conn.close()
        return jsonify({"error": "Order not found"}), 404

    total = float(row["total"])
    wallet = float(row["wallet"])
    user_id = row["user_id"]
    email = row["email"]
    current_status = row["status"]

    print(f"[PROCESS PAYMENT] Estado atual da ordem: {current_status}")

    # --------------------------------
    # LÓGICA DO PAGAMENTO
    # --------------------------------
    # Se a order não está pending, então já foi tratada antes.
    if current_status != "pending":

        print(f"[PROCESS PAYMENT] Ordem {order_id} já tratada anteriormente com estado '{current_status}'. Nenhum email enviado.")

        # Escolher mensagem correta dependendo do estado real
        if current_status.lower() == "cancelled":
            mensagem = "A ordem foi cancelada anteriormente. Nenhum pagamento foi processado."
        else:
            mensagem = "O pagamento já tinha sido processado anteriormente. Nenhum email enviado."

        return jsonify({
            "order_id": order_id,
            "status": current_status,
            "message": mensagem
        }), 200

    elif wallet >= total:
        payment_status = "completed"
        new_wallet = wallet - total

        cursor.execute("UPDATE GW SET wallet=%s WHERE user_id=%s",
                       (new_wallet, user_id))
        cursor.execute("UPDATE Orders SET status='completed' WHERE order_id=%s",
                       (order_id,))
    else:
        payment_status = "failed"
        cursor.execute("UPDATE Orders SET status='cancelled' WHERE order_id=%s",
                       (order_id,))

    # Registrar pagamento
    cursor.execute(
        "INSERT INTO Payments (order_id, amount, status) VALUES (%s, %s, %s)",
        (order_id, total, payment_status)
    )

    payment_id = cursor.lastrowid
    conn.commit()

    cursor.close()
    conn.close()

    # --------------------------------
    # NOTIFICAÇÃO AO SERVIÇO NOTIFICATIONS
    # --------------------------------
    try:
        requests.post(
            f"{NOTIFICATIONS_URL}/notifications/status",
            json={
                "email": email,
                "order_id": order_id,
                "status": payment_status,
                "total": total,
                "user_id": user_id
            },
            timeout=5
        )
        print("[NOTIFICATION] Enviada com sucesso")
    except Exception as e:
        print(f"[ERRO NOTIFICAÇÃO] {e}")

    return jsonify({
        "order_id": order_id,
        "payment_id": payment_id,
        "status": payment_status
    }), 200

# ------------------------------
# HOME
# ------------------------------
@app.route("/")
def home():
    return {"message": "Payments service online"}, 200

# ------------------------------
# RUN
# ------------------------------
if __name__ == "__main__":
    print("[STARTING SERVER] Payments service running on port 5700")
    app.run(host="0.0.0.0", port=5700)
