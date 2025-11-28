from flask import Flask, request, jsonify
import mysql.connector
import json
import os
import requests


app = Flask(__name__)

NOTIFICATIONS_URL = os.getenv("NOTIFICATIONS_URL", "http://notifications:5800")


# Configuração da DB
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

# Load dos produtos e preços
with open("Listas/produtos.json", "r") as f:
    items_prices = json.load(f)

items_prices_norm = {k.lower(): v for k, v in items_prices.items()}


# ------------------------------
#        CRIAR ORDER
# ------------------------------
@app.route("/orders", methods=["POST"])
def create_order():
    data = request.get_json()
    print(f"[CREATE ORDER] Received data: {data}")

    if not data or "items" not in data:
        print("[CREATE ORDER] Missing items in request")
        return jsonify({"error": "Missing items"}), 400

    items_input = data["items"]
    items_list = [i.strip() for i in items_input.split(",")] if isinstance(items_input, str) else items_input

    user_id = data.get("user_id")
    if not user_id:
        print("[CREATE ORDER] user_id obrigatório")
        return jsonify({"error": "user_id obrigatório"}), 400

    # Conectar ao banco
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Buscar username e email do usuário
    print(f"[CREATE ORDER] Buscando username e email para user_id: {user_id}")
    cursor.execute("SELECT username, email FROM GW WHERE user_id=%s", (user_id,))
    user_row = cursor.fetchone()
    if not user_row:
        print("[CREATE ORDER] Utilizador não encontrado")
        cursor.close()
        conn.close()
        return jsonify({"error": "Utilizador não encontrado"}), 404

    username = user_row["username"]
    email = user_row["email"]
    print(f"[CREATE ORDER] Username: {username}, Email: {email}")

    # Calcular total
    total = 0
    unknown_items = []
    for item in items_list:
        item_lower = item.lower().strip()
        if item_lower in items_prices_norm:
            total += items_prices_norm[item_lower]
        else:
            unknown_items.append(item)

    if unknown_items:
        print(f"[CREATE ORDER] Itens desconhecidos: {unknown_items}")
        cursor.close()
        conn.close()
        return jsonify({"error": "Unknown items", "items": unknown_items}), 400

    # Inserir order no banco
    cursor.execute(
        "INSERT INTO Orders (user_id, items, total, status) VALUES (%s, %s, %s, %s)",
        (user_id, ",".join(items_list), total, "pending")
    )
    conn.commit()
    order_id = cursor.lastrowid
    cursor.close()
    conn.close()

    print(f"[CREATE ORDER] Order criada com sucesso: {order_id}")

    # Notificar serviço de notifications
    try:
        response = requests.post(
            f"{NOTIFICATIONS_URL}/notifications/order_created",
            json={
                "email": email,
                "username": username,
                "order_id": order_id,
                "items": items_list,
                "total": total,
                "user_id": user_id
            },
            timeout=5
        )
        response.raise_for_status()
        print(f"[CREATE ORDER] Notificação enviada para {NOTIFICATIONS_URL}")
    except Exception as e:
        print(f"[CREATE ORDER] Falha ao notificar notifications: {e}")

    return jsonify({
        "order_id": order_id,
        "username": username,
        "items": items_list,
        "total": total,
        "status": "pending"
    }), 201



# ------------------------------
#        LISTAR ORDERS
# ------------------------------
@app.route("/orders", methods=["GET"])
def list_orders():
    print("[LIST ORDERS] Fetching all orders")
    conn = get_db_connection()
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
    """)

    orders = cursor.fetchall()
    print(f"[LIST ORDERS] Retrieved {len(orders)} orders")

    cursor.close()
    conn.close()

    return jsonify(orders)


# ------------------------------
#      OBTER ORDERS POR USERNAME
# ------------------------------
@app.route("/orders/<username>", methods=["GET"])
def get_orders_by_username(username):
    print(f"[GET ORDERS BY USERNAME] Fetching orders for username: {username}")
    conn = get_db_connection()
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

    orders = cursor.fetchall()
    print(f"[GET ORDERS BY USERNAME] Found {len(orders)} orders for {username}")

    cursor.close()
    conn.close()

    if orders:
        return jsonify(orders)

    print(f"[GET ORDERS BY USERNAME] No orders found for {username}")
    return jsonify({"error": "No orders found for this username"}), 404


# ------------------------------
#      CAMPOS DISPONÍVEIS
# ------------------------------
@app.route("/orders/fields", methods=["GET"])
def order_fields():
    print("[ORDER FIELDS] Returning available items")
    return jsonify({
        "items": list(items_prices.keys())
    })

# ------------------------------
#        CANCELAR ORDER
# ------------------------------
@app.route("/orders/cancel", methods=["POST"])
def cancelar_order():
    data = request.get_json()
    print(f"[CANCEL ORDER] Dados recebidos: {data}")

    if not data or "order_id" not in data:
        return jsonify({"error": "order_id obrigatório"}), 400

    order_id = data["order_id"]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Buscar ordem + utilizador + email
    cursor.execute("""
        SELECT 
            Orders.order_id, Orders.total, Orders.status, Orders.items,
            GW.user_id, GW.wallet, GW.email, GW.username
        FROM Orders
        JOIN GW ON Orders.user_id = GW.user_id
        WHERE Orders.order_id = %s
    """, (order_id,))
    order = cursor.fetchone()

    if not order:
        cursor.close()
        conn.close()
        return jsonify({"error": "Order not found"}), 404

    if order["status"].lower() != "pending":
        cursor.close()
        conn.close()
        return jsonify({
            "error": f"Order não pode ser cancelada porque está '{order['status']}'"
        }), 400

    # Atualizar status para 'cancelled'
    cursor.execute("UPDATE Orders SET status='cancelled' WHERE order_id=%s", (order_id,))
    conn.commit()

    # Guardar dados ANTES de fechar ligação
    email = order["email"]
    user_id = order["user_id"]
    total = float(order["total"])

    cursor.close()
    conn.close()

    # Enviar notificação AGORA fora da DB
    try:
        r = requests.post(
            f"{NOTIFICATIONS_URL}/notifications/status",
            json={
                "email": email,
                "order_id": order_id,
                "status": "cancelled",
                "total": total,
                "user_id": user_id
            },
            timeout=5
        )
        print(f"[CANCEL ORDER] Notificação enviada: {r.status_code}")
    except Exception as e:
        print(f"[CANCEL ORDER] Erro ao notificar Notifications: {e}")

    return jsonify({
        "success": True,
        "order_id": order_id,
        "status": "cancelled",
        "message": "Order cancelada com sucesso"
    }), 200


# ------------------------------
#           RUN
# ------------------------------
if __name__ == "__main__":
    print("[STARTING SERVER] Orders service running on port 5600")
    app.run(host="0.0.0.0", port=5600)
