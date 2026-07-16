# app/routes.py

import leafmap
from datetime import datetime
# import cupy as cp
from flask import flash, Blueprint, current_app, request, jsonify, session, redirect, url_for, get_flashed_messages

import folium
from ipyleaflet import Map, TileLayer, basemaps

from ipyleaflet.velocity import Velocity
from ipyleaflet import WidgetControl
from ipywidgets import HTML
import geopandas as gpd
import os
# import csv
# import ssl
# from email.mime.base import MIMEBase
# from email import encoders
# import asyncio  # Gestión del bucle asíncrono
# import asyncpg  # Librería de conexión asíncrona con PostgreSQL
from geojson import Feature, FeatureCollection
from shapely.geometry import Polygon, box
from multiprocessing import Pool, cpu_count
from functools import partial
import json

import psycopg2
from dask.distributed import Client
from datetime import datetime, timedelta
import re
# import plotly.graph_objs as go
# import plotly.graph_objects as go
# from plotly.subplots import make_subplots
# from markupsafe import Markup
# import plotly.io as pio
import numpy as np
import logging
import xarray as xr
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import io
from flask import render_template
import requests
# import branca.element
from xml.etree import ElementTree as ET
from owslib.wms import WebMapService

from flask_caching import Cache
from folium.plugins import SideBySideLayers, GroupedLayerControl, MousePosition, AntPath, TimestampedWmsTileLayers

logging.basicConfig(level=logging.INFO)  # Nivel de logs (INFO, DEBUG, ERROR)
logger = logging.getLogger(__name__)  # Configura el logger
# Configuración opcional del cliente Dask, para manejar tareas distribuidas
client = Client()  # También puedes usar opciones avanzadas si lo necesitas
main = Blueprint('main', __name__)
# base_url = "http://gis-eco.ifop.cl/ncWMS2/wms"
# Configuración de la conexión a la base de datos PostGIS
DATABASE_CONFIG = {
    "database": "gisdb",
    "user": "operador",
    "password": "3102Rodarepo",
    "host": "giscc.ifop.cl",
    "port": "5432",
}
# Configuración del correo
SMTP_CONFIG = {
    "REMITENTE": "doma.gis.ifop@gmail.com",
    "SMTP_SERVER": "smtp.gmail.com",
    "SMTP_PORT": 465,
    "SMTP_USERNAME": "doma.gis.ifop@gmail.com",
    "SMTP_PASSWORD": "tkswkmcdujdsenam"
}
# Obtener la fecha actual
fecha_actual = datetime.now()
fecha_menos = fecha_actual - timedelta(days=1)
fecha_m_f = fecha_menos.strftime('%Y%m%d')
# center = [-35.0, -110.0]  # Cambia por la latitud/longitud deseada
# zoom = 4 # Nivel de zoom inicial
maxzoom = 12
minzoom = 3


# Define un formato para los valores de latitud y longitud
def custom_formatter(**kwargs):
    lat = kwargs.get("latitude", 0.0)  # Obtiene el valor de la latitud
    lng = kwargs.get("longitude", 0.0)  # Obtiene el valor de la longitud
    return f"Lat: {lat:.5f}, Lng: {lng:.5f}"  # Formato personalizado


@main.route('/')
def home():
    return todos()


@main.route('/corrientes')
def corrientes():
    try:
        # Directorio donde buscar los archivos
        center = session.get('center', [-35, -110])
        zoom = session.get('zoom', 4)
        static_path = os.path.join(current_app.root_path, 'static')

        # Buscar archivos con formato "YYYYMMDD_Corrientes.nc"
        pattern = r'^(\d{8})_Corrientes\.nc$'
        archivos_corrientes = [
            f for f in os.listdir(static_path)
            if re.match(pattern, f)
        ]

        # Verificar si existen archivos válidos
        if not archivos_corrientes:
            return "No se encontraron archivos corrientes con el formato esperado", 404

        # Extraer las fechas de los nombres de archivo y encontrar el más reciente
        archivo_actual = max(
            archivos_corrientes,
            key=lambda x: re.match(pattern, x).group(1)  # Extraer la fecha (YYYYMMDD) como cadena
        )

        # Ruta completa del archivo seleccionado
        corr = os.path.join(static_path, archivo_actual)
        fecha_str = archivo_actual[:8]
        fecha_obj = datetime.strptime(fecha_str, "%Y%m%d")
        fecha_formateada = fecha_obj.strftime("%d/%m/%Y")

        try:
            ds2 = xr.open_dataset(corr, engine='netcdf4')
            # ds2 = filtrar_datos_invalidos(ds1)

        except (ValueError, OSError) as e:
            return f"Error al abrir archivo NetCDF: {str(e)}", 500

        if 'time' in ds2.dims:  # Validar si 'time' está en las dimensiones
            try:
                ds2 = ds2.isel(time=0)
            except Exception as e:
                return f"Error al seleccionar índice de tiempo: {str(e)}", 500

        display_options = {
            'velocityType': 'Global Wind',
            'displayPosition': 'bottomright',
            'displayEmptyString': 'No currents available'
        }
        colores = [
            "rgb(101,21,110)",
            "rgb(159,42,99)",
            "rgb(212,72,66)",
            "rgb(245,125,21)",
            "rgb(250,193,39)",
            "rgb(252,255,164)"]

        try:
            # Crear mapa Leaflet
            # m = leafmap.Map(center=center, zoom=zoom, min_zoom=minzoom, max_zoom=maxZoom, basemap='Esri.WorldStreetMap')
            m = Map(center=center,
                    zoom=zoom,
                    basemap=basemaps.Esri.WorldStreetMap,
                    layout=dict(width="100%", height="100vh"),
                    scroll_wheel_zoom=True,
                    maxzoom=maxzoom,
                    minzoom=minzoom, )

            corr = Velocity(
                data=ds2,
                zonal_speed="u_current",  # u
                meridional_speed="v_current",  # v
                latitude_dimension='latitude',
                longitude_dimension='longitude',
                velocity_scale=0.2,
                max_velocity=1,
                color_scale=colores,
                name=f'Corrientes ({fecha_formateada})',
                display_options=display_options,
            )
            m.add(corr)
            # Leyenda personalizada
            leyenda_html = HTML(
                value=f"""
                <div style="padding: 10px; background-color: white; border-radius: 5px; box-shadow: 1px 2px 5px rgba(0,0,0,0.3);">
                    <strong style="font-size: 14px;">Capa:</strong> Corrientes<br>
                    <strong style="font-size: 14px;">Fecha:</strong> {fecha_formateada}
                </div>
                """
            )
            leyenda_control = WidgetControl(widget=leyenda_html, position="topright")  # Posición de la leyenda
            m.add(leyenda_control)

        except Exception as e:
            return f"Error al generar mapa de corrientes: {str(e)}", 500

        # Generar HTML del mapa y responder con el template
        try:
            # mapa_html = m.to_html()
            temp_map_path = os.path.join(current_app.root_path, 'static', 'mapc.html')
            mapa_html = m.save(temp_map_path)
            with open(temp_map_path, 'r') as f:
                mapa_html = f.read()

            # mapa_html = m._repr_html_()
            return render_template('corrientes.html', mapa_html=mapa_html)
        except Exception as e:
            return f"Error al renderizar plantilla HTML: {str(e)}", 500

    except Exception as e:
        # Manejar cualquier excepción general
        return f"Error desconocido en la ruta '/corrientes': {str(e)}", 500


@main.route('/vientos')
def vientos():
    # Directorio donde buscar los archivos
    center = session.get('center', [-35, -110])
    zoom = session.get('zoom', 4)
    static_path = os.path.join(current_app.root_path, 'static')
    # Buscar archivos con formato "YYYYMMDD_Corrientes.nc"
    pattern = r'^(\d{8}_\d{4})_Viento\.nc$'

    archivos_viento = [
        f for f in os.listdir(static_path)
        if re.match(pattern, f)
    ]
    # Verificar si existen archivos válidos
    if not archivos_viento:
        return "No se encontraron archivos vientos con el formato esperado", 404

    # Extraer las fechas de los nombres de archivo y encontrar el más reciente
    archivo_actual = max(
        archivos_viento,
        key=lambda x: datetime.strptime(re.match(pattern, x).group(1), "%Y%m%d_%H%M")
    )

    # Ruta completa del archivo seleccionado
    # SOLO PRUEBA
    # archivo_actual = "20250707_ERA5.nc"
    viento = os.path.join(static_path, archivo_actual)
    fecha_str = archivo_actual[:8]
    fecha_obj = datetime.strptime(fecha_str, "%Y%m%d")
    fecha_formateada = fecha_obj.strftime("%d/%m/%Y")

    # Extraer la hora (4 caracteres después del guion bajo)
    hora_str = archivo_actual[9:13]
    # hora_formateada = f"{hora_str[:2]}:{hora_str[2:]}"
    hora_obj = datetime.strptime(hora_str, "%H%M")
    hora_formateada = hora_obj - timedelta(hours=4)
    hora_formateada = hora_formateada.strftime("%H:%M")

    try:
        ds2 = xr.open_dataset(viento)
        if 'time' in ds2.dims:
            # Por ejemplo, seleccionamos el primer índice de tiempo
            ds2 = ds2.isel(time=0)
        # ds2['northward_wind'] = -1 * ds2['northward_wind']
        # ds2['eastward_wind'] = -1 * ds2['eastward_wind']

    except Exception as e:
        return f"Error al abrir o procesar el archivo NetCDF: {str(e)}", 500

    display_options = {
        'velocityType': 'Global Wind',
        'displayPosition': 'bottomright',
        'displayEmptyString': 'No wind available'
    }
    colores = [
        "rgb(101,21,110)",
        "rgb(159,42,99)",
        "rgb(212,72,66)",
        "rgb(245,125,21)",
        "rgb(250,193,39)",
        "rgb(252,255,164)"]
    # m = leafmap.Map(center=center, zoom=zoom, min_zoom=minzoom, max_zoom=maxZoom, basemap='Esri.WorldStreetMap')
    m = Map(center=center,
            zoom=zoom,
            min_zoom=minzoom,
            max_zoom=maxzoom,
            basemap=basemaps.Esri.WorldStreetMap,
            layout=dict(width="100%", height="100vh"),
            scroll_wheel_zoom=True)

    viento = Velocity(
        data=ds2,
        zonal_speed="u10",  # u
        meridional_speed="v10",  # v
        latitude_dimension='latitude',
        longitude_dimension='longitude',
        velocity_scale=0.01,
        max_velocity=20,
        color_scale=colores,
        name=f'Viento ({fecha_formateada})',
        display_options=display_options, )
    m.add(viento)
    # Leyenda personalizada
    leyenda_html = HTML(
        value=f"""
                    <div style="padding: 10px; background-color: white; border-radius: 5px; box-shadow: 1px 2px 5px rgba(0,0,0,0.3);">
                        <strong style="font-size: 14px;">Capa:</strong> Vientos<br>
                        <strong style="font-size: 14px;">Fecha:</strong> {fecha_formateada}<br>
                        <strong style="font-size: 14px;">Hora:</strong> {hora_formateada}
                    </div>
                    """
    )
    leyenda_control = WidgetControl(widget=leyenda_html, position="topright")  # Posición de la leyenda
    m.add(leyenda_control)
    # mapa_html = m.to_html()
    temp_map_path = os.path.join(current_app.root_path, 'static', 'mapv.html')
    mapa_html = m.save(temp_map_path)
    with open(temp_map_path, 'r') as f:
        mapa_html = f.read()

    # mapa_html = m.to_html()
    return render_template('vientos.html', mapa_html=mapa_html)


# Ruta para servir el mapa

