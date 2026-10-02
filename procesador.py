import os
import json
import uuid
import subprocess
import yt_dlp
import openai
import imageio_ffmpeg
from config import OPENAI_API_KEY, CARPETA_ORIGEN, CARPETA_CLIPS


def hex_a_ass_color(hex_str):
    """Convierte un color HTML (#RRGGBB) al formato BGR utilizado por subtítulos ASS."""
    hex_str = hex_str.lstrip('#')
    r = hex_str[0:2]
    g = hex_str[2:4]
    b = hex_str[4:6]
    return f"&H00{b}{g}{r}"


def formato_tiempo_ass(segundos):
    """Convierte segundos en formato flotante a HH:MM:SS.cs para la especificación ASS."""
    hrs = int(segundos // 3600)
    mins = int((segundos % 3600) // 60)
    secs = int(segundos % 60)
    centis = int((segundos % 1) * 100)
    return f"{hrs:01d}:{mins:02d}:{secs:02d}.{centis:02d}"


def descargar_directo(url_video):
    """Descarga el video en una carpeta única por sesión (UUID)."""
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


def extraer_audio_ligero(ruta_video, ruta_audio_salida):
    """Extrae la pista de audio en un formato AAC liviano (.m4a)."""
    if not os.path.exists(ruta_video) or os.path.getsize(ruta_video) == 0:
        raise FileNotFoundError(f"El video de origen no existe: {ruta_video}")

    print("🔊 Extrayendo pista de audio ligera para la API...")
    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(), '-y',
        '-i', ruta_video,
        '-vn',
        '-c:a', 'aac',
        '-ar', '16000',
        '-ac', '1',
        '-b:a', '64k',
        ruta_audio_salida
    ]
    subprocess.run(cmd, check=True)
    return ruta_audio_salida


def obtener_transcripcion_api_whisper(ruta_video, api_key=None):
    """Sube el audio comprimido a la API de OpenAI Whisper."""
    print("☁️ Enviando audio a la API remota de OpenAI Whisper...")
    key_a_usar = api_key if api_key else OPENAI_API_KEY
    client = openai.OpenAI(api_key=key_a_usar)

    directorio = os.path.dirname(ruta_video)
    ruta_audio_temp = os.path.join(directorio, "audio_temp.m4a")

    try:
        extraer_audio_ligero(ruta_video, ruta_audio_temp)

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


def seleccionar_highlights(segmentos_transcripcion, cantidad_clips=5, duracion_clip=15, api_key=None):
    """Filtra la transcripción usando GPT-4o-mini."""
    print(f"🤖 Seleccionando los mejores {cantidad_clips} momentos con la IA...")
    
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
      {{"inicio": 15, "fin": {15 + duracion_clip}, "titulo": "Momento insólito"}}
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
    elif contenido.startswith("```"):
        contenido = contenido[3:-3].strip()

    return json.loads(contenido)


def generar_subtitulos_personalizados(segmentos_clip, inicio_clip, fin_clip, ruta_ass_salida,
                                      color_texto_ass="&H0000FFFF",
                                      color_borde_ass="&H00000000",
                                      tamanio_fuente=80,
                                      alineacion=5):
    """Genera archivo de subtítulos .ass personalizables."""
    cabecera = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Hormozi,Impact,{tamanio_fuente},{color_texto_ass},&H00000000,{color_borde_ass},&H80000000,1,0,0,0,100,100,0,0,1,6,0,{alineacion},50,50,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []

    for seg in segmentos_clip:
        if 'words' in seg:
            for word_info in seg['words']:
                w_start = word_info['start']
                w_end = word_info['end']
                texto = word_info['word'].strip().upper()

                if w_start >= inicio_clip and w_end <= fin_clip:
                    rel_start = w_start - inicio_clip
                    rel_end = w_end - inicio_clip

                    t_ini = formato_tiempo_ass(rel_start)
                    t_fin = formato_tiempo_ass(rel_end)

                    events.append(f"Dialogue: 0,{t_ini},{t_fin},Hormozi,,0,0,0,,{texto}")

    with open(ruta_ass_salida, 'w', encoding='utf-8') as f:
        f.write(cabecera + "\n".join(events))


def exportar_clip(ruta_video_input, inicio_sec, duracion_sec, numero_clip, segmentos, id_sesion,
                  incluir_subtitulos=True, color_texto="&H0000FFFF", color_borde="&H00000000",
                  tamanio_fuente=80, alineacion=5):
    """Exporta el clip vertical 9:16 con o sin subtítulos."""
    fin_sec = inicio_sec + duracion_sec
    carpeta_clips_sesion = os.path.join(CARPETA_CLIPS, id_sesion)
    os.makedirs(carpeta_clips_sesion, exist_ok=True)

    nombre_archivo = f"clip_{numero_clip}_viral.mp4"
    ruta_final = os.path.join(carpeta_clips_sesion, nombre_archivo)

    filtro_video = "crop=ih*(9/16):ih,scale=1080:1920"
    ruta_ass = None

    if incluir_subtitulos:
        ruta_ass = os.path.join(carpeta_clips_sesion, f"sub_{numero_clip}_{uuid.uuid4().hex[:4]}.ass")
        generar_subtitulos_personalizados(
            segmentos_clip=segmentos,
            inicio_clip=inicio_sec,
            fin_clip=fin_sec,
            ruta_ass_salida=ruta_ass,
            color_texto_ass=color_texto,
            color_borde_ass=color_borde,
            tamanio_fuente=tamanio_fuente,
            alineacion=alineacion
        )
        ruta_ass_ffmpeg = ruta_ass.replace('\\', '/').replace(':', '\\:')
        filtro_video += f",subtitles='{ruta_ass_ffmpeg}'"

    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(), '-y',
        '-threads', '0',
        '-ss', str(inicio_sec),
        '-i', ruta_video_input,
        '-t', str(duracion_sec),
        '-vf', filtro_video,
        '-c:v', 'libx264',
        '-crf', '18',
        '-preset', 'ultrafast',
        '-c:a', 'aac',
        ruta_final
    ]

    subprocess.run(cmd, check=True)

    if ruta_ass and os.path.exists(ruta_ass):
        os.remove(ruta_ass)

    print(f"🎬 Clip #{numero_clip} exportado con éxito a: {ruta_final}")
    return ruta_final
