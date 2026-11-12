from __future__ import annotations

import argparse
import getpass
import os
import subprocess
import sys
from pathlib import Path

from hispa_security import (
    AccessContext,
    _exclusive_project_operation,
    SecurityError,
    change_password,
    choose_folder,
    choose_open_file,
    choose_save_file,
    cleanup_decrypted_temp,
    create_open_copy,
    create_protected_copy,
    create_security_config,
    decrypt_all_project_files,
    decrypt_to_temp_and_open,
    encrypt_project_input,
    export_access_environment,
    forget_remembered_access,
    load_remembered_access,
    load_security_config,
    open_environment,
    project_is_protected,
    protect_all_existing_outputs,
    read_credential,
    remember_access,
    rotate_project_key,
    security_config_path,
    unwrap_owner_token,
    unwrap_project_key,
    upgrade_owner_authority,
    write_credential,
)


def msg(lang: str, es: str, en: str) -> str:
    return es if lang == "ES" else en


def yn(lang: str, prompt_es: str, prompt_en: str, default: bool = False) -> bool:
    suffix = " [S/n]: " if default else " [s/N]: "
    suffix_en = " [Y/n]: " if default else " [y/N]: "
    value = input(msg(lang, prompt_es + suffix, prompt_en + suffix_en)).strip().casefold()
    if not value:
        return default
    return value in ({"s", "si", "sí", "y", "yes"})


def _path_prompt(lang: str, es: str, en: str) -> Path | None:
    value = input(msg(lang, es, en)).strip().strip('"')
    return Path(value).expanduser().resolve() if value else None


def _save_credential_path(project_root: Path, lang: str, kind: str) -> Path | None:
    cfg = load_security_config(project_root)
    short = (cfg["project_id"][:8] if cfg else "nuevo")
    default = f"Hispa-Syng_{kind}_{short}.hsk"
    title = msg(lang, "Guardar credencial Hispa-Syng fuera de la carpeta del proyecto", "Save the Hispa-Syng credential outside the project folder")
    selected = choose_save_file(title, "Hispa-Syng credential (*.hsk)|*.hsk|All files (*.*)|*.*", default)
    if selected is None:
        selected = _path_prompt(lang, "Ruta completa para guardar la credencial (.hsk), o Enter para cancelar: ", "Full path to save the credential (.hsk), or Enter to cancel: ")
    if selected is None:
        return None
    if selected.suffix.lower() != ".hsk":
        selected = selected.with_suffix(".hsk")
    try:
        selected.relative_to(project_root.resolve())
        print(msg(lang, "Por seguridad, la credencial de recuperación no debe guardarse dentro del proyecto.", "For safety, the recovery credential must not be stored inside the project."))
        return None
    except ValueError:
        return selected


def _choose_credential(lang: str) -> Path | None:
    selected = choose_open_file(
        msg(lang, "Seleccione una credencial Hispa-Syng", "Select a Hispa-Syng credential"),
        "Hispa-Syng credential (*.hsk)|*.hsk|All files (*.*)|*.*",
    )
    if selected is None:
        selected = _path_prompt(lang, "Ruta de la credencial .hsk, o Enter para cancelar: ", "Path to the .hsk credential, or Enter to cancel: ")
    return selected


def _password_twice(lang: str) -> str | None:
    first = getpass.getpass(msg(lang, "Nueva contraseña (mínimo 12 caracteres): ", "New password (minimum 12 characters): "))
    if not first:
        return None
    second = getpass.getpass(msg(lang, "Repita la contraseña: ", "Repeat the password: "))
    if first != second:
        print(msg(lang, "Las contraseñas no coinciden.", "Passwords do not match."))
        return None
    if len(first) < 12:
        print(msg(lang, "La contraseña es demasiado corta.", "The password is too short."))
        return None
    return first