@main.route('/estaciones_met')
def estaciones_met():
    try:
        center = session.get('center', [-35, -110])
        zoom = session.get('zoom', 4)
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()

        sql = """
              SELECT nombre, \
                     detalle, \
                     latitud, \
                     longitud,
                     CASE
                         WHEN tipo = 1 THEN '1.- UDEC'
                         WHEN tipo = 2 THEN '2.- IFOP'
                         WHEN tipo = 3 THEN '3.- RedMeteo'
                         WHEN tipo = 4 THEN '4.- IMARPE'
                         WHEN tipo = 5 THEN '5.- BlueBoat'
                         WHEN tipo = 6 THEN '6.- Armada'
                         WHEN tipo = 7 THEN '7.- Est. Fijas'
                         END AS tipo_estacion,
                     geom, \
                     link, \
                     ubicacionid
              FROM public.estaciones_link2
              ORDER BY tipo \
              """
        cursor.execute(sql)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        m = folium.Map(
            location=center,
            zoom_start=zoom,
            tiles=None,  # 'Esri WorldStreetMap',
            minZoom=minzoom,
            maxZoom=maxzoom,
        )
        # Añadir el mosaico base directamente, pero fuera del control de capas
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',  # (Opcional) texto en la esquina inferior
            name='Esri WorldStreetMap',  # El nombre que aparece en el mapa, pero no en LayerControl
            control=False  # No incluir en el control de capas
        ).add_to(m)
        folium.plugins.Geocoder().add_to(m)
        folium.plugins.LocateControl().add_to(m)

        # If you want get the user device position after load the map, set auto_start=True
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
        # Agregar el script JS para copiar al portapapeles
        # JavaScript para manejar clic en el cliente

        # Cargar el shapefile de áreas marinas protegidas
        shapefile_path = '/Data/sapo_prueba/app/static/shp/amp_nac_shp/AMP_NACIONAL.shp'
        gdf = gpd.read_file(shapefile_path)
        for column in gdf.columns:
            if gdf[column].dtype == 'datetime64[ns]' or isinstance(gdf[column].iloc[0], pd.Timestamp):
                gdf[column] = gdf[column].astype(str)
        if 'geometry' in gdf.columns:
            gdf = gdf[gdf.geometry.notnull()]
            gdf = gdf[gdf.is_valid]
        else:
            raise ValueError(f"El shapefile en {shapefile_path} no contiene geometrías válidas.")
        # Cargar áreas marinas protegidas en el mapa
        fields = ['NOMBRE', 'TIPO_AMP', 'REGION']
        geojson = folium.GeoJson(gdf, name='Áreas Marinas Protegidas',
                                 style_function=lambda x: {'fillColor': 'lightgreen',
                                                           'color': 'green', 'weight': 1, 'fillOpacity': 0.5, },
                                 popup=folium.GeoJsonPopup(fields=fields, aliases=['Nombre', 'Tipo AMP', 'Región']),
                                 tooltip=folium.GeoJsonTooltip(fields=fields, aliases=['Nombre', 'Tipo AMP', 'Región']),
                                 show=False)
        geojson.add_to(m)

        color_icons = {
            "1.- UDEC": 'yellow',
            "2.- IFOP": 'blue',
            "3.- RedMeteo": 'green',
            "4.- IMARPE": 'red',
            "5.- BlueBoat": 'purple',
            "6.- Armada": 'darkgray',
            "7.- Est. Fijas": 'brown'
        }

        feature_groups = {}
        for row in rows:
            tipo = row[4]
            if tipo not in feature_groups:
                feature_groups[tipo] = folium.FeatureGroup(name=tipo)

            latitud = float(row[2].replace(',', '.'))
            longitud = float(row[3].replace(',', '.'))
            nombre = str(row[0]).strip().title()
            region = str(row[1]).strip().title()
            codigo_estacion = row[7]

            # Modificar el contenido del popup para incluir el script
            popup_content = f"""
            <div>
                <strong>{nombre}</strong><br>
                <p>Región: {region}<br>Origen: {tipo}<br>Código: {codigo_estacion}</p>
                <button type="button" 
                        style="background-color: #007bff; color: white; border: none; 
                               padding: 5px 10px; border-radius: 5px; cursor: pointer;"
                        onclick="parent.mostrarGrafico({codigo_estacion})">
                    Ver Temperatura
                </button>
            </div>
            """

            circle = folium.CircleMarker(
                location=[latitud, longitud],
                radius=4,
                popup=folium.Popup(popup_content, max_width=300),
                color='black',
                fill=True,
                fill_color=color_icons.get(tipo, 'blue'),
                fill_opacity=0.9,
                weight=0.3,
                tooltip=nombre
            )
            feature_groups[tipo].add_child(circle)

        for group in feature_groups.values():
            m.add_child(group)

        if feature_groups:
            folium.LayerControl(collapsed=False).add_to(m)

        # mapa_html = m._repr_html_()
        # Guardar el archivo HTML del mapa
        temp_map_path = os.path.join(current_app.root_path, 'static', 'map_est_met.html')
        m.save(temp_map_path)
        with open(temp_map_path, 'r') as f:
            mapa_html = f.read()

        # Limpia librerías redundantes del HTML generado automáticamente
        mapa_html = mapa_html.replace(
            '<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.js"></script>', '')
        mapa_html = mapa_html.replace(
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.css"/>', '')
        mapa_html = mapa_html.replace('<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>', '')
        mapa_html = mapa_html.replace(
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.2.2/dist/css/bootstrap.min.css"/>',
            '')

        return render_template('estaciones.html', mapa_html=mapa_html)

    except Exception as e:
        return f"Error en el procesamiento del mapa: {str(e)}", 500


@main.route('/estaciones_ocean')
def estaciones_ocean():
    try:
        center = session.get('center', [-35, -110])
        zoom = session.get('zoom', 4)
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()

        sql = """
              SELECT nombre, 
                     detalle, 
                     latitud, 
                     longitud,
                     '1.- Est. Fijas' AS tipo_estacion,
                     geom, 
                     link, 
                     ubicacionid,
                     count
              FROM public.estaciones_link3
              WHERE tipo = 7 
              ORDER BY tipo 
              """
        cursor.execute(sql)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        m = folium.Map(
            location=center,
            zoom_start=zoom,
            tiles=None,  # 'Esri WorldStreetMap',
            minZoom=minzoom,
            maxZoom=maxzoom,
        )
        # Añadir el mosaico base directamente, pero fuera del control de capas
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',  # (Opcional) texto en la esquina inferior
            name='Esri WorldStreetMap',  # El nombre que aparece en el mapa, pero no en LayerControl
            control=False  # No incluir en el control de capas
        ).add_to(m)
        folium.plugins.Geocoder().add_to(m)
        # Añadir el plugin MousePosition al mapa
        formatter = "function(lat, lng) {return `Lat: ${lat.toFixed(5)}, Lng: ${lng.toFixed(5)}`;}"
        folium.plugins.LocateControl().add_to(m)

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

        # Cargar el shapefile de áreas marinas protegidas
        shapefile_path = '/Data/sapo_prueba/app/static/shp/amp_nac_shp/AMP_NACIONAL.shp'
        gdf = gpd.read_file(shapefile_path)
        for column in gdf.columns:
            if gdf[column].dtype == 'datetime64[ns]' or isinstance(gdf[column].iloc[0], pd.Timestamp):
                gdf[column] = gdf[column].astype(str)
        if 'geometry' in gdf.columns:
            gdf = gdf[gdf.geometry.notnull()]
            gdf = gdf[gdf.is_valid]
        else:
            raise ValueError(f"El shapefile en {shapefile_path} no contiene geometrías válidas.")
        # Cargar áreas marinas protegidas en el mapa
        fields = ['NOMBRE', 'TIPO_AMP', 'REGION']
        geojson = folium.GeoJson(gdf, name='Áreas Marinas Protegidas',
                                 style_function=lambda x: {'fillColor': 'lightgreen',
                                                           'color': 'green', 'weight': 1, 'fillOpacity': 0.5, },
                                 popup=folium.GeoJsonPopup(fields=fields, aliases=['Nombre', 'Tipo AMP', 'Región']),
                                 tooltip=folium.GeoJsonTooltip(fields=fields, aliases=['Nombre', 'Tipo AMP', 'Región']),
                                 show=False)
        geojson.add_to(m)

        color_icons = {
            "1.- Est. Fijas": 'white'
        }

        feature_groups = {}
        for row in rows:
            tipo = row[4]
            if tipo not in feature_groups:
                feature_groups[tipo] = folium.FeatureGroup(name=tipo)

            latitud = float(row[2].replace(',', '.'))
            longitud = float(row[3].replace(',', '.'))
            nombre = str(row[0]).strip().title()
            region = str(row[1]).strip().title()
            codigo_estacion = row[7]
            count = row[8] if row[8] is not None else 0  # Manejar valores `None`, asignando 0 si es `None`

            # Determinar si el botón debería estar habilitado o deshabilitado, y el estilo
            if count <= 0:
                button_disabled = 'disabled'
                button_style = 'background-color: #d6d6d6; color: #808080; border: none; cursor: not-allowed;'
            else:
                button_disabled = ''
                button_style = 'background-color: #007bff; color: white; border: none; cursor: pointer;'

            # Modificar el contenido del popup para incluir el script
            popup_content = f"""
                    <div>
                        <strong>{nombre}</strong><br>
                        <p>Región: {region}<br>Origen: {tipo}<br>Código: {codigo_estacion}</p>
                        <button type="button" 
                                style="{button_style} padding: 5px 10px; border-radius: 5px;"
                                onclick="mostrarGrafico({codigo_estacion},'{nombre}', '{region}', {latitud}, {longitud})"
                                {button_disabled}>
                            Ver Gráficos
                        </button>
                    </div>
                    """

            circle_with_symbol = folium.Marker(
                location=[latitud, longitud],
                popup=folium.Popup(popup_content, max_width=300),
                icon=folium.DivIcon(
                    html=f"""
                                <div style="
                                    text-align: center;
                                    border: 2px solid black;
                                    border-radius: 50%;
                                    width: 15px;
                                    height: 15px;
                                    background-color: {color_icons.get(tipo, 'white')};
                                    display: flex;
                                    align-items: center;
                                    justify-content: center;
                                    font-size: 10px;
                                    color: blue;">
                                    ★
                                </div>
                                """
                ),
                tooltip=nombre
            )
            feature_groups[tipo].add_child(circle_with_symbol)

        for group in feature_groups.values():
            m.add_child(group)

        if feature_groups:
            folium.LayerControl(collapsed=False).add_to(m)

        # mapa_html = m._repr_html_()
        # Guardar el archivo HTML del mapa
        temp_map_path = os.path.join(current_app.root_path, 'static', 'map_est_ocean.html')
        m.save(temp_map_path)
        with open(temp_map_path, 'r') as f:
            mapa_html = f.read()

        # Limpia librerías redundantes del HTML generado automáticamente
        mapa_html = mapa_html.replace(
            '<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.js"></script>', '')
        mapa_html = mapa_html.replace(
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.css"/>', '')
        mapa_html = mapa_html.replace('<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>', '')
        mapa_html = mapa_html.replace(
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.2.2/dist/css/bootstrap.min.css"/>',
            '')

        return render_template('estaciones_22.html', mapa_html=mapa_html)

    except Exception as e:
        return f"Error en el procesamiento del mapa: {str(e)}", 500


@main.route('/get_est_met/<int:codigo_estacion>')
def get_est_met(codigo_estacion):
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()

        # Obtener información de la estación
        query_estacion = """
                         SELECT nombre, \
                                detalle, \
                                longitud, \
                                latitud,
                                CASE
                                    WHEN tipo = 1 THEN '1.- UDEC'
                                    WHEN tipo = 2 THEN '2.- IFOP'
                                    WHEN tipo = 3 THEN '3.- RedMeteo'
                                    WHEN tipo = 4 THEN '4.- IMARPE'
                                    WHEN tipo = 5 THEN '5.- BlueBoat'
                                    WHEN tipo = 6 THEN '6.- Armada'
                                    WHEN tipo = 7 THEN '7.- Est. Fija'
                                    END AS tipo_estacion
                         FROM public.estaciones_link2
                         WHERE ubicacionid = %s; \
                         """
        cursor.execute(query_estacion, (codigo_estacion,))
        estacion_info = cursor.fetchone()

        if not estacion_info:
            return jsonify({'error': 'No se encontró la estación'})

        # Variables a consultar
        variables = ['Temperatura', 'Presión', 'Humedad', 'Velocidad del Viento']
        datos_graficos = {}

        # Consulta para cada variable
        for variable in variables:
            query = """
                    SELECT hora, valor, unidad
                    FROM public.estaciones_valores(%s)
                    WHERE nombre = %s
                      AND hora >= NOW() - INTERVAL '72 hours'
                    ORDER BY hora; \
                    """
            cursor.execute(query, (codigo_estacion, variable))
            resultados = cursor.fetchall()

            datos_graficos[variable] = {
                'x': [row[0].strftime('%Y-%m-%d %H:%M') for row in resultados],
                'y': [float(row[1]) if row[1] is not None else None for row in resultados],
                'unidad': resultados[0][2] if resultados and resultados[0][2] else ''
            }

        cursor.close()
        conn.close()

        # Procesar los datos de la estación
        nombre, detalle, longitud, latitud, tipo = estacion_info
        info_estacion = {
            'nombre': nombre,
            'detalle': detalle,
            'coordenadas': f"Lat: {latitud}, Lon: {longitud}",
            'tipo': tipo
        }

        return jsonify({
            'info_estacion': info_estacion,
            'datos_graficos': datos_graficos
        })

    except Exception as e:
        print(f"Error en get_temperatura: {str(e)}")
        return jsonify({'error': f'Error al obtener datos: {str(e)}'})


@main.route('/get_est_ocean/<int:codigo_estacion>')
def get_est_ocean(codigo_estacion):
    try:
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()

        # Obtener información de la estación
        query_estacion = """
                         SELECT nombre, \
                                detalle, \
                                longitud, \
                                latitud,
                                CASE
                                    WHEN tipo = 1 THEN '1.- UDEC'
                                    WHEN tipo = 2 THEN '2.- IFOP'
                                    WHEN tipo = 3 THEN '3.- RedMeteo'
                                    WHEN tipo = 4 THEN '4.- IMARPE'
                                    WHEN tipo = 5 THEN '5.- BlueBoat'
                                    WHEN tipo = 6 THEN '6.- Armada'
                                    WHEN tipo = 7 THEN '7.- Est. Fija'
                                    END AS tipo_estacion
                         FROM public.estaciones_link3
                         WHERE ubicacionid = %s; \
                         """
        cursor.execute(query_estacion, (codigo_estacion,))
        estacion_info = cursor.fetchone()

        if not estacion_info:
            return jsonify({'error': 'No se encontró la estación'})

        # Variables a consultar
        variables = ['Temperatura', 'Salinidad', 'Clorofila_a', 'Oxigeno']
        datos_graficos = {}

        # Consulta para cada variable
        for variable in variables:
            query = """
                    SELECT hora, valor, unidad
                    FROM public.estaciones_oceano_valores(%s)
                    WHERE nombre = %s
                      AND hora >= '2013-01-01'
                    ORDER BY hora; \
                    """
            cursor.execute(query, (codigo_estacion, variable))
            resultados = cursor.fetchall()

            datos_graficos[variable] = {
                'x': [row[0].strftime('%Y-%m-%d %H:%M') for row in resultados],
                'y': [float(row[1]) if row[1] is not None else None for row in resultados],
                'unidad': resultados[0][2] if resultados and resultados[0][2] else ''
            }

        cursor.close()
        conn.close()

        # Procesar los datos de la estación
        nombre, detalle, longitud, latitud, tipo = estacion_info
        info_estacion = {
            'nombre': nombre,
            'detalle': detalle,
            'coordenadas': f"Lat: {latitud}, Lon: {longitud}",
            'tipo': tipo
        }

        return jsonify({
            'info_estacion': info_estacion,
            'datos_graficos': datos_graficos
        })

    except Exception as e:
        print(f"Error en get_temperatura: {str(e)}")
        return jsonify({'error': f'Error al obtener datos: {str(e)}'})


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
            conn = psycopg2.connect(**DATABASE_CONFIG)
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
            conn = psycopg2.connect(**DATABASE_CONFIG)
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


@main.route('/buques')
def buques():
    try:
        # Definir las constantes del mapa
        center = session.get('center', [-35, -110])
        zoom = session.get('zoom', 4)

        # Conexión a la base de datos
        # conn = psycopg2.connect(**DATABASE_CONFIG)
        # cursor = conn.cursor()
        #
        # # Consulta SQL asegurando datos únicos por código y fecha
        # sql = "SELECT codigo, buque, fecha, longitud, latitud FROM track_buques ORDER BY codigo, fecha"
        # cursor.execute(sql)
        # rows = cursor.fetchall()
        # cursor.close()
        # conn.close()
        # # Convertir los resultados a un formato legible, por ejemplo, una lista procesada
        # listado_buques = [{"codigo": row[0], "buque": row[1], "fecha": row[2].strftime("%d/%m/%Y"), "latitud": row[4],
        #                    "longitud": row[3]} for row in rows]
        #
        # # Pasar el listado usando flash
        # flash(listado_buques)

        # Crear el mapa base
        m = folium.Map(
            location=center,
            zoom_start=zoom,
            tiles=None,  # 'Esri WorldStreetMap',
            minZoom=minzoom,
            maxZoom=maxzoom,
        )
        # Añadir el mosaico base directamente, pero fuera del control de capas
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',  # (Opcional) texto en la esquina inferior
            name='Esri WorldStreetMap',  # El nombre que aparece en el mapa, pero no en LayerControl
            control=False  # No incluir en el control de capas
        ).add_to(m)
        # Cargar el shapefile de áreas marinas protegidas
        shapefile_path = '/Data/sapo_prueba/app/static/shp/amp_nac_shp/AMP_NACIONAL.shp'
        gdf = gpd.read_file(shapefile_path)
        for column in gdf.columns:
            if gdf[column].dtype == 'datetime64[ns]' or isinstance(gdf[column].iloc[0], pd.Timestamp):
                gdf[column] = gdf[column].astype(str)
        if 'geometry' in gdf.columns:
            gdf = gdf[gdf.geometry.notnull()]
            gdf = gdf[gdf.is_valid]
        else:
            raise ValueError(f"El shapefile en {shapefile_path} no contiene geometrías válidas.")
        # Cargar áreas marinas protegidas en el mapa
        fields = ['NOMBRE', 'TIPO_AMP', 'REGION']
        geojson = folium.GeoJson(gdf, name='Áreas Marinas Protegidas',
                                 style_function=lambda x: {'fillColor': 'lightgreen',
                                                           'color': 'green', 'weight': 1, 'fillOpacity': 0.5, },
                                 popup=folium.GeoJsonPopup(fields=fields, aliases=['Nombre', 'Tipo AMP', 'Región']),
                                 tooltip=folium.GeoJsonTooltip(fields=fields, aliases=['Nombre', 'Tipo AMP', 'Región']),
                                 show=False
                                 )
        geojson.add_to(m)
        # Diccionario de colores por tipo de código
        # --------------------------
        # Capa de Buques Mejorada con AntPath
        # --------------------------

        # Conexión a la base de datos
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()

        # Consulta SQL (ordenada por buque y fecha)
        sql = "SELECT codigo, buque, fecha, longitud, latitud FROM track_buques ORDER BY codigo, fecha"
        cursor.execute(sql)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        # Diccionario de colores por tipo de código
        color_icons = {
            1: 'blue',
            2: 'gray',
            3: 'orange'
        }

        # Agrupar filas por código de buque
        buque_data = {}
        for row in rows:
            codigo = row[0]
            if codigo not in buque_data:
                buque_data[codigo] = []
            buque_data[codigo].append(row)

        # Crear un diccionario para almacenar los FeatureGroups por buque
        feature_groups = {}
        buques_groups = []

        # Procesar cada buque por separado
        for codigo, registros in buque_data.items():
            # Crear un FeatureGroup para cada buque si no existe
            nombre_buque = str(registros[0][1]).strip().title()  # Nombre del buque
            if codigo not in feature_groups:
                feature_groups[codigo] = folium.FeatureGroup(
                    name=nombre_buque,  # Nombre del grupo en la leyenda
                    show=True  # Mostrar el grupo activado por defecto
                )

            # Listas para las coordenadas del `AntPath` y los puntos (`CircleMarker`)
            antpath_coords = []
            ultimo_punto = None

            num_registros = len(registros)
            for idx, row in enumerate(registros):
                # Extraer y validar coordenadas
                try:
                    latitud = float(row[4])  # Latitud
                    longitud = float(row[3])  # Longitud
                except (ValueError, TypeError):  # Si hay valores inválidos
                    print(f"Error en latitud/longitud: {row}")
                    continue
                # Verificar que las coordenadas están en el rango esperado
                if not (-90 <= latitud <= 90 and -180 <= longitud <= 180):
                    print(f"Coordenadas fuera de rango: Latitud={latitud}, Longitud={longitud}")
                    continue

                # Formatear la fecha
                try:
                    fecha_original = row[2]  # Fecha desde la base de datos
                    fecha_formateada = fecha_original.strftime("%H:%M %d/%m/%Y")
                except AttributeError:
                    print(f"Fecha no válida para formatear: {row[2]}")
                    fecha_formateada = "Fecha inválida"

                # Calcular opacidad para los puntos (0.1 para antiguos, 1 para recientes)
                fill_opacity = 0.1 + (0.9 * (idx / (num_registros - 1))) if num_registros > 1 else 1

                # Guardar las coordenadas para el AntPath
                antpath_coords.append([latitud, longitud])
                if idx == num_registros - 1:  # Es el más reciente
                    ultimo_punto = {
                        "latitud": latitud,
                        "longitud": longitud,
                        "fecha": fecha_formateada
                    }

                # Crear un popup para el círculo
                popup_content = f"""
                                <div>
                                    <strong>{nombre_buque}</strong><br>
                                    <p>{fecha_formateada}</p>
                                </div>
                                """

                # Crear un marcador para cada punto
                circle = folium.CircleMarker(
                    location=[latitud, longitud],
                    radius=5,
                    popup=folium.Popup(popup_content, max_width=300),
                    color='black',
                    fill=True,
                    fill_color=color_icons.get(codigo, 'blue'),  # Color por tipo de buque
                    fill_opacity=fill_opacity,
                    weight=0.3,
                    tooltip=f"{nombre_buque}, {fecha_formateada}"
                )
                # Agregar el círculo (punto) al FeatureGroup correspondiente
                feature_groups[codigo].add_child(circle)

                # Dibujar un AntPath conectando los puntos (track) del buque
                if len(antpath_coords) > 1:
                    AntPath(
                        locations=antpath_coords,  # Coordenadas de la trayectoria
                        reverse=False,  # Invertir animación (acorde a la dirección)
                        dash_array=[10, 20],  # Estilo de línea (guiones y espacios)
                        color=color_icons.get(codigo, 'blue'),  # Color basado en el tipo
                        opacity=0.5,  # Opacidad de la trayectoria
                        weight=2,  # Grosor de la línea
                        delay=1500
                    ).add_to(feature_groups[codigo])
                # Agregar un Popup en la posición más reciente
                if ultimo_punto:
                    popup_actual = folium.Popup(
                        f"<strong>{nombre_buque}</strong><br>"
                        f"Lat: {ultimo_punto['latitud']:.5f}<br>"
                        f"Lon: {ultimo_punto['longitud']:.5f}<br>"
                        f"Fecha: {ultimo_punto['fecha']}",
                        max_width=250
                    )
                    folium.Marker(
                        location=[ultimo_punto['latitud'], ultimo_punto['longitud']],
                        icon=folium.Icon(color=color_icons.get(codigo, 'blue'), icon='info-sign'),
                        popup=popup_actual
                    ).add_to(feature_groups[codigo])

                    # Agregar el FeatureGroup del buque a la lista
                buques_groups.append(feature_groups[codigo])

        # Agregar cada FeatureGroup al mapa
        for group in feature_groups.values():
            m.add_child(group)

        # Agregar controles de capas al mapa
        folium.LayerControl(collapsed=False).add_to(m)

        # Convertir el mapa a HTML
        # map_html = m._repr_html_()
        # Guardar el archivo HTML del mapa
        temp_map_path = os.path.join(current_app.root_path, 'static', 'map_buque.html')
        m.save(temp_map_path)
        with open(temp_map_path, 'r') as f:
            mapa_html = f.read()

        # Limpia librerías redundantes del HTML generado automáticamente
        mapa_html = mapa_html.replace(
            '<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.js"></script>', '')
        mapa_html = mapa_html.replace(
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.css"/>', '')
        mapa_html = mapa_html.replace('<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>', '')
        mapa_html = mapa_html.replace(
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.2.2/dist/css/bootstrap.min.css"/>',
            '')

        return render_template('buques.html', mapa_html=mapa_html)

    except Exception as e:
        # Manejo de errores
        return f"Error en el procesamiento del mapa: {str(e)}", 500


@main.route('/tsm')
def tsm():
    try:
        # Definir las constantes del mapa
        center = session.get('center', [-35, -110])
        zoom = session.get('zoom', 4)

        m = folium.Map(
            location=center,
            zoom_start=zoom,
            tiles=None,  # 'Esri WorldStreetMap',
            minZoom=minzoom,
            maxZoom=maxzoom,
        )
        # Añadir el mosaico base directamente, pero fuera del control de capas
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',  # (Opcional) texto en la esquina inferior
            name='Esri WorldStreetMap',  # El nombre que aparece en el mapa, pero no en LayerControl
            control=False  # No incluir en el control de capas
        ).add_to(m)
        # Añadir el plugin MousePosition al mapa
        formatter = "function(lat, lng) {return `Lat: ${lat.toFixed(5)}, Lng: ${lng.toFixed(5)}`;}"

        mouse_position = MousePosition(
            position="bottomleft",  # Posición donde se mostrará (arriba a la derecha)
            separator=" | ",
            empty_string="",
            lng_first=False,
            num_digits=4,  # Número de decimales para mostrar
            prefix="Coordenadas:",  # Prefijo del texto
            lat_formatter=None,
            lng_formatter=None,
            formatter=formatter  # Mostrar las posiciones como se definió anteriormente
        )
        mouse_position.add_to(m)
        # Cargar el archivo GeoJSON de áreas marinas protegidas
        geojson_path = '/Data/sapo_prueba/app/static/shp/amp_nac_shp/AMP_NACIONAL.geojson'
        gdf = gpd.read_file(geojson_path)
        # Procesar columnas del archivo si es necesario
        for column in gdf.columns:
            if gdf[column].dtype == 'datetime64[ns]' or isinstance(gdf[column].iloc[0], pd.Timestamp):
                gdf[column] = gdf[column].astype(str)

        # Añadir las áreas marinas protegidas al mapa
        fields = ['NOMBRE', 'TIPO_AMP', 'REGION']
        geojson = folium.GeoJson(
            gdf, name='Áreas Marinas Protegidas',
            style_function=lambda x: {
                'fillColor': 'lightgreen',
                'color': 'green',
                'weight': 1,
                'fillOpacity': 0.5,
            },
            popup=folium.GeoJsonPopup(fields=fields, aliases=['Nombre', 'Tipo AMP', 'Región']),
            tooltip=folium.GeoJsonTooltip(fields=fields, aliases=['Nombre', 'Tipo AMP', 'Región']),
            show=False

        )
        geojson.add_to(m)

        try:
            wms_url = 'https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?service=WMS&request=GetCapabilities'
            response = requests.get(wms_url)
            response.raise_for_status()  # Verifica que no haya errores HTTP

            # Parsear el XML con el manejo del namespace
            root = ET.fromstring(response.content)

            # Declarar el espacio de nombres basado en el WMS
            namespaces = {'wms': 'http://www.opengis.net/wms'}

            # Buscar la capa "Temperatura"
            layer_name = "Temperatura"
            date = "Desconocida"  # Valor inicial si no se encuentra
            for layer in root.findall(".//wms:Layer", namespaces):  # Busca todos los nodos <Layer>
                name_element = layer.find("wms:Name", namespaces)
                if name_element is not None and name_element.text == layer_name:
                    # Encontramos la capa; ahora buscamos el nodo <Dimension>
                    dimension = layer.find("wms:Dimension", namespaces)
                    if dimension is not None and dimension.attrib.get("name") == "time":
                        # Extraer la fecha del texto del nodo <Dimension>
                        date = dimension.text.strip()  # Por ejemplo: "2025-05-30T09:00:00.000Z"
                    break
            if date != "Desconocida":
                try:
                    # Convertir la fecha de la cadena ISO 8601 al formato deseado
                    parsed_date = datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%fZ")
                    date = parsed_date.strftime("%d/%m/%Y")  # Formato: dd/mm/yyyy
                except ValueError:
                    # Si ocurre algún error al convertir, dejar la fecha como estaba
                    date = "Desconocida"

            # Crear el nombre de la capa con la fecha extraída
            layer_title = f"Temperatura ({date})"

            # Agregar la capa WMS de anomalía de temperatura
            wms_layer = folium.WmsTileLayer(
                url='https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?',
                layers='Ifop_Sapo:Temperatura',
                fmt='image/png',
                transparent=True,
                version='1.1.0',
                name=layer_title,
                overlay=True,
                control=True,
                opacity=1.0
            )
            wms_layer.add_to(m)

            # Agregar la capa de isolíneas con el estilo ajustado
            wms_isolines = folium.WmsTileLayer(
                url='https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?',
                layers='Ifop_Sapo:Temperatura',  # La misma capa de datos
                styles='1_isolineas_tsm',  # Aquí se define el estilo creado en GeoServer
                fmt='image/png',
                transparent=True,
                version='1.1.0',
                name='Isolíneas de TSM',  # Nombre visible en el control de capas
                overlay=True,
                control=True,
                opacity=1.0
            )
            # Agregar ambas capas al mapa
            wms_isolines.add_to(m)

            # Agregar control de capas
            folium.LayerControl(collapsed=False).add_to(m)

            # Guardar el archivo HTML del mapa
            temp_map_path = os.path.join(current_app.root_path, 'static', 'map_tsm.html')
            m.save(temp_map_path)
            with open(temp_map_path, 'r') as f:
                mapa_html = f.read()

            # Limpia librerías redundantes del HTML generado automáticamente
            mapa_html = mapa_html.replace(
                '<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.js"></script>', '')
            mapa_html = mapa_html.replace(
                '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.css"/>', '')
            mapa_html = mapa_html.replace('<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>', '')
            mapa_html = mapa_html.replace(
                '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.2.2/dist/css/bootstrap.min.css"/>',
                '')

            # URL de la leyenda
            legend_url = (
                "https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?"
                "REQUEST=GetLegendGraphic&"
                "VERSION=1.1.0&"
                "FORMAT=image/png&"
                "WIDTH=120&"
                "HEIGHT=50&"
                "LAYER=Ifop_Sapo:Temperatura&"
                "STYLE=1_tsm_leyenda&"
                "&legend_options=fontSize:40"
            )
            # Renderizar el template HTML
            # mapa_html = m._repr_html_()
            return render_template('tsm.html',
                                   mapa_html=mapa_html,
                                   legend_url=legend_url)

        except requests.exceptions.RequestException as e:
            return f"Error al obtener metadatos: {str(e)}", 500

    except Exception as e:
        return f"Error desconocido en la ruta '/tsm': {str(e)}", 500


