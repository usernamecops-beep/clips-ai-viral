import os

# Pega aquí tu API Key de OpenAI (reemplaza las comillas)
OPENAI_API_KEY = "TEST-TU_API_KEY"

# Carpetas donde se guardarán los videos
CARPETA_ORIGEN = "video_origen"
CARPETA_CLIPS = "clips_virales"

# Crear las carpetas si no existen
os.makedirs(CARPETA_ORIGEN, exist_ok=True)
os.makedirs(CARPETA_CLIPS, exist_ok=True)

# config.py
MERCADOPAGO_ACCESS_TOKEN = "TEST-TU_ACCESS_TOKEN_AQUI"