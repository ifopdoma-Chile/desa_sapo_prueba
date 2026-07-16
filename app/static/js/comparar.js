if (!L.Mixin) {
    L.Mixin = {};
}
L.Mixin.Events = L.Evented.prototype;

let map; // Referencia global al mapa
let sideBySide; // Referencia global al control SideBySideLayers actual
let leftLayer; // Capa izquierda actual
let rightLayer; // Capa derecha actual

document.addEventListener('DOMContentLoaded', () => {
    const mapContainer = document.querySelector('.folium-map'); // Seleccionar el contenedor del mapa generado por Folium
    const mapId = mapContainer ? mapContainer.id : null;

    if (mapId) {
        // Recuperar el mapa generado por Folium
        map = window[Object.keys(window).find(key => key.startsWith('map_') && key.includes(mapId))];

        if (map) {
            console.log('Mapa cargado correctamente.');

            // Eliminar cualquier control SideBySideLayers inicial (generado por Folium)
            removeAllSideBySideControls();

            // Seleccionadores de capas
            const leftSelector = document.getElementById('left-layer');
            const rightSelector = document.getElementById('right-layer');

            // Agregar eventos de cambio a los selectores
            leftSelector.addEventListener('change', () =>
                updateSideBySideLayers(leftSelector.value, rightSelector.value)
            );

            rightSelector.addEventListener('change', () =>
                updateSideBySideLayers(leftSelector.value, rightSelector.value)
            );
        } else {
            console.error('No se encontró el mapa generado por Folium.');
        }
    } else {
        console.error('No se encontró el contenedor del mapa.');
    }
});

// Función para eliminar todos los controles SideBySide y elementos relacionados
function removeAllSideBySideControls() {
    // Eliminar controles SideBySide creados dinámicamente
    if (sideBySide) {
        map.removeControl(sideBySide); // Eliminar control existente
        sideBySide = null; // Quitar referencia
    }

    // Eliminar nodos de controles iniciales generados por Folium
    const sbsControls = document.querySelectorAll('.leaflet-sbs'); // Detectar controles SideBySide
    sbsControls.forEach(control => {
        control.remove(); // Remover del DOM
    });

    // Inspeccionar y eliminar controles desde el mapa si es necesario
    const allControls = document.querySelectorAll('.leaflet-control'); // Todos los controles
    allControls.forEach(control => {
        if (control.innerHTML.includes('side-by-side')) {
            control.remove(); // Remover controles SideBySide
        }
    });
}

// Función para actualizar las capas dinámicamente
async function updateSideBySideLayers(left, right) {
    try {
        const response = await fetch('/app/actualizar_capa', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ left: left, right: right }), // Pasar las capas
        });

        if (!response.ok) {
            console.error('Error al obtener las nuevas capas:', response.statusText);
            return;
        }

        const data = await response.json();

        if (!data.left_layer_url || !data.right_layer_url) {
            console.error('Respuesta inválida del servidor:', data);
            return;
        }

        // Remover cualquier control SideBySide existente y limpiar capas
        removeAllSideBySideControls();

        // Crear las nuevas capas dinámicas a partir de los datos del servidor
        leftLayer = L.tileLayer.wms(data.left_layer_url.url, {
            layers: data.left_layer_url.layer,
            format: data.left_layer_url.fmt,
            transparent: data.left_layer_url.transparent,
            version: data.left_layer_url.version,
        });

        rightLayer = L.tileLayer.wms(data.right_layer_url.url, {
            layers: data.right_layer_url.layer,
            format: data.right_layer_url.fmt,
            transparent: data.right_layer_url.transparent,
            version: data.right_layer_url.version,
        });

        // Añadir las nuevas capas al mapa y configurar el SideBySide
        sideBySide = L.control.sideBySide(leftLayer.addTo(map), rightLayer.addTo(map)).addTo(map);

        console.log('Capas comparativas actualizadas exitosamente:', data);
    } catch (error) {
        console.error('Error al actualizar las capas comparativas:', error);
    }
}