from rest_framework import serializers

class IdentificationSerializer(serializers.Serializer):
    type = serializers.CharField(required=False, allow_null=True)
    number = serializers.IntegerField(required=False, allow_null=True)
    identificationType = serializers.CharField(required=False, allow_null=True)
    identificationNumber = serializers.IntegerField(required=False, allow_null=True)

    def validate_number(self, value):
        if len(str(value)) < 3:
            raise serializers.ValidationError("O número de identificação informado é inválido.")
        return value

class PayerSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    identification = IdentificationSerializer()

    def validate_email(self, value):
        if len(value) < 5:
            raise serializers.ValidationError("O email informado é inválido.")
        return value

class CardSerializer(serializers.Serializer):
    transaction_amount = serializers.FloatField(required=True)
    token = serializers.CharField(required=True)
    description = serializers.CharField()
    installments = serializers.IntegerField(required=False, allow_null=True)
    payment_method_id = serializers.CharField(required=True)
    issuer_id = serializers.IntegerField(required=True)
    payer = PayerSerializer()

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("O valor de transferência deve ser maior do que zero.")
        return value
    
    def validate_token(self, value):
        if not value:
            raise serializers.ValidationError("O token é inexistente.")
        return value

    def validate_method(self, value):
        if int(value) < 1:
            raise serializers.ValidationError("O método de pagamento não foi informado corretamente.")
        return value
    
class PixSerializer(serializers.Serializer):
    transaction_amount = serializers.FloatField(required=True)
    description = serializers.CharField()
    payment_method_id = serializers.CharField(required=True)
    payer = PayerSerializer()

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("O valor de transferência deve ser maior do que zero.")
        return value