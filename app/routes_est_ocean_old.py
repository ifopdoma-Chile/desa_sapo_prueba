from flask import Blueprint, render_template, session, current_app,jsonify
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

@main.route('/estaciones_ocean')
def estaciones_ocean():
    try:
        center = session.get('center', [-35, -110])
        zoom = session.get('zoom', 4)
        conn = get_db_connection()
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
            tiles=None, #'Esri WorldStreetMap',
            minZoom =minzoom,
            maxZoom =maxzoom,
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
                                 show = False)
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
                            Gráficos Históricos
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

        #mapa_html = m._repr_html_()
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


@main.route('/get_est_ocean/<int:codigo_estacion>')
def get_est_ocean(codigo_estacion):
    try:
        conn = get_db_connection()
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


@main.route('/graficos_estacion1/<int:codigo_estacion>')
def graficos_estacion1(codigo_estacion):
    try:
        # Conectar a la base de datos
        conn = get_db_connection()
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
        #heatmap_data = heatmap_data.applymap(lambda x: None if x == 0 else x)

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
        conn = get_db_connection()
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
        #heatmap_data = heatmap_data.applymap(lambda x: None if x == 0 else x)

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
        conn = get_db_connection()
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
        #heatmap_data = heatmap_data.applymap(lambda x: None if x == 0 else x)

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
        conn = get_db_connection()
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


@main.route('/get_est_ocean_todas')
def get_all_estaciones():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Consulta para obtener todas las estaciones


        sql = """
              SELECT ubicacionid,
                     nombre, 
                     detalle, 
                     latitud, 
                     longitud,
                     '1.- Est. Fijas' AS tipo_estacion
              FROM public.estaciones_link3
              WHERE tipo = 7 
              ORDER BY tipo 
              """

        cursor.execute(sql)
        estaciones = cursor.fetchall()
        cursor.close()
        conn.close()

        if not estaciones:
            return jsonify({'error': 'No se encontraron estaciones'})

        # Formatear la respuesta a JSON
        estaciones_json = []
        for estacion in estaciones:
            codigo, nombre, detalle, latitud, longitud, tipo = estacion
            estaciones_json.append({
                'codigo': codigo,
                'nombre': nombre,
                'detalle': detalle,
                'coordenadas': f"Lat: {latitud}, Lon: {longitud}",
                'tipo': tipo
            })

        return jsonify(estaciones_json)

    except Exception as e:
        print(f"Error en get_all_estaciones: {str(e)}")
        return jsonify({'error': f'Error al obtener estaciones: {str(e)}'})
