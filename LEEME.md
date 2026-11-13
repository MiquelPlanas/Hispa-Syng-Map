# Hispa-Syng v1.0 — guía en español del paquete bilingüe

Este paquete de código incluye el programa, los manuales, `Datos_data/traits.xlsx` y el libro de ejemplo `examples/Ingesta_ejemplo.xlsx`. El libro operativo de observaciones y la carpeta cartográfica `Resources/` se incorporan por separado. Prepare ambos antes de ejecutar un análisis, como se explica a continuación.

Hispa-Syng v1.0 es un software científico bilingüe desarrollado en el marco del **Proyecto Hippo-DEC** para el análisis espacial, temporal, ecológico y de conservación de registros de signátidos en aguas marinas españolas.

Hispa-Syng ha sido desarrollado gracias a la financiación del proyecto Hippo-DEC por parte del Ministerio para la Transición Ecológica y el Reto Demográfico (MITECO) del Gobierno de España.

La carpeta raíz coordina las ediciones española (`PYTHON_ESP`) e inglesa (`PYTHON_ENGLISH`) mediante un único lanzador y una selección común de parámetros.

Version: v1.0

Software licence: PolyForm Noncommercial License 1.0.0

User manuals and guides: CC BY-NC 4.0

Zenodo DOI: 10.5281/zenodo.24157711