def _authenticate(project_root: Path, lang: str, *, require_owner: bool = False, allow_cancel: bool = True) -> AccessContext | None:
    cfg = load_security_config(project_root)
    if not cfg or cfg.get("mode") != "protected":
        return None
    remembered = load_remembered_access(cfg)
    if remembered and (not require_owner or remembered.role in {"owner", "owner_recovery"}):
        print(msg(lang, "Acceso local recordado por Windows: válido.", "Windows remembered access: valid."))
        return remembered
    print(msg(lang,
        "Esta operación necesita autorización del propietario: use su contraseña o su archivo de recuperación." if require_owner else "Para abrir los datos, use la contraseña del propietario o el archivo de acceso .hsk que le hayan entregado.",
        "This operation needs owner authorization: use the owner password or recovery file." if require_owner else "To open the data, use the owner password or the .hsk access file you received."))
    while True:
        print()
        print(msg(lang, "PROYECTO PROTEGIDO", "PROTECTED PROJECT"))
        print(msg(lang, "1. Introducir contraseña del propietario", "1. Enter owner password"))
        print(msg(lang, "2. Importar credencial .hsk", "2. Import .hsk credential"))
        if allow_cancel:
            print(msg(lang, "0. Cancelar", "0. Cancel"))
        choice = input("> ").strip()
        try:
            if choice == "1":
                password = getpass.getpass(msg(lang, "Contraseña: ", "Password: "))
                key = unwrap_project_key(cfg, password)
                if int(cfg.get("schema_version", 1)) < 2 or not cfg.get("owner_token_hash"):
                    cfg, owner_token = upgrade_owner_authority(project_root, cfg, key, password)
                    print(msg(lang, "Guarde una recuperación del propietario desde Seguridad y accesos > Gestionar contraseña y accesos > Guardar o renovar la recuperación del propietario.", "Save an owner recovery file through Security and access > Manage password and access > Save or renew owner recovery."))
                else:
                    owner_token = unwrap_owner_token(cfg, password)
                ctx = AccessContext(cfg["project_id"], key, "owner", remembered=False, owner_token=owner_token)
            elif choice == "2":
                path = _choose_credential(lang)
                if path is None:
                    continue
                ctx = read_credential(path, cfg)
            elif choice == "0" and allow_cancel:
                return None
            else:
                print(msg(lang, "Opción no válida.", "Invalid option."))
                continue
            if require_owner and ctx.role not in {"owner", "owner_recovery"}:
                print(msg(lang, "Esta operación requiere acceso del propietario o de recuperación.", "This operation requires owner or recovery access."))
                continue
            if os.name == "nt" and yn(lang, "¿Recordar este acceso en este usuario de Windows?", "Remember this access for this Windows user?", default=True):
                remember_access(ctx)
                print(msg(lang, "Acceso guardado mediante Windows DPAPI.", "Access saved using Windows DPAPI."))
            return ctx
        except SecurityError as exc:
            print(msg(lang, f"ERROR: {exc}", f"ERROR: {exc}"))


def _status(project_root: Path, lang: str) -> None:
    cfg = load_security_config(project_root)
    print()
    print(msg(lang, "ESTADO DE SEGURIDAD", "SECURITY STATUS"))
    if not cfg:
        print(msg(lang, "Modo del proyecto: ABIERTO (sin seguridad configurada)", "Project mode: OPEN (security not configured)"))
        print(msg(lang, "Las nuevas ejecuciones se generan sin cifrado del proyecto.", "New runs are generated without project encryption."))
        return
    remembered = load_remembered_access(cfg)
    print(msg(lang, "Modo del proyecto: PROTEGIDO", "Project mode: PROTECTED"))
    print(msg(lang, f"ID del proyecto: {cfg['project_id']}", f"Project ID: {cfg['project_id']}"))
    print(msg(lang, f"Entrada cifrada: {cfg.get('encrypted_input','Datos_data/Ingesta_provisional.hse')}", f"Encrypted input: {cfg.get('encrypted_input','Datos_data/Ingesta_provisional.hse')}"))
    print(msg(lang, f"Acceso recordado en este usuario de Windows: {'Sí' if remembered else 'No'}", f"Remembered access for this Windows user: {'Yes' if remembered else 'No'}"))
    if remembered:
        print(msg(lang, f"Rol local recordado: {remembered.role}", f"Remembered local role: {remembered.role}"))


