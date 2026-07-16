from flask import render_template, session, current_app
import folium
from folium.plugins import MousePosition
import os
from app.routes import main
from datetime import datetime, timedelta

maxzoom = 12
minzoom = 3
import requests
import xml.etree.ElementTree as ET

def get_atsm_times():
    url = "https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?service=WMS&request=GetCapabilities"

    try:
        r = requests.get(url, timeout=10)
        root = ET.fromstring(r.content)

        ns = {'wms': 'http://www.opengis.net/wms'}

        for layer in root.findall(".//wms:Layer", ns):
            name = layer.find("wms:Name", ns)

            # Buscar tanto ATSM_v2 como Ifop_Sapo:ATSM_v2
            if name is not None and name.text in ["ATSM_v2", "Ifop_Sapo:ATSM_v2"]:

                dim = layer.find("wms:Dimension", ns)

                if dim is not None and dim.attrib.get("name") == "time":
                    text = dim.text.strip()

                    # CASO LISTA
                    if "," in text:
                        return [t.strip() for t in text.split(",")]

                    # CASO RANGO
                    elif "/" in text:
                        start, end, step = text.split("/")

                        times = []
                        current = datetime.fromisoformat(start.replace("Z", ""))

                        end_dt = datetime.fromisoformat(end.replace("Z", ""))

                        while current <= end_dt:
                            times.append(current.isoformat() + "Z")
                            current += timedelta(days=1)

                        return times

        return []

    except Exception as e:
        print("Error obteniendo tiempos:", e)
        return []


@main.route('/nubes')
def nubes():

    center = session.get('center', [-35, -110])
    zoom = session.get('zoom', 4)

    # =========================
    # MAPA BASE
    # =========================
    m = folium.Map(
        location=center,
        zoom_start=zoom,
        tiles=None,
        minZoom=minzoom,
        maxZoom=maxzoom,
        zoomDelta=0.15,
        zoomSnap=0.15,
        wheelPxPerZoomLevel=250,
    )

    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
        attr='Esri',
        name='Base',
        control=False
    ).add_to(m)

    # =========================
    # COORDENADAS
    # =========================
    formatter = "function(lat, lng) {return `Lat: ${lat.toFixed(5)}, Lng: ${lng.toFixed(5)}`;}"
    MousePosition(
        position="bottomleft",
        separator=" | ",
        prefix="Coordenadas:",
        num_digits=5,
        formatter=formatter
    ).add_to(m)

    # =========================
    # ATSM - Las capas se crean dinámicamente en JavaScript
    # No añadimos capas WMS estáticas aquí
    # =========================

    # =========================
    # NUBES - Capa WMS global
    # =========================
    isolines_group = folium.FeatureGroup(
        name="Nubes",
        overlay=True,
        control=True,
        show=True,
    ).add_to(m)

    folium.WmsTileLayer(
        url='https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?',
        layers='Ifop_Sapo:Nubes_v2',
        styles='9_Nubes',
        fmt='image/png',
        transparent=True,
        version='1.1.0',
        name='Nubes',
        overlay=True,
        control=False,
        opacity=1.0,
        tileSize=512,
    ).add_to(isolines_group)

    folium.LayerControl(collapsed=False).add_to(m)

    # =========================
    # SCRIPT ANIMACIÓN + LOGS
    # =========================
    times = get_atsm_times()

    # Convertir las fechas a formato legible
    times_formatted = []
    if times:
        for t in times:
            try:
                dt = datetime.fromisoformat(t.replace("Z", ""))
                times_formatted.append(dt.strftime("%d/%m/%Y"))
            except:
                times_formatted.append(t)



    # =========================
    # GUARDAR HTML
    # =========================
    temp_map_path = os.path.join(current_app.root_path, 'static', 'map_atsm.html')
    m.save(temp_map_path)

    with open(temp_map_path, 'r') as f:
        mapa_html = f.read()

    # limpiar librerías duplicadas
    mapa_html = mapa_html.replace(
        '<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.js"></script>', '')
    mapa_html = mapa_html.replace(
        '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.css"/>', '')

    # insertar script
    # mapa_html = mapa_html.replace(
    #     '</body>',
    #     ATSM_ANIMATION_SCRIPT + '</body>'
    # )

    return render_template('atsm_10d.html', mapa_html=mapa_html)
