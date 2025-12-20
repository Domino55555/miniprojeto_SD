-------------------------------------------------------------------
Sistema Distribuído - Microserviços Loja XPTO
-------------------------------------------------------------------

--------------------
Microserviços Principais
--------------------

- GW (Gateway Service)
  - Porta: 5863
  - Objetivo: Ponto de entrada único, encaminhando requisições para microserviços internos
  - Responsabilidades:
    - Receber pedidos dos clientes
    - Encaminhar requisições para Orders, Payments e Notifications
    - Centralizar URLs de serviços via variáveis de ambiente
  - Integração:
    - Consume APIs: Orders (5600), Payments (5700), Notifications (5800)
    - Logs para Loki
    - Métricas para Prometheus

- Orders Service
  - Objetivo: Gestão de encomendas
  - Responsabilidades:
    - Criar e validar encomendas
    - Calcular total
    - Consultar encomendas por username
    - Cancelar encomendas pendentes
    - Notificar cliente via Notifications
  - Integração:
    - Base de dados MySQL (Orders, GW)
    - Notificações via Notifications
    - Logs para Loki
    - Métricas para Prometheus

- Payments Service
  - Objetivo: Processamento de pagamentos
  - Responsabilidades:
    - Receber pedidos de pagamento
    - Verificar saldo do cliente
    - Atualizar estado da encomenda
    - Registar pagamentos
    - Notificar cliente via Notifications
  - Integração:
    - Base de dados MySQL (Orders, Payments, GW)
    - Notificações via Notifications
    - Logs para Loki
    - Métricas para Prometheus

- Notifications Service
  - Objetivo: Envio de notificações e e-mails
  - Responsabilidades:
    - Enviar códigos de verificação
    - Notificar sobre criação de encomendas, estado de pagamentos e cancelamentos
    - Guardar histórico de notificações
  - Integração:
    - Base de dados MySQL (Notifications, GW)
    - Recebe chamadas de Orders e Payments
    - Logs para Loki
    - Métricas para Prometheus

--------------------
Base de Dados (MySQL)
--------------------
- Armazena informações de utilizadores (GW), encomendas (Orders), pagamentos (Payments) e notificações (Notifications)
- Volumes persistentes montados no host em: /var/lib/docker/volumes/
- Ficheiros de dados temporários e de inicialização também aparecem na pasta .data dentro do diretório do docker-compose

--------------------
Observabilidade
--------------------
- Prometheus: recolhe métricas de todos os serviços
- Loki: centraliza logs de todos os serviços, gateway e microserviços
- Cadvisor: monitorização de containers Docker
- Flog: gera tráfego de logs em tempo real para testar o sistema
