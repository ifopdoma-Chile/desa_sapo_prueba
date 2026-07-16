#app/routes.py

from flask import flash, Blueprint, current_app, request, jsonify, session,redirect, url_for, get_flashed_messages,abort,Response,render_template
import folium
import os
from dask.distributed import Client
from datetime import datetime, timedelta
import logging
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import io
from flask import render_template
from app.db import get_db_connection
from app.db import SMTP_CONFIG, _validate_smtp_config
from folium.plugins import SideBySideLayers, GroupedLayerControl, MousePosition, AntPath,TimestampedWmsTileLayers

logging.basicConfig(level=logging.INFO)  # Nivel de logs (INFO, DEBUG, ERROR)
logger = logging.getLogger(__name__)  # Configura el logger
# Configuración opcional del cliente Dask, para manejar tareas distribuidas
client = Client()  # También puedes usar opciones avanzadas si lo necesitas
main = Blueprint('main', __name__)
#base_url = "http://gis-eco.ifop.cl/ncWMS2/wms"
# Configuración de la conexión a la base de datos PostGIS
#TOKEN = DOMA_IFOP_777


# Obtener la fecha actual
fecha_actual = datetime.now()
fecha_menos = fecha_actual - timedelta(days=1)
fecha_m_f = fecha_menos.strftime('%Y%m%d')
#center = [-35.0, -110.0]  # Cambia por la latitud/longitud deseada
#zoom = 4 # Nivel de zoom inicial
maxzoom = 12
minzoom = 3

@main.before_app_request
def _init_map_session_defaults():
    # Inicializa center/zoom una sola vez por sesión
    if 'center' not in session:
        session['center'] = [-27.87, -105.55]
    if 'zoom' not in session:
        session['zoom'] = 4

# Define un formato para los valores de latitud y longitud
def custom_formatter(**kwargs):
    lat = kwargs.get("latitude", 0.0)  # Obtiene el valor de la latitud
    lng = kwargs.get("longitude", 0.0)  # Obtiene el valor de la longitud
    return f"Lat: {lat:.5f}, Lng: {lng:.5f}"  # Formato personalizado


@main.route('/enviar_datos', methods=['POST'])
def enviar_datos():
    try:
        datos = request.json
        nombre = datos.get('nombre_usuario')
        email = datos.get('email')
        codigo_estacion = datos.get('codigo_estacion')
        info_estacion = datos.get('info_estacion')

        if not all([nombre, email, codigo_estacion, info_estacion]):
            return jsonify({'success': False, 'message': 'Faltan datos requeridos'})

        try:
            #conn = psycopg2.connect(**DATABASE_CONFIG)
            conn = get_db_connection()
            cursor = conn.cursor()
            fecha_hora = datetime.now()

            # Registrar la consulta en la base de datos
            sql = """
                  INSERT INTO doma_consultas_estaciones
                      (fecha_hora, codigo_estacion, nombre_consultante, email_consultante)
                  VALUES (%s, %s, %s, %s)
                  """
            cursor.execute(sql, (fecha_hora, codigo_estacion, nombre, email))
            conn.commit()

            # Obtener datos históricos completos para el CSV
            variables = ['Temperatura', 'Presión', 'Humedad', 'Velocidad del Viento']
            dfs = []

            for variable in variables:
                query = """
                        SELECT hora, valor
                        FROM public.estaciones_valores(%s)
                        WHERE nombre = %s
                        ORDER BY hora;
                        """
                cursor.execute(query, (codigo_estacion, variable))
                resultados = cursor.fetchall()

                df = pd.DataFrame({
                    'Fecha': [row[0] for row in resultados],
                    'Variable': variable,
                    'Valor': [float(row[1]) if row[1] is not None else None for row in resultados],
                    'Nombre_Estacion': info_estacion['nombre'],
                    'Region': info_estacion['detalle'],
                    'Coordenadas': info_estacion['coordenadas'],
                    'Tipo_Estacion': info_estacion['tipo']
                })
                dfs.append(df)

            cursor.close()
            conn.close()

            df_final = pd.concat(dfs)
            columnas = ['Nombre_Estacion', 'Region', 'Coordenadas',
                        'Tipo_Estacion', 'Fecha', 'Variable', 'Valor']
            df_final = df_final[columnas]

            # Convertir a CSV
            csv_buffer = io.StringIO()
            df_final.to_csv(csv_buffer, index=False)
            csv_content = csv_buffer.getvalue()

            # Validar configuración SMTP antes de usarla
            _validate_smtp_config()

            # Crear mensaje de correo
            msg = MIMEMultipart()
            msg['From'] = SMTP_CONFIG['REMITENTE']
            msg['To'] = email
            msg['Subject'] = f'Datos Históricos - Estación {info_estacion["nombre"]} - SAPO'

            body = f"""Estimado/a {nombre},

            Adjunto encontrará los datos históricos completos de la estación meteorológica:
            
            Nombre: {info_estacion['nombre']}
            Región: {info_estacion['detalle']}
            Coordenadas: {info_estacion['coordenadas']}
            Tipo: {info_estacion['tipo']}
            
            Saludos cordiales,
            Equipo SAPO"""

            msg.attach(MIMEText(body, 'plain'))

            # Adjuntar CSV
            attachment = MIMEApplication(csv_content.encode('utf-8'))
            attachment[
                'Content-Disposition'] = f'attachment; filename="datos_historicos_estacion_{codigo_estacion}.csv"'
            msg.attach(attachment)

            # Enviar correo
            with smtplib.SMTP_SSL(SMTP_CONFIG['SMTP_SERVER'], SMTP_CONFIG['SMTP_PORT']) as server:
                server.login(SMTP_CONFIG['SMTP_USERNAME'], SMTP_CONFIG['SMTP_PASSWORD'])
                server.send_message(msg)

            return jsonify({'success': True, 'message': 'Datos históricos enviados exitosamente'})

        except Exception as db_error:
            print(f"Error en base de datos: {str(db_error)}")
            return jsonify({'success': False, 'message': f'Error en base de datos: {str(db_error)}'})

    except Exception as e:
        print(f"Error general: {str(e)}")
        return jsonify({'success': False, 'message': f'Error al procesar la solicitud: {str(e)}'})

