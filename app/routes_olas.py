from flask import Blueprint, render_template, session, current_app, jsonify, url_for
import os
import re
import folium
from folium.plugins import SideBySideLayers, GroupedLayerControl, MousePosition, AntPath, TimestampedWmsTileLayers

from folium import plugins
import xarray as xr
import numpy as np
import json

from datetime import datetime, timedelta

import requests
import xml.etree.ElementTree as ET
import pandas as pd
from app.routes import main
import logging

maxzoom = 12
minzoom = 3

WAVE_PATTERN_YMD_HM = re.compile(r'^(\d{8}_\d{4})_Olas\.nc$')   # YYYYMMDD_HHMM_Olas.nc
WAVE_PATTERN_8 = re.compile(r'^(\d{8})_Olas\.nc$')             # 8 dígitos (YYYYMMDD o DDMMYYYY)
WAVE_DATA_DIR = '/Data/sapo_prueba/app/static/olas'


def _parse_wave_datetime_from_filename(filename: str) -> datetime:
    m1 = WAVE_PATTERN_YMD_HM.match(filename)
    if m1:
        return datetime.strptime(m1.group(1), "%Y%m%d_%H%M")

    m2 = WAVE_PATTERN_8.match(filename)
    if m2:
        token = m2.group(1)
        # Primero intentamos YYYYMMDD (tu caso: 20260220)
        try:
            return datetime.strptime(token, "%Y%m%d")
        except ValueError:
            # Fallback por si llegara DDMMYYYY (caso antiguo: 20022026)
            return datetime.strptime(token, "%d%m%Y")

    raise ValueError(f"Nombre de archivo de olas no soportado: {filename}")



def get_latest_wave_file():
    try:
        candidates: list[tuple[datetime, str]] = []

        for f in os.listdir(WAVE_DATA_DIR):
            full = os.path.join(WAVE_DATA_DIR, f)
            if not os.path.isfile(full):
                continue
            if os.path.getsize(full) <= 0:
                continue

            if not (WAVE_PATTERN_YMD_HM.match(f) or WAVE_PATTERN_8.match(f)):
                continue

            try:
                dt = _parse_wave_datetime_from_filename(f)
            except Exception as e:
                logging.error(f"Archivo de olas ignorado por fecha inválida: {f} ({e})")
                continue

            candidates.append((dt, f))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[0])
        return candidates[-1][1]

    except Exception as e:
        logging.error(f"Error leyendo directorio olas: {e}")
        return None


def process_wave_file(filename):
    try:
        app_static = os.path.join(current_app.root_path, 'static')
        os.makedirs(app_static, exist_ok=True)

        json_path = os.path.join(app_static, 'wave_data_latest.json')
        nc_path = os.path.join(WAVE_DATA_DIR, filename)

        ds = xr.open_dataset(nc_path)

        # Si existieran como dims en otros archivos, selecciona el primero
        if 'time' in ds.dims:
            ds = ds.isel(time=0)
        if 'step' in ds.dims:
            ds = ds.isel(step=0)
        if 'surface' in ds.dims:
            ds = ds.isel(surface=0)

        # Tu NetCDF trae estas variables:
        mag = ds['altura_ola'].values
        direc = ds['direccion_ola'].values
        lats = ds['latitude'].values
        lons = ds['longitude'].values

        rad = np.deg2rad(direc)
        u = mag * np.sin(rad)
        v = mag * np.cos(rad)

        if lats[0] < lats[-1]:
            lats, u, v = lats[::-1], np.flipud(u), np.flipud(v)

        ny, nx = u.shape
        dx = float(lons[1] - lons[0])
        dy = float(abs(lats[1] - lats[0]))

        dt = _parse_wave_datetime_from_filename(filename)

        header = {
            "parameterCategory": 2,
            "nx": nx,
            "ny": ny,
            "lo1": float(lons[0]),
            "la1": float(lats[0]),
            "lo2": float(lons[-1]),
            "la2": float(lats[-1]),
            "dx": dx,
            "dy": dy,
            "refTime": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "forecastTime": 0
        }

        data_json = [
            {"header": {**header, "parameterNumber": 2}, "data": np.nan_to_num(u).flatten().tolist()},
            {"header": {**header, "parameterNumber": 3}, "data": np.nan_to_num(v).flatten().tolist()}
        ]

        with open(json_path, "w") as f:
            json.dump(data_json, f, separators=(',', ':'))

        ds.close()
        return {"fecha_dato": dt.strftime("%d/%m/%Y %H:%M")}

    except Exception as e:
        logging.error(f"Error procesando olas: {e}")
        return None


@main.route('/olas')
def olas():
    center = session.get('center', [-32, -72])
    zoom = session.get('zoom', 5)

    filename = get_latest_wave_file()
    if not filename:
        logging.error(f"No se encontraron archivos de olas en {WAVE_DATA_DIR}")
        metadata = None
    else:
        metadata = process_wave_file(filename)

    wave_date = metadata["fecha_dato"] if metadata else "Sin fecha"

    m = folium.Map(location=center, zoom_start=zoom, tiles=None, minZoom=minzoom, maxZoom=maxzoom)

    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
        attr='Esri', name='Esri WorldStreetMap', control=False
    ).add_to(m)

    app_static = os.path.join(current_app.root_path, 'static')
    json_path = os.path.join(app_static, 'wave_data_latest.json')
    wave_available = os.path.exists(json_path)

    data_url = url_for('static', filename='wave_data_latest.json')

    VELOCITY_SCRIPT = f"""
    <script src="https://cdn.jsdelivr.net/npm/leaflet-velocity@1.8.1/dist/leaflet-velocity.min.js"></script>
    <script>
    document.addEventListener("DOMContentLoaded", function() {{
        fetch('{data_url}?t=' + Date.now())
          .then(res => {{
              if (!res.ok) throw new Error('HTTP ' + res.status);
              return res.json();
          }})
          .then(data => {{
              var mapElement = document.querySelector('.folium-map');
              if (!mapElement) return;
              var map = window[mapElement.id];
              if (!map || !map.whenReady) return;

              map.whenReady(function() {{
                  var waveLayer = L.velocityLayer({{
                      data: data,
                      maxVelocity: 10,
                      velocityScale: 0.1,
                      displayValues: true,
                      displayOptions: {{
                          velocityType: 'Oleaje',
                          position: 'bottomleft',
                          emptyString: 'Sin datos',
                          angleConvention: 'meteoCW',
                          displayBackground: true
                      }},
                      colorScale: ["#3288bd","#66c2a5","#abdda4","#e6f598","#fee08b","#fdae61","#f46d43","#d53e4f"]
                  }});

                  waveLayer.addTo(map);
                  L.control.layers(null, {{"Oleaje ({wave_date})": waveLayer}}, {{collapsed:false}}).addTo(map);
              }});
          }})
          .catch(err => console.error("Error cargando olas:", err));
    }});
    </script>
    """

    temp_path = os.path.join(current_app.root_path, 'static', 'map_olas.html')
    m.save(temp_path)
    with open(temp_path, encoding='utf-8') as f:
        mapa_html = f.read()

    if wave_available:
        mapa_html = mapa_html.replace('</body>', VELOCITY_SCRIPT + '</body>')
    else:
        logging.error(f"No existe {json_path} (no se inyecta Velocity)")

    return render_template('olas.html', mapa_html=mapa_html)