@_exclusive_project_operation
def _enable(project_root: Path, lang: str) -> None:
    if project_is_protected(project_root):
        print(msg(lang, "El proyecto ya está protegido.", "The project is already protected."))
        return
    print()
    print(msg(lang, "ACTIVAR PROTECCIÓN DEL PROYECTO", "ENABLE PROJECT PROTECTION"))
    print(msg(lang,
        "Se cifrará Datos_data/Ingesta_provisional.xlsx y se eliminará la copia en claro tras verificar el cifrado. La contraseña no se guardará.",
        "Datos_data/Ingesta_provisional.xlsx will be encrypted and the plaintext copy removed after verification. The password will not be stored."))
    if not yn(lang, "¿Continuar?", "Continue?", default=False):
        return
    password = _password_twice(lang)
    if not password:
        return
    recovery_path = _save_credential_path(project_root, lang, "recovery")
    if recovery_path is None:
        print(msg(lang, "Operación cancelada: es obligatorio guardar una credencial de recuperación fuera del proyecto.", "Cancelled: a recovery credential outside the project is required."))
        return
    cfg = None
    key = None
    try:
        cfg, key = create_security_config(project_root, password)
        owner_token = unwrap_owner_token(cfg, password)
        encrypted = encrypt_project_input(project_root, cfg, key)
        if encrypted is None:
            raise SecurityError("No se encontró Ingesta_provisional.xlsx para cifrar.")
        ctx = AccessContext(cfg["project_id"], key, "owner", remembered=False, owner_token=owner_token)
        protected_existing = protect_all_existing_outputs(project_root, ctx)
        rec = write_credential(recovery_path, cfg, key, role="owner_recovery", label="Recuperación del propietario", owner_token=owner_token)
        if os.name == "nt" and yn(lang, "¿Recordar el acceso en este usuario de Windows?", "Remember access for this Windows user?", default=True):
            remember_access(ctx)
        print(msg(lang, f"Proyecto protegido. Credencial de recuperación: {rec}", f"Project protected. Recovery credential: {rec}"))
        if protected_existing.get("files", 0):
            print(msg(lang, f"Resultados sensibles existentes cifrados: {protected_existing['files']}", f"Existing sensitive output files encrypted: {protected_existing['files']}"))
    except Exception:
        # Transactional best effort: if activation fails, restore every .hse
        # already produced and remove the incomplete security configuration.
        if cfg is not None and key is not None:
            try:
                decrypt_all_project_files(project_root, cfg, key, remove_encrypted=True)
                import shutil
                shutil.rmtree(security_config_path(project_root).parent, ignore_errors=True)
                forget_remembered_access(cfg["project_id"])
            except Exception:
                pass
        raise


def _change_password(project_root: Path, lang: str) -> None:
    ctx = _authenticate(project_root, lang, require_owner=True)
    if not ctx:
        return
    password = _password_twice(lang)
    if not password:
        return
    change_password(project_root, ctx.project_key, password, owner_token=ctx.owner_token)
    print(msg(lang, "Contraseña cambiada. Las credenciales .hsk existentes siguen siendo válidas.", "Password changed. Existing .hsk credentials remain valid."))


def _credential(project_root: Path, lang: str) -> None:
    ctx = _authenticate(project_root, lang, require_owner=True)
    if not ctx:
        return
    cfg = load_security_config(project_root)
    path = _save_credential_path(project_root, lang, "access")
    if path is None:
        return
    label = input(msg(lang, "Etiqueta para la persona usuaria (opcional): ", "User label (optional): ")).strip() or "Acceso autorizado"
    out = write_credential(path, cfg, ctx.project_key, role="access", label=label)
    print(msg(lang, f"Credencial creada: {out}", f"Credential created: {out}"))
    print(msg(lang, "Quien posea este archivo podrá acceder al contenido protegido de este proyecto. Envíelo por un canal adecuado.", "Anyone holding this file can access this project's protected content. Send it through an appropriate channel."))


