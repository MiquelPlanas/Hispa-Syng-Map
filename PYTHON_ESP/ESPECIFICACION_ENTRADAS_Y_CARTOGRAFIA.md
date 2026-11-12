# Auditoría de entradas y cartografía — Hispa-Syng v1.0

**Licencia de esta guía:** [Creative Commons Atribución–NoComercial 4.0 Internacional (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/).

El programa lee la hoja `BD depurada` del libro original y comprueba campos
obligatorios, fechas, coordenadas, abundancia, profundidad y recuentos
sexuales. No modifica, deduplica ni vuelve a guardar el libro. Se permiten
valores repetidos en el `Id` de origen porque `Id` es un metadato y no una
clave analítica.

Las entradas espaciales obligatorias son las mallas marinas MITECO, las demarcaciones marinas MITECO y GSHHS. La pertenencia regional se fija primero por intersección directa con la demarcación y, cuando no existe, mediante la malla oficial MITECO de referencia de 10 km; esta referencia regional es independiente de la resolución analítica seleccionada. La malla de 1/5/10 km elegida por el usuario se utiliza después para la asignación analítica a celda. MITECO proporciona la geometría oficial sin recortar para asignar observaciones. GSHHS es la vía primaria para sustraer tierra en EPSG:3035 y obtener geometría y superficie marina efectiva. Si GSHHS devuelve un falso cero costero pero MITECO confirma superficie marina oficial válida, se conserva la celda mediante la intersección real entre la celda y la demarcación marina MITECO; el área analítica se calcula sobre esa geometría y coincide con la geometría mostrada. Solo los puntos todavía no resueltos pasan a `nearest`, entre celdas con superficie GSHHS positiva y dentro de la tolerancia configurada. Las densidades se expresan en ind./km², sin factor ×1.000, y las salidas visibles/exportadas usan como máximo dos decimales. El campo `MARINO` se audita y no filtra automáticamente celdas costeras mixtas. GSHHS no se incrusta como capa en la publicación HTML estática.

La carpeta opcional `Resources/areas_protegidas` se usa para solapes, distancias y
brechas de conservación. `Datos_data/traits.xlsx` activa la diversidad
funcional. GEBCO no es obligatorio y no sustituye la profundidad observada ni
GSHHS.

Los controles de calidad documentan coordenadas inválidas, observaciones no
asignadas, completitud de campos, asignación regional canónica (`auditoria_asignacion_regional.csv`), asignación espacial, inventario de mallas,
conservación de la marca marina, coincidencia entre geometría analítica y
visual, procedencia de superficie efectiva y contexto cartográfico. Las observaciones que no pueden asignarse con seguridad a una celda se escriben en `puntos_fuera_malla.csv`, se conservan como observaciones válidas en Mapa 1 y en las descargas completas, y no se tratan silenciosamente como celdas marinas ni participan en métricas por celda. La revisión espacial se apoya además en `auditoria_asignacion_espacial_nearest_y_no_asignados.csv`, `resumen_auditoria_asignacion_espacial.csv` y `Mapa_QC_Asignacion_Espacial.html`; este último usa Satélite como fondo predeterminado y Físico como alternativa.
