import mercadopago
from config import MERCADOPAGO_ACCESS_TOKEN

# Inicializar el SDK de Mercado Pago
sdk = mercadopago.SDK(MERCADOPAGO_ACCESS_TOKEN)


def crear_preference_pago(monto_cop=35000, titulo_plan="Suscripción Premium Clips AI"):
    """
    Crea un enlace de pago configurado en pesos colombianos (COP)
    con soporte para PSE, Nequi, Daviplata y tarjetas.
    """
    preference_data = {
        "items": [
            {
                "title": titulo_plan,
                "quantity": 1,
                "unit_price": float(monto_cop),  # Ejemplo: $35.000 COP
                "currency_id": "COP"
            }
        ],
        "back_urls": {
            "success": "http://localhost:8501/?status=success",
            "failure": "http://localhost:8501/?status=failure",
            "pending": "http://localhost:8501/?status=pending"
        },
        "auto_return": "approved"
    }

    try:
        preference_response = sdk.preference().create(preference_data)
        preference = preference_response["response"]

        # En sandbox/prueba se usa sandbox_init_point, en producción init_point
        link_pago = preference.get("sandbox_init_point") or preference.get("init_point")
        return link_pago
    except Exception as e:
        print(f"Error al generar link de Mercado Pago: {e}")
        return None