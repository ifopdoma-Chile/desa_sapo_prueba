from flask import Blueprint, render_template, session, current_app, jsonify
import os
import re
import time
import xarray as xr
import folium
from folium.plugins import SideBySideLayers, GroupedLayerControl, MousePosition, AntPath, TimestampedWmsTileLayers
from folium import plugins
import numpy as np
import json
from io import BytesIO
import rasterio
from datetime import datetime, timedelta
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from requests.auth import HTTPBasicAuth
from app.routes import main
import pytz
import logging



maxzoom = 12
minzoom = 3

chile_tz = pytz.timezone('America/Santiago')
CURRENT_PATTERN = re.compile(r'^(\d{8})_Corrientes\.nc$')
CURRENT_DATA_DIR = '/Data2/sapo2024/Historico/Corriente'

CURRENT_NX = 1080
CURRENT_NY = 511
CURRENT_LO1 = -180.0
CURRENT_LO2 = 179.9583
CURRENT_LA1 = 90.0
CURRENT_LA2 = -80.0
CURRENT_DX = abs(CURRENT_LO2 - CURRENT_LO1) / CURRENT_NX
CURRENT_DY = abs(CURRENT_LA2 - CURRENT_LA1) / CURRENT_NY

def get_latest_current_file():
    try:
        files = [
            f for f in os.listdir(CURRENT_DATA_DIR)
            if CURRENT_PATTERN.match(f)
            and os.path.getsize(os.path.join(CURRENT_DATA_DIR, f)) > 0
        ]
    except Exception as e:
        logging.error(f"No se pudo leer directorio corrientes: {e}")
        return None

    if not files:
        return None

    return max(
        files,
        key=lambda x: datetime.strptime(
            CURRENT_PATTERN.match(x).group(1),
            "%Y%m%d"
        )
    )

def process_current_file(filename):
    try:
        app_static = os.path.join(current_app.root_path, 'static')
        os.makedirs(app_static, exist_ok=True)

        metadata_path = os.path.join(app_static, 'current_metadata.json')
        json_path = os.path.join(app_static, 'current_data_latest.json')

        nc_path = os.path.join(CURRENT_DATA_DIR, filename)

        ds = xr.open_dataset(nc_path)

        # --------------------------------------------------
        # 🔹 Seleccionar superficie y primer tiempo
        # --------------------------------------------------
        if 'time' in ds.dims:
            ds = ds.isel(time=0)
        if 'depth' in ds.dims:
            ds = ds.isel(depth=0)

        # --------------------------------------------------
        # 🔹 REDUCCIÓN DE RESOLUCIÓN (CLAVE DEL RENDIMIENTO)
        # --------------------------------------------------
        factor = 4   # ← 5–7 ideal para corrientes

        u_var = 'u_current' if 'u_current' in ds.data_vars else 'uo'
        v_var = 'v_current' if 'v_current' in ds.data_vars else 'vo'
        u = ds[u_var].values[::factor, ::factor]
        v = ds[v_var].values[::factor, ::factor]
        lats = ds['latitude'].values[::factor]
        lons = ds['longitude'].values[::factor]

        # --------------------------------------------------
        # 🔹 Normalizar latitudes (Norte → Sur)
        # --------------------------------------------------
        if lats[0] < lats[-1]:
            lats = lats[::-1]
            u = np.flipud(u)
            v = np.flipud(v)

        # --------------------------------------------------
        # 🔹 LIMPIEZA + REDONDEO (reduce peso JSON)
        # --------------------------------------------------
        u = np.round(np.nan_to_num(u), 3)
        v = np.round(np.nan_to_num(v), 3)

        ny, nx = u.shape

        dx = float(lons[1] - lons[0]) if len(lons) > 1 else 1.0
        dy = float(abs(lats[1] - lats[0])) if len(lats) > 1 else 1.0

        lo1, lo2 = float(lons[0]), float(lons[-1])
        la1, la2 = float(lats[0]), float(lats[-1])

        # --------------------------------------------------
        # 🔹 Fecha del archivo
        # --------------------------------------------------
        fecha_utc = datetime.strptime(filename[:8], "%Y%m%d")
        ref_time_iso = fecha_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        header_base = {
            "parameterCategory": 2,
            "nx": nx,
            "ny": ny,
            "lo1": lo1,
            "la1": la1,
            "lo2": lo2,
            "la2": la2,
            "dx": abs(dx),
            "dy": abs(dy),
            "refTime": ref_time_iso,
            "forecastTime": 0
        }

        u_component = {
            "header": {**header_base, "parameterNumber": 2},
            "data": u.flatten().tolist()
        }

        v_component = {
            "header": {**header_base, "parameterNumber": 3},
            "data": v.flatten().tolist()
        }

        # JSON compacto
        with open(json_path, "w") as f:
            json.dump([u_component, v_component], f, separators=(',', ':'))

        # --------------------------------------------------
        # 🔹 Metadata
        # --------------------------------------------------
        fecha_local = pytz.utc.localize(fecha_utc).astimezone(chile_tz)

        metadata = {
            "archivo": filename,
            "fecha_dato": fecha_local.strftime("%d/%m/%Y %H:%M"),
            "fecha_proceso": datetime.now().isoformat()
        }

        with open(metadata_path, "w") as f:
            json.dump(metadata, f)

        ds.close()
        return metadata

    except Exception as e:
        logging.error(f"Error procesando corrientes: {e}")
        return None


