import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import rasterize
from affine import Affine
import xarray as xr

# === CONFIGURACIÓN DE RUTAS ===
# Ruta de entrada del archivo Shapefile (reemplaza con tu ruta)
shapefile_path = "/Data/sapo_prueba/app/static/shp/amp_nac_shp/AMP_NACIONAL.shp"

# Ruta de salida del archivo NetCDF
output_netcdf = "/Data/sapo_prueba/app/static/shp/amp.nc"

# Resolución de la grilla (en las unidades del CRS del shapefile)
resolution = 0.01  # Ejemplo: 0.01 grados (~1km)


def transform_shapefile_to_netcdf(shapefile_path, output_netcdf, resolution):
    """
    Transforma un archivo shapefile (.shp) en un archivo NetCDF (.nc).

    Args:
        shapefile_path (str): Ruta al archivo shapefile de entrada.
        output_netcdf (str): Ruta donde se guardará el archivo NetCDF.
        resolution (float): Resolución espacial de la grilla de salida.

    Returns:
        None
    """
    # === PASO 1: Leer el archivo Shapefile ===
    print(f"Cargando shapefile: {shapefile_path}")
    gdf = gpd.read_file(shapefile_path)

    # Verificar el sistema de coordenadas
    print(f"Sistema de coordenadas original: {gdf.crs}")
    if gdf.crs is None or gdf.crs.to_string() != "EPSG:4326":
        print("Reproyectando a WGS84 (EPSG:4326)...")
        gdf = gdf.to_crs("EPSG:4326")

    # Verificar límites y estructura del shapefile
    minx, miny, maxx, maxy = gdf.total_bounds
    print(f"Límites del Shapefile: {gdf.total_bounds}")

    # === PASO 2: Crear la grilla para rasterizar ===
    print("Creando grilla...")
    x = np.arange(minx, maxx, resolution)
    y = np.arange(miny, maxy, resolution)

    # Transformación afín para el raster
    transform = Affine(resolution, 0, minx, 0, -resolution, maxy)

    # Rasterizar las geometrías del shapefile en una matriz
    print("Rasterizando el shapefile...")
    raster = rasterize(
        ((geom, 1) for geom in gdf.geometry),  # Geometrías del shapefile
        out_shape=(len(y), len(x)),  # Tamaño de la grilla
        transform=transform,
        fill=0,  # Valor de fondo
        dtype='float32'  # Tipo de dato para el raster
    )

    print(f"Rasterización completa. Tamaño de la grilla: {raster.shape}")

    # === PASO 3: Crear el archivo NetCDF ===
    print("Creando archivo NetCDF...")

    # Convertir el raster a un DataArray de xarray
    da = xr.DataArray(
        data=raster,
        dims=["lat", "lon"],  # Dimensiones de la grilla
        coords={
            "lat": y[::-1],  # Coordenadas de latitud (invertido para NetCDF)
            "lon": x  # Coordenadas de longitud
        },
        attrs={
            "description": "Datos rasterizados a partir del shapefile",
            "resolution": f"{resolution} units"
        }
    )

    # Crear un Dataset de xarray
    ds = xr.Dataset({"variable": da})  # Cambia "variable" por el nombre deseado

    # Guardar el archivo NetCDF
    ds.to_netcdf(output_netcdf)
    print(f"Archivo NetCDF creado exitosamente en: {output_netcdf}")


# === LLAMAR A LA FUNCIÓN ===
transform_shapefile_to_netcdf(shapefile_path, output_netcdf, resolution)