def _recovery_credential(project_root: Path, lang: str) -> None:
    ctx = _authenticate(project_root, lang, require_owner=True)
    if not ctx:
        return
    cfg = load_security_config(project_root)
    if not ctx.owner_token:
        raise SecurityError("No existe autoridad reforzada del propietario; autentíquese con la contraseña para actualizarla.")
    path = _save_credential_path(project_root, lang, "recovery")
    if path is None:
        return
    out = write_credential(
        path, cfg, ctx.project_key, role="owner_recovery",
        label="Recuperación del propietario", owner_token=ctx.owner_token
    )
    print(msg(lang, f"Nueva credencial de recuperación creada: {out}", f"New recovery credential created: {out}"))
    print(msg(lang, "Guárdela fuera del proyecto. Las recuperaciones anteriores siguen siendo válidas hasta rotar la clave.", "Store it outside the project. Earlier recovery credentials remain valid until key rotation."))


def _import_and_remember(project_root: Path, lang: str) -> None:
    cfg = load_security_config(project_root)
    if not cfg:
        print(msg(lang, "Este proyecto no está protegido.", "This project is not protected."))
        return
    path = _choose_credential(lang)
    if path is None:
        return
    ctx = read_credential(path, cfg)
    print(msg(lang, f"Credencial válida. Rol: {ctx.role}", f"Valid credential. Role: {ctx.role}"))
    if os.name == "nt" and yn(lang, "¿Recordar este acceso en este usuario de Windows?", "Remember this access for this Windows user?", default=True):
        remember_access(ctx)
        print(msg(lang, "Acceso local recordado mediante Windows DPAPI.", "Local access remembered using Windows DPAPI."))


def _open_protected(project_root: Path, lang: str) -> None:
    ctx = _authenticate(project_root, lang)
    if not ctx:
        return
    cfg = load_security_config(project_root)
    path = choose_open_file(msg(lang, "Seleccione un archivo cifrado Hispa-Syng", "Select an encrypted Hispa-Syng file"), "Hispa-Syng encrypted (*.hse)|*.hse|All files (*.*)|*.*")
    if path is None:
        path = _path_prompt(lang, "Ruta del archivo .hse: ", "Path to the .hse file: ")
    if path is None:
        return
    out = decrypt_to_temp_and_open(path, cfg, ctx)
    print(msg(lang, f"Copia temporal descifrada: {out}", f"Temporary decrypted copy: {out}"))
    print(msg(lang, "Se eliminará desde el menú de seguridad con 'Limpiar copias temporales'.", "It can be removed from the security menu with 'Clean temporary copies'."))


def _create_open_copy(project_root: Path, lang: str) -> None:
    print()
    print(msg(lang, "COPIA ABIERTA PARA COMPARTIR", "OPEN COPY FOR SHARING"))
    print(msg(lang,
        "Se creará OTRA carpeta con el programa y los datos de entrada sin contraseña. El destinatario podrá leer todos los datos incluidos. No se copian resultados anteriores. Este proyecto conserva su estado.",
        "A DIFFERENT folder will contain the program and input data without a password. The recipient can read all included data. Previous results are not copied. This project keeps its current state."))
    if not yn(lang, "¿Crear esta copia abierta?", "Create this open copy?", default=False):
        return
    cfg = load_security_config(project_root)
    ctx = _authenticate(project_root, lang, require_owner=True) if cfg else None
    if cfg and not ctx:
        return
    parent = choose_folder(msg(lang, "Seleccione la carpeta donde crear la copia abierta", "Select the folder where the open copy will be created"))
    if parent is None:
        parent = _path_prompt(lang, "Carpeta de destino, o Enter para cancelar: ", "Destination folder, or Enter to cancel: ")
    if parent is None:
        return
    destination = parent / (project_root.name + "_ABIERTO")
    out = create_open_copy(project_root, destination, ctx)
    print(msg(lang, f"Copia completamente abierta creada: {out}", f"Fully open copy created: {out}"))
    print(msg(lang, "El destinatario debe ejecutar Hispa-Syng.bat desde la nueva carpeta para generar sus resultados.", "The recipient runs Hispa-Syng.bat from the new folder to generate their results."))


