import os
import time
import streamlit as st
from config import CARPETA_CLIPS, OPENAI_API_KEY
from procesador import (
    descargar_directo,
    obtener_transcripcion_api_whisper,
    seleccionar_highlights,
    exportar_clip,
    hex_a_ass_color
)
from pagos_mp import crear_preference_pago

# Configuración de Streamlit
st.set_page_config(
    page_title="Creador de Clips Virales AI",
    page_icon="🎬",
    layout="wide"
)

# 1. Detectar si el usuario regresa de un pago exitoso en Mercado Pago
query_params = st.query_params
if query_params.get("status") == "success":
    st.session_state['es_premium'] = True

# Control de estado de la sesión
if 'es_premium' not in st.session_state:
    st.session_state['es_premium'] = False
if 'anuncio_visto' not in st.session_state:
    st.session_state['anuncio_visto'] = False

st.title("🎬 Creador de Highlights Virales con IA")
st.caption("Pega el enlace de un directo resubido para cortar, subtitular y descargar automáticamente los mejores momentos.")

st.divider()

# 🎛️ BARRA LATERAL: Suscripción, Ajustes de Recorte y Subtítulos
with st.sidebar:
    st.header("⚙️ Configuración")
    api_key_input = st.text_input("OpenAI API Key", value=OPENAI_API_KEY, type="password")

    st.divider()
    st.header("💎 Plan de Usuario")

    if st.session_state['es_premium']:
        st.success("⭐ Estado: Membresía Premium VIP Activa")
    else:
        st.info("ℹ️️ Plan Gratuito: Hasta 5 clips estándar.")
        
        # Botón de Pago con Mercado Pago
        if st.button("💳 Suscribirse VIP ($35.000 COP/mes)", type="primary"):
            url_pago = crear_preference_pago(monto_cop=35000, titulo_plan="Suscripción Clips AI VIP")
            if url_pago:
                st.link_button("👉 Pagar con PSE / Nequi / Tarjeta", url_pago)
            else:
                st.error("No se pudo conectar con Mercado Pago. Verifica tu Access Token.")

    # Toggle manual para pruebas en desarrollo
    st.session_state['es_premium'] = st.toggle("Modo Prueba VIP (Simulación)", value=st.session_state['es_premium'])

    st.divider()
    st.header("✂️ Parámetros del Recorte")

    # Duración de recorte de 10 a 30 segundos
    duracion_recorte = st.slider(
        "Duración de cada clip (segundos):",
        min_value=10,
        max_value=30,
        value=15,
        step=1
    )

    # Cantidad de clips según el Plan
    if st.session_state['es_premium']:
        cantidad_clips = st.slider("Cantidad de clips a generar:", min_value=5, max_value=15, value=10)
    else:
        max_gratuitos = 8 if st.session_state['anuncio_visto'] else 5
        cantidad_clips = st.number_input("Cantidad de clips:", min_value=1, max_value=max_gratuitos, value=5, disabled=True)

        if not st.session_state['anuncio_visto']:
            st.warning("📺 ¿Quieres 3 clips extra gratis?")
            if st.button("Ver Video Publicitario (5s)"):
                with st.spinner("Reproduciendo anuncio..."):
                    time.sleep(5)
                st.session_state['anuncio_visto'] = True
                st.success("¡Anuncio completado! Ahora puedes generar hasta 8 clips.")
                st.rerun()

    st.divider()
    st.header("🎨 Configuración de Subtítulos")

    usar_subtitulos = st.checkbox("Incrustar subtítulos automáticos", value=True)

    if usar_subtitulos:
        color_texto_hex = st.color_picker("Color del texto", "#FFFF00")
        color_borde_hex = st.color_picker("Color del borde", "#000000")
        tamanio_fuente = st.slider("Tamaño del texto", min_value=40, max_value=120, value=80, step=5)

        posicion_opcion = st.radio(
            "Posición del subtítulo",
            options=["Centro (Recomendado)", "Parte Inferior", "Parte Superior"],
            index=0
        )

        mapa_alineacion_ass = {
            "Centro (Recomendado)": 5,
            "Parte Inferior": 2,
            "Parte Superior": 8
        }
        alineacion_ass = mapa_alineacion_ass[posicion_opcion]

        # Vista previa en CSS
        st.subheader("👁️ Vista Previa del Subtítulo")
        mapa_flex = {"Parte Superior": "flex-start", "Centro (Recomendado)": "center", "Parte Inferior": "flex-end"}
        st.markdown(
            f"""
            <div style="
                width: 100%; height: 180px; background-color: #121212; border-radius: 10px;
                border: 2px solid #333; display: flex; justify-content: center; align-items: {mapa_flex[posicion_opcion]};
                padding: 10px; box-sizing: border-box;
            ">
                <span style="
                    color: {color_texto_hex}; font-family: 'Impact', sans-serif; font-size: {tamanio_fuente // 2}px;
                    text-transform: uppercase; font-weight: bold; text-align: center;
                    text-shadow: -2px -2px 0 {color_borde_hex}, 2px -2px 0 {color_borde_hex}, -2px 2px 0 {color_borde_hex}, 2px 2px 0 {color_borde_hex};
                ">
                    MOMENTO VIRAL
                </span>
            </div>
            """,
            unsafe_allow_html=True
        )

