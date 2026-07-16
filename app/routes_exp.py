from flask import render_template, session, current_app
import folium
from folium.plugins import SideBySideLayers, GroupedLayerControl, MousePosition, AntPath,TimestampedWmsTileLayers
import os
import requests
from owslib.wms import WebMapService

from app.routes import main
maxzoom = 12
minzoom = 3


@main.route('/tsm2')
def tsm2():
    try:
        # Definir las constantes del mapa
        center = session.get('center', [-35, -110])
        zoom = session.get('zoom', 4)

        m = folium.Map(
            location=center,
            zoom_start=zoom,
            tiles=None, #'Esri WorldStreetMap',
            minZoom =minzoom,
            maxZoom =maxzoom,
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
            #wms_url = 'https://gis-eco.ifop.cl/geoserver/Ifop_Sapo/wms?service=WMS&request=GetCapabilities'
            url = "https://pae-paha.pacioos.hawaii.edu/thredds/wms/dhw_5km?service=WMS"

            web_map_services = WebMapService(url)
            layer = "CRW_SST"

            wms = web_map_services.contents[layer]
            name = wms.title
            #name = wms.title
            #lon = (wms.boundingBox[0] + wms.boundingBox[2]) / 2.0
            #lat = (wms.boundingBox[1] + wms.boundingBox[3]) / 2.0
            #center = lat, lon

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
            #mapa_html = m._repr_html_()
            return render_template('tsm2.html',
                                   mapa_html=mapa_html)

        except requests.exceptions.RequestException as e:
            return f"Error al obtener metadatos: {str(e)}", 500

    except Exception as e:
        return f"Error desconocido en la ruta '/tsm2': {str(e)}", 500

# #--------------------------------------
# #Desde acá es la prueba de tsm con las fechas:
# #--------------------------------------
#
# import netCDF4
# import datetime as dt
# from functools import lru_cache
# import matplotlib
# matplotlib.use("Agg")
# import matplotlib.pyplot as plt
# from matplotlib.colors import Normalize
#
# NETCDF_UV_PATH = "/Data/sapo_prueba/app/static/UVClimCroco.nc"  # ajusta a tu ruta real
#
#
# def matlab_datenum_to_datetime(dn_array):
#     out = []
#     for dn in np.asarray(dn_array, dtype=float):
#         ordinal = int(dn); frac = dn - ordinal
#         out.append(dt.datetime.fromordinal(ordinal) + dt.timedelta(days=frac) - dt.timedelta(days=366))
#     return out
#
# @lru_cache(maxsize=1)
# def load_uv_cached(nc_path: str):
#     with netCDF4.Dataset(nc_path, mode="r") as ds:
#         lon = ds.variables["lon"][:]     # (nx,)
#         lat = ds.variables["lat"][:]     # (ny,)
#         time = ds.variables["time"][:]
#         u = ds.variables["u"][:]         # (t, ny, nx)
#         v = ds.variables["v"][:]         # (t, ny, nx)
#     # Enmascara solo donde ambas son 0.0 (tierra)
#     mask_land = (u == 0.0) & (v == 0.0)
#     u = np.where(mask_land, np.nan, u).astype(np.float32)
#     v = np.where(mask_land, np.nan, v).astype(np.float32)
#     fechas = [d.strftime("%Y-%m-%d") for d in matlab_datenum_to_datetime(time)]
#     return lon, lat, fechas, u, v
#
# def build_leaflet_velocity_payload(lon, lat, u2d, v2d, stride=1):
#     """
#     Formato 'windy' para Leaflet-velocity.
#     - lon: (nx,), lat: (ny,)
#     - u2d, v2d: (ny, nx) en m/s
#     Deja datos en orden N->S (requerido por el plugin).
#     """
#     lon = np.asarray(lon); lat = np.asarray(lat)
#     u2d = np.asarray(u2d, dtype=np.float32)
#     v2d = np.asarray(v2d, dtype=np.float32)
#
#     lat_is_ascending = lat.size > 1 and (lat[1] > lat[0])  # Sur->Norte
#     if lat_is_ascending:
#         lat_grid = lat[::-1]
#         u_grid = u2d[::-1, :]
#         v_grid = v2d[::-1, :]
#     else:
#         lat_grid = lat
#         u_grid = u2d
#         v_grid = v2d
#
#     # Submuestreo
#     stride = max(1, int(stride))
#     lon_s = lon[::stride]
#     lat_s = lat_grid[::stride]
#     u_s = u_grid[::stride, ::stride]
#     v_s = v_grid[::stride, ::stride]
#
#     nx = int(lon_s.size)
#     ny = int(lat_s.size)
#
#     dx = float(np.mean(np.diff(lon_s))) if nx > 1 else 0.0
#     dy = float(np.mean(np.abs(np.diff(lat_s)))) if ny > 1 else 0.0  # positivo
#
#     header_common = {
#         "parameterCategory": 2,
#         "parameterUnit": "m.s-1",
#         "lo1": float(lon_s.min()),
#         "la1": float(lat_s[0]),    # Norte
#         "lo2": float(lon_s.max()),
#         "la2": float(lat_s[-1]),   # Sur
#         "dx": dx,
#         "dy": dy,
#         "nx": nx,
#         "ny": ny,
#         "refTime": "2013-01-01 00:00:00"
#     }
#     header_u = dict(header_common, **{
#         "parameterNumber": 2,
#         "parameterNumberName": "eastward_wind"
#     })
#     header_v = dict(header_common, **{
#         "parameterNumber": 3,
#         "parameterNumberName": "northward_wind"
#     })
#
#     u_s[~np.isfinite(u_s)] = np.nan
#     v_s[~np.isfinite(v_s)] = np.nan
#
#     def flatten(arr):
#         flat = []
#         for j in range(arr.shape[0]):    # N->S
#             row = arr[j, :]              # W->E
#             flat.extend([None if np.isnan(x) else float(x) for x in row])
#         return flat
#
#     data_u = flatten(u_s)
#     data_v = flatten(v_s)
#
#     if len(data_u) != nx * ny or len(data_v) != nx * ny:
#         raise ValueError(f"U/V no coinciden con nx*ny: {len(data_u)}/{len(data_v)} vs {nx*ny}")
#
#     return [{"header": header_u, "data": data_u},
#             {"header": header_v, "data": data_v}]
#
# @main.route("/mapa_corrientes")
# def mapa_corrientes():
#     lon, lat, fechas, u, v = load_uv_cached(NETCDF_UV_PATH)
#     info = {
#         "lon_min": float(lon.min()), "lon_max": float(lon.max()),
#         "lat_min": float(lat.min()), "lat_max": float(lat.max()),
#         "n_frames": int(u.shape[0]),
#         "fechas": fechas
#     }
#     return render_template("mapa_corrientes.html", info=info)
#
# @main.route("/api/uv_velocity")
# def api_uv_velocity():
#     lon, lat, _, u, v = load_uv_cached(NETCDF_UV_PATH)
#     try:
#         i = int(request.args.get("t", "0"))
#     except ValueError:
#         abort(400, description="Parámetro t inválido")
#     if not (0 <= i < u.shape[0]):
#         abort(404, description="Frame fuera de rango")
#
#     stride = max(1, int(request.args.get("s", "3")))
#     payload = build_leaflet_velocity_payload(lon, lat, u[i], v[i], stride=stride)
#     return jsonify(payload)
#
# @main.route("/api/uv_mag_png")
# def api_uv_mag_png():
#     """
#     Devuelve PNG de la magnitud |U| para el frame t, con NaN transparente.
#     Parámetros:
#       - t: índice de tiempo
#       - s: stride (submuestreo opcional)
#       - vmax: escala superior (float). Si no viene, usa p98 del frame.
#     """
#     lon, lat, _, u, v = load_uv_cached(NETCDF_UV_PATH)
#     try:
#         i = int(request.args.get("t", "0"))
#     except ValueError:
#         abort(400, description="Parámetro t inválido")
#     if not (0 <= i < u.shape[0]):
#         abort(404, description="Frame fuera de rango")
#
#     stride = max(1, int(request.args.get("s", "1")))
#     U = u[i][::stride, ::stride]
#     V = v[i][::stride, ::stride]
#     MAG = np.hypot(U, V).astype(np.float32)
#
#     # Escala
#     vmax_q = request.args.get("vmax", None)
#     if vmax_q is not None:
#         try:
#             vmax = float(vmax_q)
#         except ValueError:
#             vmax = 0.6
#     else:
#         vmax = 0.6  # fijo y consistente entre días
#
#     vmin = 0.0
#
#     # Malla
#     LON = np.asarray(lon)[::stride]
#     LAT = np.asarray(lat)[::stride]
#     LON2, LAT2 = np.meshgrid(LON, LAT)
#
#     # Render PNG
#     fig, ax = plt.subplots(figsize=(6, 6), dpi=200)
#     ax.set_axis_off()
#     cmap = plt.get_cmap("turbo").copy()
#     cmap.set_bad(alpha=0.0)
#     im = ax.pcolormesh(LON2, LAT2, MAG, cmap=cmap, norm=Normalize(vmin=vmin, vmax=vmax), shading="nearest")
#     ax.set_xlim(float(LON.min()), float(LON.max()))
#     ax.set_ylim(float(LAT.min()), float(LAT.max()))
#     plt.tight_layout(pad=0)
#     buf = io.BytesIO()
#     plt.savefig(buf, format="png", transparent=True, bbox_inches="tight", pad_inches=0)
#     plt.close(fig)
#     buf.seek(0)
#     return Response(buf.getvalue(), mimetype="image/png")
#
# @main.route("/api/uv_stats")
# def api_uv_stats():
#     _, _, _, u, v = load_uv_cached(NETCDF_UV_PATH)
#     try:
#         i = int(request.args.get("t", "0"))
#     except ValueError:
#         abort(400, description="Parámetro t inválido")
#     U = u[i]; V = v[i]
#     valid = np.isfinite(U) & np.isfinite(V)
#     mag = np.where(valid, np.hypot(U, V), np.nan)
#     stats = {
#         "shape": list(U.shape),
#         "valid_count": int(np.isfinite(U).sum()),
#         "both_valid": int(valid.sum()),
#         "u_minmax": [float(np.nanmin(U)) if np.isfinite(U).any() else None,
#                      float(np.nanmax(U)) if np.isfinite(U).any() else None],
#         "v_minmax": [float(np.nanmin(V)) if np.isfinite(V).any() else None,
#                      float(np.nanmax(V)) if np.isfinite(V).any() else None],
#         "mag_p95": float(np.nanpercentile(mag, 95)) if np.isfinite(mag).any() else None
#     }
#     return jsonify(stats)
#
# #
# #------------------------------------
# # Ahora con la ATSM
# #------------------------------------
#
# from matplotlib.colors import TwoSlopeNorm
#
# NETCDF_ATSM_PATH = "/Data/sapo2024/Recortado/ATSM_last30.nc"  # salida del script de combinación
# VAR_ATSM = "temp"  # como lo generamos arriba
#
# def cf_time_to_dates(num, units, calendar):
#     try:
#         dts = netCDF4.num2date(num, units=units, calendar=calendar)
#         # normalizar a date/datetime naive ISO
#         out = []
#         for d in np.atleast_1d(dts):
#             if isinstance(d, (np.datetime64,)):
#                 d = dt.datetime.utcfromtimestamp((d - np.datetime64("1970-01-01T00:00:00Z")) / np.timedelta64(1, "s"))
#             elif hasattr(d, "tzinfo") and d.tzinfo is not None:
#                 d = d.replace(tzinfo=None)
#             out.append(d.strftime("%Y-%m-%d"))
#         return out
#     except Exception:
#         # último recurso: tratar como días estilo MATLAB
#         fechas = []
#         arr = np.asarray(num, dtype=float).ravel()
#         for dn in arr:
#             ordinal = int(dn); frac = dn - ordinal
#             d = dt.datetime.fromordinal(ordinal) + dt.timedelta(days=frac) - dt.timedelta(days=366)
#             fechas.append(d.strftime("%Y-%m-%d"))
#         return fechas
#
# @lru_cache(maxsize=1)
# def load_atsm_cached(nc_path: str):
#     with netCDF4.Dataset(nc_path, mode="r") as ds:
#         lon = ds.variables["lon"][:].astype(np.float32)   # (nx,) o (lon)
#         lat = ds.variables["lat"][:].astype(np.float32)   # (ny,)
#         time = ds.variables["time"][:]
#         time_units = getattr(ds.variables["time"], "units", "")
#         time_cal = getattr(ds.variables["time"], "calendar", "standard")
#         temp = ds.variables[VAR_ATSM][:].astype(np.float32)  # (t, ny, nx) con FILL_VALUE
#         fv = getattr(ds.variables[VAR_ATSM], "_FillValue", -9999.0)
#
#     # Convertir FILL_VALUE a NaN para facilitar gráficos
#     temp = np.where(temp == fv, np.nan, temp).astype(np.float32)
#
#     # Fechas legibles
#     fechas = cf_time_to_dates(time, time_units, time_cal)
#     return lon, lat, fechas, temp
#
# @main.route("/mapa_atsm")
# def mapa_atsm():
#     lon, lat, fechas, temp = load_atsm_cached(NETCDF_ATSM_PATH)
#     info = {
#         "lon_min": float(np.nanmin(lon)), "lon_max": float(np.nanmax(lon)),
#         "lat_min": float(np.nanmin(lat)), "lat_max": float(np.nanmax(lat)),
#         "n_frames": int(temp.shape[0]),
#         "fechas": fechas
#     }
#     return render_template("mapa_atsm.html", info=info)
#
# @main.route("/api/atsm_png")
# def api_atsm_png():
#     """
#     Devuelve PNG de la anomalía TSM para el frame t, con NaN transparente.
#     Parámetros:
#       - t: índice de tiempo (int)
#       - s: stride (submuestreo entero, default 1)
#       - v: vmax (float) escala simétrica [-v, +v]; default computa percentil 98 abs.
#     """
#     lon, lat, _, temp = load_atsm_cached(NETCDF_ATSM_PATH)
#     try:
#         i = int(request.args.get("t", "0"))
#     except ValueError:
#         abort(400, description="Parámetro t inválido")
#
#     if not (0 <= i < temp.shape[0]):
#         abort(404, description="Frame fuera de rango")
#
#     stride = max(1, int(request.args.get("s", "1")))
#     T = temp[i][::stride, ::stride]  # (ny, nx)
#     LON = np.asarray(lon)[::stride]
#     LAT = np.asarray(lat)[::stride]
#
#     # Malla
#     LON2, LAT2 = np.meshgrid(LON, LAT)
#
#     # Escala simétrica centrada en 0 (anomalías)
#     vmax_q = request.args.get("v", None)
#     if vmax_q is not None:
#         try:
#             vmax = float(vmax_q)
#         except ValueError:
#             vmax = None
#     else:
#         vmax = None
#
#     if vmax is None:
#         # robusto: percentil 98 de |T| ignorando NaN
#         if np.isfinite(T).any():
#             vmax = float(np.nanpercentile(np.abs(T), 98))
#             vmax = max(vmax, 0.5)  # evita vmax demasiado bajo
#         else:
#             vmax = 1.0
#     vmin = -vmax
#
#     # Render PNG
#     fig, ax = plt.subplots(figsize=(6, 6), dpi=200)
#     ax.set_axis_off()
#     # Paleta divergente
#     cmap = plt.get_cmap("RdBu_r").copy()
#     cmap.set_bad(alpha=0.0)
#     norm = TwoSlopeNorm(vmin=vmin, vcenter=0.0, vmax=vmax)
#     im = ax.pcolormesh(LON2, LAT2, T, cmap=cmap, norm=norm, shading="nearest")
#
#     ax.set_xlim(float(LON.min()), float(LON.max()))
#     ax.set_ylim(float(LAT.min()), float(LAT.max()))
#     plt.tight_layout(pad=0)
#     buf = io.BytesIO()
#     plt.savefig(buf, format="png", transparent=True, bbox_inches="tight", pad_inches=0)
#     plt.close(fig)
#     buf.seek(0)
#     return Response(buf.getvalue(), mimetype="image/png")

@main.route('/puntos')
def puntos():
    try:
        # Definir las constantes del mapa
        center = session.get('center', [-35, -73])
        zoom = session.get('zoom', 6)

        m = folium.Map(
            location=center,
            zoom_start=zoom,
            tiles='OpenStreetMap',
            minZoom=minzoom,
            maxZoom=maxzoom,
        )

        # Leer el archivo GeoJSON
        geojson_path = os.path.join(current_app.root_path, 'static', 'doc', 'datos_jaime.geojson')

        # Añadir la capa GeoJSON al mapa
        folium.GeoJson(
            geojson_path,
            name='Puntos de datos',
            marker=folium.CircleMarker(
                radius=3,
                color='blue',
                fill=True,
                fillColor='blue',
                fillOpacity=0.6
            ),
            tooltip=folium.GeoJsonTooltip(
                fields=['date', 'sum_horas'],
                aliases=['Fecha:', 'Horas:'],
                localize=True
            ),
            popup=folium.GeoJsonPopup(
                fields=['date', 'sum_horas'],
                aliases=['Fecha:', 'Horas:'],
                localize=True
            )
        ).add_to(m)

        # Guardar el archivo HTML del mapa
        temp_map_path = os.path.join(current_app.root_path, 'static', 'map_puntos.html')
        m.save(temp_map_path)

        with open(temp_map_path, 'r') as f:
            mapa_html = f.read()

        # Limpiar librerías redundantes del HTML generado automáticamente
        mapa_html = mapa_html.replace(
            '<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.js"></script>', '')
        mapa_html = mapa_html.replace(
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.3/dist/leaflet.css"/>', '')
        mapa_html = mapa_html.replace('<script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>', '')
        mapa_html = mapa_html.replace(
            '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.2.2/dist/css/bootstrap.min.css"/>', '')

        # Renderizar el template HTML
        return render_template('puntos.html', mapa_html=mapa_html)

    except Exception as e:
        return f"Error en la ruta '/puntos': {str(e)}", 500
