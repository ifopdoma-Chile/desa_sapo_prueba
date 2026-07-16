from flask import Blueprint, render_template, session, current_app, request, jsonify
import folium
from folium.plugins import SideBySideLayers, GroupedLayerControl, MousePosition, AntPath,TimestampedWmsTileLayers
import geopandas as gpd
import pandas as pd
import os
import psycopg2
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from app.routes import main
from app.db import get_db_connection
from app.copia_ssh import actualizar_geoserver_historico

maxzoom = 12
minzoom = 3

@main.route('/todos_v2')
def todos_v2():
    try:
        # Crear el mapa base
        center = session.get('center', [-27.87, -105.55])
        zoom = session.get('zoom', 8)
        selected_date_str = session.get("selected_date")
        m = folium.Map(
            location=center,
            zoom_start=zoom,
            tiles=None,  # 'Esri WorldStreetMap',
            minZoom=minzoom,
            maxZoom=maxzoom,
            zoomDelta=0.15,  # cada click + / - cambia 0.25 en vez de 1
            zoomSnap=0.15,
            wheelPxPerZoomLevel=250,
        )
        # Añadir el plugin MousePosition al mapa
        formatter = "function(lat, lng) {return `Lat: ${lat.toFixed(5)}, Lng: ${lng.toFixed(5)}`;}"

        mouse_position = MousePosition(
            position="bottomleft",  # Posición donde se mostrará (arriba a la derecha)
            separator=" | ",
            empty_string="",
            lng_first=False,
            num_digits=5,  # Número de decimales para mostrar
            prefix="Coordenadas:",  # Prefijo del texto
            lat_formatter=None,
            lng_formatter=None,
            formatter=formatter  # Mostrar las posiciones como se definió anteriormente
        )
        mouse_position.add_to(m)
        #folium.plugins.Geocoder().add_to(m)
        folium.plugins.MeasureControl(position='topleft',
                primary_length_unit='kilometers',
                secondary_length_unit='meters',
                primary_area_unit='sqkilometers',
                secondary_area_unit='sqmeters').add_to(m)

        # Añadir el mosaico base directamente, pero fuera del control de capas
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',  # (Opcional) texto en la esquina inferior
            name='Esri WorldStreetMap',  # El nombre que aparece en el mapa, pero no en LayerControl
            control=False  # No incluir en el control de capas
        ).add_to(m)
        folium.plugins.LocateControl().add_to(m)

        wms_url = 'https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?service=WMS&request=GetCapabilities'
        response = requests.get(wms_url)
        response.raise_for_status()  # Verifica que no haya errores HTTP

        # Parsear el XML con el manejo del namespace
        root = ET.fromstring(response.content)

        # Declarar el espacio de nombres basado en el WMS
        namespaces = {'wms': 'http://www.opengis.net/wms'}

        # Helpers: detectar capa y extraer time
        def _layer_node_by_name(layer_name: str):
            for lyr in root.findall(".//wms:Layer", namespaces):
                name_element = lyr.find("wms:Name", namespaces)
                if name_element is not None and name_element.text == layer_name:
                    return lyr
            return None

        def _layer_time_text(layer_name: str):
            lyr = _layer_node_by_name(layer_name)
            if lyr is None:
                return None
            dimension = lyr.find("wms:Dimension", namespaces)
            if dimension is None:
                return None
            if dimension.attrib.get("name") != "time":
                return None
            txt = (dimension.text or "").strip()
            return txt or None

        def _parse_time_to_labels(time_text: str):
            # time_text esperado: "2025-05-30T09:00:00.000Z"
            parsed = datetime.strptime(time_text, "%Y-%m-%dT%H:%M:%S.%fZ")
            return parsed.strftime("%d/%m/%Y"), parsed.strftime("%Y-%m-%d")

        date_iso = None  # <- SIEMPRE definido; se llenará con la primera capa existente
        #selected_date_str = ""  # se setea más abajo con date_iso si existe

        # Config de capas (solo se agregan si existen en capabilities)
        capas = [
            {
                "layer_name": "Anomalia_temperatura_temp",
                "title_prefix": "Anomalía de Temperatura",
                "wms_layer": "Ifop_Sapo:Anomalia_temperatura_temp",
                "isoline_name": "Isolíneas de ATSM",
                "isoline_style": "2_isolineas_atsm",
            },
            {
                "layer_name": "Temperatura_temp",
                "title_prefix": "Temperatura",
                "wms_layer": "Ifop_Sapo:Temperatura_temp",
                "isoline_name": "Isolíneas de TSM",
                "isoline_style": "1_isolineas_tsm",
            },
            {
                "layer_name": "Clorofila_temp",
                "title_prefix": "Clorofila",
                "wms_layer": "Ifop_Sapo:Clorofila_temp",
                "isoline_name": "Isolíneas de Clorofila",
                "isoline_style": "3_isolineas_clo",
            },
        ]

        for cfg in capas:
            # time_text = _layer_time_text(cfg["layer_name"])
            # if time_text is None:
            #     # No existe la capa (o no tiene time) => no la cargamos
            #     continue
            #
            # try:
            #     date_hum, date_iso_candidate = _parse_time_to_labels(time_text)
            # except ValueError:
            #     date_hum, date_iso_candidate = "Desconocida", None

            # if date_iso is None and date_iso_candidate:
            #     date_iso = date_iso_candidate

            # layer_title = f'{cfg["title_prefix"]} ({date_hum})'
            if selected_date_str:
                date_hum = datetime.strptime(selected_date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
                layer_title = f'{cfg["title_prefix"]} ({date_hum})'
            else:
                layer_title = cfg["title_prefix"]

            folium.WmsTileLayer(
                url='https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?',
                layers=cfg["wms_layer"],
                fmt='image/png',
                transparent=True,
                version='1.1.0',
                name=layer_title,
                overlay=True,
                control=True,
                opacity=1.0
            ).add_to(m)

            folium.WmsTileLayer(
                url='https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?',
                layers=cfg["wms_layer"],
                styles=cfg["isoline_style"],
                fmt='image/png',
                transparent=True,
                version='1.1.0',
                name=cfg["isoline_name"],
                overlay=True,
                control=True,
                opacity=1.0
            ).add_to(m)

        # if date_iso:
        #     selected_date_str = f"{date_iso}"
        # else:
        #     selected_date_str = ""

        # ------------------------------------------------------
        # Agregar todos los FeatureGroups al mapa

        folium.LayerControl(collapsed=False).add_to(m)

        # Guardar el mapa como HTML
        temp_map_path = os.path.join(current_app.root_path, 'static', 'map_todos_v2.html')
        m.save(temp_map_path)

        # Leer el archivo generado y renderizar
        with open(temp_map_path, 'r') as f:
            mapa_html = f.read()

        # Fechas para el selector (hoy y hace 1 año)
        hoy = datetime.utcnow().date()
        fecha_min = hoy - timedelta(days=365)
        hoy_str = hoy.strftime("%Y-%m-%d")
        fecha_min_str = fecha_min.strftime("%Y-%m-%d")

        return render_template(
                'todos_v2.html',
                mapa_html=mapa_html,
                today_str=hoy_str,
                min_date_str=fecha_min_str,
                selected_date_str=selected_date_str
        )
    except Exception as e:

        return render_template('error.html', mensaje=f"Ocurrió un error inesperado: {str(e)}"), 500


@main.route('/todos_v2_fecha', methods=['POST'])
def todos_v2_fecha():
    """
    Recibe JSON {"fecha": "YYYY-MM-DD"} desde el selector.
    - Copia los NetCDF históricos a 10.10.10.63 con nombres temporales.
    - Reinicia GeoServer.
    - Retorna información sobre las fechas realmente usadas (pueden diferir de la solicitada).
    """
    try:
        data = request.get_json(silent=True) or {}
        fecha_str = data.get("fecha")

        if not fecha_str:
            return jsonify({"ok": False, "error": "Falta parámetro 'fecha'"}), 400

        # Validar formato y rango (opcional, pero recomendable)
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        hoy = datetime.utcnow().date() - timedelta(days=1)
        fecha_min = hoy - timedelta(days=365)
        if not (fecha_min <= fecha <= hoy):
            return jsonify({"ok": False, "error": "Fecha fuera de rango permitido"}), 400

        # Ejecutar actualización en el servidor GeoServer
        # Retorna dict con las fechas realmente usadas para cada producto
        fechas_usadas = actualizar_geoserver_historico(fecha_str)

        session["selected_date"] = fecha_str

        # Verificar si alguna fecha difiere de la solicitada
        fechas_diferentes = []
        for producto, fecha_usada in fechas_usadas.items():
            if fecha_usada != fecha_str:
                fecha_usada_dt = datetime.strptime(fecha_usada, "%Y-%m-%d")
                fecha_solicitada_dt = datetime.strptime(fecha_str, "%Y-%m-%d")
                dias_diff = (fecha_usada_dt - fecha_solicitada_dt).days
                fechas_diferentes.append({
                    "producto": producto,
                    "fecha_usada": fecha_usada,
                    "diferencia_dias": dias_diff
                })

        return jsonify({
            "ok": True,
            "fecha_solicitada": fecha_str,
            "fechas_usadas": fechas_usadas,
            "advertencia": fechas_diferentes if fechas_diferentes else None
        })

    except FileNotFoundError as e:
        # No se encontró alguno de los NetCDF históricos
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500