def _create_protected_copy(project_root: Path, lang: str) -> None:
    print()
    print(msg(lang, "COPIA PROTEGIDA PARA COMPARTIR", "PROTECTED COPY FOR SHARING"))
    print(msg(lang,
        "Se creará OTRA carpeta independiente con el programa y los datos cifrados. Tendrá su propia contraseña y recuperación. No se copian resultados anteriores. Este proyecto conserva su estado.",
        "A DIFFERENT independent folder will contain the program and encrypted data. It will have its own password and recovery file. Previous results are not copied. This project keeps its current state."))
    if not yn(lang, "¿Crear esta copia protegida?", "Create this protected copy?", default=False):
        return
    source_cfg = load_security_config(project_root)
    source_ctx = _authenticate(project_root, lang, require_owner=True) if source_cfg else None
    if source_cfg and not source_ctx:
        return
    parent = choose_folder(msg(lang, "Seleccione la carpeta donde crear la copia protegida", "Select the folder where the protected copy will be created"))
    if parent is None:
        parent = _path_prompt(lang, "Carpeta de destino, o Enter para cancelar: ", "Destination folder, or Enter to cancel: ")
    if parent is None:
        return
    password = _password_twice(lang)
    if not password:
        return
    # The new copy does not yet have an ID, so use a neutral default filename.
    rec = choose_save_file(msg(lang, "Guardar la recuperación de la nueva copia fuera de ella", "Save the new copy recovery credential outside it"), "Hispa-Syng credential (*.hsk)|*.hsk|All files (*.*)|*.*", "Hispa-Syng_recovery_new_copy.hsk")
    if rec is None:
        rec = _path_prompt(lang, "Ruta para la credencial de recuperación, o Enter para cancelar: ", "Path for the recovery credential, or Enter to cancel: ")
    if rec is None:
        return
    if rec.suffix.lower() != ".hsk":
        rec = rec.with_suffix(".hsk")
    destination = parent / (project_root.name + "_PROTEGIDO")
    out, recout = create_protected_copy(project_root, destination, password, rec, source_ctx)
    print(msg(lang, f"Copia protegida creada: {out}\nRecuperación: {recout}", f"Protected copy created: {out}\nRecovery: {recout}"))
    print(msg(lang,
        "Para dar acceso sin administración, abra el BAT de ESTA NUEVA COPIA y entre en Seguridad y accesos > Preparar una copia para compartir > Crear un archivo de acceso para este proyecto. Conserve usted la contraseña y la recuperación de la copia.",
        "To grant access without administration, open the BAT in THIS NEW COPY and choose Security and access > Prepare a copy to share > Create an access file for this project. Keep the copy's password and recovery file yourself."))


def _protect_existing(project_root: Path, lang: str) -> None:
    ctx = _authenticate(project_root, lang, require_owner=False)
    if not ctx:
        return
    result = protect_all_existing_outputs(project_root, ctx)
    print(msg(lang, f"Revisión completada. Archivos sensibles cifrados ahora: {result.get('files', 0)}", f"Review completed. Sensitive files encrypted now: {result.get('files', 0)}"))
    print(msg(lang, "La recuperación pendiente se comprueba antes de iniciar un análisis protegido o crear una copia autorizada.", "Pending recovery is checked before starting a protected analysis or creating an authorized copy."))