@main.route('/atsm')
def atsm():
    try:
        # Definir las constantes del mapa
        center = session.get('center', [-35, -110])
        zoom = session.get('zoom', 4)
        # Crear el mapa basel
        m = folium.Map(
            location=center,
            zoom_start=zoom,
            tiles=None,  # 'Esri WorldStreetMap',
            minZoom=minzoom,
            maxZoom=maxzoom,
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
        folium.plugins.Geocoder().add_to(m)
        # Añadir el mosaico base directamente, pero fuera del control de capas
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',  # (Opcional) texto en la esquina inferior
            name='Esri WorldStreetMap',  # El nombre que aparece en el mapa, pero no en LayerControl
            control=False  # No incluir en el control de capas
        ).add_to(m)
        # Cargar el shapefile de áreas marinas protegidas
        shapefile_path = '/Data/sapo_prueba/app/static/shp/amp_nac_shp/AMP_NACIONAL.shp'
        gdf = gpd.read_file(shapefile_path)
        for column in gdf.columns:
            if gdf[column].dtype == 'datetime64[ns]' or isinstance(gdf[column].iloc[0], pd.Timestamp):
                gdf[column] = gdf[column].astype(str)
        if 'geometry' in gdf.columns:
            gdf = gdf[gdf.geometry.notnull()]
            gdf = gdf[gdf.is_valid]
        else:
            raise ValueError(f"El shapefile en {shapefile_path} no contiene geometrías válidas.")
        # Cargar áreas marinas protegidas en el mapa
        fields = ['NOMBRE', 'TIPO_AMP', 'REGION']
        geojson = folium.GeoJson(gdf, name='Áreas Marinas Protegidas',
                                 style_function=lambda x: {'fillColor': 'lightgreen',
                                                           'color': 'green', 'weight': 1, 'fillOpacity': 0.5, },
                                 popup=folium.GeoJsonPopup(fields=fields, aliases=['Nombre', 'Tipo AMP', 'Región']),
                                 tooltip=folium.GeoJsonTooltip(fields=fields,
                                                               aliases=['Nombre', 'Tipo AMP', 'Región']),
                                 show=False
                                 )
        geojson.add_to(m)
        try:
            wms_url = 'https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?service=WMS&request=GetCapabilities'
            response = requests.get(wms_url)
            response.raise_for_status()  # Verifica que no haya errores HTTP

            # Parsear el XML con el manejo del namespace
            root = ET.fromstring(response.content)

            # Declarar el espacio de nombres basado en el WMS
            namespaces = {'wms': 'http://www.opengis.net/wms'}

            # Buscar la capa "Temperatura"
            layer_name = "Anomalia_temperatura"
            date = "Desconocida"  # Valor inicial si no se encuentra
            for layer in root.findall(".//wms:Layer", namespaces):  # Busca todos los nodos <Layer>
                name_element = layer.find("wms:Name", namespaces)
                if name_element is not None and name_element.text == layer_name:
                    # Encontramos la capa; ahora buscamos el nodo <Dimension>
                    dimension = layer.find("wms:Dimension", namespaces)
                    if dimension is not None and dimension.attrib.get("name") == "time":
                        # Extraer la fecha del texto del nodo <Dimension>
                        date = dimension.text.strip()  # Por ejemplo: "2025-05-30T09:00:00.000Z"
                    break
            if date != "Desconocida":
                try:
                    # Convertir la fecha de la cadena ISO 8601 al formato deseado
                    parsed_date = datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%fZ")
                    date = parsed_date.strftime("%d/%m/%Y")  # Formato: dd/mm/yyyy
                except ValueError:
                    # Si ocurre algún error al convertir, dejar la fecha como estaba
                    date = "Desconocida"

            # Crear el nombre de la capa con la fecha extraída
            layer_title = f"Anomalía de Temperatura ({date})"
            # Agregar la capa WMS de anomalía de temperatura
            wms_layer = folium.WmsTileLayer(
                url='https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?',
                layers='Ifop_Sapo:Anomalia_temperatura',
                fmt='image/png',
                transparent=True,
                version='1.1.0',
                name=layer_title,
                overlay=True,
                control=True,
                opacity=1.0
            )
            wms_layer.add_to(m)
            # Agregar la capa de isolíneas con el estilo ajustado
            wms_isolines = folium.WmsTileLayer(
                url='https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?',
                layers='Ifop_Sapo:Anomalia_temperatura',  # La misma capa de datos
                styles='2_isolineas_atsm',  # Aquí se define el estilo creado en GeoServer
                fmt='image/png',
                transparent=True,
                version='1.1.0',
                name='Isolíneas de ATSM',  # Nombre visible en el control de capas
                overlay=True,
                control=True,
                opacity=1.0
            )
            # Agregar ambas capas al mapa
            wms_isolines.add_to(m)
            # Agregar control de capas
            folium.LayerControl(collapsed=False).add_to(m)

            # # Guardar y leer el mapa
            # temp_map_path = os.path.join(current_app.root_path, 'static', 'map_atsm.html')
            # m.save(temp_map_path)
            # with open(temp_map_path, 'r') as f:
            #     mapa_html = f.read()

            # URL de la leyenda
            legend_url = (
                "https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?"
                "REQUEST=GetLegendGraphic&"
                "VERSION=1.1.0&"
                "FORMAT=image/png&"
                "WIDTH=120&"
                "HEIGHT=50&"
                "LAYER=Ifop_Sapo:Anomalia_temperatura&"
                "STYLE=2_atsm_leyenda&"
                "&legend_options=fontSize:25"
            )
            # mapa_html = m._repr_html_()
            # Guardar el archivo HTML del mapa
            temp_map_path = os.path.join(current_app.root_path, 'static', 'map_atsm.html')
            m.save(temp_map_path)
            with open(temp_map_path, 'r') as f:
                mapa_html = f.read()

            # Limpia librerías redundantes del HTML generado automáticamente
            mapa_html = mapa_html.replace(
                '<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.js"></script>', '')
            mapa_html = mapa_html.replace(
                '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.css"/>', '')
            mapa_html = mapa_html.replace('<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>', '')
            mapa_html = mapa_html.replace(
                '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.2.2/dist/css/bootstrap.min.css"/>',
                '')

            return render_template('atsm.html',
                                   mapa_html=mapa_html,
                                   legend_url=legend_url)

        except requests.exceptions.RequestException as e:
            return f"Error al obtener metadatos: {str(e)}", 500

    except Exception as e:
        return f"Error desconocido en la ruta '/atsm': {str(e)}", 500