def fetch_current_from_wcs():
    try:
        app_static = os.path.join(current_app.root_path, 'static')
        os.makedirs(app_static, exist_ok=True)

        json_path = os.path.join(app_static, 'current_data_latest.json')
        metadata_path = os.path.join(app_static, 'current_metadata.json')

        auth = HTTPBasicAuth(GEOSERVER_USER, GEOSERVER_PASS)
        wcs_url = f"{GEOSERVER_URL}/Ifop_Sapo/wcs"

        # WCS 2.0.1 con coverageId (formato: workspace__coverage)
        params_u = {
            "service": "WCS", "version": "2.0.1", "request": "GetCoverage",
            "coverageId": "Ifop_Sapo__uo",
            "format": "image/tiff"
        }

        params_v = {
            "service": "WCS", "version": "2.0.1", "request": "GetCoverage",
            "coverageId": "Ifop_Sapo__vo",
            "format": "image/tiff"
        }

        resp_u = requests.get(wcs_url, params=params_u, auth=auth, timeout=120)
        resp_u.raise_for_status()
        resp_v = requests.get(wcs_url, params=params_v, auth=auth, timeout=120)
        resp_v.raise_for_status()

        with rasterio.open(BytesIO(resp_u.content)) as src:
            u = src.read(1).astype(np.float64)

        with rasterio.open(BytesIO(resp_v.content)) as src:
            v = src.read(1).astype(np.float64)

        # Reducir resolución (factor 8 para manejar 4320x2041)
        factor = 8
        u = u[::factor, ::factor]
        v = v[::factor, ::factor]

        u = np.nan_to_num(u, nan=0.0)
        v = np.nan_to_num(v, nan=0.0)
        u = np.round(u, 3)
        v = np.round(v, 3)

        ny, nx = u.shape

        with rasterio.open(BytesIO(resp_u.content)) as src_ref:
            left, bottom, right, top = src_ref.bounds
        # nx, ny son las dimensiones después de reducir resolución con factor
        # dx, dy son el espaciado de la grilla reducida
        dx = (right - left) / nx
        dy = (top - bottom) / ny

        ref_time_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        header_base = {
            "parameterCategory": 2, "nx": nx, "ny": ny,
            "lo1": left, "la1": top, "lo2": right, "la2": bottom,
            "dx": abs(dx), "dy": abs(dy),
            "refTime": ref_time_iso, "forecastTime": 0
        }

        u_component = {"header": {**header_base, "parameterNumber": 2}, "data": u.flatten().tolist()}
        v_component = {"header": {**header_base, "parameterNumber": 3}, "data": v.flatten().tolist()}

        with open(json_path, "w") as f:
            json.dump([u_component, v_component], f, separators=(',', ':'))

        fecha_local = datetime.now(pytz.utc).astimezone(chile_tz)
        metadata = {
            "fuente": "WCS GeoServer",
            "fecha_dato": fecha_local.strftime("%d/%m/%Y %H:%M"),
            "fecha_proceso": datetime.now().isoformat()
        }
        with open(metadata_path, "w") as f:
            json.dump(metadata, f)

        return metadata, True

    except Exception as e:
        logging.error(f"Error obteniendo corrientes desde WCS: {e}")
        return None, False