@main.route('/enviar_datos2', methods=['POST'])
def enviar_datos2():
    try:
        # Obtener datos del cliente
        datos = request.json
        nombre = datos.get('nombre_usuario')
        email = datos.get('email')
        codigo_estacion = datos.get('codigo_estacion')
        info_estacion = datos.get('info_estacion')  # Debe incluir nombre, región, coordenadas

        if not all([nombre, email, codigo_estacion, info_estacion]):
            return jsonify({'success': False, 'message': 'Faltan datos requeridos'})

        try:
            # Conexión a la base de datos
            conn = get_db_connection()
            cursor = conn.cursor()
            fecha_hora = datetime.now()

            # Registrar la consulta en la base de datos
            sql = """
                  INSERT INTO doma_consultas_estaciones
                      (fecha_hora, codigo_estacion, nombre_consultante, email_consultante)
                  VALUES (%s, %s, %s, %s)
                  """
            cursor.execute(sql, (fecha_hora, codigo_estacion, nombre, email))
            conn.commit()

            # Extraer datos de la estación para generar el CSV
            query = """
                    SELECT *
                    FROM v_datos_estacion
                    WHERE codigo_estacion = %s AND fecha_año > 2013
                    """
            cursor.execute(query, (codigo_estacion,))
            resultados = cursor.fetchall()

            if not resultados:
                return jsonify({'success': False, 'message': 'No se encontraron datos para esta estación'})

            # Crear un DataFrame a partir de la consulta
            columnas = [desc[0] for desc in cursor.description]  # Obtener nombres de las columnas
            df = pd.DataFrame(resultados, columns=columnas)

            # Agregar metadatos al DataFrame
            df['Nombre_Estacion'] = info_estacion['nombre']
            df['Region'] = info_estacion['region']
            df['Coordenadas'] = info_estacion['coordenadas']

            # Ordenar columnas para el CSV
            columnas_ordenadas = ['Nombre_Estacion', 'Region', 'Coordenadas'] + columnas
            df = df[columnas_ordenadas]

            # Convertir el DataFrame a CSV y almacenar en memoria
            csv_buffer = io.StringIO()
            df.to_csv(csv_buffer, index=False)
            csv_content = csv_buffer.getvalue()

            # Validar configuración SMTP antes de usarla
            _validate_smtp_config()

            # Crear el correo con el archivo adjunto
            msg = MIMEMultipart()
            msg['From'] = SMTP_CONFIG['REMITENTE']
            msg['To'] = email
            msg['Subject'] = f'Datos Estación {info_estacion["nombre"]} - DOMA'

            # Cuerpo del correo
            body = f"""Estimado/a {nombre},

            Adjuntamos los datos solicitados para la estación:

            Nombre: {info_estacion['nombre']}
            Región: {info_estacion['region']}
            Coordenadas: {info_estacion['coordenadas']}

            Saludos cordiales,
            Equipo DOMA
            """
            msg.attach(MIMEText(body, 'plain'))

            # Adjuntar el CSV
            attachment = MIMEApplication(csv_content.encode('utf-8'))
            attachment[
                'Content-Disposition'] = f'attachment; filename="datos_estacion_{codigo_estacion}.csv"'
            msg.attach(attachment)

            # Enviar el correo
            with smtplib.SMTP_SSL(SMTP_CONFIG['SMTP_SERVER'], SMTP_CONFIG['SMTP_PORT']) as server:
                server.login(SMTP_CONFIG['SMTP_USERNAME'], SMTP_CONFIG['SMTP_PASSWORD'])
                server.send_message(msg)

            return jsonify({'success': True, 'message': 'Datos enviados exitosamente al correo'})

        except Exception as db_error:
            print(f"Error en base de datos: {str(db_error)}")
            return jsonify({'success': False, 'message': f'Error en base de datos: {str(db_error)}'})

    except Exception as e:
        print(f"Error general: {str(e)}")
        return jsonify({'success': False, 'message': f'Error al procesar la solicitud: {str(e)}'})

