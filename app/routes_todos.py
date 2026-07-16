from flask import Blueprint, render_template, session, current_app
import folium
from folium.plugins import SideBySideLayers, GroupedLayerControl, MousePosition, AntPath,TimestampedWmsTileLayers
import geopandas as gpd
import pandas as pd
import os
import psycopg2

from app.routes import main
from app.db import get_db_connection

maxzoom = 12
minzoom = 3

@main.route('/')
def home():
    return todos()

@main.route('/todos')
def todos():
    try:
        # Crear el mapa base
        center = session.get('center', [-27.87, -105.55])
        zoom = session.get('zoom', 8)
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
        folium.plugins.Geocoder().add_to(m)
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

        # If you want get the user device position after load the map, set auto_start=True
        #folium.plugins.LocateControl(auto_start=False).add_to(m)
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
        geojson_path = '/Data/python/sapo_prueba/app/static/shp/amp_nac_shp/AMP_NACIONAL.geojson'
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

        # ------------------
        #Capa de Estaciones Oceanograficas
        # ------------------
        conn = get_db_connection()
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
                            Gráficos Históricos
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
        #folium.LayerControl(collapsed=False).add_to(m)

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

        GroupedLayerControl(
            groups={
                'Capas Satelitales': [fg_atsm, fg_tsm, fg_clorofila],
                'Isolineas': [fg_atsm_isolines, fg_tsm_isolines, fg_clorofila_isolines],
                'Otras Capas': [fg_amp,fg_batimetria],
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