@main.route('/clo')
def clo():
    try:
        # Crear el mapa base
        center = session.get('center', [-35, -110])
        zoom = session.get('zoom', 4)
        m = folium.Map(
            location=center,
            zoom_start=zoom,
            tiles=None,  # 'Esri WorldStreetMap',
            minZoom=minzoom,
            maxZoom=maxzoom,
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
        # Añadir el mosaico base directamente, pero fuera del control de capas
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',  # (Opcional) texto en la esquina inferior
            name='Esri WorldStreetMap',  # El nombre que aparece en el mapa, pero no en LayerControl
            control=False  # No incluir en el control de capas
        ).add_to(m)
        try:
            # Cargar el shapefile de áreas marinas protegidas
            shapefile_path = '/Data/sapo_prueba/app/static/shp/amp_nac_shp/AMP_NACIONAL.shp'
            gdf = gpd.read_file(shapefile_path)
            for column in gdf.columns:
                if gdf[column].dtype == 'datetime64[ns]' or isinstance(gdf[column].iloc[0], pd.Timestamp):
                    gdf[column] = gdf[column].astype(str)
            if 'geometry' in gdf.columns:
                gdf = gdf[gdf.geometry.notnull()]
                gdf = gdf[gdf.is_valid]
            else:
                raise ValueError(f"El shapefile en {shapefile_path} no contiene geometrías válidas.")
            # Cargar áreas marinas protegidas en el mapa
            fields = ['NOMBRE', 'TIPO_AMP', 'REGION']
            geojson = folium.GeoJson(gdf, name='Áreas Marinas Protegidas',
                                     style_function=lambda x: {'fillColor': 'lightgreen',
                                                               'color': 'green', 'weight': 1, 'fillOpacity': 0.5, },
                                     popup=folium.GeoJsonPopup(fields=fields, aliases=['Nombre', 'Tipo AMP', 'Región']),
                                     tooltip=folium.GeoJsonTooltip(fields=fields,
                                                                   aliases=['Nombre', 'Tipo AMP', 'Región']),
                                     show=False
                                     )
            geojson.add_to(m)
            wms_url = 'https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?service=WMS&request=GetCapabilities'
            response = requests.get(wms_url)
            response.raise_for_status()  # Verifica que no haya errores HTTP

            # Parsear el XML con el manejo del namespace
            root = ET.fromstring(response.content)

            # Declarar el espacio de nombres basado en el WMS
            namespaces = {'wms': 'http://www.opengis.net/wms'}

            # Buscar la capa "Temperatura"
            layer_name = "Clorofila"
            date = "Desconocida"  # Valor inicial si no se encuentra
            for layer in root.findall(".//wms:Layer", namespaces):  # Busca todos los nodos <Layer>
                name_element = layer.find("wms:Name", namespaces)
                if name_element is not None and name_element.text == layer_name:
                    # Encontramos la capa; ahora buscamos el nodo <Dimension>
                    dimension = layer.find("wms:Dimension", namespaces)
                    if dimension is not None and dimension.attrib.get("name") == "time":
                        # Extraer la fecha del texto del nodo <Dimension>
                        date = dimension.text.strip()  # Por ejemplo: "2025-05-30T09:00:00.000Z"
                    break
            if date != "Desconocida":
                try:
                    # Convertir la fecha de la cadena ISO 8601 al formato deseado
                    parsed_date = datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%fZ")
                    date = parsed_date.strftime("%d/%m/%Y")  # Formato: dd/mm/yyyy
                except ValueError:
                    # Si ocurre algún error al convertir, dejar la fecha como estaba
                    date = "Desconocida"

            # Crear el nombre de la capa con la fecha extraída
            layer_title = f"Clorofila ({date})"
            # Agregar la capa WMS de Clorofila
            wms_layer = folium.WmsTileLayer(
                url='https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?',
                layers='Ifop_Sapo:Clorofila',
                fmt='image/png',
                transparent=True,
                version='1.1.0',
                name=layer_title,
                overlay=True,
                control=True,
                opacity=1.0
            )
            wms_layer.add_to(m)
            # Agregar la capa de isolíneas con el estilo ajustado
            wms_isolines = folium.WmsTileLayer(
                url='https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?',
                layers='Ifop_Sapo:Clorofila',  # La misma capa de datos
                styles='3_isolineas_clo',  # Aquí se define el estilo creado en GeoServer
                fmt='image/png',
                transparent=True,
                version='1.1.0',
                name='Isolíneas de Clorofila',  # Nombre visible en el control de capas
                overlay=True,
                control=True,
                opacity=1.0
            )
            # Agregar ambas capas al mapa
            wms_isolines.add_to(m)
            # Configurar URL de la leyenda
            legend_url = (
                "https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?"
                "REQUEST=GetLegendGraphic&"
                "VERSION=1.1.0&"
                "FORMAT=image/png&"
                "WIDTH=120&"
                "HEIGHT=50&"
                "LAYER=Ifop_Sapo:Clorofila&"
                "STYLE=3_clo_leyenda&"
                "&legend_options=fontSize:25"
            )

            # Agregar controles de capas al mapa
            folium.LayerControl(collapsed=False).add_to(m)
            # Guardar el archivo HTML del mapa
            temp_map_path = os.path.join(current_app.root_path, 'static', 'map_clo.html')
            m.save(temp_map_path)
            with open(temp_map_path, 'r') as f:
                mapa_html = f.read()

            # Limpia librerías redundantes del HTML generado automáticamente
            mapa_html = mapa_html.replace(
                '<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.js"></script>', '')
            mapa_html = mapa_html.replace(
                '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.css"/>', '')
            mapa_html = mapa_html.replace('<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>', '')
            mapa_html = mapa_html.replace(
                '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.2.2/dist/css/bootstrap.min.css"/>',
                '')

            return render_template('clo.html',
                                   mapa_html=mapa_html,
                                   legend_url=legend_url)
        except requests.exceptions.RequestException as e:
            return f"Error al obtener metadatos: {str(e)}", 500

    except Exception as e:
        return f"Error desconocido en la ruta '/clo': {str(e)}", 500


