import xarray as xr
import geopandas as gpd
from shapely.geometry import LineString
import matplotlib.pyplot as plt
import numpy as np

# Archivo NetCDF de entrada
filepath = '/Data/sapo_prueba/app/static/Profundidad.grd'

# Cargar el dataset de profundidad
ds = xr.open_dataset(filepath)

# Extraer coordenadas de rango, resolución y datos de profundidad
x_min, x_max = ds['x_range'].values  # Longitudes
y_min, y_max = ds['y_range'].values  # Latitudes
spacing_x, spacing_y = ds['spacing'].values  # Resolución (paso)
z = ds['z'].values.reshape(int(ds['dimension'][1]),
                           int(ds['dimension'][0]))  # Matriz de profundidad (14362 filas x 17068 columnas)

# Generar malla de coordenadas
ny, nx = z.shape  # Extraer dimensiones de la matriz z: filas (latitudes), columnas (longitudes)
x_coords = np.linspace(x_min, x_max, nx)  # Generar longitudes (17068 valores)
y_coords = np.linspace(y_min, y_max, ny)  # Generar latitudes (14362 valores)
X, Y = np.meshgrid(x_coords, y_coords)  # Crear malla 2D de coordenadas (compatible con z)

print(f"Dimensiones de X: {X.shape}, Dimensiones de Y: {Y.shape}, Dimensiones de Z: {z.shape}")

# Configurar niveles de contornos
levels = [50, 100, 250, 500, 1000, 2000, 3000, 4000, 5000]

# Crear contornos con matplotlib
fig, ax = plt.subplots(figsize=(8, 6))
cont = ax.contour(X, Y, z, levels=levels, colors='black')

# Convertir contornos a geometrías (LineString)
geoms = []
values = []
for level, collection in zip(levels, cont.collections):
    for path in collection.get_paths():
        try:
            vertices = path.vertices
            line = LineString(vertices)
            geoms.append(line)
            values.append(level)
        except Exception as e:
            print(f"Error al procesar contorno: {e}")

# Crear un GeoDataFrame con las geometrías y los valores de profundidad
gdf = gpd.GeoDataFrame({"value": values}, geometry=geoms, crs="EPSG:4326")

# Guardar el archivo intermedio en formato GeoJSON (puedes usar Shapefile si prefieres)
output_path = '/Data/sapo_prueba/static/profundidad.geojson'
gdf.to_file(output_path, driver='GeoJSON')

print(f"Archivo intermedio guardado en: {output_path}")