def _rotate(project_root: Path, lang: str) -> None:
    ctx = _authenticate(project_root, lang, require_owner=True)
    if not ctx:
        return
    print(msg(lang,
        "Esta operación genera una nueva clave del proyecto, vuelve a cifrar todos los .hse; las credenciales anteriores no abren los archivos recifrados. Las copias antiguas conservan acceso con sus credenciales antiguas.",
        "This creates a new project key, re-encrypts every .hse file; previous credentials cannot open the re-encrypted files. Old copies remain readable with their old credentials."))
    if not yn(lang, "¿Rotar la clave del proyecto y crear una nueva recuperación?", "Rotate the project key and create a new recovery credential?", default=False):
        return
    password = _password_twice(lang)
    if not password:
        return
    rec = _save_credential_path(project_root, lang, "recovery_rotated")
    if rec is None:
        return
    newctx = rotate_project_key(project_root, ctx, password, rec)
    if os.name == "nt" and yn(lang, "¿Recordar la nueva clave en Windows?", "Remember the new key in Windows?", default=True):
        remember_access(newctx)
    print(msg(lang, "Clave rotada. Las credenciales anteriores no abren los archivos recifrados; las copias antiguas siguen siendo accesibles con sus claves anteriores.", "Key rotated. Previous credentials cannot open re-encrypted files; old copies remain accessible with their old keys."))


def _sharing_menu(project_root: Path, lang: str) -> None:
    while True:
        cfg = load_security_config(project_root)
        print()
        print(msg(lang, "PREPARAR UNA COPIA PARA COMPARTIR", "PREPARE A COPY TO SHARE"))
        print(msg(lang, "Las copias se crean en otra carpeta, fuera del proyecto actual. El original conserva su estado.", "Copies are created in a different folder outside the current project. The original keeps its current state."))
        print(msg(lang, "1. Crear copia protegida (datos cifrados, contraseña propia)", "1. Create protected copy (encrypted data, its own password)"))
        print(msg(lang, "2. Crear copia abierta (datos legibles, sin contraseña)", "2. Create open copy (readable data, no password)"))
        if cfg:
            print(msg(lang, "3. Crear un archivo de acceso para este proyecto (.hsk)", "3. Create an access file for this project (.hsk)"))
            print(msg(lang, "   La opción 3 crea una llave de acceso; no crea otra carpeta ni otro proyecto.", "   Option 3 creates an access key; it does not create another folder or project."))
        print(msg(lang, "0. Volver a Seguridad y accesos", "0. Back to Security and access"))
        choice = input("> ").strip()
        try:
            if choice == "0":
                return
            if choice == "1":
                _create_protected_copy(project_root, lang)
            elif choice == "2":
                _create_open_copy(project_root, lang)
            elif cfg and choice == "3":
                print(msg(lang,
                    "Este archivo permite leer los datos de ESTE proyecto, pero no administrarlo. Quien lo posea podrá usarlo. No sirve para una copia independiente con otra clave.",
                    "This file allows reading THIS project's data without administration. Anyone holding it can use it. It does not work with an independent copy using a different key."))
                _credential(project_root, lang)
            else:
                print(msg(lang, "Opción no válida.", "Invalid option."))
        except (SecurityError, OSError) as exc:
            print(msg(lang, f"ERROR: {exc}", f"ERROR: {exc}"))