def ensure_latest_current_processed():
    """Solo WCS desde GeoServer (sin fallback local)."""
    wcs_metadata, wcs_ok = fetch_current_from_wcs()
    return wcs_metadata, wcs_ok


@main.route('/corrientes')
def corrientes():
    center = session.get('center', [-30, -72])
    zoom = session.get('zoom', 4)

    metadata, current_available = ensure_latest_current_processed()

    m = folium.Map(
        location=center,
        zoom_start=zoom,
        tiles=None,
        minZoom=minzoom,
        maxZoom=maxzoom,
        zoomDelta=1,
        zoomSnap=1,
        wheelPxPerZoomLevel=250,
    )
    
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
        attr='Esri',
        name='Esri WorldStreetMap',
        control=False,
    ).add_to(m)

    mouse_position = MousePosition(
        position="bottomleft",
        separator=" | ",
        empty_string="",
        lng_first=False,
        num_digits=4,
        prefix="Coordenadas:"
    )
    mouse_position.add_to(m)
    folium.plugins.LocateControl(position='bottomleft').add_to(m)

    alturamar_date = get_wms_date("Alturamar_v2")

    folium.WmsTileLayer(
        url='https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms',
        layers='Ifop_Sapo:Alturamar_v2',
        name=f'Altura de mar ({alturamar_date})',
        fmt='image/png',
        transparent=True,
        overlay=True,
        opacity=0.6,
        control=True,
        tileSize=256,
        no_wrap=True,
    ).add_to(m)

    folium.WmsTileLayer(
        url='https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms',
        layers='Ifop_Sapo:Alturamar_v2',
        styles='7_alturamar_iso',
        name='Isolíneas Altura de mar',
        fmt='image/png',
        transparent=True,
        overlay=True,
        control=True,
        opacity=1.0,
        tileSize=256,
        no_wrap=True,
    ).add_to(m)

    current_date = metadata["fecha_dato"] if metadata else "Sin fecha"
    current_date = current_date.split(" ")[0] if current_date != "Sin fecha" else "Sin fecha"

    VELOCITY_SCRIPT = f"""
        <script src="https://cdn.jsdelivr.net/npm/leaflet-velocity@1.8.1/dist/leaflet-velocity.min.js"></script>
        <script>
        document.addEventListener("DOMContentLoaded", function() {{

            fetch('/app/static/current_data_latest.json?t=' + Date.now())
              .then(response => response.json())
              .then(data => {{
                  window.currentData = data;
                  var mapElement = document.querySelector('.folium-map');
                  if (!mapElement) return;
                  var map = window[mapElement.id];
                  map.whenReady(function() {{
                      var velocityLayer = L.velocityLayer({{
                            data: data,
                            maxVelocity: 20,
                            velocityScale: 0.15,
                            particleAge: 60,
                            lineWidth: 2,
                            particleMultiplier: 1/300,
                            frameRate: 15,
                            displayValues: true,
                            displayOptions: {{
                                velocityType: 'Corriente',
                                position: 'bottomleft',
                                emptyString: 'Sin datos',
                                displayBackground: false
                            }},
                           colorScale: ['black','black'],
                      }});

                      velocityLayer.addTo(map);
                      var overlays = {{}};
                      for (var id in map._layers) {{
                          var layer = map._layers[id];

                          if (layer instanceof L.TileLayer.WMS) {{
                              if (layer.wmsParams.layers &&
                                  layer.wmsParams.layers.includes("Alturamar_v2") &&
                                  !layer.wmsParams.styles) {{
                                  overlays["Altura de mar ({alturamar_date})"] = layer;
                              }}

                              if (layer.wmsParams.layers &&
                                  layer.wmsParams.layers.includes("Alturamar_v2") &&
                                  layer.wmsParams.styles &&
                                  layer.wmsParams.styles.includes("7_alturamar_iso")) {{
                                  overlays["Isolíneas Altura de mar"] = layer;
                              }}
                          }}
                      }}

                      overlays["Corrientes ({current_date})"] = velocityLayer;

                      L.control.layers(null, overlays, {{
                          collapsed: false
                      }}).addTo(map);

                  }});

              }})
              .catch(err => console.error("Error cargando corrientes:", err));

        }});
        </script>
        """

    temp_path = os.path.join(current_app.root_path, 'static', 'mapc.html')
    m.save(temp_path)

    with open(temp_path, encoding='utf-8') as f:
        mapa_html = f.read()

    if current_available:
        mapa_html = mapa_html.replace(
            '</body>',
            VELOCITY_SCRIPT + '</body>'
        )

    return render_template('corrientes.html', mapa_html=mapa_html)


