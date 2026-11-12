# Hispa-Syng v1.0 — edición española (Proyecto Hippo-DEC)

**Licencia de esta guía:** [Creative Commons Atribución–NoComercial 4.0 Internacional (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/). El código fuente se rige por [PolyForm Noncommercial 1.0.0](../LICENSE).

Esta aplicación ejecuta en español el flujo cartográfico y ecológico completo de Hispa-Syng v1.0,
desarrollado en el marco del Proyecto Hippo-DEC. Lee el libro original `Ingesta_provisional.xlsx` sin cambiar su
hoja, cabeceras ni valores. Las cabeceras españolas de entrada se reconocen
como alias y se convierten únicamente dentro del programa.

## Productos principales

- tres mapas interactivos de distribución, el mapa de zonas prioritarias de
  conservación y un visor web único con cuatro pestañas;
- descargas de información completa desde la barra superior del visor
  integrado: Word, Excel y un ZIP de datos reutilizable;
- una carpeta estática `Publicacion_Web`, lista para subir, y un manual de
  usuario completo;
- resúmenes descriptivos de intensidad de observación, riqueza, abundancia, frecuencia de detección registrada y
  dominancia;
- análisis de hábitat, profundidad y composición sexual;
- matrices comunitarias, diversidad beta, PERMANOVA, betadisper, NMDS y PCoA;
- IndVal, SIMPER, coocurrencia, rango-abundancia y decaimiento con la
  distancia;
- LCBD, rareza, coldspots y singularidad biogeográfica integrada;
- comunidad: soporte por eventos proxy; Hellinger–Euclídea y Jaccard como vistas principales; LCBD Jaccard/Hellinger con BH-FDR; PCoA Bray–Curtis con Lingoes; Mantel–Spearman para distance-decay; IndVal regional con BH-FDR; clústeres Louvain tratados como exploratorios/post hoc;
- clasificación núcleo–satélite, gradientes latitudinales y diversidad
  funcional opcional (solo especies observadas seleccionadas, esquema explícito de rasgos, espacio Gower/PCoA, dimensionalidad común para FRic/FDiv, métricas principales por incidencia y sensibilidad ponderada por abundancia);
- redes de similitud, clústeres de Louvain y sensibilidad al umbral;
- análisis multiescala de 10, 5 y 1 km, hotspots y persistencia;
- modelos temporales avanzados, comparaciones, mapas, clasificaciones y
  narrativas;
- prioridad ecológica, prioridad de seguimiento temporal y suficiencia de datos como productos separados;
- zonas prioritarias **estratégicas** obtenidas con la metodología científica existente: núcleos Alta/Muy alta, un único anillo opcional de extensiones Media adyacentes con soporte mínimo y candidatas Media aisladas para validación. Cuando se solicita 1 km, el visor mantiene prioridad descriptiva a 1 km y usa unidades de planificación de 5 km para esta delimitación estratégica;
- zonas **operativas de conservación** derivadas después, sin recalcular la prioridad: celdas oficiales MITECO de 1 km con observaciones dentro de cada zona estratégica, agrupadas solo por contigüidad rook y sin añadir celdas vacías de enlace. Una zona estratégica puede originar varias subzonas operativas; estas huellas focalizan actuaciones, pero no representan por sí mismas límites completos de población o hábitat;
- tres vías ecológicas explícitas (evidencia convergente, presencia persistente y núcleo de diversidad), sin permitir que un registro aislado defina una unidad Alta/Muy alta; filtro multiselección combinado por prioridad y papel espacial, brechas de protección, recomendaciones de gestión, mapa interactivo, GeoPackages e informes Word;
- archivos de control de calidad y manifiestos de salidas SHA-256.

Todo el texto dirigido a la persona usuaria —consola, HTML, ventanas
emergentes, leyendas, figuras, informes, tablas, nombres de columnas
exportadas, categorías, carpetas y nombres de archivo— se genera en español.
Los nombres científicos, códigos oficiales MITECO y valores de metadatos
originales se conservan.

## Fondos cartográficos

Los visores principales ofrecen **Satélite — Esri World Imagery** (predeterminado), **Batimetría marina — EMODnet Bathymetry World Base Layer** y **Físico — OpenTopoMap**, en ese orden. `Mapa_QC_Asignacion_Espacial.html` utiliza **Satélite** (predeterminado) y **Físico** únicamente, sin solicitar teselas al servidor estándar de OpenStreetMap. Todos son fondos de contexto en línea: requieren Internet, no requieren API key ni suscripción y no intervienen en los cálculos científicos.

## Datos de entrada obligatorios

Mantenga `Ingesta_provisional.xlsx` (o una copia numerada) y `traits.xlsx` en `Datos_data/`, y el PNG del logotipo en la raíz. Dentro de `Resources/`, coloque estos recursos cartográficos:

1. `Mallas_marinas_MITECO.zip` o la carpeta de malla MITECO extraída;
2. `demarcaciones_miteco`, con el shapefile de demarcaciones marinas MITECO
   y sus archivos auxiliares;
3. `GSHHS`, con `GSHHS_h_L1.shp` y sus archivos auxiliares, o un ZIP GSHHS;
4. `areas_protegidas`, con capas `.shp` o `.gpkg` legibles, cuando esté
   disponible.

Entradas opcionales recomendadas:

- `areas_protegidas` permite evaluar solapamientos y brechas de conservación;
- `Datos_data/traits.xlsx` activa la diversidad funcional;
- el PNG del logotipo institucional se muestra en las cabeceras.

GEBCO no es obligatorio. El campo observado `Depth` se utiliza para los
análisis de profundidad. Las geometrías oficiales MITECO sin recortar son la referencia para asignar observaciones. GSHHS es obligatorio y constituye la vía primaria para sustraer tierra en EPSG:3035 y obtener geometría y superficie marina efectiva. Si GSHHS produce un falso cero costero pero MITECO confirma superficie marina oficial válida, se activa un respaldo cuya geometría es la intersección real entre la celda y la demarcación marina MITECO; `Area_mar_km2` se calcula a partir de esa misma geometría y la representación cartográfica utiliza exactamente el mismo recorte. Solo los puntos aún no resueltos pasan a `nearest`, exclusivamente entre celdas con superficie GSHHS positiva y dentro de la tolerancia configurada. GSHHS nunca se incrusta como capa personalizada de tierra o costa en la publicación HTML estática.

## Inicio rápido en Windows

1. Extraiga el ZIP en una ruta con permisos de escritura, por ejemplo
   `C:\Hispa-Syng`.
2. Copie los datos de entrada indicados arriba en la carpeta extraída.
3. Haga doble clic en `instalar_y_ejecutar_windows.bat`.
4. Seleccione el periodo, la malla de 1/5/10 km, la demarcación MITECO y las
   especies.
5. Abra los archivos creados dentro de `Resultados`.

Durante la ejecución, la consola muestra las etapas 1/8–8/8, todos sus
subpasos y el tiempo transcurrido `[HH:MM:SS]` de cada edición y del proceso
bilingüe completo.

La primera ejecución crea `.venv` y descarga las dependencias validadas. Las
siguientes reutilizan ese entorno. Si Windows bloquea el BAT, desbloquee el
ZIP en Propiedades antes de extraerlo. Use `reparar_entorno_windows.bat` si
el entorno queda incompleto o bloqueado.

Compatibilidad operativa: Python de 64 bits 3.10–3.13. Para Hispa-Syng v1.0,
se distribuye un archivo de dependencias para Python 3.13 en Windows x64; el
instalador prioriza Python 3.13 sin obligar a reconstruir un entorno compatible
que ya funcione. La prueba de regresión bilingüe se ejecuta desde la raíz con
`RUN_REGRESSION_TESTS.bat`.

Los registros de validación automatizada incluidos corresponden a Linux/Python 3.12.14. La ejecución de Windows del 19 de octubre de 2026, revisada por separado, registra Python 3.13.15, pandas 2.3.3 y GeoPandas 1.2.0, con coincidencia de los controles principales ES/EN; véanse [la evidencia de Windows](../Validation/EJECUCION_WINDOWS_20261019.md) y [el alcance de validación](../Validation/VALIDACION_ES.md).

## Estructura de resultados

Cada ejecución crea una carpeta nueva y no sobrescribe ejecuciones anteriores:

| Carpeta | Contenido |
|---|---|
| `00_registros` | registro completo de ejecución |
| `01_parametros` | configuración y rutas resueltas |
| `02_intermedios` | mallas de análisis y GeoPackages |
| `03_mapas` | mapas interactivos 1–3 |
| `04_tablas` | tablas CSV con punto y coma y XLSX |
| `05_figuras` | figuras PNG y PDF de alta resolución |
| `06_modelos` | resúmenes de modelos, métodos y narrativas |
| `07_control_calidad` | auditorías, controles y manifiestos |
| `08_visores` | visor cartográfico unificado |
| `09_zonas_prioritarias_conservacion` | tablas, GIS, mapas e informe específico de zonas prioritarias |
| `10_informe_tecnico` | informe técnico integral automático de la ejecución, con síntesis, discusión, mapas etiquetados y trazabilidad |
| `Publicacion_Web` | visor integrado, descargas, paquetes de datos, manuales y manifiesto de integridad |

`Publicacion_Web/index.html` es la entrada destinada al alojamiento
institucional.

El informe integral se guarda como `10_informe_tecnico/Informe_Tecnico_Integral_Hispa-Syng_v1.0_ES.docx`. Sus rutas internas se expresan desde la raíz del programa (`Resultados/<ejecución>/...`), nunca mediante rutas absolutas del ordenador. Cuando existen zonas prioritarias, el capítulo 11 incorpora una vista general etiquetada y una vista de detalle por ámbito geográfico. Los popups de conservación incluyen además la composición por especie: cada celda muestra las especies presentes con abundancia y densidad por celda, y cada zona presenta el resumen equivalente a escala zonal, siempre en ind./km² marinos. Los valores visibles y exportados de densidad se presentan con un máximo de dos decimales; los cálculos analíticos mantienen la precisión completa.

En los Mapas 2 y 3, la escala cromática de densidad se desacopla de los valores extremos: con al menos 20 celdas positivas usa P95 como referencia visual y redondea el techo de la leyenda; densidades superiores se representan con el tono máximo sin alterar su valor. Con menos de 20 celdas positivas se conserva el máximo observado. En Mapa 2 el P95 se recalcula al cambiar las especies activas. Los popups y las exportaciones conservan siempre la densidad exacta.
 La publicación sigue siendo estática para los productos no sensibles. Si el proyecto está protegido, Mapa 1 y las descargas controladas se cifran como contenedores `.hse` después de terminar la ejecución; no existe una contraseña incrustada en el HTML ni una copia en texto claro de la contraseña. El acceso se autoriza desde `Hispa-Syng.bat > Seguridad y accesos`, mediante la contraseña del proyecto, una credencial `.hsk` o el acceso recordado con Windows DPAPI. Los archivos sensibles se abren desde la opción `Abrir archivo protegido .hse`.

En modo protegido, los productos se generan en un área temporal privada fuera de Resultados, con acceso restringido al usuario del sistema operativo. Se cifran y verifican antes de incorporarlos a Resultados o a la publicación web. Los cálculos pueden necesitar archivos temporales en claro dentro de esa área privada; esta protección no equivale a cifrado permanente de todo el almacenamiento local. Antes de iniciar un análisis protegido, el programa revisa automáticamente las recuperaciones pendientes y los resultados existentes. Una ejecución interrumpida durante el cálculo se recupera como incompleta, con productos protegidos; no se presenta como una ejecución científica terminada. Si una verificación o recuperación falla, el programa bloquea el nuevo análisis y conserva el registro pendiente. Revisar y proteger resultados existentes permite ejecutar también esta revisión desde el menú.

Solo se produce un mapa interactivo de conservación. Su nombre contiene la
resolución seleccionada, por ejemplo:

`Mapa_Interactivo_Zonas_Prioritarias_Conservacion_10km.html`

En este visor, las geometrías oficiales MITECO se usan para asignar. La geometría marina analítica y la copia de representación proceden del recorte GSHHS o, cuando GSHHS produce un falso cero costero confirmado por MITECO, del respaldo celda-demarcación MITECO. Las celdas costeras mixtas se conservan incluso cuando `MARINO=0`; no se publica GSHHS como geometría HTML personalizada. La capa opcional `Zonas prioritarias` utiliza los mismos
colores de clase que la leyenda y `Etiquetas de zonas prioritarias` se puede
activar por separado. Las áreas protegidas se restringen a su intersección
marina con la máscara oficial MITECO; sus ventanas muestran nombre de la
designación, tipo de protección, nivel disponible y archivo de origen.

## Integridad de la resolución

En `[2/8 · 5/7]`, la red de similitud es adaptativa y dispersa: cada celda
aporta como máximo 12 vecinos. Las comunidades Louvain originales permanecen
en las salidas de auditoría, mientras que el análisis y las figuras usan como
máximo ocho clústeres fusionados. IndVal se calcula por clúster individual, no
para las combinaciones exponenciales entre clústeres.

La malla elegida al inicio se propaga a la malla maestra de hotspots, la señal
temporal, la puntuación de conservación, las celdas seleccionadas, las zonas
contiguas, los GeoPackages, los mapas y los informes. Las comprobaciones
automáticas verifican superficies nominales de 1, 25 y 100 km² para las
selecciones de 1, 5 y 10 km, respectivamente.

Las densidades totales y por especie utilizan siempre `Area_marina_km2`. La vía primaria es la geometría MITECO recortada por GSHHS en EPSG:3035. Si ese recorte produce un falso cero costero pero MITECO confirma superficie marina válida, se usa la intersección real celda–demarcación marina MITECO como geometría de respaldo. `Area_mar_km2` se calcula sobre esa geometría, que es también la representada, y `Area_mar_source` documenta la procedencia del denominador.
Antes de escribir la publicación web se recalculan y comprueban ambas tablas de
densidad; una discrepancia detiene la publicación.

El recorte GSHHS se almacena de forma persistente en `.cache/marine_areas`. Cada entrada conserva el `grid_id`, una huella de la geometría MITECO y el área marina calculada por GSHHS; no almacena geometría GSHHS. La caché solo se reutiliza si coincide la geometría exacta de la celda y no ha cambiado la firma de contenido de GSHHS. Las celdas que requieren respaldo MITECO se identifican en tiempo de ejecución a partir de la información marina oficial. Las ediciones española e inglesa comparten esta caché. Puede eliminarse sin riesgo: se reconstruye automáticamente en la siguiente ejecución.

## Compatibilidad con Excel

El libro de origen se lee en modo solo lectura. Cabeceras como `N hembra`,
`N macho`, `N_indeterminado` y `Captura incidental` no se modifican en el
libro. Las salidas españolas usan nombres como `N_hembra`, `N_macho`,
`N_indeterminado` y `Captura_incidental` cuando corresponde.

Los valores de hábitat se presentan en español: `Arena`, `Pradera marina`,
`Rocas`, `No determinado`, `Antrópico` y `Pelágico`. El libro de origen nunca
se modifica. La pertenencia regional se fija antes de asignar celdas analíticas: primero se usa la intersección directa punto-demarcación y, cuando no existe, se obtiene una región canónica con la malla oficial MITECO de referencia de 10 km, independientemente de que el análisis utilice celdas de 1, 5 o 10 km. La malla analítica seleccionada se utiliza después para asignación a celda, superficie marina, densidades y análisis espaciales. La auditoría regional documenta el método, la celda de referencia y la distancia cuando corresponde. Las métricas regionales vacías se marcan como no calculables, en lugar de producir un estadístico vacío sin explicación.

La asignación espacial sigue una jerarquía explícita: intersección directa con celda de superficie marina validada; conservación de la celda MITECO original mediante respaldo oficial cuando GSHHS produce un falso cero costero coherente con la demarcación; y, solo después, `nearest` entre celdas con superficie GSHHS positiva dentro de la tolerancia configurada. Los casos `nearest` y no asignados se documentan en `07_control_calidad`: `auditoria_asignacion_espacial_nearest_y_no_asignados.csv`, `resumen_auditoria_asignacion_espacial.csv` y `Mapa_QC_Asignacion_Espacial.html`. El mapa QC representa asignaciones directas en verde, `nearest` en naranja y no asignadas en rojo; muestra las celdas MITECO implicadas y el contexto terrestre GSHHS, con Satélite activo por defecto y Físico como alternativa. Las observaciones válidas que no pueden asignarse con seguridad a una celda permanecen en Mapa 1 y en las descargas completas, pero no participan en métricas por celda. La auditoría no cambia la tolerancia ni fuerza asignaciones.

Las salidas registradas duplicadas se eliminan después del análisis y se
conserva el primer archivo canónico de cada firma de contenido normalizada. La
información completa de zonas prioritarias aparece una sola vez en el libro
multiconjunto `Tabla_21_Zonas_Prioritarias_Conservacion.xlsx`. Las advertencias
de ejecución se capturan en `control_advertencias_ejecucion.csv` junto con la
fase y la acción afectadas.

En `Figura_Riqueza_Taxonomica_frente_a_Funcional` se mantienen todas las regiones MITECO del resumen. Las regiones cuyo FRic relativo no sea estimable no se eliminan: aparecen con una marca `X` en la banda `N.E.`. Los puntos con idéntica riqueza taxonómica y FRic se separan muy ligeramente en X para que sean visibles; este desplazamiento es solo gráfico y las tablas conservan los valores originales. Las salidas funcionales se organizan en `diversidad_funcional`, separadas de `comunidad_biogeografia`.

El `Id` de origen se conserva como metadato. No se utiliza como variable
analítica, clave espacial ni criterio de deduplicación. Cada fila válida recibe
un `obs_id` interno separado.

## Configuración de producción

La configuración inferencial recomendada es de 999 permutaciones. Valores
menores, como 49, se destinan únicamente a comprobaciones de instalación. Una
ejecución se declara correcta solo después de que superen los controles de
calidad analítica y espacial.

Consulte `../Manual_Hispa_Syng_v1_0_ES.docx`,
`MANUAL_ANALISIS_COMPLETO.md` y `VALIDACION.md` para obtener más información.

## Proxy común de eventos de observación

Cada observación válida proyectada recibe `sampling_event_id`, construido de forma determinista a partir de fecha + observador normalizado + posición EPSG:3035 redondeada a 1 m. No usa especie, abundancia, `Id` ni resolución de malla. El bloque temporal usa `n_sampling_events` como proxy principal de intensidad de observación y conserva `n_records` como descriptor/sensibilidad. El modelo temporal principal es Poisson sobre conteos con offset `log(n_sampling_events)` y corrección de sobredispersión de Pearson con `phi >= 1`; la inferencia requiere al menos 8 años de detección, 20 eventos con detección y 10 años de amplitud. La señal temporal canónica se calcula directamente sobre `grid_id` MITECO y usa cambios relativos simétricos invariantes a las unidades. La infraestructura común de eventos se utiliza también para el soporte de comunidad, multiescala y conservación; `n_records` se conserva como volumen descriptivo y no como esfuerzo de muestreo medido.

## Resultados protegidos y alcance de las credenciales

En modo protegido, los productos se generan en un área temporal privada fuera de Resultados, con acceso restringido al usuario del sistema operativo. Se cifran y verifican antes de incorporarlos a Resultados o a la publicación web. Los cálculos pueden necesitar archivos temporales en claro dentro de esa área privada; esta protección no equivale a cifrado permanente de todo el almacenamiento local.

Antes de iniciar un análisis protegido, el programa revisa automáticamente las recuperaciones pendientes y los resultados existentes. Una ejecución interrumpida durante el cálculo se recupera como incompleta, con productos protegidos; no se presenta como una ejecución científica terminada. Si una verificación o recuperación falla, el programa bloquea el nuevo análisis y conserva el registro pendiente. Revisar y proteger resultados existentes permite ejecutar también esta revisión desde el menú.

Se cifran Mapa 1 y el mapa QC, tablas, documentos, paquetes, registros y todo producto sin clasificación pública expresa. Los mapas agregados 2 y 3, visores, mapas agregados de conservación y recursos institucionales registrados se verifican y permanecen disponibles. El nombre o la extensión no conceden acceso público. Los campos y puntos de observaciones individuales se rechazan. La capa oficial de protección admite sus puntos catalogados. En celdas y zonas se representan solo los componentes poligonales, sin alterar la geometría analítica. Las figuras y auxiliares no registrados se cifran por defecto. Los HTML sensibles muestran una página informativa y conservan el original en .html.hse. La auditoría registra todos los archivos, su clasificación, motivo y SHA-256. Los hashes permiten contrastar integridad; no autentican al propietario.

El proyecto admite una sola operación activa de análisis o mantenimiento. Antes de crear una copia abierta o protegida, exige la autoridad del propietario y recupera los trabajos pendientes. Si falla la recuperación, bloquea la copia y su credencial y conserva el área privada y el registro. Los resultados incompletos se identifican como tales y se excluyen de las copias del programa.

La rotación prepara y verifica los nuevos contenedores y la recuperación antes de sustituir archivos activos. Mantiene un registro persistente y copias de recuperación hasta confirmar el cambio. Tras una interrupción, el siguiente acceso restaura el estado anterior si no se confirmó la operación, o completa la limpieza si ya se confirmó. La rotación no se inicia mientras haya ejecuciones privadas pendientes de recuperación.

La rotación impide que las credenciales antiguas abran los archivos recifrados del proyecto actualizado. No retira el acceso a copias antiguas conservadas con sus claves anteriores ni a información ya exportada. Cambiar la contraseña o volver a emitir una recuperación con la misma clave y el mismo token no invalida credenciales existentes. Olvidar acceso elimina el registro DPAPI local; no revoca otras copias conservadas de ese registro.

DPAPI utiliza el alcance del usuario actual de Windows, sin habilitar el alcance compartido por equipo. El token secreto del propietario se protege con la contraseña y solo se incluye en la credencial de recuperación y, si se recuerda autoridad administrativa, en el material DPAPI. La configuración contiene su hash de comprobación. Una credencial access no contiene ese token; el rol declarado en variables de entorno no concede administración. La separación presupone que el código y la configuración local no han sido sustituidos por un atacante con control del equipo. Un usuario autorizado para descifrar puede conservar o exportar los datos.

## Lectura de mallas y tiempos de preparación

El análisis completo utiliza las mallas oficiales de 1, 5 y 10 km, independientemente de la resolución seleccionada y de las comparaciones temporales. Las ventanas espaciales próximas a las observaciones se reúnen en una única consulta por archivo, sin simplificar sus límites ni cambiar las celdas seleccionadas. El orden original de las celdas se conserva. Cuando el controlador no dispone de GEOS o una ventana de borde es degenerada, se utiliza la lectura compatible por ventanas.

La consola muestra el archivo, las ventanas consultadas, las celdas cargadas y los tiempos de lectura y preparación. En el bloque multiescala se informa por separado del tiempo de superficies marinas y del total de cada escala. La caché de áreas GSHHS sigue siendo reutilizable; no es necesario borrarla. Esta caché evita repetir el recorte de superficies, pero no elimina la lectura de la cartografía. La consulta espacial no añade archivos con posiciones de observaciones ni una caché de geometrías seleccionadas.

## Uso sencillo de la protección

Para ejecutar un análisis habitual, elija **Ejecutar Hispa-Syng** en el menú principal. La carpeta actual conserva su estado abierto o protegido entre ejecuciones.

Dentro de **Seguridad y accesos**, **Proteger mi proyecto actual** cifra los datos de esta misma carpeta. **Preparar una copia para compartir** abre un apartado separado: una copia protegida crea otra carpeta con contraseña y clave propias; una copia abierta crea otra carpeta con datos legibles sin contraseña. Ninguna copia incluye resultados anteriores.

En un proyecto protegido, **Abrir archivo protegido .hse** permite consultar resultados. **Gestionar contraseña y accesos** reúne el cambio de contraseña, la recuperación del propietario, la rotación de clave, la revisión de resultados y la gestión del acceso recordado y de temporales. Para emitir una credencial ordinaria, use **Preparar una copia para compartir > Crear un archivo de acceso para este proyecto (.hsk)**. En una copia independiente, emita la credencial desde esa copia.

Cambiar contraseña no invalida credenciales existentes. **Retirar accesos anteriores al proyecto actual (rotar clave)** exige credenciales nuevas para los archivos recifrados; las copias antiguas con sus claves antiguas siguen siendo accesibles.

La guía **SEGURIDAD_Y_CONTRASENAS_HISPA_SYNG.docx** explica las carpetas y los siete casos prácticos.
