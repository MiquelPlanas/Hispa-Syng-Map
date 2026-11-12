# Third-Party Notices

The Hispa-Syng v1.0 source code is licensed under the PolyForm Noncommercial License 1.0.0. User manuals and guides bearing a CC BY-NC 4.0 notice are licensed under [Creative Commons Attribution–NonCommercial 4.0 International (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/). Third-party components, data, services, names, logos and other materials identified below remain subject to their respective licences and terms.

## Leaflet

Hispa-Syng bundles Leaflet 1.9.4 in both language editions under:

`src/hippodec_maps/vendor/leaflet/`

Leaflet is licensed under the BSD 2-Clause License. The upstream Leaflet license file is retained with the bundled files.

Source: https://leafletjs.com/

## GSHHS / GSHHG

Hispa-Syng uses a high-resolution GSHHS coastline/land polygon shapefile subset to subtract land from MITECO grid cells in EPSG:3035. That clipped geometry supplies both the density denominator and the matching cartographic display. When GSHHS produces a coastal false zero but the official MITECO marine subdivision confirms valid marine surface, the fallback geometry is the actual cell–marine-subdivision intersection, and its calculated area is used consistently for density and display.

The upstream GSHHG project is distributed under the GNU Lesser General Public License (LGPL). The GSHHS/GSHHG data retain their upstream licence.

Upstream project: https://github.com/GenericMappingTools/gshhg-gmt

Recommended scientific reference:

Wessel, P. & Smith, W. H. F. (1996). A global, self-consistent, hierarchical, high-resolution shoreline database. Journal of Geophysical Research, 101(B4), 8741–8743.

Source release identified by the package maintainer: **GSHHG 2.3.7**, released on 15 June 2017, from `gshhg-shp-2.3.7.zip`.

Reported source download: https://www.ngdc.noaa.gov/mgg/shorelines/data/gshhg/latest/gshhg-shp-2.3.7.zip

Maintainers' distribution: https://www.soest.hawaii.edu/pwessel/gshhg/gshhg-shp-2.3.7.zip

The Resources distribution retains the original archive's licence and notices in `Resources/GSHHS/LICENSE.TXT`, `COPYING.LESSERv3`, `README.TXT` and `SHAPEFILES.TXT`, the GNU GPL v3 text referenced by the LGPL in `COPYINGv3`, and bilingual provenance in `ORIGEN_Y_LICENCIA_GSHHG.txt`. The original licence notice specifies LGPL version 3 or later. This identifies the reported source release; it does not assert independently verified byte identity for local shapefiles.

## MITECO marine reference grids

Source: Ministerio para la Transición Ecológica y el Reto Demográfico (MITECO), Banco de Datos de la Naturaleza.

The official catalogue describes Shapefile grids with nominal cell sizes of 1, 5 and 10 km, developed in December 2012 and revised in April 2020. These catalogue dates do not establish independently verified identity of local files.

Catalogue: https://www.miteco.gob.es/es/biodiversidad/servicios/banco-datos-naturaleza/informacion-disponible/bdn-cart-aux-malla-marina.html
Downloads: https://www.miteco.gob.es/es/biodiversidad/servicios/banco-datos-naturaleza/informacion-disponible/bdn-cart-aux-descargas-marina.html
General legal notice: https://www.miteco.gob.es/es/atencion-al-ciudadano/aviso-legal.html

Reuse is subject to MITECO's applicable terms, including source attribution, preservation of existing update/reuse metadata, third-party rights and any specific conditions. Inclusion does not imply MITECO endorsement. These data are not relicensed under Hispa-Syng's software licence.

The Resources distribution records the packager's reported origin of `Mallas_marinas_MITECO.zip` in `Resources/ORIGEN_Y_CONDICIONES_MALLAS_MITECO.txt` (Spanish and English). Pages checked on 14 October 2026. This notice covers the reference grids; it does not identify the separate marine-demarcation or protected-area layers.

## MITECO marine demarcations

Source: Ministerio para la Transición Ecológica y el Reto Demográfico (MITECO).

Official download page: https://www.miteco.gob.es/es/cartografia-y-sig/ide/descargas/costas-medio-marino/demarcaciones-marinas.html
Download access: https://gis.miteco.gob.es/descargas/app/DescargaFichero?f=ddmm.zip
Service description: https://gis.miteco.gob.es/descargas/info/EM_DDMM.pdf

The download page states an update date of 5 October 2022. The packager reports the local file stem `Demarcaciones_Marinas_20220909_ModeloDatosINSPIRE`; its embedded date is a separate reference. Exact local-file identity against the upstream download has not been verified.

The specific conditions allow free use with MITECO attribution and require a notice that the map serves technical purposes and does not officially delimit international borders. The required Spanish wording and an English translation are retained in `Resources/demarcaciones_miteco/ORIGEN_Y_CONDICIONES_DEMARCACIONES_MITECO.txt`. Preserve the attribution, notice and available original metadata with this layer and its cartographic representations. These data retain their own reuse terms independently of Hispa-Syng's software licence.

Pages checked on 14 October 2026. This section covers marine demarcations; protected-area layers require their own provenance and terms.

## MITECO protected-area layers

Source: Ministerio para la Transición Ecológica y el Reto Demográfico (MITECO).

The Resources distribution includes `ENP/Enp2024.shp`, two Natura 2000 shapefiles with the `202412` filename reference, and `RAMPE/Rampe_2025.shp`, under `Resources/areas_protegidas/`. The OSPAR folder in the inspected input is empty and supplies no layer.

Reported download pages:
- RAMPE: https://www.miteco.gob.es/es/cartografia-y-sig/ide/descargas/biodiversidad/rampe.html
- Natura 2000: https://www.miteco.gob.es/es/biodiversidad/servicios/banco-datos-naturaleza/informacion-disponible/rednatura_2000_desc.html
- ENP: https://www.miteco.gob.es/es/cartografia-y-sig/ide/descargas/biodiversidad/enp.html

Natura 2000 catalogue and specific terms: https://www.miteco.gob.es/es/cartografia-y-sig/ide/descargas/biodiversidad/rn2000.html

The official RAMPE, ENP and RN2000 pages allow free use with MITECO attribution as author and owner. Preserve source credit and original metadata. These layers retain their own reuse conditions independently of the software licence.

The bilingual `Resources/areas_protegidas/ORIGEN_Y_CONDICIONES_AREAS_PROTEGIDAS.txt` records exact filenames, technical dates, coordinate systems and metadata limitations, and retains the required source-credit wording. Existing metadata and the ENP data dictionary are preserved. Current portal update dates are not asserted as the versions of local files. Exact byte identity against upstream downloads remains unverified. Pages checked on 14 October 2026.

## Online basemaps

Hispa-Syng main interactive maps use three remote basemap services for geographic context. The spatial-assignment QC map uses the Esri World Imagery and OpenTopoMap services only. The browser requests basemaps from their providers under the respective service terms. They require an Internet connection and do not participate in scientific calculations.

### Esri World Imagery

**Satellite — Esri World Imagery** is the default basemap. Source attribution displayed in the viewer includes Esri, Vantor, Earthstar Geographics, and the GIS User Community. Use is subject to Esri's applicable terms and attribution requirements.

Esri legal/terms information: https://www.esri.com/en-us/legal/overview

### OpenTopoMap

**Physical — OpenTopoMap** uses OpenStreetMap data and SRTM-derived elevation information with the OpenTopoMap cartographic style. The viewer displays the required source and style attribution. OpenTopoMap is accessed through its public raster tile service and requires no API key or subscription.

OpenTopoMap: https://opentopomap.org/
OpenStreetMap copyright: https://www.openstreetmap.org/copyright

### EMODnet Bathymetry

**Marine bathymetry — EMODnet Bathymetry World Base Layer** is an optional global bathymetric/topographic basemap served through the EMODnet Bathymetry tiled web service. It is not intended for navigation. EMODnet data products are generally made available under Creative Commons Attribution 4.0 (CC BY 4.0), subject to the associated metadata and terms of use. The viewer displays EMODnet attribution.

EMODnet Bathymetry: https://emodnet.ec.europa.eu/en/bathymetry
EMODnet terms of use: https://emodnet.ec.europa.eu/en/terms-use-emodnet-online-services-data-and-data-products

## Institutional and project logos

Logos and marks displayed with Hispa-Syng, including institutional, governmental, funding-program, CSIC/IIM, and Hippo-DEC marks, remain subject to the rights and branding rules of their respective owners.

## Python dependencies

Hispa-Syng depends on third-party Python packages listed in `requirements.txt`. Each installed package remains subject to its own upstream licence.