GEOSERVER_URL = os.environ.get('GEOSERVER_URL', "https://gis-eco.ifop.cl/geoserver")
GEOSERVER_USER = os.environ.get('GEOSERVER_USER', "agarcia")
GEOSERVER_PASS = os.environ.get('GEOSERVER_PASS', "dream2004")
GEOSERVER_WMS_URL = os.environ.get('GEOSERVER_WMS_URL', "https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms")

WIND_PATTERN = re.compile(r'^(\d{8}_\d{4})_Viento_ECMWF\.nc$')
WIND_DATA_DIR = '/Data2/sapo2024/Historico/Viento'

WIND_NX = 1440
WIND_NY = 721
WIND_DX = 0.25
WIND_DY = 0.25
WIND_LO1 = -180.0
WIND_LO2 = 179.75
WIND_LA1 = 90.0
WIND_LA2 = -90.0


def get_latest_wind_file():
    try:
        files = [
            f for f in os.listdir(WIND_DATA_DIR)
            if WIND_PATTERN.match(f)
            and os.path.getsize(os.path.join(WIND_DATA_DIR, f)) > 0
        ]
    except Exception as e:
        logging.error(f"No se pudo leer directorio viento: {e}")
        return None

    if not files:
        return None

    return max(
        files,
        key=lambda x: datetime.strptime(
            WIND_PATTERN.match(x).group(1),
            "%Y%m%d_%H%M"
        )
    )

def process_wind_file(filename):

    try:
        app_static = os.path.join(current_app.root_path, 'static')
        os.makedirs(app_static, exist_ok=True)

        metadata_path = os.path.join(app_static, 'wind_metadata.json')
        json_path = os.path.join(app_static, 'wind_data_latest.json')

        nc_path = os.path.join(WIND_DATA_DIR, filename)

        ds = xr.open_dataset(nc_path)

        # Seleccionar primer tiempo si existe
        if 'time' in ds.dims:
            ds = ds.isel(time=0)

        u = ds['u10'].values
        v = ds['v10'].values
        lats = ds['latitude'].values
        lons = ds['longitude'].values

        ny, nx = u.shape

        # Resolución espacial
        dx = float(lons[1] - lons[0]) if len(lons) > 1 else 1.0
        dy = float(abs(lats[1] - lats[0])) if len(lats) > 1 else 1.0

        lo1 = float(lons[0])
        lo2 = float(lons[-1])

        la1 = float(lats[0])
        la2 = float(lats[-1])

        # Normalizar para que la1 sea norte y la2 sur
        if la1 < la2:
            la1, la2 = la2, la1
            u = np.flipud(u)
            v = np.flipud(v)

        # Fecha ISO (UTC)
        fecha_utc = datetime.strptime(filename[:13], "%Y%m%d_%H%M")
        ref_time_iso = fecha_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        header_base = {
            "parameterCategory": 2,
            "nx": nx,
            "ny": ny,
            "lo1": lo1,
            "la1": la1,
            "lo2": lo2,
            "la2": la2,
            "dx": abs(dx),
            "dy": abs(dy),
            "refTime": ref_time_iso,
            "forecastTime": 0
        }

        u_component = {
            "header": {**header_base, "parameterNumber": 2},
            "data": np.nan_to_num(u).flatten().tolist()
        }

        v_component = {
            "header": {**header_base, "parameterNumber": 3},
            "data": np.nan_to_num(v).flatten().tolist()
        }

        with open(json_path, "w") as f:
            json.dump([u_component, v_component], f, separators=(',', ':'))

        # Metadata
        fecha_local = pytz.utc.localize(fecha_utc).astimezone(chile_tz)

        metadata = {
            "archivo": filename,
            "fecha_dato": fecha_local.strftime("%d/%m/%Y %H:%M"),
            "fecha_proceso": datetime.now().isoformat()
        }

        with open(metadata_path, "w") as f:
            json.dump(metadata, f)

        ds.close()
        return metadata

    except Exception as e:
        logging.error(f"Error procesando viento: {e}")
        return None