@main.route('/batimetria')
def batimetria():
    try:
        # Crear el mapa base
        center = session.get('center', [-35, -110])
        zoom = session.get('zoom', 4)
        m = folium.Map(
            location=center,
            zoom_start=zoom,
            tiles=None,  # 'Esri WorldStreetMap',
            minZoom=minzoom,
            maxZoom=maxzoom,
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
        # Añadir el mosaico base directamente, pero fuera del control de capas
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',  # (Opcional) texto en la esquina inferior
            name='Esri WorldStreetMap',  # El nombre que aparece en el mapa, pero no en LayerControl
            control=False  # No incluir en el control de capas
        ).add_to(m)
        # Cargar el shapefile de áreas marinas protegidas
        shapefile_path = '/Data/sapo_prueba/app/static/shp/amp_nac_shp/AMP_NACIONAL.shp'
        gdf = gpd.read_file(shapefile_path)
        for column in gdf.columns:
            if gdf[column].dtype == 'datetime64[ns]' or isinstance(gdf[column].iloc[0], pd.Timestamp):
                gdf[column] = gdf[column].astype(str)
        if 'geometry' in gdf.columns:
            gdf = gdf[gdf.geometry.notnull()]
            gdf = gdf[gdf.is_valid]
        else:
            raise ValueError(f"El shapefile en {shapefile_path} no contiene geometrías válidas.")
        # Cargar áreas marinas protegidas en el mapa
        fields = ['NOMBRE', 'TIPO_AMP', 'REGION']
        geojson = folium.GeoJson(gdf, name='Áreas Marinas Protegidas',
                                 style_function=lambda x: {'fillColor': 'lightgreen',
                                                           'color': 'green', 'weight': 1, 'fillOpacity': 0.5, },
                                 popup=folium.GeoJsonPopup(fields=fields, aliases=['Nombre', 'Tipo AMP', 'Región']),
                                 tooltip=folium.GeoJsonTooltip(fields=fields, aliases=['Nombre', 'Tipo AMP', 'Región']),
                                 show=False
                                 )
        geojson.add_to(m)
        # Agregar la capa de líneas de profundidad
        wms_isolines = folium.WmsTileLayer(
            url='https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?',
            layers='Ifop_Sapo:Profundidad',  # La misma capa de datos
            styles='4_profundidad',  # Aquí se define el estilo creado en GeoServer
            fmt='image/png',
            transparent=True,
            version='1.1.0',
            name='Batimetría (ETopo2)',  # Nombre visible en el control de capas
            overlay=True,
            control=True,
            opacity=1.0
        )
        # Agregar ambas capas al mapa
        wms_isolines.add_to(m)

        # Añadir controles de capa para el mapa
        folium.LayerControl(collapsed=False).add_to(m)
        # mapa_html = m._repr_html_()
        # Guardar el archivo HTML del mapa
        temp_map_path = os.path.join(current_app.root_path, 'static', 'map_bati.html')
        m.save(temp_map_path)
        with open(temp_map_path, 'r') as f:
            mapa_html = f.read()

        # Limpia librerías redundantes del HTML generado automáticamente
        mapa_html = mapa_html.replace(
            '<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.js"></script>', '')
        mapa_html = mapa_html.replace(
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.css"/>', '')
        mapa_html = mapa_html.replace('<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>', '')
        mapa_html = mapa_html.replace(
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.2.2/dist/css/bootstrap.min.css"/>',
            '')

        # Renderizar el mapa en la plantilla
        return render_template('estaciones.html', mapa_html=mapa_html)

    except Exception as e:
        # Manejar y devolver un error en caso de falla
        print(f"Error detectado: {str(e)}")
        return f"Error en el procesamiento del mapa: {str(e)}", 500


@main.route('/graficos_estacion1/<int:codigo_estacion>')
def graficos_estacion1(codigo_estacion):
    try:
        # Conectar a la base de datos
        conn = psycopg2.connect(**DATABASE_CONFIG)
        query = """
        SELECT * 
        FROM v_datos_estacion 
        WHERE codigo_estacion = %s AND fecha_año > 2013 and not temp is null
        """
        df = pd.read_sql_query(query, conn, params=(codigo_estacion,))
        df.columns = df.columns.str.lower()  # Convertir nombres de columnas a minúsculas
        conn.close()

        # Validación si no hay datos
        if df.empty:
            return jsonify({'error': f'No se encontraron datos para la estación {codigo_estacion}'}), 404

        # Procesar datos
        df['fecha'] = pd.to_datetime(dict(year=df['fecha_año'], month=df['mes'], day=df['dia']))
        # Ajustar la profundidad según la estación
        if codigo_estacion == 719:
            df = df[df['profundidad'] <= 1100]  # Para estación 719: usar profundidad 1100
        else:
            df = df[df['profundidad'] <= 50]  # Para otras estaciones: usar profundidad <= 50

        # Cálculo del perfil promedio
        perfil_promedio = df.groupby('profundidad')['temp'].mean()
        ultima_fecha = df['fecha'].max()
        perfil_ultima_medicion = df[df['fecha'] == ultima_fecha].set_index('profundidad')['temp']

        # Evitar NaN en los cálculos de diferencia
        perfil_promedio = perfil_promedio.fillna(0)  # Reemplazar NaN por 0 en el promedio
        perfil_ultima_medicion = perfil_ultima_medicion.fillna(0)  # Reemplazar NaN por 0 en última medición
        diferencia = perfil_ultima_medicion - perfil_promedio
        diferencia = diferencia.fillna(0)  # Reemplazar NaN por 0 en la diferencia

        # Matriz de calor
        heatmap_data = df.pivot_table(index='profundidad', columns='fecha', values='temp', aggfunc='mean')
        heatmap_data = heatmap_data.sort_index(ascending=True).fillna(0)  # Reemplazar NaN por 0 en la matriz
        # heatmap_data = heatmap_data.applymap(lambda x: None if x == 0 else x)

        # Preparar datos para el frontend
        response_data = {
            'heatmap': {
                'z': heatmap_data.values.tolist(),
                'x': heatmap_data.columns.strftime('%Y-%m-%d').tolist(),
                'y': heatmap_data.index.tolist(),
            },
            'perfil_promedio': {
                'x': perfil_promedio.tolist(),
                'y': perfil_promedio.index.tolist()
            },
            'ultima_medicion': {
                'x': perfil_ultima_medicion.tolist(),
                'y': perfil_ultima_medicion.index.tolist()
            },
            'diferencia': {
                'x': diferencia.tolist(),
                'y': diferencia.index.tolist()
            }
        }

        return jsonify(response_data)

    except Exception as e:
        # Manejo de errores genéricos
        print("Error detectado:", str(e))
        return jsonify({'error temperatura': f"Error creando gráficos: {str(e)}"}), 500


@main.route('/graficos_estacion2/<int:codigo_estacion>')
def graficos_estacion2(codigo_estacion):
    try:
        # Conectar a la base de datos
        conn = psycopg2.connect(**DATABASE_CONFIG)
        query = """
        SELECT * 
        FROM v_datos_estacion 
        WHERE codigo_estacion = %s AND fecha_año > 2013 and not salinidad is null
        """
        df = pd.read_sql_query(query, conn, params=(codigo_estacion,))
        df.columns = df.columns.str.lower()  # Convertir nombres de columnas a minúsculas
        conn.close()

        # Validación si no hay datos
        if df.empty:
            return jsonify({'error': f'No se encontraron datos para la estación {codigo_estacion}'}), 404

        # Procesar datos
        df['fecha'] = pd.to_datetime(dict(year=df['fecha_año'], month=df['mes'], day=df['dia']))
        # Ajustar la profundidad según la estación
        if codigo_estacion == 719:
            df = df[df['profundidad'] <= 1100]  # Para estación 719: usar profundidad 1100
        else:
            df = df[df['profundidad'] <= 50]  # Para otras estaciones: usar profundidad <= 50

        # Cálculo del perfil promedio
        perfil_promedio = df.groupby('profundidad')['salinidad'].mean()
        ultima_fecha = df['fecha'].max()
        perfil_ultima_medicion = df[df['fecha'] == ultima_fecha].set_index('profundidad')['salinidad']

        # Evitar NaN en los cálculos de diferencia
        perfil_promedio = perfil_promedio.fillna(0)  # Reemplazar NaN por 0 en el promedio
        perfil_ultima_medicion = perfil_ultima_medicion.fillna(0)  # Reemplazar NaN por 0 en última medición
        diferencia = perfil_ultima_medicion - perfil_promedio
        diferencia = diferencia.fillna(0)  # Reemplazar NaN por 0 en la diferencia

        # Matriz de calor
        heatmap_data = df.pivot_table(index='profundidad', columns='fecha', values='salinidad', aggfunc='mean')
        heatmap_data = heatmap_data.sort_index(ascending=True).fillna(0)  # Reemplazar NaN por 0 en la matriz
        # heatmap_data = heatmap_data.applymap(lambda x: None if x == 0 else x)

        # Preparar datos para el frontend
        response_data = {
            'heatmap': {
                'z': heatmap_data.values.tolist(),
                'x': heatmap_data.columns.strftime('%Y-%m-%d').tolist(),
                'y': heatmap_data.index.tolist(),
            },
            'perfil_promedio': {
                'x': perfil_promedio.tolist(),
                'y': perfil_promedio.index.tolist()
            },
            'ultima_medicion': {
                'x': perfil_ultima_medicion.tolist(),
                'y': perfil_ultima_medicion.index.tolist()
            },
            'diferencia': {
                'x': diferencia.tolist(),
                'y': diferencia.index.tolist()
            }
        }

        return jsonify(response_data)

    except Exception as e:
        # Manejo de errores genéricos
        print("Error detectado:", str(e))
        return jsonify({'error salinidad': f"Error creando gráficos: {str(e)}"}), 500


@main.route('/graficos_estacion3/<int:codigo_estacion>')
def graficos_estacion3(codigo_estacion):
    try:
        # Conectar a la base de datos
        conn = psycopg2.connect(**DATABASE_CONFIG)
        query = """
        SELECT * 
        FROM v_datos_estacion 
        WHERE codigo_estacion = %s AND fecha_año > 2013 and not oxigeno is null
        """
        df = pd.read_sql_query(query, conn, params=(codigo_estacion,))
        df.columns = df.columns.str.lower()  # Convertir nombres de columnas a minúsculas
        conn.close()

        # Validación si no hay datos
        if df.empty:
            return jsonify({'error': f'No se encontraron datos para la estación {codigo_estacion}'}), 404

        # Procesar datos
        df['fecha'] = pd.to_datetime(dict(year=df['fecha_año'], month=df['mes'], day=df['dia']))
        # Ajustar la profundidad según la estación
        if codigo_estacion == 719:
            df = df[df['profundidad'] <= 1100]  # Para estación 719: usar profundidad 1100
        else:
            df = df[df['profundidad'] <= 50]  # Para otras estaciones: usar profundidad <= 50

        # Cálculo del perfil promedio
        perfil_promedio = df.groupby('profundidad')['oxigeno'].mean()
        ultima_fecha = df['fecha'].max()
        perfil_ultima_medicion = df[df['fecha'] == ultima_fecha].set_index('profundidad')['oxigeno']

        # Evitar NaN en los cálculos de diferencia
        perfil_promedio = perfil_promedio.fillna(0)  # Reemplazar NaN por 0 en el promedio
        perfil_ultima_medicion = perfil_ultima_medicion.fillna(0)  # Reemplazar NaN por 0 en última medición
        diferencia = perfil_ultima_medicion - perfil_promedio
        diferencia = diferencia.fillna(0)  # Reemplazar NaN por 0 en la diferencia

        # Matriz de calor
        heatmap_data = df.pivot_table(index='profundidad', columns='fecha', values='oxigeno', aggfunc='mean')
        heatmap_data = heatmap_data.sort_index(ascending=True).fillna(0)  # Reemplazar NaN por 0 en la matriz
        # heatmap_data = heatmap_data.applymap(lambda x: None if x == 0 else x)

        # Preparar datos para el frontend
        response_data = {
            'heatmap': {
                'z': heatmap_data.values.tolist(),
                'x': heatmap_data.columns.strftime('%Y-%m-%d').tolist(),
                'y': heatmap_data.index.tolist(),
            },
            'perfil_promedio': {
                'x': perfil_promedio.tolist(),
                'y': perfil_promedio.index.tolist()
            },
            'ultima_medicion': {
                'x': perfil_ultima_medicion.tolist(),
                'y': perfil_ultima_medicion.index.tolist()
            },
            'diferencia': {
                'x': diferencia.tolist(),
                'y': diferencia.index.tolist()
            }
        }

        return jsonify(response_data)

    except Exception as e:
        # Manejo de errores genéricos
        print("Error detectado:", str(e))
        return jsonify({'error oxigeno': f"Error creando gráficos: {str(e)}"}), 500


@main.route('/graficos_estacion4/<int:codigo_estacion>')
def graficos_estacion4(codigo_estacion):
    try:
        # Conectar a la base de datos
        conn = psycopg2.connect(**DATABASE_CONFIG)
        query = """
        SELECT * 
        FROM v_datos_estacion 
        WHERE codigo_estacion = %s AND fecha_año > 2013 
        """
        df = pd.read_sql_query(query, conn, params=(codigo_estacion,))
        df.columns = df.columns.str.lower()  # Convertir nombres de columnas a minúsculas
        conn.close()

        # Validación si no hay datos
        if df.empty:
            return jsonify({'error': f'No se encontraron datos para la estación {codigo_estacion}'}), 404

        # Procesar datos
        df['fecha'] = pd.to_datetime(dict(year=df['fecha_año'], month=df['mes'], day=df['dia']))
        # Ajustar la profundidad según la estación
        if codigo_estacion == 719:
            df = df[df['profundidad'] <= 1100]  # Para estación 719: usar profundidad 1100
        else:
            df = df[df['profundidad'] <= 50]  # Para otras estaciones: usar profundidad <= 50

        # Cálculo del perfil promedio
        perfil_promedio = df.groupby('profundidad')['clorofila_a'].mean()
        ultima_fecha = df['fecha'].max()
        perfil_ultima_medicion = df[df['fecha'] == ultima_fecha].set_index('profundidad')['clorofila_a']

        # Evitar NaN en los cálculos de diferencia
        perfil_promedio = perfil_promedio.fillna(0)  # Reemplazar NaN por 0 en el promedio
        perfil_ultima_medicion = perfil_ultima_medicion.fillna(0)  # Reemplazar NaN por 0 en la última medición
        diferencia = perfil_ultima_medicion - perfil_promedio
        diferencia = diferencia.fillna(0)  # Reemplazar NaN por 0 en la diferencia

        # Cálculo de la suma de clorofila por fecha (reemplazo del heatmap)
        clorofila_sumada = (
            df.groupby('fecha')['clorofila_a']
            .sum()
            .sort_index()
            .fillna(0)  # Reemplazar NaN por 0
        )
        # Encontrar la profundidad con mayor clorofila para cada fecha
        if not df['clorofila_a'].isnull().all():
            # Filtrar datos con valores válidos de clorofila_a antes de calcular idxmax
            df_validos = df.dropna(subset=['clorofila_a'])

            mejor_profundidad = (
                df_validos.loc[df_validos.groupby('fecha')['clorofila_a'].idxmax()][
                    ['fecha', 'profundidad', 'clorofila_a']]
                .set_index('fecha')
                .sort_index()
            )
        else:
            # Si todos los valores son NaN, mejor_profundidad estará vacío
            mejor_profundidad = pd.DataFrame(columns=['fecha', 'profundidad', 'clorofila_a']).set_index('fecha')

        # Preparar datos para el frontend
        response_data = {
            'clorofila_sumada': {  # Nuevo dato para el gráfico de líneas
                'x': clorofila_sumada.index.strftime('%Y-%m-%d').tolist(),  # Fechas (eje X)
                'y': clorofila_sumada.tolist()  # Suma de clorofila (eje Y)
            },
            'mejor_profundidad': {
                'x': mejor_profundidad.index.strftime('%Y-%m-%d').tolist(),  # Fechas (eje X)
                'y': (-1 * mejor_profundidad['profundidad']).tolist()  # Profundidad (eje Y, negativa)
            },
            'perfil_promedio': {
                'x': perfil_promedio.tolist(),
                'y': perfil_promedio.index.tolist()
            },
            'ultima_medicion': {
                'x': perfil_ultima_medicion.tolist(),
                'y': perfil_ultima_medicion.index.tolist()
            },
            'diferencia': {
                'x': diferencia.tolist(),
                'y': diferencia.index.tolist()
            }
        }

        return jsonify(response_data)

    except Exception as e:
        # Manejo de errores genéricos
        print("Error detectado:", str(e))
        return jsonify({'error clorofila': f"Error creando gráficos: {str(e)}"}), 500


@main.route('/actualizar_mapa', methods=['POST'])
def actualizar_mapa():
    # Obtén la información enviada desde el cliente para el posicionamiento del mapa entre opciones
    data = request.json

    # Extrae las coordenadas y zoom del JSON enviado por el cliente
    center = data.get('center', [-35, -110])
    zoom = data.get('zoom', 4)

    # Guarda las coordenadas y el zoom en la sesión (clave global)
    session['center'] = center
    session['zoom'] = zoom

    # Devuelve confirmación
    return jsonify({'status': 'success', 'center': center, 'zoom': zoom})


@main.route('/todos')
def todos():
    try:
        # Crear el mapa base
        center = session.get('center', [-35, -110])
        zoom = session.get('zoom', 4)
        m = folium.Map(
            location=center,
            zoom_start=zoom,
            tiles=None,  # 'Esri WorldStreetMap',
            minZoom=minzoom,
            maxZoom=maxzoom,
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
        folium.plugins.Geocoder().add_to(m)
        # Añadir el mosaico base directamente, pero fuera del control de capas
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',  # (Opcional) texto en la esquina inferior
            name='Esri WorldStreetMap',  # El nombre que aparece en el mapa, pero no en LayerControl
            control=False  # No incluir en el control de capas
        ).add_to(m)
        folium.plugins.LocateControl().add_to(m)

        # If you want get the user device position after load the map, set auto_start=True
        # folium.plugins.LocateControl(auto_start=False).add_to(m)
        # --------------------------------------------------
        # Crear grupos de capas (ATSM, TSM, Clorofila)
        # --------------------------------------------------

        # Crear grupos de FeatureGroups
        fg_atsm = folium.FeatureGroup(name='ATSM (Anomalía de Temperatura)', show=True)
        fg_atsm_isolines = folium.FeatureGroup(name='Isolíneas de ATSM', show=True)

        fg_tsm = folium.FeatureGroup(name='TSM (Temperatura del Mar)', show=False)
        fg_tsm_isolines = folium.FeatureGroup(name='Isolíneas de TSM', show=False)

        fg_clorofila = folium.FeatureGroup(name='Clorofila', show=False)
        fg_clorofila_isolines = folium.FeatureGroup(name='Isolíneas de Clorofila', show=False)

        # ------------------
        # Isolineas Layers
        # ------------------
        folium.WmsTileLayer(
            url='https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?',
            layers='Ifop_Sapo:Anomalia_temperatura',
            styles='2_isolineas_atsm',
            fmt='image/png',
            transparent=True,
            version='1.1.0',
            name='Isolíneas de ATSM',
            overlay=True,
            control=True,
            opacity=1.0
        ).add_to(fg_atsm_isolines)

        folium.WmsTileLayer(
            url='https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?',
            layers='Ifop_Sapo:Temperatura',
            styles='1_isolineas_tsm',
            fmt='image/png',
            transparent=True,
            version='1.1.0',
            name='Isolíneas de TSM',
            overlay=True,
            control=True,
            opacity=1.0
        ).add_to(fg_tsm_isolines)

        folium.WmsTileLayer(
            url='https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?',
            layers='Ifop_Sapo:Clorofila',
            styles='3_isolineas_clo',
            fmt='image/png',
            transparent=True,
            version='1.1.0',
            name='Isolíneas de Clorofila',
            overlay=True,
            control=True,
            opacity=1.0
        ).add_to(fg_clorofila_isolines)

        # ------------------
        # Sat Layers
        # ------------------
        folium.WmsTileLayer(
            url='https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?',
            layers='Ifop_Sapo:Anomalia_temperatura',
            fmt='image/png',
            transparent=True,
            version='1.1.0',
            name='Anomalía de Temperatura',
            overlay=True,
            control=True,
            opacity=1.0
        ).add_to(fg_atsm)

        folium.WmsTileLayer(
            url='https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?',
            layers='Ifop_Sapo:Temperatura',
            fmt='image/png',
            transparent=True,
            version='1.1.0',
            name='Temperatura (TSM)',
            overlay=True,
            control=True,
            opacity=1.0
        ).add_to(fg_tsm)

        folium.WmsTileLayer(
            url='https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?',
            layers='Ifop_Sapo:Clorofila',
            fmt='image/png',
            transparent=True,
            version='1.1.0',
            name='Clorofila',
            overlay=True,
            control=True,
            opacity=1.0
        ).add_to(fg_clorofila)

        # Añadir grupo de batimetría (opcional)
        fg_batimetria = folium.FeatureGroup(name='Batimetría', show=False)
        folium.WmsTileLayer(
            url='https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?',
            layers='Ifop_Sapo:Profundidad',
            styles='4_profundidad',
            fmt='image/png',
            transparent=True,
            version='1.1.0',
            name='Batimetría (ETopo2)',
            overlay=True,
            control=True,
            opacity=1.0
        ).add_to(fg_batimetria)

        # ------------------
        # GeoJSON Layer (AMP)
        # ------------------
        geojson_path = '/Data/sapo_prueba/app/static/shp/amp_nac_shp/AMP_NACIONAL.geojson'
        gdf = gpd.read_file(geojson_path)

        # Convertir columnas de fechas si existen
        for column in gdf.columns:
            if gdf[column].dtype == 'datetime64[ns]' or isinstance(gdf[column].iloc[0], pd.Timestamp):
                gdf[column] = gdf[column].astype(str)

        fields = ['NOMBRE', 'TIPO_AMP', 'REGION']
        style = lambda x: {'fillColor': 'lightgreen', 'color': 'green', 'weight': 1, 'fillOpacity': 0.5}

        fg_amp = folium.FeatureGroup(name='Áreas Marinas Protegidas', show=False)
        folium.GeoJson(
            gdf,
            name='Áreas Marinas Protegidas',
            style_function=style,
            popup=folium.GeoJsonPopup(fields=fields, aliases=['Nombre', 'Tipo AMP', 'Región']),
            tooltip=folium.GeoJsonTooltip(fields=fields, aliases=['Nombre', 'Tipo AMP', 'Región']),
        ).add_to(fg_amp)
        # ------------------
        # GeoJSON Layer (AMERB)
        # ------------------
        # geojson_path = '/Data/sapo_prueba/app/static/shp/amerb_nac_shp/AMERB_NACIONAL.shp'
        # gdf = gpd.read_file(geojson_path)
        #
        # # Convertir columnas de fechas si existen
        # for column in gdf.columns:
        #     if gdf[column].dtype == 'datetime64[ns]' or isinstance(gdf[column].iloc[0], pd.Timestamp):
        #         gdf[column] = gdf[column].astype(str)
        #
        # fields = ['NOMBRE', 'COMUNA', 'REGION']
        # style = lambda x: {'fillColor': 'lightgreen', 'color': 'green', 'weight': 1, 'fillOpacity': 0.5}
        #
        # fg_amerb = folium.FeatureGroup(name='AMERB', show=False)
        # folium.GeoJson(
        #     gdf,
        #     name='AMERB',
        #     style_function=style,
        #     popup=folium.GeoJsonPopup(fields=fields, aliases=['Nombre', 'Comuna', 'Región']),
        #     tooltip=folium.GeoJsonTooltip(fields=fields, aliases=['Nombre', 'Comuna', 'Región']),
        # ).add_to(fg_amerb)

        # --------------------------
        # Capa de Buques Mejorada con AntPath
        # --------------------------

        # Conexión a la base de datos
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cursor = conn.cursor()

        # Consulta SQL (ordenada por buque y fecha)
        sql = "SELECT codigo, buque, fecha, longitud, latitud FROM track_buques ORDER BY codigo, fecha"
        cursor.execute(sql)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        # Diccionario de colores por tipo de código
        color_icons = {
            1: 'blue',
            2: 'gray',
            3: 'orange'
        }

        # Agrupar filas por código de buque
        buque_data = {}
        for row in rows:
            codigo = row[0]
            if codigo not in buque_data:
                buque_data[codigo] = []
            buque_data[codigo].append(row)

        # Crear un diccionario para almacenar los FeatureGroups por buque
        feature_groups = {}
        buques_groups = []

        # Procesar cada buque por separado
        for codigo, registros in buque_data.items():
            # Crear un FeatureGroup para cada buque si no existe
            nombre_buque = str(registros[0][1]).strip().title()  # Nombre del buque
            if codigo not in feature_groups:
                feature_groups[codigo] = folium.FeatureGroup(
                    name=nombre_buque,  # Nombre del grupo en la leyenda
                    show=True  # Mostrar el grupo activado por defecto
                )

            # Listas para las coordenadas del `AntPath` y los puntos (`CircleMarker`)
            antpath_coords = []
            ultimo_punto = None

            num_registros = len(registros)
            for idx, row in enumerate(registros):
                # Extraer y validar coordenadas
                try:
                    latitud = float(row[4])  # Latitud
                    longitud = float(row[3])  # Longitud
                except (ValueError, TypeError):  # Si hay valores inválidos
                    print(f"Error en latitud/longitud: {row}")
                    continue
                # Verificar que las coordenadas están en el rango esperado
                if not (-90 <= latitud <= 90 and -180 <= longitud <= 180):
                    print(f"Coordenadas fuera de rango: Latitud={latitud}, Longitud={longitud}")
                    continue

                # Formatear la fecha
                try:
                    fecha_original = row[2]  # Fecha desde la base de datos
                    fecha_formateada = fecha_original.strftime("%H:%M %d/%m/%Y")
                except AttributeError:
                    print(f"Fecha no válida para formatear: {row[2]}")
                    fecha_formateada = "Fecha inválida"

                # Calcular opacidad para los puntos (0.1 para antiguos, 1 para recientes)
                fill_opacity = 0.1 + (0.9 * (idx / (num_registros - 1))) if num_registros > 1 else 1

                # Guardar las coordenadas para el AntPath
                antpath_coords.append([latitud, longitud])
                if idx == num_registros - 1:  # Es el más reciente
                    ultimo_punto = {
                        "latitud": latitud,
                        "longitud": longitud,
                        "fecha": fecha_formateada
                    }

                # Crear un popup para el círculo
                popup_content = f"""
                        <div>
                            <strong>{nombre_buque}</strong><br>
                            <p>{fecha_formateada}</p>
                        </div>
                        """

                # Crear un marcador para cada punto
                circle = folium.CircleMarker(
                    location=[latitud, longitud],
                    radius=5,
                    popup=folium.Popup(popup_content, max_width=300),
                    color='black',
                    fill=True,
                    fill_color=color_icons.get(codigo, 'blue'),  # Color por tipo de buque
                    fill_opacity=fill_opacity,
                    weight=0.3,
                    tooltip=f"{nombre_buque}, {fecha_formateada}"
                )
                # Agregar el círculo (punto) al FeatureGroup correspondiente
                feature_groups[codigo].add_child(circle)

                # Dibujar un AntPath conectando los puntos (track) del buque
                if len(antpath_coords) > 1:
                    AntPath(
                        locations=antpath_coords,  # Coordenadas de la trayectoria
                        reverse=False,  # Invertir animación (acorde a la dirección)
                        dash_array=[10, 20],  # Estilo de línea (guiones y espacios)
                        color=color_icons.get(codigo, 'blue'),  # Color basado en el tipo
                        opacity=0.5,  # Opacidad de la trayectoria
                        weight=2,  # Grosor de la línea
                        delay=1500
                    ).add_to(feature_groups[codigo])
                # Agregar un Popup en la posición más reciente
                if ultimo_punto:
                    popup_actual = folium.Popup(
                        f"<strong>{nombre_buque}</strong><br>"
                        f"Lat: {ultimo_punto['latitud']:.5f}<br>"
                        f"Lon: {ultimo_punto['longitud']:.5f}<br>"
                        f"Fecha: {ultimo_punto['fecha']}",
                        max_width=250
                    )
                    folium.Marker(
                        location=[ultimo_punto['latitud'], ultimo_punto['longitud']],
                        icon=folium.Icon(color=color_icons.get(codigo, 'blue'), icon='info-sign'),
                        popup=popup_actual
                    ).add_to(feature_groups[codigo])

                    # Agregar el FeatureGroup del buque a la lista
                buques_groups.append(feature_groups[codigo])

        # Agregar cada FeatureGroup al mapa
        for group in feature_groups.values():
            m.add_child(group)

        # ------------------
        # Capa de Estaciones Oceanograficas
        # ------------------
        conn = psycopg2.connect(**DATABASE_CONFIG)
        cursor2 = conn.cursor()

        sql = """
                      SELECT nombre, 
                             detalle, 
                             latitud, 
                             longitud,
                             '1.- Est. Fijas' AS tipo_estacion,
                             geom, 
                             link, 
                             ubicacionid,
                             count
                      FROM public.estaciones_link3
                      WHERE tipo = 7 
                      ORDER BY tipo 
                      """
        cursor2.execute(sql)
        rows = cursor2.fetchall()
        cursor2.close()
        conn.close()

        estaciones_groups = []

        feature_groups = {}
        for row in rows:
            tipo = row[4]
            if tipo not in feature_groups:
                feature_groups[tipo] = folium.FeatureGroup(name=tipo)

            latitud = float(row[2].replace(',', '.'))
            longitud = float(row[3].replace(',', '.'))
            nombre = str(row[0]).strip().title()
            region = str(row[1]).strip().title()
            codigo_estacion = row[7]
            count = row[8] if row[8] is not None else 0  # Manejar valores `None`, asignando 0 si es `None`

            # Determinar si el botón debería estar habilitado o deshabilitado, y el estilo
            if count <= 0:
                button_disabled = 'disabled'
                button_style = 'background-color: #d6d6d6; color: #808080; border: none; cursor: not-allowed;'
            else:
                button_disabled = ''
                button_style = 'background-color: #007bff; color: white; border: none; cursor: pointer;'

            # Modificar el contenido del popup para incluir el script
            popup_content = f"""
                    <div>
                        <strong>{nombre}</strong><br>
                        <p>Región: {region}<br>Origen: {tipo}<br>Código: {codigo_estacion}</p>
                        <button type="button" 
                                style="{button_style} padding: 5px 10px; border-radius: 5px;"
                                onclick="mostrarGrafico({codigo_estacion},'{nombre}', '{region}', {latitud}, {longitud})"
                                {button_disabled}>
                            Ver Gráficos
                        </button>
                    </div>
                    """

            # circle = folium.CircleMarker(
            #     location=[latitud, longitud],
            #     radius=5,
            #     popup=folium.Popup(popup_content, max_width=300),
            #     color='black',
            #     fill=True,
            #     fill_color=color_icons.get(tipo, 'blue'),
            #     fill_opacity=0.9,
            #     weight=0.3,
            #     tooltip=nombre
            # )
            # feature_groups[tipo].add_child(circle)
            circle_with_symbol = folium.Marker(
                location=[latitud, longitud],
                popup=folium.Popup(popup_content, max_width=300),
                icon=folium.DivIcon(
                    html=f"""
                    <div style="
                        text-align: center;
                        border: 2px solid black;
                        border-radius: 50%;
                        width: 15px;
                        height: 15px;
                        background-color: {color_icons.get(tipo, 'white')};
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        font-size: 10px;
                        color: blue;">
                        ★
                    </div>
                    """
                ),
                tooltip=nombre
            )
            feature_groups[tipo].add_child(circle_with_symbol)

            estaciones_groups.append(feature_groups[tipo])

        for group in feature_groups.values():
            m.add_child(group)
        # Agregar controles de capas al mapa
        # folium.LayerControl(collapsed=False).add_to(m)

        # ------------------------------------------------------
        # Agregar todos los FeatureGroups al mapa

        m.add_child(fg_atsm)
        m.add_child(fg_tsm)
        m.add_child(fg_clorofila)
        m.add_child(fg_atsm_isolines)
        m.add_child(fg_tsm_isolines)
        m.add_child(fg_clorofila_isolines)
        m.add_child(fg_batimetria)
        m.add_child(fg_amp)
        # m.add_child(fg_amerb)

        # GroupedLayerControl(
        #     groups={
        #         'ATSM (Anomalía de Temperatura)': [fg_atsm, fg_atsm_isolines],
        #         'TSM (Temperatura del Mar)': [fg_tsm, fg_tsm_isolines],
        #         'Clorofila': [fg_clorofila, fg_clorofila_isolines],
        #         'Otros': [fg_amp,fg_batimetria],
        #         'Buques': buques_groups,
        #         'Estaciones': estaciones_groups
        #     },
        #     exclusive_groups=False,  # Las subcapas no son exclusivas entre sí
        #     collapsed=False  # Mostrar todos los grupos expandidos
        # ).add_to(m)

        GroupedLayerControl(
            groups={
                'Capas Satelitales': [fg_atsm, fg_tsm, fg_clorofila],
                'Isolineas': [fg_atsm_isolines, fg_tsm_isolines, fg_clorofila_isolines],
                'Otras Capas': [fg_amp, fg_batimetria],
                'Buques Científicos': buques_groups,
                'Estaciones Oceanográficas': estaciones_groups
            },
            exclusive_groups=False,  # Las subcapas no son exclusivas entre sí
            collapsed=False  # Mostrar todos los grupos expandidos
        ).add_to(m)

        # Guardar el mapa como HTML
        temp_map_path = os.path.join(current_app.root_path, 'static', 'map_todos.html')
        m.save(temp_map_path)

        # Leer el archivo generado y renderizar
        with open(temp_map_path, 'r') as f:
            mapa_html = f.read()

        return render_template('todos.html', mapa_html=mapa_html)

    except Exception as e:

        return render_template('error.html', mensaje=f"Ocurrió un error inesperado: {str(e)}"), 500


@main.route('/comparar')
def comparar():
    try:
        # Variables básicas
        center = session.get('center', [-35, -110])
        zoom = session.get('zoom', 4)

        # Crear el mapa base
        m = folium.Map(
            location=center,
            zoom_start=zoom,
            tiles=None,
            minZoom=minzoom,
            maxZoom=maxzoom
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


@main.route('/tsm2')
def tsm2():
    try:
        # Definir las constantes del mapa
        center = session.get('center', [-35, -110])
        zoom = session.get('zoom', 4)

        m = folium.Map(
            location=center,
            zoom_start=zoom,
            tiles=None,  # 'Esri WorldStreetMap',
            minZoom=minzoom,
            maxZoom=maxzoom,
        )
        # Añadir el mosaico base directamente, pero fuera del control de capas
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',  # (Opcional) texto en la esquina inferior
            name='Esri WorldStreetMap',  # El nombre que aparece en el mapa, pero no en LayerControl
            control=False  # No incluir en el control de capas
        ).add_to(m)
        # Añadir el plugin MousePosition al mapa
        formatter = "function(lat, lng) {return `Lat: ${lat.toFixed(5)}, Lng: ${lng.toFixed(5)}`;}"

        mouse_position = MousePosition(
            position="bottomleft",  # Posición donde se mostrará (arriba a la derecha)
            separator=" | ",
            empty_string="",
            lng_first=False,
            num_digits=4,  # Número de decimales para mostrar
            prefix="Coordenadas:",  # Prefijo del texto
            lat_formatter=None,
            lng_formatter=None,
            formatter=formatter  # Mostrar las posiciones como se definió anteriormente
        )
        mouse_position.add_to(m)

        try:
            # wms_url = 'https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?service=WMS&request=GetCapabilities'
            url = "https://pae-paha.pacioos.hawaii.edu/thredds/wms/dhw_5km?service=WMS"

            web_map_services = WebMapService(url)
            layer = "CRW_SST"

            wms = web_map_services.contents[layer]
            name = wms.title
            # name = wms.title
            # lon = (wms.boundingBox[0] + wms.boundingBox[2]) / 2.0
            # lat = (wms.boundingBox[1] + wms.boundingBox[3]) / 2.0
            # center = lat, lon

            time_interval = "{0}/{1}".format(
                wms.timepositions[0].strip(), wms.timepositions[-1].strip()
            )
            style = "boxfill/sst_36"
            if style not in wms.styles:
                style = None
            wms_tile_layer = folium.WmsTileLayer(
                url=url,
                name=name,
                styles=style,
                fmt="image/png",
                transparent=True,
                layers=layer,
                overlay=True,
                COLORSCALERANGE="1.2,28",
            ).add_to(m)

            folium.plugins.TimestampedWmsTileLayers(
                wms_tile_layer,
                period="P1D",
                time_interval=time_interval,
            ).add_to(m)

            folium.LayerControl().add_to(m)

            # Guardar el archivo HTML del mapa
            temp_map_path = os.path.join(current_app.root_path, 'static', 'map_tsm.html')
            m.save(temp_map_path)
            with open(temp_map_path, 'r') as f:
                mapa_html = f.read()

            # Limpia librerías redundantes del HTML generado automáticamente
            mapa_html = mapa_html.replace(
                '<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.js"></script>', '')
            mapa_html = mapa_html.replace(
                '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.css"/>', '')
            mapa_html = mapa_html.replace('<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>', '')
            mapa_html = mapa_html.replace(
                '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.2.2/dist/css/bootstrap.min.css"/>',
                '')

            # Renderizar el template HTML
            # mapa_html = m._repr_html_()
            return render_template('tsm2.html',
                                   mapa_html=mapa_html)

        except requests.exceptions.RequestException as e:
            return f"Error al obtener metadatos: {str(e)}", 500

    except Exception as e:
        return f"Error desconocido en la ruta '/tsm2': {str(e)}", 500


