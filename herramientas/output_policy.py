"""Explicit public-product registration; all unregistered output is private.

This policy assumes trusted program code and local configuration. A registration
is bound to file bytes and a generator role, not a filename or extension.
"""
from __future__ import annotations
import copy
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path

REGISTRY_NAME = '.hispa_public_outputs.json'
PRODUCTS = frozenset({'aggregate_map2', 'aggregate_map3', 'aggregate_conservation',
                      'viewer', 'bilingual_index', 'institutional_logo',
                      'upload_instructions', 'integrity_manifest'})
PRIVATE_FIELDS = frozenset({'obsid','idobservacion','observer','observers','observador','observadores',
                           'comment','comments','comentario','comentarios','linkobservation','linkobservacion',
                           'samplingeventid','sourcefile','sourcerow','filaorigen','sourceid',
                           'originalx','originaly','xoriginal','yoriginal','xaux','yaux',
                           'sourcex','sourcey','sourceepsg','epsgoriginal','originalcoordinates',
                           'coordenadasoriginales','latitude','longitude','latitud','longitud',
                           'observations','observaciones','observationsjson'})


def _token(value):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(value)).casefold() if c.isalnum())


def polygonal_public_features(collection):
    """Keep polygon components in display-only aggregate geometry collections."""
    result = copy.deepcopy(collection)
    def polygons(geometry):
        kind = geometry.get('type')
        if kind == 'Polygon':return [geometry['coordinates']]
        if kind == 'MultiPolygon':return list(geometry['coordinates'])
        if kind == 'GeometryCollection':
            return [item for child in geometry.get('geometries', []) for item in polygons(child)]
        return []
    for feature in result.get('features', []):
        geometry = feature.get('geometry') or {}
        if geometry.get('type') == 'GeometryCollection':
            components = polygons(geometry)
            if not components:
                raise ValueError('Aggregate map features require polygonal geometry.')
            feature['geometry'] = {'type': 'MultiPolygon', 'coordinates': components}
    return result


def _validate_official_protected_layer(collection):
    """Public catalog geometry may be punctual; observation metadata never may."""
    if not isinstance(collection, dict) or set(collection) != {'type', 'features'} or collection['type'] != 'FeatureCollection':
        raise ValueError('Invalid official protected-area layer.')
    fields = {'protected_name', 'protected_type', 'protected_level', 'protected_source'}
    for feature in collection['features']:
        if not isinstance(feature, dict) or set(feature) != {'type', 'geometry', 'properties'} or feature['type'] != 'Feature':
            raise ValueError('Invalid official protected-area feature.')
        props = feature['properties']
        if not isinstance(props, dict) or set(props) != fields or not isinstance(props['protected_source'], str) or not props['protected_source'].strip():
            raise ValueError('Official protection geometry requires catalog metadata and source.')
        validate_public_data(props)
        # Only this fixed official-catalog layer may contain points. These are
        # not observation records; the source generator supplies the provenance.
        geometry = feature['geometry']
        if not isinstance(geometry, dict) or geometry.get('type') not in {
            'Point', 'MultiPoint', 'Polygon', 'MultiPolygon', 'LineString', 'MultiLineString', 'GeometryCollection'}:
            raise ValueError('Invalid official protected-area geometry.')
        if geometry.get('type') == 'GeometryCollection':
            for child in geometry.get('geometries', []):
                _validate_official_protected_layer({'type': 'FeatureCollection', 'features': [
                    {'type': 'Feature', 'properties': props, 'geometry': child}]})
        elif set(geometry) != {'type', 'coordinates'}:
            raise ValueError('Unexpected official protected-area geometry fields.')