def fetch_wind_from_wcs():
    """Obtiene datos de viento desde GeoServer vía WCS 2.0.1 (GetCoverage en GeoTIFF).
    
    Reemplaza la lectura de archivos NetCDF locales usando las capas publicadas
    Ifop_Sapo__u10 / Ifop_Sapo__v10 en GeoServer.
    """
    try:
        app_static = os.path.join(current_app.root_path, 'static')
        os.makedirs(app_static, exist_ok=True)

        json_path = os.path.join(app_static, 'wind_data_latest.json')
        metadata_path = os.path.join(app_static, 'wind_metadata.json')

        auth = HTTPBasicAuth(GEOSERVER_USER, GEOSERVER_PASS)
        wcs_url = f"{GEOSERVER_URL}/Ifop_Sapo/wcs"

        # Obtener la última fecha disponible desde WMS GetCapabilities
        latest_time = None
        try:
            wms_url = f"{GEOSERVER_URL}/Ifop_Sapo/wms"
            caps_params = {
                'service': 'WMS', 'request': 'GetCapabilities', 'version': '1.3.0'
            }
            caps_r = requests.get(wms_url, params=caps_params, auth=auth, timeout=30, verify=False)
            if caps_r.status_code == 200:
                import re
                for layer in ['u10', 'v10']:
                    pattern = rf'<Layer>.*?<Name>{layer}</Name>.*?<Dimension[^>]*name="time"[^>]*>(.*?)</Dimension>'
                    match = re.search(pattern, caps_r.text, re.DOTALL)
                    if match:
                        dim_text = match.group(1).strip()
                        # Tomar el último tiempo disponible (separado por comas)
                        times = [t.strip() for t in dim_text.split(',') if t.strip()]
                        if times:
                            latest_time = times[-1]
                        # También intentar con el default
                        default_match = re.search(r'default="([^"]+)"', match.group())
                        if default_match:
                            latest_time = default_match.group(1)
                        break
        except Exception:
            pass

        # Construir parámetros como lista de tuplas para permitir múltiples "subset"
        # Nota: se omite el subset de tiempo porque GeoServer ya devuelve el dato más
        # reciente por defecto. Si se requiere una fecha específica, usar:
        # ("subset", 'time("YYYY-MM-DDT00:00:00Z")')
        def make_wcs_params(coverage_id):
            return [
                ("service", "WCS"),
                ("version", "2.0.1"),
                ("request", "GetCoverage"),
                ("coverageId", coverage_id),
                ("format", "image/tiff"),
                ("subset", "Long(-180,180)"),
                ("subset", "Lat(-90,90)"),
            ]

        # Consultar u10 (componente zonal del viento)
        resp_u = requests.get(
            wcs_url, params=make_wcs_params("Ifop_Sapo__u10"),
            auth=auth, timeout=120, verify=False
        )
        resp_u.raise_for_status()

        # Consultar v10 (componente meridional del viento)
        resp_v = requests.get(
            wcs_url, params=make_wcs_params("Ifop_Sapo__v10"),
            auth=auth, timeout=120, verify=False
        )
        resp_v.raise_for_status()

        # Leer GeoTIFFs con rasterio
        with rasterio.open(BytesIO(resp_u.content)) as src_u:
            u = src_u.read(1).astype(np.float64)
            transform_u = src_u.transform

        with rasterio.open(BytesIO(resp_v.content)) as src_v:
            v = src_v.read(1).astype(np.float64)

        # Reemplazar NaN con 0
        u = np.nan_to_num(u, nan=0.0)
        v = np.nan_to_num(v, nan=0.0)

        # Verificar consistencia de dimensiones
        if u.shape != v.shape:
            raise ValueError(f"Dimensiones inconsistentes: u={u.shape}, v={v.shape}")

        ny, nx = u.shape

        # Extraer metadatos de georeferenciación del GeoTIFF
        # Transform afín: | a, b, c |
        #                 | d, e, f |
        # donde:
        #   a = dx (ancho de píxel en grados de longitud)
        #   e = dy (alto de píxel en grados de latitud, negativo si decrece)
        #   c = lo1 (longitud superior-izquierda)
        #   f = la1 (latitud superior-izquierda)
        dx = abs(transform_u.a)
        dy = abs(transform_u.e)
        lo1 = transform_u.c          # longitud de la esquina superior-izquierda
        la1 = transform_u.f          # latitud de la esquina superior-izquierda
        lo2 = lo1 + nx * dx          # longitud de la esquina inferior-derecha
        la2 = la1 - ny * dy          # latitud de la esquina inferior-derecha
        la1 = round(la1, 2)
        lo2 = round(lo2, 2)
        la2 = round(la2, 2)
        dx = round(dx, 4)
        dy = round(dy, 4)

        # Fecha de referencia
        if latest_time:
            ref_dt = datetime.strptime(latest_time.replace('Z', '').split('.')[0], "%Y-%m-%dT%H:%M:%S")
            ref_time_iso = ref_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            ref_time_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        header_base = {
            "parameterCategory": 2,
            "nx": nx,
            "ny": ny,
            "lo1": lo1,
            "la1": la1,
            "lo2": lo2,
            "la2": la2,
            "dx": dx,
            "dy": dy,
            "refTime": ref_time_iso,
            "forecastTime": 0
        }

        u_component = {
            "header": {**header_base, "parameterNumber": 2},
            "data": np.round(u, 3).flatten().tolist()
        }

        v_component = {
            "header": {**header_base, "parameterNumber": 3},
            "data": np.round(v, 3).flatten().tolist()
        }

        with open(json_path, "w") as f:
            json.dump([u_component, v_component], f, separators=(',', ':'))

        # Metadata
        if latest_time:
            try:
                ref_dt_utc = datetime.strptime(latest_time.replace('Z', '').split('.')[0], "%Y-%m-%dT%H:%M:%S")
                ref_dt_utc = ref_dt_utc.replace(tzinfo=pytz.utc)
                fecha_local = ref_dt_utc.astimezone(chile_tz)
                fecha_dato_str = fecha_local.strftime("%d/%m/%Y %H:%M")
            except Exception:
                fecha_dato_str = datetime.now(pytz.utc).astimezone(chile_tz).strftime("%d/%m/%Y %H:%M")
        else:
            fecha_dato_str = datetime.now(pytz.utc).astimezone(chile_tz).strftime("%d/%m/%Y %H:%M")

        metadata = {
            "fuente": "WCS GeoServer",
            "fecha_dato": fecha_dato_str,
            "fecha_proceso": datetime.now().isoformat(),
            "geoserver_time": latest_time or "desconocida",
            "shape": f"{ny}x{nx}"
        }
        with open(metadata_path, "w") as f:
            json.dump(metadata, f)

        logging.info(f"Viento desde WCS OK: {nx}x{ny}, fecha={latest_time}")
        return metadata, True

    except Exception as e:
        logging.error(f"Error obteniendo datos desde WCS: {e}")
        return None, False


