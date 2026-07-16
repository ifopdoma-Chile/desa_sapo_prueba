import paramiko
from datetime import datetime, timedelta
import requests
import time

GEOSERVER_BASE_URL = "https://gis-eco.ifop.cl/geoserver"
GEOSERVER_USER = "agarcia"
GEOSERVER_PASS = "dream2004"

GEOSERVER_HOST = "10.10.10.63"
SSH_USER = "agarcia"
SSH_PASS = "dream2004"

BASE_HISTORICO = "/datos/servicio_wms/historico"
BASE_WMS = "/datos/servicio_wms"

# ==============================
# SSH
# ==============================
def create_ssh_client():
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(GEOSERVER_HOST, 22, SSH_USER, SSH_PASS)
    return ssh

def ejecutar(ssh, cmd):
    stdin, stdout, stderr = ssh.exec_command(cmd)
    return stdout.read().decode().strip(), stderr.read().decode().strip()

# ==============================
# GWC TRUNCATE
# ==============================
def truncar_cache():
    capas = [
        "Ifop_Sapo:Temperatura_temp",
        "Ifop_Sapo:Anomalia_temperatura_temp",
        "Ifop_Sapo:Clorofila_temp",
    ]

    for capa in capas:
        url = f"{GEOSERVER_BASE_URL}/gwc/rest/seed/{capa}.xml"
        body = f"""
        <seedRequest>
          <name>{capa}</name>
          <srs><number>4326</number></srs>
          <zoomStart>0</zoomStart>
          <zoomStop>30</zoomStop>
          <format>image/png</format>
          <type>truncate</type>
          <threadCount>1</threadCount>
        </seedRequest>
        """.strip()

        r = requests.post(
            url,
            data=body,
            headers={"Content-Type": "text/xml"},
            auth=(GEOSERVER_USER, GEOSERVER_PASS),
            timeout=15
        )
        print(f"GWC truncate {capa}: {r.status_code}")

# ==============================
# OPCIÓN A: RELOAD VIA REST (sin reiniciar el servicio)
# ==============================
def recargar_geoserver():
    """
    Recarga el catálogo de GeoServer via REST API.
    Fuerza la re-lectura de los NetCDF desde disco sin detener el servicio.
    Tarda ~2-5s vs ~30s de un systemctl restart.
    """
    url = f"{GEOSERVER_BASE_URL}/rest/reload"
    r = requests.post(
        url,
        auth=(GEOSERVER_USER, GEOSERVER_PASS),
        timeout=30
    )
    r.raise_for_status()
    print(f"GeoServer catalog reload: {r.status_code}")

# ==============================
# OPCIÓN B: LISTAR ARCHIVOS (1 solo comando SSH)
# ==============================
def listar_archivos_historico(ssh):
    """
    Obtiene todos los .nc disponibles con un único exec_command.
    Evita hasta 45 round-trips SSH del método anterior.
    """
    out, _ = ejecutar(ssh, f"ls {BASE_HISTORICO}/*.nc 2>/dev/null")
    if not out:
        return set()
    return set(line.strip() for line in out.split('\n') if line.strip())

# ==============================
# BUSCAR ARCHIVO PARA UN PRODUCTO (sin SSH adicional)
# ==============================
def buscar_archivo_producto(archivos_disponibles, fecha_base, patron_src, dst, rango_dias=7):
    """
    Busca el archivo más cercano a fecha_base en la lista pre-obtenida.
    Prioriza fecha exacta, luego ±1, ±2, ..., ±rango_dias días.
    Sin round-trips SSH — toda la lógica es Python local.
    """
    nombre_producto = dst.split('/')[-1].replace('temp.nc', '').replace('.nc', '')

    yyyymmdd = fecha_base.strftime("%Y%m%d")
    src = patron_src.format(fecha=yyyymmdd)
    if src in archivos_disponibles:
        print(f"✔ {nombre_producto}: Fecha exacta {fecha_base.strftime('%Y-%m-%d')}")
        return src, dst, fecha_base.strftime("%Y-%m-%d")

    for offset in range(1, rango_dias + 1):
        for delta, label in [(-offset, "anterior"), (+offset, "posterior")]:
            fecha_eval = fecha_base + timedelta(days=delta)
            yyyymmdd = fecha_eval.strftime("%Y%m%d")
            src = patron_src.format(fecha=yyyymmdd)
            if src in archivos_disponibles:
                print(f"⚠ {nombre_producto}: Usando fecha {label} {fecha_eval.strftime('%Y-%m-%d')} ({delta:+d} días)")
                return src, dst, fecha_eval.strftime("%Y-%m-%d")

    raise FileNotFoundError(
        f"No se encontró archivo para {nombre_producto} en el rango "
        f"[{(fecha_base - timedelta(days=rango_dias)).strftime('%Y-%m-%d')} a "
        f"{(fecha_base + timedelta(days=rango_dias)).strftime('%Y-%m-%d')}]"
    )

