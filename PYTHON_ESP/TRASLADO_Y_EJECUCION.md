# Trasladar y ejecutar el programa

**Licencia de esta guía:** [Creative Commons Atribución–NoComercial 4.0 Internacional (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/).

La carpeta completa extraída puede copiarse a otro ordenador o ubicación.
Copie el programa junto con el libro de entrada, las mallas, los shapefiles,
las áreas protegidas opcionales, los rasgos y el logotipo. No copie `.venv`
entre ordenadores diferentes; permita que `instalar_y_ejecutar_windows.bat`
cree un entorno compatible en el ordenador de destino.

Mover la carpeta dentro del mismo ordenador no requiere cambiar rutas fijas,
porque la búsqueda de entradas es relativa a la carpeta del programa. Las
carpetas `Resultados` existentes pueden conservarse o archivarse por separado.

Para una instalación nueva, desbloquee el ZIP antes de extraerlo, coloque los
datos en la carpeta del programa y ejecute `instalar_y_ejecutar_windows.bat`.
En macOS o Linux puede crear un entorno virtual con `python3 -m venv .venv`,
instalar `requirements.txt` y ejecutar `python ejecutar_hippodec.py`.