def ensure_latest_wind_processed():
    """Solo WCS desde GeoServer (sin fallback local ni caché)."""
    wcs_metadata, wcs_ok = fetch_wind_from_wcs()
    return wcs_metadata, wcs_ok

def get_wms_date(layer_name="presatm2"):
    try:
        url = 'https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?service=WMS&request=GetCapabilities'
        r = requests.get(url, timeout=10)
        r.raise_for_status()

        root = ET.fromstring(r.content)
        ns = {'wms': 'http://www.opengis.net/wms'}

        for layer in root.findall(".//wms:Layer", ns):
            name = layer.find("wms:Name", ns)
            if name is not None and name.text == layer_name:
                dim = layer.find("wms:Dimension", ns)
                if dim is not None:
                    raw = dim.text.strip()
                    dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%fZ")
                    return dt.strftime("%d/%m/%Y")

    except Exception as e:
        logging.error(f"Error obteniendo fecha WMS: {e}")

    return "Desconocida"

@main.route('/vientos')
def vientos():

    center = session.get('center', [-30, -72])
    zoom = session.get('zoom', 4)


    metadata, wind_available = ensure_latest_wind_processed()
    wms_date = get_wms_date()

    m = folium.Map(
        location=center,
        zoom_start=zoom,
        tiles=None,
        minZoom=minzoom,
        maxZoom=maxzoom,
        zoomDelta=1,
        zoomSnap=1,
        wheelPxPerZoomLevel=250,
    )
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
        attr='Esri',  # (Opcional) texto en la esquina inferior
        name='Esri WorldStreetMap',  # El nombre que aparece en el mapa, pero no en LayerControl
        control=False,  # No incluir en el control de capas
        # no_wrap=True  # Asegura que el mapa base también se repita
    ).add_to(m)

    formatter = """
            function(lat, lng) {
                // Si la longitud es positiva pero estamos en la "copia" de la izquierda
                var virtual_lng = lng;
                if (lng > 0 && map.getCenter().lng < -100) { virtual_lng = lng - 360; }
                return `Lat: ${lat.toFixed(5)}, Lng: ${virtual_lng.toFixed(5)}`;
            }
            """
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
    folium.plugins.LocateControl(position='bottomleft').add_to(m)
    # Presión
    folium.WmsTileLayer(
        url='https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms',
        layers='Ifop_Sapo:presatm2',
        name=f'Presión Atmosférica ({wms_date})',
        fmt='image/png',
        transparent=True,
        overlay=True,
        opacity=0.5,
        control=True,
        tileSize=256,
        no_wrap=True,
    ).add_to(m)

    # Isolíneas
    folium.WmsTileLayer(
        url='https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms',
        layers='Ifop_Sapo:presatm2',
        styles='6_presatm_iso',
        name='Isolíneas PresAtm',
        fmt='image/png',
        transparent=True,
        overlay=True,
        control=True,
        opacity=1.0,
        tileSize=256,
        no_wrap=True,
    ).add_to(m)

    #folium.LayerControl(collapsed=False).add_to(m)

    wind_date = metadata["fecha_dato"] if metadata else "Sin fecha"
    wind_date = wind_date.split(" ")[0] if wind_date != "Sin fecha" else "Sin fecha"

    VELOCITY_SCRIPT = f"""
    <script src="https://cdn.jsdelivr.net/npm/leaflet-velocity@1.8.1/dist/leaflet-velocity.min.js"></script>
    <script>
    document.addEventListener("DOMContentLoaded", function() {{

        fetch('/app/static/wind_data_latest.json?t=' + Date.now())
          .then(response => response.json())
          .then(data => {{
                  window.windData = data;
              var mapElement = document.querySelector('.folium-map');
              if (!mapElement) return;

              var map = window[mapElement.id];

              map.whenReady(function() {{

                  var velocityLayer = L.velocityLayer({{
                      data: data,
                      maxVelocity: 20,
                      velocityScale: 0.01,
                      displayValues: true,
                      displayOptions: {{
                          velocityType: 'Viento',
                          position: 'bottomleft',
                          emptyString: 'Sin datos'
                      }},
                      colorScale: ['black','black'],
                  }});

                  velocityLayer.addTo(map);

                  var overlays = {{}};

                  for (var id in map._layers) {{
                      var layer = map._layers[id];

                      if (layer instanceof L.TileLayer.WMS) {{
                          if (layer.wmsParams.layers.includes("presatm2") &&
                              !layer.wmsParams.styles) {{
                              overlays["Presión Atmosférica ({wms_date})"] = layer;
                          }}

                          if (layer.wmsParams.styles &&
                              layer.wmsParams.styles.includes("6_presatm_iso")) {{
                              overlays["Isolíneas PresAtm"] = layer;
                          }}
                      }}
                  }}

                  overlays["Viento ({wind_date})"] = velocityLayer;

                  L.control.layers(null, overlays, {{
                      collapsed: false
                  }}).addTo(map);

              }});

          }})
          .catch(err => console.error("Error cargando viento:", err));

    }});
    </script>
    """

    temp_path = os.path.join(current_app.root_path, 'static', 'mapv.html')
    m.save(temp_path)

    with open(temp_path, encoding='utf-8') as f:
        mapa_html = f.read()

    if wind_available:
        mapa_html = mapa_html.replace(
            '</body>',
            VELOCITY_SCRIPT + '</body>'
        )

    return render_template('vientos.html', mapa_html=mapa_html)