def _access_management_menu(project_root: Path, lang: str) -> None:
    while True:
        cfg = load_security_config(project_root)
        if not cfg:
            return
        print()
        print(msg(lang, "GESTIONAR CONTRASEÑA Y ACCESOS", "MANAGE PASSWORD AND ACCESS"))
        print(msg(lang, "Para el uso habitual, vuelva al menú principal y ejecute el análisis.", "For everyday use, return to the main menu and run the analysis."))
        print(msg(lang, "1. Cambiar contraseña (las credenciales existentes siguen válidas)", "1. Change password (existing credentials remain valid)"))
        print(msg(lang, "2. Recordar acceso con una credencial .hsk en este usuario de Windows", "2. Remember access with an .hsk credential for this Windows user"))
        print(msg(lang, "3. Guardar o renovar la recuperación del propietario", "3. Save or renew owner recovery"))
        print(msg(lang, "4. Retirar accesos anteriores al proyecto actual (rotar clave)", "4. Withdraw previous access to the current project (rotate key)"))
        print(msg(lang, "5. Revisar y proteger resultados existentes", "5. Review and protect existing outputs"))
        print(msg(lang, "6. Olvidar acceso recordado en este usuario de Windows", "6. Forget remembered access for this Windows user"))
        print(msg(lang, "7. Limpiar copias temporales descifradas", "7. Clean temporary decrypted copies"))
        print(msg(lang, "0. Volver a Seguridad y accesos", "0. Back to Security and access"))
        choice = input("> ").strip()
        try:
            if choice == "0":
                return
            if choice == "1":
                print(msg(lang, "Cambia la contraseña del propietario; no retira el acceso de las credenciales .hsk ya emitidas.", "Changes the owner password; it does not withdraw access from issued .hsk credentials."))
                _change_password(project_root, lang)
            elif choice == "2":
                print(msg(lang, "Recuerda el acceso y el rol de su credencial para su usuario de Windows. El proyecto sigue cifrado.", "Remembers your credential's access and role for your Windows user. The project remains encrypted."))
                _import_and_remember(project_root, lang)
            elif choice == "3":
                print(msg(lang, "La recuperación permite administrar el proyecto aunque olvide la contraseña. Guárdela fuera del proyecto; no la entregue como acceso ordinario.", "Recovery allows project administration if you forget the password. Store it outside the project; do not share it as ordinary access."))
                _recovery_credential(project_root, lang)
            elif choice == "4":
                _rotate(project_root, lang)
            elif choice == "5":
                _protect_existing(project_root, lang)
            elif choice == "6":
                removed = forget_remembered_access(cfg["project_id"])
                print(msg(lang, "Acceso local olvidado." if removed else "No había acceso local recordado.", "Local access forgotten." if removed else "No remembered local access was present."))
                print(msg(lang, "Las credenciales .hsk y los accesos de otros usuarios siguen siendo válidos.", ".hsk credentials and other users' access remain valid."))
            elif choice == "7":
                cleanup_decrypted_temp(cfg)
                print(msg(lang, "Copias temporales eliminadas. Las copias que haya guardado fuera de ese destino no se eliminan.", "Temporary copies removed. Copies you saved outside that destination are not removed."))
            else:
                print(msg(lang, "Opción no válida.", "Invalid option."))
        except (SecurityError, OSError) as exc:
            print(msg(lang, f"ERROR: {exc}", f"ERROR: {exc}"))


