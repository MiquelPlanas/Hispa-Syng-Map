# Validación — Hispa-Syng v1.0 — edición española

Este documento describe los criterios y las familias de comprobación de la edición española. El estado y la identificación del paquete respaldados por los registros disponibles se presentan en [el informe de alcance de validación](../Validation/VALIDACION_ES.md). Esta descripción no certifica que todas las comprobaciones se hayan repetido sobre el ZIP actual.

La validación cubre sintaxis, pruebas unitarias, alias de entrada, invariancia
numérica, integridad HTML, integridad PNG/PDF, apertura XLSX, apertura DOCX y
capas GeoPackage. La resolución seleccionada se comprueba a 1, 5 y 10 km,
correspondientes a superficies nominales de 1, 25 y 100 km².

La capa de presentación española no debe cambiar entradas analíticas ni
fórmulas. Las tablas numéricas se comparan con la edición inglesa después de
igualar columnas y categorías traducidas. Una ejecución solo se acepta cuando
el estado final de control de calidad es `SUPERADO`.

Las comprobaciones de publicación verifican las cuatro pestañas integradas,
los enlaces protegidos de Word, Excel y ZIP de datos reutilizable en cada mapa,
las rutas relativas del servidor estático, los manifiestos de paquetes, la
localización de hábitat limitada a campos de hábitat generados, la
inmutabilidad del libro de origen, la asignación regional MITECO canónica independiente de la resolución analítica 1/5/10 km, la eliminación de duplicados y los controles independientes de
densidad total y por especie usando superficie marina efectiva. También
verifican que las geometrías personalizadas de tierra, costa y demarcaciones
MITECO no estén en el HTML estático, y que la auditoría de `MARINO` y de
registros fuera de malla quede documentada. Las regresiones de salida de densidad verifican además las unidades ind./km² y un máximo de dos decimales en valores visibles/exportados, manteniendo la precisión interna completa.

Las regresiones espaciales incluyen la asignación regional canónica mediante la malla oficial MITECO de referencia de 10 km para puntos sin intersección directa con una demarcación, la invariancia del ámbito regional entre resoluciones analíticas de 1/5/10 km, celdas marinas completas, celdas costeras mixtas `MARINO=0`, recorte GSHHS, igualdad entre geometría analítica y visual, conservación de la geometría oficial para asignación y el respaldo MITECO de falsos ceros costeros. Comprueban que una celda de respaldo pueda conservar directamente su observación cuando la demarcación oficial es coherente, que `nearest` solo actúe después y únicamente sobre celdas con superficie GSHHS positiva dentro de la tolerancia, y que los puntos sin asignación segura permanezcan documentados y conservados en Mapa 1 sin entrar en métricas por celda.

El JavaScript generado para los mapas 1, 2, 3 y conservación se comprueba con
`node --check`; los controles y ventanas emergentes pasan un escáner de
idioma. Las figuras afectadas se renderizan para revisión visual y los
productos DOCX/XLSX se abren estructuralmente. Las tablas de completitud
regional y de advertencias explican qué resultados son calculables.

El informe técnico integral se valida adicionalmente como producto final de la ejecución: se comprueba la equivalencia estructural ES/EN, la presencia de las tablas de cobertura temporal, regional y composición sexual cuando son calculables, la inserción efectiva de las dos vistas etiquetadas de zonas prioritarias cuando existen, la ausencia de rutas absolutas del ordenador y la coherencia de las rutas relativas `Resultados/<ejecución>/...`. Los DOCX se renderizan para revisión visual de tablas, figuras, pies y saltos de página.

Ningún programa científico puede garantizar una ejecución correcta con un
archivo corrupto, un esquema desconocido o un bloqueo de seguridad del sistema
operativo. Esta edición falla de forma explícita y registra diagnósticos en
lugar de aceptar datos inválidos silenciosamente.

## Regresión de zonas operativas de conservación

La validación comprueba que la delimitación operativa no altera puntuaciones, clases, celdas seleccionadas ni zonas estratégicas. Una geometría sintética con dos grupos de celdas MITECO de 1 km con evidencia separados por celdas vacías debe producir dos zonas operativas independientes, sin puentes vacíos y siempre contenidas en su zona estratégica progenitora. También se comprueba que los popups preexistentes de celdas, zonas estratégicas y áreas protegidas conservan todos sus campos.
## Regresión de escala cromática robusta de densidad

Las regresiones de Mapas 2 y 3 comprueban que la densidad siga calculándose y exportándose sin recorte, mientras que la escala cromática use el percentil empírico 95 cuando existan al menos 20 celdas con densidad positiva. Los valores que superan el techo visual deben conservar su valor exacto y saturarse únicamente en color. Con menos de 20 celdas positivas se exige el máximo observado completo, y Mapa 2 debe recalcular la escala tras cada cambio de especies activas.

