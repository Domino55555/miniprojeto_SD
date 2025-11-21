# aviso ja que as mensagens sao feias de ler, temos que alterar e por mais bonito dps

from flask import Flask, request, jsonify, json
import random

app = Flask(__name__)

# ficheiro com contas estaticas (temporário)
accounts_file = "Listas/contas.json"


# load da file de json

with open(accounts_file, "r") as f:
    accounts = json.load(f)

print("Serviço de notificações online.")

# verificar se a conta existe na data (ficheiro json temporario)

@app.route("/notifications/payment", methods=["POST"])
def payment_notification():
    
    data = request.get_json()
    print("Requisição recebida:", data)

# validacao inicial
    if not data or "username" not in data or "password" not in data or "amount" not in data:
        response = {"error": "Missing fields"}
        print("Erro:", response)
        return jsonify(response), 400

    username = data["username"]
    password = data["password"]
    amount = float(data["amount"])
    print(f"A pesquisar utilizador: {username}")


# check para verificar se o utilizador existe, dps adiciona-se um check de username + password hash
    if username not in accounts:
        response = {"error": "User not found"}
        print("Erro:", response)
        return jsonify(response), 404

# temporariamente uma lista estatica
    user_account = accounts[username]
    print(f"Conta encontrada: {user_account}")

# verificar password
    if password != user_account["password"]:
        response = {"error": "Invalid password"}
        print("Erro:", response)
        return jsonify(response), 401

    print("Password correta inserida.")

    # roll the dice!
    status = "success" if random.random() < 0.5 else "failed"
    print(f"Status do pagamento decidido internamente: {status}")

# mensagens de sucesso ou failed, dps costumiza-se melhor
    if status == "success":
        message = f"Pagamento de {amount} realizado com sucesso para {username} (Account ID: {user_account['user_id']})."
    else:
        message = f"Pagamento de {amount} falhou para {username} (Account ID: {user_account['user_id']})."

    response = {
        "notification": message,
        "status": status
    }

    print("Resposta enviada:", response, "\n")
    return jsonify(response)


# so para testar\ administradores verificarem as contas

@app.route("/notifications/contas", methods=["GET"])
def list_accounts():
    """
    Apenas para debug/listagem de contas
    """
    print("Requisição GET /notifications/accounts")
    response = accounts
    print("Resposta enviada:", response, "\n")
    return jsonify(response)


if __name__ == "__main__":
    print("Servidor a correr em http://0.0.0.0:5800\n")
    app.run(host="0.0.0.0", port=5800)
