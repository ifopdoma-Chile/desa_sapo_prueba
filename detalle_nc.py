import netCDF4
import os

def print_netcdf_metadata(netcdf_path):
    # Abrir el archivo NetCDF
    dataset = netCDF4.Dataset(netcdf_path, mode='r')

    # Imprimir atributos globales
    print("Atributos globales:")
    for attr in dataset.ncattrs():
        print(f"{attr}: {dataset.getncattr(attr)}")

    # Imprimir atributos de las variables
    print("\nAtributos de las variables:")
    for var_name in dataset.variables:
        var = dataset.variables[var_name]
        print(f"\nVariable: {var_name}")
        for attr in var.ncattrs():
            print(f"  {attr}: {var.getncattr(attr)}")

    for variable_name in dataset.variables:
        variable = dataset.variables[variable_name]
        # Obtiene la forma de la variable (tamaño de cada dimensión)
        shape = variable.shape
        # Calcula la cantidad total de datos en la variable
        size = variable.size
        print(f"Variable: {variable_name}")
        print(f"  Shape: {shape}")
        print(f"  Size (total number of elements): {size}\n")
    # Iterar sobre las variables
    print("Primeros valores de las variables:")
    for var_name in dataset.variables:
        variable = dataset.variables[var_name]
        print(f"\nVariable: {var_name}")

        # Imprimimos los primeros valores dependiendo de las dimensiones
        if variable.ndim > 0:  # Si la variable tiene dimensiones
            sample_data = variable[:5]  # Obtener los primeros 5 valores (ajusta según tu necesidad)
            print(f"  Primeros valores: {sample_data}")
        else:
            # Si no tiene dimensiones, es una constante o un escalar
            print(f"  Valor: {variable[...]}")

    # Cerrar el archivo NetCDF
    dataset.close()

# Ruta al archivo NetCDF
#netcdf_path = os.getcwd() + '/Profundidad/Profundidad.nc'
#netcdf_path = os.getcwd() + '/app/static/Profundidad.grd'
#netcdf_path = '/Data/sapo2024/Recortado/TSM.nc'
netcdf_path = '/Data/JFAUNDEZ/UVClimCroco.nc'


# Imprimir los metadatos del archivo NetCDF
print_netcdf_metadata(netcdf_path)