# 🚀 ÁREA PRINCIPAL
col_url, col_btn = st.columns([3, 1])

with col_url:
    url_directo = st.text_input("URL del directo de YouTube:", placeholder="https://www.youtube.com/watch?v=...")

with col_btn:
    st.write("##")
    btn_procesar = st.button("🚀 Generar Clips", type="primary", use_container_width=True)

# LÓGICA DE PROCESAMIENTO
if btn_procesar:
    if not url_directo:
        st.warning("⚠️ Por favor ingresa una URL válida de YouTube.")
    elif not api_key_input:
        st.error("❌ Se requiere una API Key de OpenAI para continuar.")
    else:
        st.info("⌛ Procesando el directo resubido...")
        barra_progreso = st.progress(0, text="Descargando video...")

        try:
            # 1. Descarga aislada por UUID
            ruta_video, id_sesion = descargar_directo(url_directo)
            barra_progreso.progress(25, text="Transcribiendo audio mediante la API de Whisper...")

            # 2. Transcripción API
            segmentos = obtener_transcripcion_api_whisper(ruta_video, api_key=api_key_input)
            barra_progreso.progress(50, text=f"Seleccionando {cantidad_clips} momentos virales con la IA...")

            # 3. Selección de momentos clave
            highlights = seleccionar_highlights(
                segmentos_transcripcion=segmentos,
                cantidad_clips=cantidad_clips,
                duracion_clip=duracion_recorte,
                api_key=api_key_input
            )
            barra_progreso.progress(75, text=f"Renderizando {len(highlights)} clips de {duracion_recorte}s...")

            # Conversión de colores
            color_texto_ass = hex_a_ass_color(color_texto_hex) if usar_subtitulos else "&H0000FFFF"
            color_borde_ass = hex_a_ass_color(color_borde_hex) if usar_subtitulos else "&H00000000"

            # 4. Renderizado de clips
            clips_resultados = []
            for i, clip in enumerate(highlights, 1):
                ruta_clip = exportar_clip(
                    ruta_video_input=ruta_video,
                    inicio_sec=clip['inicio'],
                    duracion_sec=duracion_recorte,
                    numero_clip=i,
                    segmentos=segmentos,
                    id_sesion=id_sesion,
                    incluir_subtitulos=usar_subtitulos,
                    color_texto=color_texto_ass,
                    color_borde=color_borde_ass,
                    tamanio_fuente=tamanio_fuente if usar_subtitulos else 80,
                    alineacion=alineacion_ass if usar_subtitulos else 5
                )
                clips_resultados.append({
                    "ruta": ruta_clip,
                    "titulo": clip.get("titulo", f"Clip #{i}")
                })

            barra_progreso.progress(100, text="¡Completado!")
            st.success(f"🎉 ¡Se han exportado {len(clips_resultados)} clips de {duracion_recorte} segundos!")

            st.session_state['clips_generados'] = clips_resultados

        except Exception as e:
            st.error(f"Ocurrió un error durante el procesamiento: {e}")

st.divider()

# RESULTADOS EN PANTALLA
if 'clips_generados' in st.session_state and st.session_state['clips_generados']:
    st.subheader("📹 Highlights Listos para Descargar")

    clips = st.session_state['clips_generados']

    num_columnas = min(3, len(clips))
    columnas = st.columns(num_columnas)

    for idx, c_info in enumerate(clips):
        col_actual = columnas[idx % num_columnas]
        with col_actual:
            st.markdown(f"**{c_info['titulo']}**")

            if os.path.exists(c_info['ruta']):
                st.video(c_info['ruta'])

                with open(c_info['ruta'], "rb") as file_data:
                    st.download_button(
                        label=f"⬇️ Descargar Clip #{idx + 1}",
                        data=file_data,
                        file_name=os.path.basename(c_info['ruta']),
                        mime="video/mp4",
                        key=f"dl_btn_{idx}"
                    )
