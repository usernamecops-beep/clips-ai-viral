import os
import json
import uuid
import subprocess
import yt_dlp
import openai
import imageio_ffmpeg
from config import OPENAI_API_KEY, CARPETA_ORIGEN, CARPETA_CLIPS


# 1. Conversión de colores HTML Hex (#RRGGBB) a formato ASS (&H00BBGGRR)
def hex_a_ass_color(hex_str):
    """Convierte un color HTML (#RRGGBB) al formato BGR utilizado por subtítulos ASS."""
    hex_str = hex_str.lstrip('#')
    r = hex_str[0:2]
    g = hex_str[2:4]
    b = hex_str[4:6]
    return f"&H00{b}{g}{r}"


# 2. Formato de marcas de tiempo para archivos .ass
def formato_tiempo_ass(segundos):
    """Convierte segundos en formato flotante a HH:MM:SS.cs para la especificación ASS."""
    hrs = int(segundos // 3600)
    mins = int((segundos % 3600) // 60)
    secs = int(segundos % 60)
    centis = int((segundos % 1) * 100)
    return f"{hrs:01d}:{mins:02d}:{secs:02d}.{centis:02d}"


# 3. Descarga multi-usuario aislada y verificada
def descargar_directo(url_video):
    """
    Descarga el video en una carpeta con identificador único (UUID)
    para evitar conflictos cuando varios procesos se ejecutan al mismo tiempo.
    """
    id_sesion = str(uuid.uuid4())[:8]
    carpeta_sesion = os.path.join(CARPETA_ORIGEN, id_sesion)
    os.makedirs(carpeta_sesion, exist_ok=True)

    ruta_salida = os.path.join(carpeta_sesion, 'directo.mp4')

    opciones = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': ruta_salida,
        'merge_output_format': 'mp4',
        'ffmpeg_location': imageio_ffmpeg.get_ffmpeg_exe(),
        'overwrites': True,
        'concurrent_fragment_downloads': 4,
        'nocheckcertificate': True,
        'ignoreerrors': False
    }

    print(f"⏬ Descargando directo resubido (Sesión ID: {id_sesion})...")
    with yt_dlp.YoutubeDL(opciones) as ydl:
        ydl.download([url_video])

    if not os.path.exists(ruta_salida) or os.path.getsize(ruta_salida) == 0:
        raise FileNotFoundError(f"La descarga del video falló o el archivo está vacío: {ruta_salida}")

    print(f"✅ Video guardado en: {ruta_salida}")
    return ruta_salida, id_sesion


# 4. Extracción rápida de audio usando el códec AAC nativo (Solución al fallo libmp3lame / status 254)
def extraer_audio_ligero(ruta_video, ruta_audio_salida):
    """
    Extrae la pista de audio en un formato AAC liviano (.m4a)
    evitando errores de códecs MP3 faltantes en Windows y servidores Linux.
    """
    if not os.path.exists(ruta_video) or os.path.getsize(ruta_video) == 0:
        raise FileNotFoundError(f"El video de origen no existe o no se descargó correctamente: {ruta_video}")

    print("🔊 Extrayendo pista de audio ligera para la API...")
    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(), '-y',
        '-i', ruta_video,
        '-vn',                   # Sin pista de video
        '-c:a', 'aac',           # Códec AAC nativo universal (sin librerías externas)
        '-ar', '16000',          # Frecuencia optimizada para Whisper
        '-ac', '1',              # Canal mono
        '-b:a', '64k',           # Compresión liviana para subida rápida
        ruta_audio_salida
    ]
    subprocess.run(cmd, check=True)
    return ruta_audio_salida


# 5. Transcripción remota usando la API de OpenAI Whisper
def obtener_transcripcion_api_whisper(ruta_video, api_key=None):
    """
    Sube el audio comprimido .m4a a los servidores de OpenAI mediante la API oficial
    y obtiene marcas de tiempo palabra por palabra sin consumo de RAM local.
    """
    print("☁️ Enviando audio a la API remota de OpenAI Whisper...")
    key_a_usar = api_key if api_key else OPENAI_API_KEY
    client = openai.OpenAI(api_key=key_a_usar)

    directorio = os.path.dirname(ruta_video)
    ruta_audio_temp = os.path.join(directorio, "audio_temp.m4a")

    try:
        # Extraer audio rápido en formato M4A (AAC)
        extraer_audio_ligero(ruta_video, ruta_audio_temp)

        # Enviar a la API de OpenAI Whisper
        with open(ruta_audio_temp, "rb") as audio_file:
            respuesta = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["word"]
            )

        segmentos_formateados = []
        words_data = getattr(respuesta, 'words', [])

        if words_data:
            segmentos_formateados.append({
                'start': words_data[0]['start'] if isinstance(words_data[0], dict) else words_data[0].start,
                'end': words_data[-1]['end'] if isinstance(words_data[-1], dict) else words_data[-1].end,
                'text': getattr(respuesta, 'text', ''),
                'words': [
                    {
                        'word': w['word'] if isinstance(w, dict) else w.word,
                        'start': w['start'] if isinstance(w, dict) else w.start,
                        'end': w['end'] if isinstance(w, dict) else w.end
                    } for w in words_data
                ]
            })
        else:
            segments_data = getattr(respuesta, 'segments', [])
            for seg in segments_data:
                seg_dict = seg if isinstance(seg, dict) else seg.model_dump()
                segmentos_formateados.append(seg_dict)

        print("✅ Transcripción en la nube completada con éxito.")
        return segmentos_formateados

    finally:
        if os.path.exists(ruta_audio_temp):
            os.remove(ruta_audio_temp)


# 6. Selección de momentos clave con la IA de OpenAI
def seleccionar_highlights(segmentos_transcripcion, cantidad_clips=5, duracion_clip=15, api_key=None):
    """Filtra la transcripción usando GPT-4o-mini para elegir los momentos virales en JSON."""
    print(f"🤖 Seleccionando los mejores {cantidad_clips} momentos con la IA de OpenAI...")

    key_a_usar = api_key if api_key else OPENAI_API_KEY
    client = openai.OpenAI(api_key=key_a_usar)

    texto_resumido = ""
    for seg in segmentos_transcripcion[:200]:
        texto_resumido += f"[{int(seg['start'])}s - {int(seg['end'])}s]: {seg['text']}\n"

    prompt = f"""
    Eres un editor experto en contenido viral para TikTok, Shorts y Reels.
    Revisa la siguiente transcripción y selecciona EXACTAMENTE los mejores {cantidad_clips} momentos virales.
    Cada momento debe tener una duración recomendada cercana a {duracion_clip} segundos.

    Responde ÚNICAMENTE en formato JSON válido con este esquema exacto:
    [
      {{"inicio": 15, "fin": {15 + duracion_clip}, "titulo": "Momento insólito"}},
      ...
    ]

    Transcripción:
    {texto_resumido}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    contenido = response.choices[0].message.content.strip()

    if contenido.startswith("```json"):
        contenido = contenido[7:-3].strip()
    elif contenido.startswith("
