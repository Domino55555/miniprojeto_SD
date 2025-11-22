# depois temos que mudar os logs para ficarem mais bonitos, ja tive q refazer esta meda umas 5 vezes e ja tou farto 

from flask import Flask, request, jsonify
import mysql.connector
import json
import os

app = Flask(__name__)

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
        print("[CREATE ORDER] Missing 'items' field in request")
        return jsonify({"error": "Missing items"}), 400

    # Aceitar string ou lista
    items_input = data["items"]
    if isinstance(items_input, str):
        items_list = [i.strip() for i in items_input.split(",")]
    elif isinstance(items_input, list):
        items_list = items_input
    else:
        print("[CREATE ORDER] Invalid items format")
        return jsonify({"error": "Items inválidos"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Buscar um utilizador (por agora apenas o primeiro)
    cursor.execute("SELECT user_id, username FROM GW LIMIT 1")
    user_row = cursor.fetchone()
    print(f"[CREATE ORDER] Selected user: {user_row}")

    if not user_row:
        cursor.close()
        conn.close()
        print("[CREATE ORDER] No users found in DB")
        return jsonify({"error": "No users found in DB"}), 500

    user_id = user_row["user_id"]
    username = user_row["username"]

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
        cursor.close()
        conn.close()
        print(f"[CREATE ORDER] Unknown items: {unknown_items}")
        return jsonify({
            "error": "Unknown items",
            "items": unknown_items
        }), 400

    # Inserir na DB
    cursor.execute(
        "INSERT INTO Orders (user_id, items, total, status) VALUES (%s, %s, %s, %s)",
        (user_id, ",".join(items_list), total, "pending")
    )
    conn.commit()
    order_id = cursor.lastrowid
    print(f"[CREATE ORDER] Order created with ID {order_id} for user {username}")

    cursor.close()
    conn.close()

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
#           RUN
# ------------------------------
if __name__ == "__main__":
    print("[STARTING SERVER] Orders service running on port 5600")
    app.run(host="0.0.0.0", port=5600)