# ==============================
# PROCESO PRINCIPAL
# ==============================
def actualizar_geoserver_historico(fecha_str, rango_dias=7):
    fecha = datetime.strptime(fecha_str, "%Y-%m-%d")
    ssh = None

    print(f"\n{'='*60}")
    print(f"Iniciando actualización para fecha: {fecha_str}")
    print(f"Rango de búsqueda: ±{rango_dias} días")
    print(f"{'='*60}\n")

    try:
        ssh = create_ssh_client()
        print("✔ Conexión SSH establecida")

        # Opción B: lista completa de archivos en 1 comando SSH
        print("--- Listando archivos históricos disponibles ---")
        archivos_disponibles = listar_archivos_historico(ssh)
        print(f"✔ {len(archivos_disponibles)} archivos .nc encontrados")

        productos = [
            (f"{BASE_HISTORICO}/{{fecha}}_TSM_Nuevo_v2.nc",   f"{BASE_WMS}/TSMtemp.nc",         "Temperatura"),
            (f"{BASE_HISTORICO}/{{fecha}}_ATSM_Nuevo_v2.nc",  f"{BASE_WMS}/AnomaliaTSMtemp.nc", "Anomalía Temperatura"),
            (f"{BASE_HISTORICO}/{{fecha}}_CLO_Nuevo_v2.nc",   f"{BASE_WMS}/CLO_temp.nc",        "Clorofila"),
        ]

        archivos_finales = []
        fechas_usadas = {}

        print("\n--- Buscando archivos históricos ---")
        for patron, dst, nombre in productos:
            src, dst, fecha_usada = buscar_archivo_producto(
                archivos_disponibles, fecha, patron, dst, rango_dias
            )
            archivos_finales.append((src, dst))
            fechas_usadas[nombre] = fecha_usada

        print("\n--- Copiando archivos NetCDF ---")
        for src, dst in archivos_finales:
            nombre_archivo = dst.split('/')[-1]
            print(f"Copiando {nombre_archivo}...")
            ejecutar(ssh, f"cp {src} {dst}")

            size_src, _ = ejecutar(ssh, f"stat -c %s {src}")
            size_dst, _ = ejecutar(ssh, f"stat -c %s {dst}")

            if int(size_src) != int(size_dst):
                raise RuntimeError(
                    f"Fallo en validación de copia: {src} ({size_src} bytes) → {dst} ({size_dst} bytes)"
                )
            print(f"✔ {nombre_archivo} copiado y validado ({size_dst} bytes)")

        print("\n--- Limpiando caché de GeoWebCache ---")
        truncar_cache()
        print("✔ Caché limpiado")

        # Opción A: reload via REST en lugar de systemctl restart
        print("\n--- Recargando catálogo GeoServer via REST ---")
        recargar_geoserver()
        print("✔ GeoServer recargado (sin reinicio del servicio)")

    except Exception as e:
        print(f"\n✗ Error durante el proceso: {str(e)}")
        raise
    finally:
        if ssh:
            ssh.close()
            print("✔ Conexión SSH cerrada")

    print(f"\n{'='*60}")
    print("✅ PROCESO COMPLETADO EXITOSAMENTE")
    print(f"{'='*60}")
    print("\n📅 Fechas utilizadas por capa:")
    for producto, fecha_u in fechas_usadas.items():
        diferencia = ""
        if fecha_u != fecha_str:
            dias_diff = (datetime.strptime(fecha_u, "%Y-%m-%d") - fecha).days
            diferencia = f" (diferencia: {dias_diff:+d} días)"
        print(f"  • {producto:25} → {fecha_u}{diferencia}")
    print(f"\n{'='*60}\n")

    return fechas_usadas
