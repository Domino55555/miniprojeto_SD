from flask import Flask, request, jsonify

app = Flask(__name__)


orders_db = {}
next_id = 1


# Criar uma order
@app.route("/orders", methods=["POST"])
def create_order():
    global next_id
    data = request.get_json()
    
    # Validação 
    if not data or "user_id" not in data or "items" not in data or "total" not in data:
        return jsonify({"error": "Missing fields"}), 400

    order_id = str(next_id)
    next_id += 1

    order = {
        "id": order_id,
        "user_id": data["user_id"],
        "items": data["items"],
        "total": data["total"],
        "status": "pending"
    }

    orders_db[order_id] = order
    return jsonify(order), 201

@app.route("/orders", methods=["GET"])
def list_orders():
    return jsonify(list(orders_db.values()))

@app.route("/orders/<order_id>", methods=["GET"])
def get_order(order_id):
    order = orders_db.get(order_id)
    if order:
        return jsonify(order)
    return jsonify({"error": "Order not found"}), 404

@app.route("/orders/fields", methods=["GET"])
def order_fields():
    fields = {
        "user_id": "ID do utilizador ",
        "items": " lista de itens",
        "total": "valor total da order"
    }
    return jsonify(fields)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5600)