def validate_public_data(value, *, allow_official_protection=False):
    """Reject individual data; admit only explicitly typed official context points."""
    if isinstance(value, dict):
        if value.get('type') in {'Point', 'MultiPoint'} and 'coordinates' in value:
            raise ValueError('Individual point geometry is not permitted in an aggregate product.')
        for key, item in value.items():
            if _token(key) in PRIVATE_FIELDS:
                raise ValueError(f'Individual observation field is not permitted in a public product: {key}')
            if str(key).endswith('_json') and isinstance(item, str):
                try:item = json.loads(item)
                except json.JSONDecodeError as exc:raise ValueError('Invalid structured public payload.') from exc
            if key == 'protected_json' and allow_official_protection:
                _validate_official_protected_layer(item)
            else:
                validate_public_data(item)
    elif isinstance(value, (list, tuple)):
        for item in value:validate_public_data(item)


def _validate_content(path,product):
    if product == 'institutional_logo':
        if path.suffix.lower() not in {'.png','.jpg','.jpeg'}:
            raise ValueError('Unsupported institutional logo format.')
        return
    text=path.read_text(encoding='utf-8')
    if product == 'integrity_manifest':
        value=json.loads(text)
        if set(value)-{'product','created','updated','files','security_refreshed_at'}:
            raise ValueError('Unexpected public manifest metadata.')
        validate_public_data(value)
        return
    if product == 'upload_instructions':
        return
    if path.suffix.lower() != '.html':
        raise ValueError('Public interactive products must be HTML.')
    # Independently inspect JSON literals embedded by the known templates.
    decoder=json.JSONDecoder()
    for match in re.finditer(r'\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?=[\[{])',text):
        try:value,_=decoder.raw_decode(text[match.end():])
        except json.JSONDecodeError:continue  # Static JavaScript expressions are not JSON datasets.
        if product == 'aggregate_conservation' and match.group(1) == 'protectedAreas':
            _validate_official_protected_layer(value)
        else:
            validate_public_data(value)
    # Check quoted individual-field literals, including attributes in nested datasets.
    for match in re.finditer(r'["\']([A-Za-z_][A-Za-z_0-9 ]*)["\']\s*:',text):
        if _token(match.group(1)) in PRIVATE_FIELDS:
            raise ValueError('Individual observation field found in public HTML.')


def _load_registry(folder):
    path=Path(folder)/REGISTRY_NAME
    if not path.is_file() or path.is_symlink():return None
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
        if set(value)!={'schema_version','files'} or value['schema_version']!=1 or not isinstance(value['files'],dict):return None
        for name,record in value['files'].items():
            if not isinstance(name,str) or Path(name).name!=name or '\\' in name or name in {'.','..',REGISTRY_NAME}:return None
            if not isinstance(record,dict) or set(record)!={'product','sha256'} or record['product'] not in PRODUCTS:return None
            if not isinstance(record['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',record['sha256']):return None
        return value
    except (OSError,UnicodeError,ValueError,TypeError):return None


def public_product(path):
    path=Path(path)
    if not path.is_file() or path.is_symlink():return None
    if path.name==REGISTRY_NAME:
        return 'classification_registry' if _load_registry(path.parent) is not None else None
    registry=_load_registry(path.parent)
    record=registry['files'].get(path.name) if registry else None
    if record is None:return None
    try:
        if hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:return None
        _validate_content(path,record['product'])
        return record['product']
    except (OSError,UnicodeError,ValueError,TypeError):return None


def is_public_output(path):
    return public_product(path) is not None


def register_public_output(path,product,payload=None):
    """Called only by trusted generators after writing the complete product."""
    path=Path(path)
    if product not in PRODUCTS or path.is_symlink() or not path.is_file():
        raise ValueError('Invalid public-product registration.')
    if payload is not None:validate_public_data(payload, allow_official_protection=product == 'aggregate_conservation')
    _validate_content(path,product)
    registry=_load_registry(path.parent)
    registry_path=path.parent/REGISTRY_NAME
    if registry is None:
        if registry_path.exists():raise ValueError('Invalid output classification registry.')
        registry={'schema_version':1,'files':{}}
    registry['files'][path.name]={'product':product,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix=REGISTRY_NAME,suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump(registry,stream,ensure_ascii=False,sort_keys=True)
            stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,registry_path)
    finally:Path(tmp).unlink(missing_ok=True)


def copy_public_registration(source,destination):
    product=public_product(source)
    if product and product!='classification_registry':register_public_output(destination,product)
