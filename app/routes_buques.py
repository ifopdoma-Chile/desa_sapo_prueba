from flask import Blueprint, render_template, session, current_app,jsonify
import folium
from folium.plugins import SideBySideLayers, GroupedLayerControl, MousePosition, AntPath,TimestampedWmsTileLayers
import geopandas as gpd
import pandas as pd
import os
import psycopg2

from app.db import get_db_connection
from app.routes import main

maxzoom = 12
minzoom = 3


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
            zoomDelta=0.15,  # cada click + / - cambia 0.25 en vez de 1
            zoomSnap=0.15,
            wheelPxPerZoomLevel=250,
        )
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
        # Diccionario de colores por tipo de código
        # --------------------------
        # Capa de Buques Mejorada con AntPath
        # --------------------------

        # Conexión a la base de datos
        conn = get_db_connection()
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
        #map_html = m._repr_html_()
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