@main.route('/actualizar_mapa', methods=['POST'])
def actualizar_mapa():
    # Obtén la información enviada desde el cliente para el posicionamiento del mapa entre opciones
    data = request.json

    # Extrae las coordenadas y zoom del JSON enviado por el cliente
    center = data.get('center', [-27.87, -105.55])
    zoom = data.get('zoom', 4)

    # Guarda las coordenadas y el zoom en la sesión (clave global)
    session['center'] = center
    session['zoom'] = zoom
    # Agrega un mensaje flash y reenvíalo en la misma respuesta para mostrarlo sin recargar
    flash(f'Vista actualizada. Centro: [{center[0]:.5f}, {center[1]:.5f}] | Zoom: {zoom}', 'info')
    messages = get_flashed_messages(with_categories=True)

    # Devuelve confirmación
    return jsonify({'status': 'success', 'center': center, 'zoom': zoom, 'messages': messages})

@main.route('/comparar')
def comparar():
    try:
        # Variables básicas
        center = session.get('center', [-27.87, -105.55])
        zoom = session.get('zoom', 4)

        # Crear el mapa base
        m = folium.Map(
            location=center,
            zoom_start=zoom,
            tiles=None,
            minZoom=minzoom,
            maxZoom=maxzoom,
            zoomDelta=0.15,  # cada click + / - cambia 0.25 en vez de 1
            zoomSnap=0.15,
            wheelPxPerZoomLevel=250,
        )
        # Añadir mosaico base al mapa
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',
            name='Esri WorldStreetMap',
            control=False  # Fuera del control de capas
        ).add_to(m)

        # Crear las capas WMS
        # Capa 1: ATSM
        wms_atsm = folium.WmsTileLayer(
            url='https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?',
            layers='Ifop_Sapo:Anomalia_temperatura',
            fmt='image/png',
            transparent=True,
            version='1.1.0',
            name='Anomalía de Temperatura',
            overlay=True,
            control=True,
            opacity=1.0
        )
        wms_atsm.add_to(m)
        wms_clorofila = folium.WmsTileLayer(
            url='https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?',
            layers='Ifop_Sapo:Anomalia_temperatura',
            fmt='image/png',
            transparent=True,
            version='1.1.0',
            name='Anomalía de Temperatura',
            overlay=True,
            control=True,
            opacity=1.0
        )
        wms_clorofila.add_to(m)

        # Añadir capas y Side by Side Layers al mapa

        sbs = SideBySideLayers(layer_left=wms_clorofila, layer_right=wms_atsm)
        sbs.add_to(m)

        # Guardar el mapa como un archivo HTML
        temp_map_path = os.path.join(current_app.root_path, 'static', 'map_side.html')
        m.save(temp_map_path)  # Guarda el mapa dinámicamente

        # Leer el contenido del archivo HTML generado por Folium
        with open(temp_map_path, 'r') as f:
            mapa_html = f.read()

        # Limpiar librerías redundantes instaladas por Folium (si es necesario)
        mapa_html = mapa_html.replace(
            '<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.js"></script>', '')
        mapa_html = mapa_html.replace(
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.css"/>', '')

        mapa_html += """
           <script>
               if (!L.Mixin) {
                   L.Mixin = {};
               }
               L.Mixin.Events = L.Evented.prototype;
           </script>
           """

        # Retornar el template con el HTML renderizado
        return render_template('comparar2.html', mapa_html=mapa_html)

    except Exception as e:
        # Capturar excepciones y devolver un mensaje claro
        return f"Error en la ruta 'comparar': {str(e)}", 500

@main.route('/actualizar_capa', methods=['POST'])
def actualizar_capa():
    try:
        # Recibimos la selección desde el frontend
        data = request.get_json()
        left_layer_name = data.get('left', 'Anomalia_temperatura')
        right_layer_name = data.get('right', 'Temperatura')

        # Base URL común del servicio WMS
        base_url = 'https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?'

        # Formar URLs para las capas dinámica y correctamente
        left_layer_url = {
            "url": base_url,
            "layer": f"Ifop_Sapo:{left_layer_name}",
            "fmt": "image/png",
            "transparent": True,
            "version": "1.1.0"
        }

        right_layer_url = {
            "url": base_url,
            "layer": f"Ifop_Sapo:{right_layer_name}",
            "fmt": "image/png",
            "transparent": True,
            "version": "1.1.0"
        }

        # Pasar recursos específicos al frontend
        return jsonify({
            "left_layer_url": left_layer_url,
            "right_layer_url": right_layer_url
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

from app import routes_tsm_atsm_clo     # noqa: F401
from app import routes_exp              # noqa: F401
from app import routes_est_ocean        # noqa: F401
from app import routes_est_met          # noqa: F401
from app import routes_buques           # noqa: F401
from app import routes_viento_corrientes# noqa: F401
from app import routes_todos            # noqa: F401
from app import routes_todos_v2         # noqa: F401
from app import copia_ssh               # noqa: F401
from app import shortener               # noqa: F401
from app import routes_olas
from app import atsm_10d               # noqa: F401