def _security_menu(project_root: Path, lang: str) -> None:
    while True:
        cfg = load_security_config(project_root)
        print()
        print(msg(lang, "SEGURIDAD Y ACCESOS", "SECURITY AND ACCESS"))
        print(msg(lang, f"Carpeta actual: {project_root}", f"Current folder: {project_root}"))
        print(msg(lang, "1. Consultar el estado de este proyecto", "1. Check this project's status"))
        if cfg:
            print(msg(lang, "Este proyecto está PROTEGIDO. Puede seguir trabajando desde esta misma carpeta.", "This project is PROTECTED. You can keep working from this same folder."))
            print(msg(lang, "2. Abrir archivo protegido .hse (consultar un resultado)", "2. Open protected .hse file (view a result)"))
            print(msg(lang, "3. Preparar una copia para compartir", "3. Prepare a copy to share"))
            print(msg(lang, "4. Gestionar contraseña y accesos", "4. Manage password and access"))
        else:
            print(msg(lang, "Este proyecto está ABIERTO. Puede analizar los datos sin configurar protección.", "This project is OPEN. You can analyse data without setting up protection."))
            print(msg(lang, "2. Proteger mi proyecto actual (esta misma carpeta)", "2. Protect my current project (this same folder)"))
            print(msg(lang, "3. Preparar una copia para compartir (otra carpeta)", "3. Prepare a copy to share (another folder)"))
        print(msg(lang, "0. Volver al menú principal", "0. Back to the main menu"))
        choice = input("> ").strip()
        try:
            if choice == "0":
                return
            if choice == "1":
                _status(project_root, lang)
            elif not cfg and choice == "2":
                print(msg(lang,
                    "Se protegerán los datos de ESTA carpeta. No se crea otra instalación. Necesitará una contraseña y guardar la recuperación fuera del proyecto.",
                    "The data in THIS folder will be protected. No other installation is created. You will need a password and must save recovery outside the project."))
                _enable(project_root, lang)
            elif cfg and choice == "2":
                print(msg(lang, "El archivo se abrirá mediante una copia temporal privada. Al terminar puede limpiarla desde Gestionar contraseña y accesos.", "The file opens through a private temporary copy. Afterwards you can clean it through Manage password and access."))
                _open_protected(project_root, lang)
            elif choice == "3":
                _sharing_menu(project_root, lang)
            elif cfg and choice == "4":
                _access_management_menu(project_root, lang)
            else:
                print(msg(lang, "Opción no válida.", "Invalid option."))
        except (SecurityError, OSError) as exc:
            print(msg(lang, f"ERROR: {exc}", f"ERROR: {exc}"))


def _run_analysis(project_root: Path, lang: str, extra_args: list[str]) -> int:
    cfg = load_security_config(project_root)
    if cfg:
        ctx = _authenticate(project_root, lang, allow_cancel=True)
        if not ctx:
            return 0
        env = export_access_environment(ctx)
    else:
        env = open_environment()
    coordinator = project_root / "herramientas" / "ejecutar_bilingue.py"
    cmd = [sys.executable, str(coordinator), "--ui-language", lang, "--project-root", str(project_root)] + extra_args
    return subprocess.run(cmd, cwd=str(project_root), env=env, check=False).returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hispa-Syng project security and access coordinator")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--ui-language", default="ES")
    parser.add_argument("analysis_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    project_root = Path(args.project_root).expanduser().resolve()
    lang = "EN" if str(args.ui_language).upper().startswith("EN") else "ES"
    while True:
        print()
        print("============================================================")
        print("              HISPA-SYNG v1.0")
        print("============================================================")
        cfg = load_security_config(project_root)
        status = msg(lang, "PROTEGIDO" if cfg else "ABIERTO", "PROTECTED" if cfg else "OPEN")
        print(msg(lang, f"Proyecto: {status}", f"Project: {status}"))
        pending = project_root / ".hispa_security" / "pending"
        if cfg and pending.is_dir() and any(pending.glob("*.json")):
            print(msg(lang,
                "Hay ejecuciones pendientes: se recuperarán tras autorizar un análisis o una copia. Si la recuperación falla, la operación se bloqueará.",
                "Pending runs require recovery after authorizing an analysis or copy. Recovery failure blocks the operation."))
        print()
        print(msg(lang, "1. Ejecutar Hispa-Syng", "1. Run Hispa-Syng"))
        print(msg(lang, "2. Seguridad y accesos", "2. Security and access"))
        print(msg(lang, "0. Salir", "0. Exit"))
        choice = input("> ").strip()
        try:
            if choice == "1":
                return _run_analysis(project_root, lang, args.analysis_args)
            if choice == "2":
                _security_menu(project_root, lang)
                continue
            if choice == "0":
                return 0
            print(msg(lang, "Opción no válida.", "Invalid option."))
        except KeyboardInterrupt:
            print()
            return 130
        except (SecurityError, OSError) as exc:
            print(msg(lang, f"ERROR: {exc}", f"ERROR: {exc}"))


if __name__ == "__main__":
    raise SystemExit(main())
