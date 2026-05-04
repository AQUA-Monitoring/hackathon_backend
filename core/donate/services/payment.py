from django.views.decorators.csrf import csrf_exempt
import mercadopago, os, json, uuid

class PaymentService:
    def payment_card(request):
        sdk = mercadopago.SDK(os.getenv('ACCESS_TOKEN'))
        request_options = mercadopago.config.RequestOptions()
        request_options.custom_headers = {
            'x-idempotency-key': str(uuid.uuid4())
        }

        data = json.loads(request.body)
        payer = data.get('payer')
        identification = payer.get('identification')
        payment_data = {
            'transaction_amount': data.get('transaction_amount'),
            'token': data.get('token'),
            'description': data.get('description'),
            'installments': data.get('installments'),
            'payment_method_id': data.get('payment_method_id'),
            'issuer_id': data.get('issuer_id'),
            'payer': {
                'email': payer.get('email'),
                'identification': {
                    'type': identification.get('type'),
                    'number': identification.get('number'),
                }
            }
        }
        response = sdk.payment().create(payment_data, request_options)
        payment = response['response']
        return payment
    
    def payment_pix(request):
        sdk = mercadopago.SDK(os.getenv('ACCESS_TOKEN'))
        request_options = mercadopago.config.RequestOptions()
        request_options.custom_headers = {
            'x-idempotency-key': str(uuid.uuid4())
        }
    
        data = json.loads(request.body)
        payment_data = {
            'transaction_amount': data.get('transaction_amount'),
            'description': data.get('description'),
            'payment_method_id': data.get('payment_method_id'),
            'payer': {
                'email': data['payer'].get('email'),
                'first_name': data['payer'].get('first_name'),
                'last_name': data['payer'].get('last_name'),
                'identification': {
                    'type': data['payer']['identification'].get('type'),
                    'number': data['payer']['identification'].get('number'),
                }
            }
        }

        response = sdk.payment().create(payment_data, request_options)
        payment = response['response']
        return payment
    
    def saved_card(request):
        sdk = mercadopago.SDK(os.getenv('ACCESS_TOKEN'))
        request_options = mercadopago.config.RequestOptions()
        request_options.custom_headers = {
            'x-idempotency-key': str(uuid.uuid4())
        }
        data = json.loads(request.body)
        customer_data = {
            'email': data.get('email')
        }

        customer_response = sdk.customer().create(customer_data)
        customer = customer_response['response']

        card_data = {
            'token': data.get('token'),
            'payment_method_id': data.get('payment_method_id')
        }
        card_response = sdk.card().create(customer['id'], card_data)
        card = card_response['response']
        
        return card
    
    def create_webhook(request):
        payment_status = {}
        data = json.loads(request.body)
        payment_data = data.get('data')
        payment_id = payment_data.get('id')
        status = payment_data.get("status")
        payment_status[payment_id] = status

        result = {"payment_id": payment_id, "status": payment_status}
        print(f'[Webhook] Pagamento {payment_id} recebido')
        return result