from flask import Blueprint, render_template, session, current_app, request, Response
import folium
from folium.plugins import SideBySideLayers, GroupedLayerControl, MousePosition, AntPath,TimestampedWmsTileLayers
import geopandas as gpd
import pandas as pd
import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

from branca.element import Element, MacroElement
from jinja2 import Template

from app.routes import main

maxzoom = 12
minzoom = 3


@main.route('/proxy_wms_featureinfo')
def proxy_wms_featureinfo():
    url_wms = "https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms"
    # Solo permite ciertos parámetros
    params = {k: v for k, v in request.args.items() if k.upper() in [
        "SERVICE", "REQUEST", "VERSION", "SRS", "BBOX", "WIDTH", "HEIGHT", "LAYERS", "QUERY_LAYERS", "INFO_FORMAT", "X", "Y"
    ]}
    # Reenvía la consulta GetFeatureInfo al GeoServer
    backend_r = requests.get(url_wms, params=params, timeout=10)
    resp = Response(backend_r.content, status=backend_r.status_code, content_type=backend_r.headers.get('content-type'))
    # Ahora, CORS permitido localmente:
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


@main.route('/tsm')
def tsm():
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
        # folium.plugins.Geocoder().add_to(m)
        # Añadir el mosaico base directamente, pero fuera del control de capas
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',  # (Opcional) texto en la esquina inferior
            name='Esri WorldStreetMap',  # El nombre que aparece en el mapa, pero no en LayerControl
            control=False  # No incluir en el control de capas
        ).add_to(m)
        # Cargar el shapefile de áreas marinas protegidas
        shapefile_path = '/Data/python/sapo_prueba/app/static/shp/amp_nac_shp/AMP_NACIONAL.shp'
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
                "&legend_options=fontSize:25"
            )
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
            tiles= None, #'Esri WorldStreetMap',
            minZoom =minzoom,
            maxZoom =maxzoom,
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
        # Añadir el mosaico base directamente, pero fuera del control de capas
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',  # (Opcional) texto en la esquina inferior
            name='Esri WorldStreetMap',  # El nombre que aparece en el mapa, pero no en LayerControl
            control=False  # No incluir en el control de capas
        ).add_to(m)
        # Cargar el shapefile de áreas marinas protegidas
        shapefile_path = '/Data/python/sapo_prueba/app/static/shp/amp_nac_shp/AMP_NACIONAL.shp'
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
            tiles= None, #'Esri WorldStreetMap',
            minZoom =minzoom,
            maxZoom =maxzoom,
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
        # Añadir el mosaico base directamente, pero fuera del control de capas
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',  # (Opcional) texto en la esquina inferior
            name='Esri WorldStreetMap',  # El nombre que aparece en el mapa, pero no en LayerControl
            control=False  # No incluir en el control de capas
        ).add_to(m)
        try:
            # Cargar el shapefile de áreas marinas protegidas
            shapefile_path = '/Data/python/sapo_prueba/app/static/shp/amp_nac_shp/AMP_NACIONAL.shp'
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
                                     show = False
                                     )
            geojson.add_to(m)
            wms_url = 'https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?service=WMS&request=GetCapabilities'
            response = requests.get(wms_url)
            response.raise_for_status()  # Verifica que no haya errores HTTP

            # Parsear el XML con el manejo del namespace
            root = ET.fromstring(response.content)

            # Declarar el espacio de nombres basado en el WMS
            namespaces = {'wms': 'http://www.opengis.net/wms'}

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

@main.route('/clo2')
def clo2():
    try:
        # Crear el mapa base
        center = session.get('center', [-35, -110])
        zoom = session.get('zoom', 4)
        m = folium.Map(
            location=center,
            zoom_start=zoom,
            tiles= None, #'Esri WorldStreetMap',
            minZoom =minzoom,
            maxZoom =maxzoom,
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
        # Añadir el mosaico base directamente, pero fuera del control de capas
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',  # (Opcional) texto en la esquina inferior
            name='Esri WorldStreetMap',  # El nombre que aparece en el mapa, pero no en LayerControl
            control=False  # No incluir en el control de capas
        ).add_to(m)
        try:
            # Cargar el shapefile de áreas marinas protegidas
            shapefile_path = '/Data/python/sapo_prueba/app/static/shp/amp_nac_shp/AMP_NACIONAL.shp'
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
                                     show = False
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
            layer_name = "clo_nuevo"
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
                layers='Ifop_Sapo:clo_nuevo',
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
                layers='Ifop_Sapo:clo_nuevo',  # La misma capa de datos
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
                "LAYER=Ifop_Sapo:clo_nuevo&"
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
        return f"Error desconocido en la ruta '/clo2': {str(e)}", 500

@main.route('/batimetria')
def batimetria():
    try:
        # Crear el mapa base
        center = session.get('center', [-35, -110])
        zoom = session.get('zoom', 4)
        m = folium.Map(
            location=center,
            zoom_start=zoom,
            tiles= None, #'Esri WorldStreetMap',
            minZoom =minzoom,
            maxZoom =maxzoom,
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
        # Añadir el mosaico base directamente, pero fuera del control de capas
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',  # (Opcional) texto en la esquina inferior
            name='Esri WorldStreetMap',  # El nombre que aparece en el mapa, pero no en LayerControl
            control=False  # No incluir en el control de capas
        ).add_to(m)
        # Cargar el shapefile de áreas marinas protegidas
        shapefile_path = '/Data/python/sapo_prueba/app/static/shp/amp_nac_shp/AMP_NACIONAL.shp'
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
        #mapa_html = m._repr_html_()
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

