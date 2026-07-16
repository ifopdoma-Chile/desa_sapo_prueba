#!/usr/bin/env python3
"""Diagnóstico del servidor GeoServer via SSH."""
import sys
sys.path.insert(0, '/Data/sapo_prueba')

import paramiko
from app.copia_ssh import (
    create_ssh_client, ejecutar,
    BASE_HISTORICO, BASE_WMS
)

def main():
    print("Conectando al servidor...")
    ssh = create_ssh_client()
    print("✔ Conexión establecida\n")

    # 1. Estado del servicio GeoServer
    print("=== Estado GeoServer ===")
    out, _ = ejecutar(ssh, "systemctl status geoserver --no-pager -l 2>&1 | head -20")
    print(out)

    # 2. Verificar archivos actuales en BASE_WMS
    print("\n=== Archivos temporales actuales ===")
    out, _ = ejecutar(ssh, f"ls -lh {BASE_WMS}/*.nc 2>&1")
    print(out)

    # 3. Verificar el archivo CLO_temp.nc específicamente
    print("\n=== Detalles CLO_temp.nc ===")
    out, _ = ejecutar(ssh, f"ls -lh {BASE_WMS}/CLO_temp.nc 2>&1")
    print(out)

    # 4. Revisar variables y dimensiones del CLO con ncdump
    print("\n=== Metadata CLO_temp.nc (ncdump -h) ===")
    out, err = ejecutar(ssh, f"ncdump -h {BASE_WMS}/CLO_temp.nc 2>&1 | head -60")
    print(out or err)

    # 5. Comparar con TSMtemp.nc para ver diferencias
    print("\n=== Metadata TSMtemp.nc (ncdump -h, primeras 30 líneas) ===")
    out, err = ejecutar(ssh, f"ncdump -h {BASE_WMS}/TSMtemp.nc 2>&1 | head -30")
    print(out or err)

    # 6. Contar archivos CLO disponibles en histórico
    print("\n=== Archivos CLO disponibles en histórico ===")
    out, _ = ejecutar(ssh, f"ls {BASE_HISTORICO}/*CLO*.nc 2>/dev/null | wc -l")
    print(f"Total archivos CLO: {out}")
    out, _ = ejecutar(ssh, f"ls {BASE_HISTORICO}/*CLO*.nc 2>/dev/null | tail -5")
    print(f"Últimos 5:\n{out}")

    # 7. Logs recientes de GeoServer
    print("\n=== Últimas líneas de log GeoServer ===")
    out, err = ejecutar(ssh, "journalctl -u geoserver -n 30 --no-pager 2>&1")
    print(out or err)

    ssh.close()
    print("\n✔ Diagnóstico completo.")

if __name__ == "__main__":
    main()
