# Manual del análisis completo — Hispa-Syng v1.0

**Licencia de esta guía:** [Creative Commons Atribución–NoComercial 4.0 Internacional (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/).

## Flujo de trabajo

1. Leer y auditar el libro Excel original.
2. Filtrar especies y fechas de observación.
3. Transformar las observaciones válidas a EPSG:3035.
4. Fijar primero la pertenencia regional MITECO canónica (intersección directa con la demarcación y, si falta, malla oficial de referencia de 10 km) y asignar después las observaciones a la malla analítica seleccionada de 1/5/10 km.
5. Calcular las métricas de celda y los mapas 1–3.
6. Ejecutar los bloques analíticos 8–21.
7. Generar el **bloque documental 22**, que construye el informe técnico integral a partir exclusivamente de los resultados de la ejecución actual.
8. Aplicar los controles de calidad analítica, espacial y documental finales.

La presentación española se aplica al exportar. Los valores de hábitat se
mantienen como `Arena`, `Pradera marina`, `Rocas`, `No determinado`,
`Antrópico` y `Pelágico`; el libro de ingesta nunca se reescribe. La auditoría de asignación regional distingue intersecciones directas con la demarcación, asignaciones canónicas mediante la malla oficial de referencia de 10 km y casos no resueltos, y registra la celda de referencia y la distancia cuando corresponde. La pertenencia regional es así independiente de la resolución analítica. Los registros que pertenecen al ámbito regional canónico seleccionado pero no pueden asignarse con seguridad a una celda de la resolución elegida se conservan en `puntos_fuera_malla.csv`, Mapa 1 y las descargas completas, pero se excluyen de densidades y análisis espaciales por celda.

Cuando la malla MITECO contiene el campo `MARINO`, se conserva como metadato de auditoría y no se usa por sí solo para eliminar celdas costeras mixtas. Para cada celda, la superficie marina efectiva se obtiene prioritariamente en EPSG:3035 como geometría MITECO menos tierra GSHHS. Si GSHHS produce un falso cero costero pero MITECO confirma superficie marina oficial válida, se utiliza como respaldo la intersección real entre la celda y la demarcación marina MITECO; `Area_mar_km2` se calcula sobre esa misma geometría y la copia cartográfica es idéntica. La asignación se intenta primero por intersección directa; en celdas de respaldo exige coherencia entre la región marina del punto y la de la celda. Solo los puntos todavía no resueltos pasan a `nearest`, entre celdas con superficie GSHHS positiva y dentro de la tolerancia configurada. Las densidades se calculan como `N / Area_mar_km2` y se expresan en ind./km², sin factor ×1.000. Los valores visibles y exportados se presentan con un máximo de dos decimales; los cálculos analíticos conservan la precisión completa.

La representación cromática de densidad no modifica esa fórmula. Para evitar que una celda costera con una fracción marina extremadamente pequeña comprima toda la gama de colores, Mapas 2 y 3 usan un techo visual robusto basado en P95 cuando hay al menos 20 celdas con densidad positiva. El techo se redondea a un valor legible; valores superiores se saturan únicamente en color y siguen mostrando su densidad exacta en popups y exportaciones. Con menos de 20 celdas positivas se usa el máximo completo.

Los casos `nearest` y los no asignados se documentan en `auditoria_asignacion_espacial_nearest_y_no_asignados.csv`, se resumen en `resumen_auditoria_asignacion_espacial.csv` y se visualizan en `Mapa_QC_Asignacion_Espacial.html`. El mapa QC distingue asignaciones directas en verde, por proximidad en naranja y no asignadas en rojo; incorpora las celdas MITECO implicadas y el contexto terrestre GSHHS próximo. Usa Satélite — Esri World Imagery como fondo predeterminado y Físico — OpenTopoMap como alternativa, sin solicitar teselas al servidor estándar de OpenStreetMap. Las observaciones válidas sin celda segura se conservan en Mapa 1 y en las descargas completas, pero no intervienen en análisis por celda. Este control es diagnóstico: no cambia la tolerancia ni fuerza nuevas asignaciones.

El lanzador muestra las etapas 1/8–8/8, cada subpaso analítico y su tiempo
transcurrido `[HH:MM:SS]`, además del tiempo de cada edición y del total bilingüe.

## Bloques analíticos

- **8–9:** intensidad de observación mediante proxies, riqueza, abundancia, frecuencia/amplitud relativa de detección registrada, distribución costera registrada, dominancia, hábitat, clases de profundidad y contrastes estadísticos;
- **10–11:** matrices de abundancia y presencia, diversidad beta
  Bray–Curtis/Jaccard, PERMANOVA, betadisper, NMDS/PCoA, LCBD y contexto
  ambiental;
- **12:** análisis directo sobre las mallas oficiales MITECO de 10/5/1 km, LCBD-Jaccard con soporte por eventos y BH-FDR, persistencia simétrica 1→5→10 km, decaimiento mediante Mantel, Monte Carlo de Moran y clústeres descriptivos de hotspots;
- **Funcional:** distancia de Gower y métricas FRic, FEve, FDiv, FDis y RaoQ
  basadas en PCoA;
- **Sexual:** resúmenes globales y regionales, pruebas binomiales exactas,
  chi-cuadrado, residuos estandarizados y modelo regional cuasi-binomial;
- **13–19:** IndVal con BH-FDR, SIMPER, rareza ponderada por rango observado, clases relativas de frecuencia de detección, redes, clústeres comunitarios, composición biogeográfica y sensibilidad al umbral. La red
  adaptativa conserva como máximo 12 vecinos por celda; las comunidades
  Louvain originales se auditan y se fusionan en un máximo de ocho clústeres
  analíticos. IndVal se limita a clústeres individuales;
- **20:** series anuales ajustadas por intensidad de observación mediante eventos proxy, modelos de Poisson, splines
  flexibles, comparaciones entre periodos, cambios por celda, mapas de cambio,
  clasificaciones y narrativas;
- **21:** prioridad ecológica, prioridad independiente de seguimiento temporal y suficiencia de datos; si la resolución solicitada es 1 km, el visor presenta prioridad descriptiva a 1 km y unidades de planificación estratégica a 5 km. Las zonas prioritarias estratégicas mantienen la metodología de núcleos Alta/Muy alta, extensiones Media elegibles y contigüidad rook. Después, sin recalcular prioridad, se delimitan zonas operativas mediante celdas MITECO oficiales de 1 km con observaciones dentro de cada zona estratégica: solo se unen celdas con evidencia que comparten borde y nunca se añaden celdas vacías de enlace. Una zona estratégica puede dividirse en varias subzonas operativas. Estas huellas se destinan a focalizar actuaciones y no equivalen a límites completos de población o hábitat. El bloque conserva las tres vías ecológicas (convergencia, presencia persistente y núcleo de diversidad), la sensibilidad a ponderaciones, las brechas de áreas protegidas, la gestión y las necesidades de validación.
- **22 (documental, sin recalcular análisis):** genera `10_informe_tecnico/Informe_Tecnico_Integral_Hispa-Syng_v1.0_ES.docx`. Integra las salidas de los bloques anteriores, desarrolla la discusión científica, incorpora tablas de cobertura temporal/regional/sexual, añade dos mapas etiquetados de zonas prioritarias cuando existen y finaliza con la localización de archivos mediante rutas relativas a la raíz de Hispa-Syng.

Cuando un grupo regional no tiene observaciones completas para una métrica, la
salida se conserva con `estado_calculo = no_calculable` y una explicación. Las
advertencias se capturan y se informan en los controles de calidad; no se
silencian. La publicación estática ofrece un informe Word, un libro Excel y un
ZIP de datos reutilizable para cada uno de los cuatro mapas. Cada ZIP contiene
datos CSV, el Excel y Word correspondientes, capas GeoPackage cuando existen,
parámetros, metodología, diccionario de datos y manifiesto de sumas de
comprobación.

En `Figura_Riqueza_Taxonomica_frente_a_Funcional` se representan siempre las regiones MITECO incluidas en el resumen regional: riqueza taxonómica en X y FRic relativo en Y. Si FRic no puede estimarse por insuficiencia de especies funcionalmente caracterizadas para la dimensionalidad común, la región no desaparece del gráfico: se muestra con una marca `X` en la banda `N.E.` (no estimable), fuera de la escala numérica de FRic. Si dos o más regiones
tienen exactamente ambos valores iguales, los símbolos se separan hasta 0,025
unidades a cada lado **solo en la posición horizontal dibujada** para evitar
que se tapen. La riqueza taxonómica real sigue siendo un número entero, y ni
FRic ni las tablas exportadas cambian. La figura explica expresamente este
desplazamiento; para citar cifras, use
`Table_Taxonomic_vs_Functional_Richness_by_Region` y la tabla de diversidad
funcional, no la posición desplazada de un símbolo. Las salidas de este bloque se guardan de forma independiente en `04_tablas\diversidad_funcional`, `05_figuras\diversidad_funcional` y `06_modelos\diversidad_funcional`; no se mezclan con `comunidad_biogeografia`.

Cuando el proyecto está protegido, Mapa 1, el mapa QC, los productos intermedios a nivel de observación y las descargas controladas se cifran al finalizar la ejecución como contenedores `.hse`. La contraseña es una propiedad persistente del proyecto y no de cada ejecución. El acceso se gestiona desde `Hispa-Syng.bat > Seguridad y accesos`; puede autorizarse con la contraseña del propietario, una credencial `.hsk` o una clave local recordada mediante Windows DPAPI. Los valores, popups y contenidos analíticos no se modifican por el cifrado. En modo abierto no se aplica este cifrado.

## Interpretación

Las salidas describen la base de datos disponible y son sensibles a la intensidad de observación, la cobertura espacial y la cobertura temporal. `sampling_event_id` es un proxy reproducible de ocasión/intensidad de observación, no una medida de tiempo, superficie o detectabilidad y, por tanto, no es esfuerzo de muestreo medido. La
significación estadística no demuestra por sí sola causalidad, tendencia
poblacional ni estado de conservación. Las clases de prioridad ecológica son categorías de screening relativas a la ejecución actual, usan umbrales fijos y no fuerzan un porcentaje de unidades en Alta/Muy alta. Las zonas se anclan en núcleos Alta/Muy alta y pueden incorporar un único anillo de extensiones Media adyacentes con soporte mínimo; las candidatas Media aisladas se exportan aparte. La prioridad de seguimiento temporal y la suficiencia de datos se informan por separado. Los productos apoyan la evaluación técnica y requieren validación de campo, revisión experta y el procedimiento reglamentario aplicable.


### Seguridad del proyecto
En modo protegido, los productos se generan en un área temporal privada fuera de Resultados, con acceso restringido al usuario del sistema operativo. Se cifran y verifican antes de incorporarlos a Resultados o a la publicación web. Los cálculos pueden necesitar archivos temporales en claro dentro de esa área privada; esta protección no equivale a cifrado permanente de todo el almacenamiento local. Antes de iniciar un análisis protegido, el programa revisa automáticamente las recuperaciones pendientes y los resultados existentes. Una ejecución interrumpida durante el cálculo se recupera como incompleta, con productos protegidos; no se presenta como una ejecución científica terminada. Si una verificación o recuperación falla, el programa bloquea el nuevo análisis y conserva el registro pendiente. Revisar y proteger resultados existentes permite ejecutar también esta revisión desde el menú.

## Resultados protegidos y alcance de las credenciales

En modo protegido, los productos se generan en un área temporal privada fuera de Resultados, con acceso restringido al usuario del sistema operativo. Se cifran y verifican antes de incorporarlos a Resultados o a la publicación web. Los cálculos pueden necesitar archivos temporales en claro dentro de esa área privada; esta protección no equivale a cifrado permanente de todo el almacenamiento local.

Antes de iniciar un análisis protegido, el programa revisa automáticamente las recuperaciones pendientes y los resultados existentes. Una ejecución interrumpida durante el cálculo se recupera como incompleta, con productos protegidos; no se presenta como una ejecución científica terminada. Si una verificación o recuperación falla, el programa bloquea el nuevo análisis y conserva el registro pendiente. Revisar y proteger resultados existentes permite ejecutar también esta revisión desde el menú.

Se cifran Mapa 1 y el mapa QC, tablas, documentos, paquetes, registros y todo producto sin clasificación pública expresa. Los mapas agregados 2 y 3, visores, mapas agregados de conservación y recursos institucionales registrados se verifican y permanecen disponibles. El nombre o la extensión no conceden acceso público. Los campos y puntos de observaciones individuales se rechazan. La capa oficial de protección admite sus puntos catalogados. En celdas y zonas se representan solo los componentes poligonales, sin alterar la geometría analítica. Las figuras y auxiliares no registrados se cifran por defecto. Los HTML sensibles muestran una página informativa y conservan el original en .html.hse. La auditoría registra todos los archivos, su clasificación, motivo y SHA-256. Los hashes permiten contrastar integridad; no autentican al propietario.

El proyecto admite una sola operación activa de análisis o mantenimiento. Antes de crear una copia abierta o protegida, exige la autoridad del propietario y recupera los trabajos pendientes. Si falla la recuperación, bloquea la copia y su credencial y conserva el área privada y el registro. Los resultados incompletos se identifican como tales y se excluyen de las copias del programa.

La rotación prepara y verifica los nuevos contenedores y la recuperación antes de sustituir archivos activos. Mantiene un registro persistente y copias de recuperación hasta confirmar el cambio. Tras una interrupción, el siguiente acceso restaura el estado anterior si no se confirmó la operación, o completa la limpieza si ya se confirmó. La rotación no se inicia mientras haya ejecuciones privadas pendientes de recuperación.

La rotación impide que las credenciales antiguas abran los archivos recifrados del proyecto actualizado. No retira el acceso a copias antiguas conservadas con sus claves anteriores ni a información ya exportada. Cambiar la contraseña o volver a emitir una recuperación con la misma clave y el mismo token no invalida credenciales existentes. Olvidar acceso elimina el registro DPAPI local; no revoca otras copias conservadas de ese registro.

DPAPI utiliza el alcance del usuario actual de Windows, sin habilitar el alcance compartido por equipo. El token secreto del propietario se protege con la contraseña y solo se incluye en la credencial de recuperación y, si se recuerda autoridad administrativa, en el material DPAPI. La configuración contiene su hash de comprobación. Una credencial access no contiene ese token; el rol declarado en variables de entorno no concede administración. La separación presupone que el código y la configuración local no han sido sustituidos por un atacante con control del equipo. Un usuario autorizado para descifrar puede conservar o exportar los datos.