[Read in English](https://github.com/MiquelPlanas/Hispa-Syng-Map/blob/main/README.md) · [Índice de documentación](https://github.com/MiquelPlanas/Hispa-Syng-Map/blob/main/LEEME.md#documentaci%C3%B3n)

## Inicio rápido en Windows

1. Extraiga el paquete completo de código de Hispa-Syng en una carpeta de Windows con permisos de escritura, por ejemplo `C:\Hispa-Syng`.
2. Para una demostración, **copie** [examples/Ingesta_ejemplo.xlsx](examples/Ingesta_ejemplo.xlsx) dentro de `Datos_data/` y cambie el nombre de la copia a **`Ingesta_provisional.xlsx`**. Conserve el ejemplo original en `examples/`. Para un análisis propio, utilice en su lugar un libro de observaciones compatible; si ya hay uno, guárdelo aparte antes de sustituirlo.
3. Descargue `Resources.zip` desde **Assets** en la [página de Releases](https://github.com/MiquelPlanas/Hispa-Syng-Map/releases). Extraiga el ZIP de modo que la carpeta `Resources/` quede junto a `Hispa-Syng.bat`.
4. Haga doble clic en `Hispa-Syng.bat`.
5. Escriba `1` o `2` para seleccionar el idioma de los mensajes y pulse Enter. Elija **Ejecutar Hispa-Syng** en el menú principal.
6. Seleccione años, resolución de malla, región MITECO, especies y periodos comparativos. La misma selección se aplica a ambas ediciones; los resultados se crean dentro de `Resultados/`.

Utilice los resultados del ejemplo para aprender y comprobar el flujo; no constituyen evidencia científica sobre observaciones reales. Los libros operativos locales quedan excluidos del control de versiones mediante `.gitignore`.

La consola muestra todas las etapas principales y sus subpasos analíticos, con
un cronómetro transcurrido `[HH:MM:SS]` para cada edición y para la ejecución
bilingüe completa.

La estructura compartida recomendada es:

```text
Datos_data/
├── Ingesta_provisional.xlsx
└── traits.xlsx

Resources/
├── areas_protegidas/
├── demarcaciones_miteco/
├── GSHHS/
└── Mallas_marinas_MITECO.zip
```

Las configuraciones y manifiestos técnicos de cada ejecución bilingüe se guardan automáticamente en `.ejecuciones/<id>/`; los productos científicos continúan bajo `Resultados/`.

La primera ejecución crea el entorno virtual `.venv` y descarga las dependencias necesarias. Las ejecuciones posteriores reutilizan ese entorno. Si el entorno queda incompleto o bloqueado, utilice `REPARAR_ENTORNO_HISPA_SYNG.bat` desde la raíz.

El instalador admite **Python de 64 bits 3.10–3.13** y prioriza Python 3.13 si está disponible. `requirements-lock-py313-win64.txt` conserva una configuración de dependencias destinada a Python 3.13 en Windows x64; no sustituye los requisitos de instalación normales. Los registros históricos de la batería general corresponden a Linux con Python 3.12.14. La ejecución operativa en Windows del 19 de octubre de 2026, revisada por separado, registra Python 3.13.15, pandas 2.3.3 y GeoPandas 1.2.0 en ambas ediciones, con coincidencia de los controles principales. Consulte [la evidencia de Windows](Validation/EJECUCION_WINDOWS_20261019.md) para conocer su alcance. Los informes JSON actuales conservan las rutas exactas de los archivos registrados; véanse [las comprobaciones de integridad de referencias](Validation/REFERENCIAS_JSON_VALIDACION.md), con sus pruebas y límites. Consulte [Validation/VALIDACION_ES.md](Validation/VALIDACION_ES.md) para identificar las evidencias y las comprobaciones nativas pendientes.

El [registro específico de seguridad en Windows](Validation/SEGURIDAD_WINDOWS_20261021.md), aportado por separado, registra nueve grupos de escenarios y el ciclo DPAPI del usuario actual superados. El aislamiento entre cuentas y la inspección independiente de ACL siguen sin verificarse; consulte el alcance en ese informe.

Hispa-Syng genera además un campo técnico reproducible `sampling_event_id` para cada observación válida proyectada. Se define mediante fecha interpretada + observador normalizado + posición EPSG:3035 redondeada a 1 m; no intervienen la especie, la abundancia, `Id` ni la resolución de malla. Si falta el observador se usa de forma conservadora la fila de origen para no fusionar registros sin evidencia. En Hispa-Syng v1.0, el **análisis temporal usa `n_sampling_events` como proxy principal de intensidad de observación**, manteniendo `n_records` como descriptor/sensibilidad. Las tendencias inferenciales usan Poisson con offset `log(n_sampling_events)` y corrección conservadora de sobredispersión de Pearson; las especies con soporte insuficiente quedan como `descriptive_only`. La señal temporal canónica se calcula además sobre `grid_id` MITECO oficial y con cambios relativos simétricos invariantes a las unidades. La comunidad y biogeografía usan soporte por eventos, Hellinger–Euclídea/Jaccard, LCBD dual con BH-FDR, PCoA con Lingoes y Mantel–Spearman; el multiescala opera directamente sobre mallas oficiales MITECO 1/5/10 km y conservación separa prioridad ecológica, prioridad de seguimiento temporal y suficiencia de datos. La priorización científica y la delimitación de **zonas prioritarias estratégicas** no se modifican: las zonas se anclan en núcleos Alta/Muy alta, pueden incorporar un único anillo de extensiones Media adyacentes con soporte mínimo y exportan por separado las unidades Media fuertes pero aisladas como candidatas para validación. Cuando el análisis descriptivo es de 1 km, el visor conserva además la clasificación ecológica de 1 km como una capa separada de **prioridad descriptiva**, mientras que la delimitación estratégica utiliza una unidad mínima de planificación de 5 km. A partir de cada zona estratégica se generan **zonas operativas de conservación** usando las celdas oficiales MITECO de 1 km que contienen observaciones y quedan dentro de la zona estratégica. Solo se fusionan celdas con evidencia que comparten borde (contigüidad rook); nunca se añaden celdas vacías para salvar discontinuidades, por lo que una misma zona estratégica puede dividirse en varias subzonas operativas. Estas huellas operativas sirven para focalizar acciones de campo o gestión, pero no deben interpretarse como límites completos de población ni como modelos de idoneidad de hábitat. Con resoluciones solicitadas de 5 o 10 km, prioridad descriptiva y planificación estratégica coinciden en la resolución seleccionada, pero la huella operativa sigue aprovechando la malla multiescala oficial de 1 km. Conservación usa tres vías ecológicas explícitas: evidencia convergente, núcleo de presencia persistente y núcleo de diversidad; un registro aislado nunca puede definir una unidad Alta/Muy alta. En las unidades de planificación, años, eventos, riqueza y abundancia se recalculan directamente desde las observaciones asignadas, evitando depender de resúmenes temporales intermedios. Cada ejecución exporta un resumen QA del proxy de eventos en `07_control_calidad` para la edición española y `07_quality_control` para la inglesa.

Para comprobar una instalación o una versión antes de distribuirla, ejecute `RUN_REGRESSION_TESTS.bat`. La suite de `tests/` utiliza geometrías sintéticas temporales y no modifica los datos operativos ni los resultados.

La carpeta principal puede moverse o renombrarse. No cambie los nombres ni separe las carpetas `PYTHON_ESP` y `PYTHON_ENGLISH`.

## Resultados de una ejecución bilingüe

Para cada ejecución se crean, entre otros, estos productos en `Resultados`:

- `ejecucion_<id>_ESP/`: resultados completos de la edición española;
- `run_<id>_EN/`: resultados completos de la edición inglesa;
- `Publicacion_Web_Bilingue_<id>/`: publicación web estática bilingüe que integra las dos ediciones.

Cada edición conserva además su propia estructura de tablas, figuras, modelos, control de calidad, visores y productos de zonas prioritarias. Consulte la documentación específica de cada edición para el detalle completo.

El análisis comunitario separa la composición relativa (Hellinger–Euclídea) de la incidencia (Jaccard). LCBD se calcula en dos perspectivas con p bruto y BH-FDR, y el soporte se expresa también mediante `n_sampling_events`. La PCoA Bray–Curtis aplica Lingoes si aparecen autovalores negativos y el distance-decay usa Mantel–Spearman permutacional; la regresión entre pares queda solo como descriptiva.

En la red biogeográfica, cada celda conserva como máximo sus 12 vecinos más
similares para evitar una red cuadrática en la malla de 1 km. Las comunidades
Louvain originales se auditan y la presentación analítica se fusiona en un
máximo de ocho clústeres interpretables.

### Informe técnico integral automático

Al finalizar una ejecución completa, cada edición genera automáticamente un informe técnico integral con la misma estructura y contenido científico en español e inglés. Se guarda, siempre desde la raíz del programa, en:

- `Resultados/ejecucion_<id>_ESP/10_informe_tecnico/Informe_Tecnico_Integral_Hispa-Syng_v1.0_ES.docx`
- `Resultados/run_<id>_EN/10_technical_report/Hispa-Syng_v1.0_Integrated_Technical_Report_EN.docx`

El informe integra los resultados de los bloques analíticos, desarrolla su interpretación científica, incluye tablas de cobertura temporal, regional y composición sexual, incorpora las zonas prioritarias y dos vistas cartográficas etiquetadas de esas zonas cuando existen, y termina con una guía de localización de los productos usando únicamente rutas relativas a la raíz de Hispa-Syng.

En los popups de conservación se muestra también la composición por especie: cada celda priorizada incluye el listado de especies presentes con su abundancia y densidad, y cada zona prioritaria resume esas mismas métricas a escala de zona; las densidades se expresan como individuos por km² de superficie marina. Los valores visibles y exportados se presentan con un máximo de dos decimales, mientras que los cálculos analíticos conservan la precisión completa. `Area_mar_km2` procede prioritariamente de la geometría MITECO tras sustraer la tierra GSHHS en EPSG:3035. Si GSHHS produce un falso cero costero pero MITECO confirma superficie marina oficial válida, la geometría de respaldo es la intersección real entre la celda y la demarcación marina oficial MITECO. `Area_mar_km2` se calcula a partir de esa misma geometría y la geometría marina mostrada en los mapas es idéntica a la utilizada como denominador de densidad.

Las escalas de color de densidad de los Mapas 2 y 3 son exclusivamente cartográficas. Cuando existen al menos 20 celdas con densidad positiva, el límite cromático se basa en el percentil empírico 95 (P95) y se redondea a un valor de leyenda legible; las celdas que superan ese límite conservan su densidad exacta y reciben el tono más oscuro. Con menos de 20 celdas positivas se utiliza el máximo observado completo. En Mapa 2 la escala robusta se recalcula cada vez que cambia la selección activa de especies. Los valores numéricos de popups, tablas, descargas y análisis nunca se recortan ni se winsorizan.

Para evitar repetir el recorte GSHHS costoso en cada ejecución, Hispa-Syng mantiene una caché validada en `.cache/marine_areas`. La primera ejecución de una resolución calcula las superficies GSHHS necesarias; las siguientes reutilizan únicamente las celdas cuya geometría MITECO coincide exactamente y siempre que no haya cambiado el contenido de GSHHS. Las celdas que requieren respaldo MITECO se identifican en tiempo de ejecución a partir de la información marina oficial y no se convierten silenciosamente en celdas GSHHS ordinarias. La caché es compartida por las ediciones española e inglesa, puede borrarse con seguridad y se reconstruirá automáticamente.

## Asignación espacial y superficie marina costera

La pertenencia regional y la asignación analítica a celda se resuelven por separado. Hispa-Syng intenta primero la intersección directa punto-demarcación; si no existe, fija una región canónica mediante la malla oficial MITECO de referencia de 10 km, independientemente de que el análisis utilice celdas de 1, 5 o 10 km. La malla analítica elegida se emplea después para asignación a celda, superficie marina, densidades y análisis espaciales. La auditoría regional se guarda en la carpeta de control de calidad de cada edición.

La malla oficial MITECO es la referencia de asignación. La superficie marina se obtiene prioritariamente mediante el recorte GSHHS. Si GSHHS produce un falso cero costero pero MITECO confirma superficie marina oficial válida, Hispa-Syng conserva la celda MITECO original mediante un respaldo cuya geometría es la intersección real entre la celda y la demarcación marina MITECO; el área usada en densidad coincide así con la geometría representada. Solo las observaciones todavía no resueltas pasan a `nearest`, y únicamente contra celdas con superficie GSHHS positiva dentro de la tolerancia configurada. Las observaciones válidas que aun así no pueden asignarse con seguridad se mantienen en Mapa 1 y en las descargas completas, pero se excluyen de las métricas espaciales por celda. Los casos `nearest` y no asignados quedan trazados en `07_control_calidad` mediante la auditoría detallada, su resumen y `Mapa_QC_Asignacion_Espacial.html`.

## Datos de entrada y recursos externos

Hispa-Syng localiza los recursos necesarios dentro de la estructura del proyecto. Los datos tabulares compartidos se mantienen en `Datos_data/`: `Ingesta_provisional.xlsx` para las observaciones y `traits.xlsx` para los rasgos. La distribución cartográfica recomendada es `Resources/areas_protegidas`, `Resources/demarcaciones_miteco`, `Resources/GSHHS` y `Resources/Mallas_marinas_MITECO.zip`. Los recursos cartográficos voluminosos o sujetos a distribución separada pueden mantenerse fuera del repositorio GitHub siempre que estén disponibles localmente al ejecutar el programa.

El archivo `Datos_data/traits.xlsx` contiene la información de rasgos utilizada por los análisis funcionales correspondientes.
La diversidad funcional usa exclusivamente las especies realmente presentes en la ejecución, un esquema explícito de seis rasgos, el espacio funcional resultante Gower/PCoA y una dimensionalidad común para comparar FRic/FDiv entre regiones. Los índices principales se basan en incidencia; la ponderación por `N_total` se conserva solo como sensibilidad y se exportan diagnósticos de cobertura/exclusión de rasgos.

### Fondos cartográficos interactivos

Los mapas interactivos principales ofrecen tres fondos en línea, en este orden: **Satélite — Esri World Imagery** (activo por defecto), **Batimetría marina — EMODnet Bathymetry World Base Layer** y **Físico — OpenTopoMap**. El mapa de control de calidad de asignación espacial utiliza únicamente **Satélite** (predeterminado) y **Físico** y no solicita teselas al servidor estándar de OpenStreetMap. Todos estos fondos aportan solo contexto visual, no intervienen en ningún cálculo científico y requieren conexión a Internet, pero no una clave API ni suscripción.

En la figura `Figura_Riqueza_Taxonomica_frente_a_Funcional` de la edición española,
la riqueza taxonómica se compara con **FRic relativo** (FRic regional dividido por
el casco funcional global de las especies seleccionadas). Si varias regiones
presentan exactamente los mismos valores, sus puntos se separan mínimamente en
horizontal para hacerlos visibles. La edición inglesa aplica el mismo criterio en
`Figure_Taxonomic_vs_Functional_Richness`. El desplazamiento es únicamente gráfico.

## Datos de entrada en la distribución pública

El paquete público de código **no incluye** `Ingesta_provisional.xlsx` real. Esa base de ocurrencias es operativa y debe mantenerse fuera del repositorio. Para una demostración, copie `examples/Ingesta_ejemplo.xlsx` como `Datos_data/Ingesta_provisional.xlsx`, siguiendo el inicio rápido. Para un análisis propio, coloque un libro compatible en esa ruta o configure su ubicación. Mantenga los datos operativos reales fuera del control de versiones.

## Seguridad, contraseña y credenciales

Hispa-Syng puede trabajar en **modo abierto** o como **proyecto protegido**. La contraseña pertenece al proyecto, no a una ejecución concreta: una vez activada la protección, todas las ejecuciones posteriores de ese mismo proyecto utilizan la misma configuración hasta que el propietario cambie la contraseña o rote la clave. La contraseña nunca se guarda en texto claro ni se incorpora al código.

Después de elegir el idioma, `Hispa-Syng.bat` ofrece `Ejecutar Hispa-Syng`, `Seguridad y accesos` y `Salir`. Desde `Seguridad y accesos` se puede activar la protección, consultar su estado, cambiar la contraseña, crear o importar credenciales `.hsk`, abrir archivos cifrados `.hse`, crear copias abiertas o protegidas, olvidar el acceso recordado, limpiar copias temporales, revisar resultados existentes y rotar la clave del proyecto.

Al activar la protección, `Datos_data/Ingesta_provisional.xlsx` se cifra como `Datos_data/Ingesta_provisional.hse`; la copia en claro se elimina después de verificar criptográficamente el contenedor. Durante una ejecución protegida, el libro se descifra **en memoria** para el análisis. En modo protegido, los productos se generan en un área temporal privada fuera de Resultados, con acceso restringido al usuario del sistema operativo. Se cifran y verifican antes de incorporarlos a Resultados o a la publicación web. Los cálculos pueden necesitar archivos temporales en claro dentro de esa área privada; esta protección no equivale a cifrado permanente de todo el almacenamiento local. Se cifran Mapa 1 y el mapa QC, tablas, documentos, paquetes, registros y todo producto sin clasificación pública expresa. Los mapas agregados 2 y 3, visores, mapas agregados de conservación y recursos institucionales registrados se verifican y permanecen disponibles. El nombre o la extensión no conceden acceso público. Los campos y puntos de observaciones individuales se rechazan. La capa oficial de protección admite sus puntos catalogados. En celdas y zonas se representan solo los componentes poligonales, sin alterar la geometría analítica. Las figuras y auxiliares no registrados se cifran por defecto. Los HTML sensibles muestran una página informativa y conservan el original en .html.hse. La auditoría registra todos los archivos, su clasificación, motivo y SHA-256. Los hashes permiten contrastar integridad; no autentican al propietario.

En Windows puede elegirse **Recordar acceso en este ordenador**. Hispa-Syng protege entonces la clave del proyecto mediante Windows DPAPI, vinculada al usuario de Windows. En ejecuciones posteriores del mismo proyecto y con ese mismo usuario de Windows, no es necesario volver a introducir la contraseña. Ese permiso local no se copia con la carpeta del proyecto y debe autorizarse de nuevo en otro ordenador o usuario de Windows.

Las credenciales `.hsk` son **credenciales portadoras** y deben guardarse y enviarse como secretos. Una credencial `access` contiene el material necesario para descifrar el proyecto, pero **no contiene autoridad de propietario**. La autoridad de propietario/recuperación se protege con un segundo token independiente, de modo que una credencial `access` no puede convertirse en `owner_recovery` simplemente modificando el archivo. La credencial `owner_recovery` contiene acceso a los datos y esa autoridad adicional. Cambiar la contraseña **no** revoca las credenciales de acceso ya emitidas. Para revocarlas se usa `Rotar clave y revocar credenciales`, que genera una nueva clave y una nueva autoridad de propietario, vuelve a cifrar los `.hse` y exige guardar una nueva credencial de recuperación.

Una **copia completamente abierta** se crea deliberadamente sin configuración de seguridad y con el libro de entrada en claro; está pensada para un colaborador de plena confianza. Una **copia protegida** recibe su propio ID de proyecto, contraseña y clave, independientes del original. Las copias excluyen `Resultados`, `.ejecuciones`, `.venv`, `.git` y cachés de ejecución, por lo que se distribuye un proyecto limpio sin modificar el original.

En modo protegido, los productos se generan en un área temporal privada fuera de Resultados, con acceso restringido al usuario del sistema operativo. Se cifran y verifican antes de incorporarlos a Resultados o a la publicación web. Los cálculos pueden necesitar archivos temporales en claro dentro de esa área privada; esta protección no equivale a cifrado permanente de todo el almacenamiento local. Antes de iniciar un análisis protegido, el programa revisa automáticamente las recuperaciones pendientes y los resultados existentes. Una ejecución interrumpida durante el cálculo se recupera como incompleta, con productos protegidos; no se presenta como una ejecución científica terminada. Si una verificación o recuperación falla, el programa bloquea el nuevo análisis y conserva el registro pendiente. Revisar y proteger resultados existentes permite ejecutar también esta revisión desde el menú.

El menú del proyecto protegido incluye además `Crear o renovar credencial de recuperación del propietario`, útil si se actualiza un proyecto creado con un esquema anterior o si el propietario desea generar una nueva recuperación. Hispa-Syng no distribuye una contraseña universal ni archivos de contraseña en texto claro. Para abrir un `.hse`, use `Hispa-Syng.bat > Seguridad y accesos > Abrir archivo protegido .hse`. El archivo se descifra en una carpeta temporal local; puede eliminarse con `Limpiar copias temporales descifradas`. El borrado ordinario no constituye borrado forense seguro en SSD/discos administrados por el sistema operativo.

La publicación web de un proyecto protegido sigue siendo estática para los productos no sensibles, pero los productos cifrados `.hse` **no se descifran en el navegador**. Para una publicación web con usuarios autorizados, debe aplicarse autenticación/autorización del servidor o publicar deliberadamente una copia abierta solo en un entorno cuya política de acceso sea adecuada.

## Documentación

**Orden recomendado:** empiece por este LEEME y continúe con la guía de instalación y publicación. Consulte el manual completo para interpretar los análisis y la guía de seguridad antes de activar la protección o preparar una copia para compartir. No necesita leer todos los archivos antes de empezar.

Los documentos españoles e ingleses de la tabla cumplen funciones equivalentes. El LEEME de la raíz presenta todo el proyecto bilingüe; el LEEME o README de cada edición ofrece sus instrucciones específicas.

| Qué necesita hacer | Español | Inglés |
| --- | --- | --- |
| Empezar y conocer la estructura | [LEEME.md](LEEME.md) | [README.md](README.md) |
| Instalar, ejecutar, reparar y publicar la web | [MANUAL_INSTALACION_PUBLICACION.docx](MANUAL_INSTALACION_PUBLICACION.docx) | [INSTALLATION_AND_WEB_PUBLICATION.docx](INSTALLATION_AND_WEB_PUBLICATION.docx) |
| Entender los análisis, las métricas y los resultados; ejemplos y glosario | [Manual_Hispa_Syng_v1_0_ES.docx](Manual_Hispa_Syng_v1_0_ES.docx) | [Manual_Hispa_Syng_v1_0_EN.docx](Manual_Hispa_Syng_v1_0_EN.docx) |
| Entender contraseñas, credenciales, copias y carpetas con siete casos prácticos | [SEGURIDAD_Y_CONTRASENAS_HISPA_SYNG.docx](SEGURIDAD_Y_CONTRASENAS_HISPA_SYNG.docx) | [SECURITY_PASSWORDS_AND_ACCESS_HISPA_SYNG_EN.docx](SECURITY_PASSWORDS_AND_ACCESS_HISPA_SYNG_EN.docx) |
| Consultar la ejecución y las salidas de una edición | [PYTHON_ESP/LEEME.md](PYTHON_ESP/LEEME.md) | [PYTHON_ENGLISH/README.md](PYTHON_ENGLISH/README.md) |
| Consultar el flujo y los bloques de análisis en formato Markdown | [PYTHON_ESP/MANUAL_ANALISIS_COMPLETO.md](PYTHON_ESP/MANUAL_ANALISIS_COMPLETO.md) | [PYTHON_ENGLISH/FULL_ANALYSIS_MANUAL.md](PYTHON_ENGLISH/FULL_ANALYSIS_MANUAL.md) |
| Preparar las columnas de entrada y entender los requisitos cartográficos | [PYTHON_ESP/ESPECIFICACION_ENTRADAS_Y_CARTOGRAFIA.md](PYTHON_ESP/ESPECIFICACION_ENTRADAS_Y_CARTOGRAFIA.md) | [PYTHON_ENGLISH/INPUT_AND_CARTOGRAPHY_SPECIFICATION.md](PYTHON_ENGLISH/INPUT_AND_CARTOGRAPHY_SPECIFICATION.md) |
| Consultar una guía breve de puesta en marcha de una edición | [PYTHON_ESP/LEEME_PRIMERO.txt](PYTHON_ESP/LEEME_PRIMERO.txt) | [PYTHON_ENGLISH/READ_ME_FIRST.txt](PYTHON_ENGLISH/READ_ME_FIRST.txt) |
| Mover la instalación a otra carpeta u ordenador | [PYTHON_ESP/TRASLADO_Y_EJECUCION.md](PYTHON_ESP/TRASLADO_Y_EJECUCION.md) | [PYTHON_ENGLISH/RELOCATION_AND_EXECUTION.md](PYTHON_ENGLISH/RELOCATION_AND_EXECUTION.md) |
| Consultar los criterios de validación propios de una edición | [PYTHON_ESP/VALIDACION.md](PYTHON_ESP/VALIDACION.md) | [PYTHON_ENGLISH/VALIDATION.md](PYTHON_ENGLISH/VALIDATION.md) |
| Consultar los informes fechados de validación del paquete | [Validation/VALIDACION_ES.md](Validation/VALIDACION_ES.md) | [Validation/VALIDACION_EN.md](Validation/VALIDACION_EN.md) |

Otros archivos de referencia compartidos:

| Archivo | Para qué sirve |
| --- | --- |
| [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | Fuentes y avisos de los recursos cartográficos, fondos web y componentes de terceros. |
| [CITATION.cff](CITATION.cff) | Metadatos para citar el software. |
| [LICENSE](LICENSE) | Condiciones de licencia del código fuente de Hispa-Syng. |
| [tests/README.md](tests/README.md) | Alcance, comandos y familias de pruebas de regresión. |
| [Validation/COMPROBACION_WINDOWS.md](Validation/COMPROBACION_WINDOWS.md) | Lista de comprobaciones nativas de Windows; no constituye un informe de pruebas superadas. |
| [Validation/LECTURA_ESPACIAL.md](Validation/LECTURA_ESPACIAL.md) | Ensayo fechado de lectura de las mallas MITECO. |
| [Validation/REVISION_CAPAS_PROTEGIDAS.md](Validation/REVISION_CAPAS_PROTEGIDAS.md) | Revisión de las capas cartográficas de espacios protegidos; no equivale a validar todo el análisis. |

Los JSON de `Validation/` conservan resultados estructurados de comprobaciones concretas. Sus fechas, entornos y alcance corresponden a esas comprobaciones. Los informes incluidos describen pruebas automatizadas en Linux; las comprobaciones nativas de Windows y una ejecución operativa completa requieren sus propias evidencias. Un cambio posterior en los archivos no actualiza automáticamente esos registros ni `Validation/CONTENIDO_SHA256.txt`.

## Licencia y citación

El código fuente de Hispa-Syng se distribuye bajo la **licencia PolyForm Noncommercial 1.0.0**. El texto completo figura en [LICENSE](LICENSE).

Los manuales y guías con aviso CC BY-NC 4.0, incluido este LEEME, se distribuyen bajo la licencia [Creative Commons Atribución–NoComercial 4.0 Internacional (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/).

Los componentes de terceros, los recursos cartográficos, los servicios y las marcas se rigen por sus propias condiciones. Consulte [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

La información de citación se encuentra en [CITATION.cff](CITATION.cff). Para citar Hispa-Syng Map v1.0, utilice el DOI de Zenodo [10.5281/zenodo.24157711](https://doi.org/10.5281/zenodo.24157711).

## Identidad del software

El nombre público del software es **Hispa-Syng v1.0** y **Hippo-DEC** identifica el proyecto marco. Los identificadores `hippodec_maps` y `HIPPODEC_ROOT` son nombres técnicos internos de implementación. La carpeta `.ejecuciones/` almacena únicamente configuraciones y manifiestos internos de cada ejecución bilingüe.


## Arquitectura científica de los análisis

La arquitectura científica integra un `sampling_event_id` compartido como proxy de intensidad de observación; análisis temporal basado en eventos proxy; comunidad con Hellinger–Euclídea/Jaccard, BH-FDR, Lingoes y Mantel; diversidad funcional con espacio Gower/PCoA y dimensionalidad común; multiescala directamente sobre mallas oficiales MITECO 1/5/10 km; y conservación separada en prioridad ecológica, prioridad de seguimiento temporal y suficiencia de datos. Los eventos proxy **no son esfuerzo de muestreo medido**, y los registros oportunistas no se convierten en un diseño de detección ni en un censo poblacional.


## Resultados protegidos y alcance de las credenciales

En modo protegido, los productos se generan en un área temporal privada fuera de Resultados, con acceso restringido al usuario del sistema operativo. Se cifran y verifican antes de incorporarlos a Resultados o a la publicación web. Los cálculos pueden necesitar archivos temporales en claro dentro de esa área privada; esta protección no equivale a cifrado permanente de todo el almacenamiento local.

Antes de iniciar un análisis protegido, el programa revisa automáticamente las recuperaciones pendientes y los resultados existentes. Una ejecución interrumpida durante el cálculo se recupera como incompleta, con productos protegidos; no se presenta como una ejecución científica terminada. Si una verificación o recuperación falla, el programa bloquea el nuevo análisis y conserva el registro pendiente. Revisar y proteger resultados existentes permite ejecutar también esta revisión desde el menú.

Se cifran Mapa 1 y el mapa QC, tablas, documentos, paquetes, registros y todo producto sin clasificación pública expresa. Los mapas agregados 2 y 3, visores, mapas agregados de conservación y recursos institucionales registrados se verifican y permanecen disponibles. El nombre o la extensión no conceden acceso público. Los campos y puntos de observaciones individuales se rechazan. La capa oficial de protección admite sus puntos catalogados. En celdas y zonas se representan solo los componentes poligonales, sin alterar la geometría analítica. Las figuras y auxiliares no registrados se cifran por defecto. Los HTML sensibles muestran una página informativa y conservan el original en .html.hse. La auditoría registra todos los archivos, su clasificación, motivo y SHA-256. Los hashes permiten contrastar integridad; no autentican al propietario.

La rotación prepara y verifica los nuevos contenedores y la recuperación antes de sustituir archivos activos. Mantiene un registro persistente y copias de recuperación hasta confirmar el cambio. Tras una interrupción, el siguiente acceso restaura el estado anterior si no se confirmó la operación, o completa la limpieza si ya se confirmó. La rotación no se inicia mientras haya ejecuciones privadas pendientes de recuperación.

La rotación impide que las credenciales antiguas abran los archivos recifrados del proyecto actualizado. No retira el acceso a copias antiguas conservadas con sus claves anteriores ni a información ya exportada. Cambiar la contraseña o volver a emitir una recuperación con la misma clave y el mismo token no invalida credenciales existentes. Olvidar acceso elimina el registro DPAPI local; no revoca otras copias conservadas de ese registro.

DPAPI utiliza el alcance del usuario actual de Windows, sin habilitar el alcance compartido por equipo. El token secreto del propietario se protege con la contraseña y solo se incluye en la credencial de recuperación y, si se recuerda autoridad administrativa, en el material DPAPI. La configuración contiene su hash de comprobación. Una credencial access no contiene ese token; el rol declarado en variables de entorno no concede administración. La separación presupone que el código y la configuración local no han sido sustituidos por un atacante con control del equipo. Un usuario autorizado para descifrar puede conservar o exportar los datos.

## Lectura de mallas y tiempos de preparación

El análisis completo utiliza las mallas oficiales de 1, 5 y 10 km, independientemente de la resolución seleccionada y de las comparaciones temporales. Las ventanas espaciales próximas a las observaciones se reúnen en una única consulta por archivo, sin simplificar sus límites ni cambiar las celdas seleccionadas. El orden original de las celdas se conserva. Cuando el controlador no dispone de GEOS o una ventana de borde es degenerada, se utiliza la lectura compatible por ventanas.

La consola muestra el archivo, las ventanas consultadas, las celdas cargadas y los tiempos de lectura y preparación. En el bloque multiescala se informa por separado del tiempo de superficies marinas y del total de cada escala. La caché de áreas GSHHS sigue siendo reutilizable; no es necesario borrarla. Esta caché evita repetir el recorte de superficies, pero no elimina la lectura de la cartografía. La consulta espacial no añade archivos con posiciones de observaciones ni una caché de geometrías seleccionadas.

El proyecto admite una sola operación activa de análisis o mantenimiento. Antes de crear una copia abierta o protegida, exige la autoridad del propietario y recupera los trabajos pendientes. Si falla la recuperación, bloquea la copia y su credencial y conserva el área privada y el registro. Los resultados incompletos se identifican como tales y se excluyen de las copias del programa.

Las exportaciones conservan los valores originales de identificadores, comentarios, observadores, enlaces y archivos de origen en ambas ediciones. Las etiquetas de presentación y las categorías de hábitat se localizan; los cálculos internos conservan su precisión.

## Uso sencillo de la protección

Para ejecutar un análisis habitual, elija **Ejecutar Hispa-Syng** en el menú principal. La carpeta actual conserva su estado abierto o protegido entre ejecuciones.

Dentro de **Seguridad y accesos**, **Proteger mi proyecto actual** cifra los datos de esta misma carpeta. **Preparar una copia para compartir** abre un apartado separado: una copia protegida crea otra carpeta con contraseña y clave propias; una copia abierta crea otra carpeta con datos legibles sin contraseña. Ninguna copia incluye resultados anteriores.

En un proyecto protegido, **Abrir archivo protegido .hse** permite consultar resultados. **Gestionar contraseña y accesos** reúne el cambio de contraseña, la recuperación del propietario, la rotación de clave, la revisión de resultados y la gestión del acceso recordado y de temporales. Para emitir una credencial ordinaria, use **Preparar una copia para compartir > Crear un archivo de acceso para este proyecto (.hsk)**. En una copia independiente, emita la credencial desde esa copia.

Cambiar contraseña no invalida credenciales existentes. **Retirar accesos anteriores al proyecto actual (rotar clave)** exige credenciales nuevas para los archivos recifrados; las copias antiguas con sus claves antiguas siguen siendo accesibles.

La guía **SEGURIDAD_Y_CONTRASENAS_HISPA_SYNG.docx** explica las carpetas y los siete casos prácticos.
