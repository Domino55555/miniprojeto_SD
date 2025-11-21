from flask import Flask, request, jsonify, json

app = Flask(__name__)

with open("Listas/produtos.json", "r") as f:
    items_prices = json.load(f)

items_prices_norm = {k.lower(): v for k, v in items_prices.items()}

orders_db = {}
next_id = 1


# Criar uma order
@app.route("/orders", methods=["POST"])
def create_order():
    global next_id
    data = request.get_json()
    
    # Validação 
    if not data or "user_id" not in data or "items" not in data:
        return jsonify({"error": "Missing fields"}), 400
    
      # Aceitar string ou lista
    items_input = data["items"]
    if isinstance(items_input, str):
        items_list = [i.strip() for i in items_input.split(",")]
    elif isinstance(items_input, list):
        items_list = items_input
    else:
        return jsonify({"error": "Items inválidos"}), 400
    

    total = 0
    unknown_items = []
    
    for item in items_list:
        item_lower = item.lower().strip()

        if item_lower in items_prices_norm:
            total += items_prices_norm[item_lower]
        else:
            unknown_items.append(item)

    if unknown_items:
        return jsonify({"error": "Unknown items", "items": unknown_items}), 400

    order_id = str(next_id)
    next_id += 1

    order = {
        "id": order_id,
        "user_id": data["user_id"],
        "items": items_list,
        "total": total,
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
        "items": list(items_prices.keys())
    }
    return jsonify(fields)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5600)
