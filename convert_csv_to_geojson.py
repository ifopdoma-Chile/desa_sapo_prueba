#!/usr/bin/env python3
"""
Script para convertir datos_jaime.csv a GeoJSON
Solo incluye registros con fecha, lat y lon válidos
"""
import pandas as pd
import json

# Leer CSV
csv_path = 'app/static/doc/datos_jaime.csv'
print(f"Leyendo {csv_path}...")
df = pd.read_csv(csv_path)

print(f"Total de filas en CSV: {len(df)}")

# Filtrar solo filas con fecha válida (no NaN/NA)
df = df.dropna(subset=['date'])
print(f"Filas con fecha válida: {len(df)}")

# Filtrar también coordenadas válidas
df = df.dropna(subset=['lat_round', 'lon_round'])
print(f"Filas con coordenadas válidas: {len(df)}")

# Crear estructura GeoJSON
geojson = {
    "type": "FeatureCollection",
    "features": []
}

# Convertir cada fila a una Feature de GeoJSON
for idx, row in df.iterrows():
    feature = {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [float(row['lon_round']), float(row['lat_round'])]  # GeoJSON usa [lon, lat]
        },
        "properties": {
            "date": str(row['date']),
            "sum_horas": float(row['sum_horas']) if pd.notna(row['sum_horas']) else 0.0,
            "median_horas": float(row['median_horas']) if pd.notna(row['median_horas']) else None,
            "avg_horas": float(row['avg_horas']) if pd.notna(row['avg_horas']) else None
        }
    }
    geojson["features"].append(feature)

# Guardar GeoJSON
output_path = 'app/static/doc/datos_jaime.geojson'
print(f"Guardando {len(geojson['features'])} puntos en {output_path}...")

with open(output_path, 'w') as f:
    json.dump(geojson, f, indent=2)

print("¡Conversión completada!")
print(f"Archivo guardado: {output_path}")
