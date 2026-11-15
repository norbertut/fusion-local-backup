# -*- coding: utf-8 -*-
"""
Fusion Local Backup - Copia local de disenos de Autodesk Fusion.

Fase 1:
  * Formatos: archivo de Fusion (F3D, o F3Z si el diseno tiene referencias
    externas) y STEP.
  * Alcance: un grupo de ficheros, un proyecto entero o todos los proyectos
    del hub activo.
  * Reproduce en disco la estructura Hub / Proyecto / Carpetas.

Se ejecuta desde Fusion: UTILIDADES > Complementos > Scripts.
"""

import csv
import datetime
import os
import re
import time
import traceback

import adsk.core
import adsk.fusion

CMD_ID = 'fusionLocalBackupCmd'
CMD_NAME = 'Fusion Local Backup'
CMD_TOOLTIP = 'Exporta disenos a F3D/F3Z y STEP por ficheros, proyecto o hub.'

SCOPE_FILES = 'Ficheros seleccionados'
SCOPE_PROJECT = 'Un proyecto'
SCOPE_ALL = 'Todo (todos los proyectos del hub)'

ID_SCOPE = 'scope'
ID_PROJECT = 'project'
ID_FILES = 'files'
ID_F3D = 'fmtF3d'
ID_STEP = 'fmtStep'
ID_FOLDER = 'outFolder'
ID_BROWSE = 'browse'
ID_SKIP = 'skipExisting'
ID_INFO = 'info'

# Segundos maximos de espera a que Fusion termine de escribir un F3Z.
F3Z_TIMEOUT = 300

app = None
ui = None
handlers = []

# Estado compartido entre los manejadores del dialogo.
state = {
    'projects': [],      # DataProject, en el mismo orden que el desplegable
    'files': [],         # (DataFile, [carpetas]) en el orden de la lista
    'files_project': -1  # indice del proyecto cuyos ficheros estan cargados
}


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------

def sanitize(name):
    """Convierte un nombre de Fusion en un nombre valido de fichero/carpeta."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name or '')
    name = name.strip().rstrip('.')
    return name or '_'


def items(collection):
    """Itera una coleccion de la API de Fusion de forma segura."""
    for i in range(collection.count):
        item = collection.item(i)
        if item:
            yield item


def walk_folder(folder, parts):
    """Recorre una carpeta de datos y devuelve (DataFile, [carpetas])."""
    for data_file in items(folder.dataFiles):
        yield data_file, parts
    for sub in items(folder.dataFolders):
        for result in walk_folder(sub, parts + [sanitize(sub.name)]):
            yield result


def extension_of(data_file):
    try:
        return (data_file.fileExtension or '').lstrip('.').lower()
    except Exception:
        return ''


def has_external_references(doc, data_file):
    """True si el diseno enlaza otros disenos (necesita F3Z en vez de F3D)."""
    try:
        if doc.documentReferences.count > 0:
            return True
    except Exception:
        pass
    try:
        return bool(data_file.hasChildReferences)
    except Exception:
        return False


def unique_base(folder, base, used):
    """Evita que dos disenos con el mismo nombre se pisen en la misma carpeta."""
    candidate = base
    n = 2
    while os.path.join(folder, candidate).lower() in used:
        candidate = '{} ({})'.format(base, n)
        n += 1
    used.add(os.path.join(folder, candidate).lower())
    return candidate


# --------------------------------------------------------------------------
# Exportadores
# --------------------------------------------------------------------------

def export_f3d(design, path):
    mgr = design.exportManager
    options = mgr.createFusionArchiveExportOptions(path)
    if not mgr.execute(options):
        raise RuntimeError('Fusion no pudo crear el F3D')


def export_step(design, path):
    mgr = design.exportManager
    options = mgr.createSTEPExportOptions(path)
    if not mgr.execute(options):
        raise RuntimeError('Fusion no pudo crear el STEP')


def export_f3z(folder, base):
    """
    Exporta el documento activo como F3Z.

    La API publica no ofrece F3Z, asi que se usa el comando de texto
    'data.fileExport' (no documentado). Fusion elige el nombre del fichero,
    por lo que se detecta el F3Z nuevo o modificado y se renombra.
    """
    def snapshot():
        found = {}
        for name in os.listdir(folder):
            if name.lower().endswith('.f3z'):
                full = os.path.join(folder, name)
                try:
                    found[name] = (os.path.getmtime(full), os.path.getsize(full))
                except OSError:
                    pass
        return found

    before = snapshot()
    app.executeTextCommand('data.fileExport f3z "{}"'.format(folder))

    deadline = time.time() + F3Z_TIMEOUT
    produced = None
    last_size = -1
    while time.time() < deadline:
        adsk.doEvents()
        time.sleep(0.5)
        now = snapshot()
        changed = [n for n, info in now.items() if before.get(n) != info or n not in before]
        if not changed and produced is None:
            continue
        if changed:
            produced = changed[0]
        size = now.get(produced, (0, 0))[1]
        # Se da por terminado cuando el tamano deja de crecer.
        if size > 0 and size == last_size:
            break
        last_size = size
    else:
        produced = None if last_size <= 0 else produced

    if not produced:
        raise RuntimeError('No se genero el F3Z (comando data.fileExport sin resultado)')

    target = os.path.join(folder, base + '.f3z')
    source = os.path.join(folder, produced)
    if os.path.normcase(source) != os.path.normcase(target):
        os.replace(source, target)
    return target


# --------------------------------------------------------------------------
# Proceso principal
# --------------------------------------------------------------------------

def collect_targets(scope, project_index, selected_file_indexes):
    """Devuelve una lista de (DataFile, [hub, proyecto, carpetas...])."""
    hub_name = sanitize(app.data.activeHub.name)
    targets = []

    if scope == SCOPE_FILES:
        project = state['projects'][project_index]
        prefix = [hub_name, sanitize(project.name)]
        for i in selected_file_indexes:
            data_file, parts = state['files'][i]
            targets.append((data_file, prefix + parts))
        return targets

    if scope == SCOPE_PROJECT:
        projects = [state['projects'][project_index]]
    else:
        projects = state['projects']

    for project in projects:
        prefix = [hub_name, sanitize(project.name)]
        for data_file, parts in walk_folder(project.rootFolder, []):
            targets.append((data_file, prefix + parts))
    return targets


def run_export(targets, out_root, want_archive, want_step, skip_existing):
    log = []          # (estado, ruta, detalle)
    used = set()
    counts = {'ok': 0, 'omitido': 0, 'error': 0}

    def record(status, where, detail=''):
        log.append((status, where, detail))
        counts[status] += 1

    progress = ui.createProgressDialog()
    progress.cancelButtonText = 'Cancelar'
    progress.isCancelButtonShown = True
    progress.isBackgroundTranslucent = False
    progress.show(CMD_NAME, 'Preparando...', 0, max(len(targets), 1), 0)

    cancelled = False
    for index, (data_file, parts) in enumerate(targets):
        adsk.doEvents()
        if progress.wasCancelled:
            cancelled = True
            break

        name = data_file.name
        where = '/'.join(parts + [name])
        progress.progressValue = index
        progress.message = '%v de %m\n{}'.format(where)

        if extension_of(data_file) != 'f3d':
            record('omitido', where, 'No es un diseno 3D (.{})'.format(extension_of(data_file)))
            continue

        folder = os.path.join(out_root, *parts)
        base = unique_base(folder, sanitize(name), used)
        f3d_path = os.path.join(folder, base + '.f3d')
        f3z_path = os.path.join(folder, base + '.f3z')
        step_path = os.path.join(folder, base + '.step')

        need_archive = want_archive
        need_step = want_step
        if skip_existing:
            if os.path.exists(f3d_path) or os.path.exists(f3z_path):
                need_archive = False
            if os.path.exists(step_path):
                need_step = False
        if not need_archive and not need_step:
            record('omitido', where, 'Ya existia en disco')
            continue

        doc = None
        try:
            os.makedirs(folder, exist_ok=True)
            doc = app.documents.open(data_file, True)
            design = adsk.fusion.Design.cast(
                doc.products.itemByProductType('DesignProductType'))
            if not design:
                record('omitido', where, 'El documento no contiene un diseno')
                continue

            done = []
            errors = []

            if need_archive:
                try:
                    if has_external_references(doc, data_file):
                        export_f3z(folder, base)
                        done.append('F3Z')
                    else:
                        export_f3d(design, f3d_path)
                        done.append('F3D')
                except Exception as exc:
                    errors.append('Archivo: {}'.format(exc))

            if need_step:
                try:
                    export_step(design, step_path)
                    done.append('STEP')
                except Exception as exc:
                    errors.append('STEP: {}'.format(exc))

            if errors:
                detail = '; '.join(errors)
                if done:
                    detail += ' (correcto: {})'.format(', '.join(done))
                record('error', where, detail)
            else:
                record('ok', where, ', '.join(done))
        except Exception as exc:
            record('error', where, str(exc))
        finally:
            if doc:
                try:
                    doc.close(False)
                except Exception:
                    pass

    progress.hide()
    return log, counts, cancelled


def write_log(out_root, log):
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    path = os.path.join(out_root, 'export_log_{}.csv'.format(stamp))
    with open(path, 'w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.writer(handle, delimiter=';')
        writer.writerow(['estado', 'fichero', 'detalle'])
        writer.writerows(log)
    return path


# --------------------------------------------------------------------------
# Dialogo
# --------------------------------------------------------------------------

def selected_project_index(inputs):
    item = inputs.itemById(ID_PROJECT).selectedItem
    return item.index if item else -1


def load_files(inputs):
    """Carga en la lista los disenos del proyecto elegido."""
    index = selected_project_index(inputs)
    files_input = inputs.itemById(ID_FILES)
    if index < 0 or index == state['files_project']:
        return
    files_input.listItems.clear()
    state['files'] = []
    project = state['projects'][index]
    found = [(f, parts) for f, parts in walk_folder(project.rootFolder, [])
             if extension_of(f) == 'f3d']
    found.sort(key=lambda entry: '/'.join(entry[1] + [entry[0].name]).lower())
    for data_file, parts in found:
        files_input.listItems.add('/'.join(parts + [data_file.name]), False, '')
    state['files'] = found
    state['files_project'] = index


def refresh_visibility(inputs):
    scope = inputs.itemById(ID_SCOPE).selectedItem.name
    inputs.itemById(ID_PROJECT).isVisible = scope != SCOPE_ALL
    inputs.itemById(ID_FILES).isVisible = scope == SCOPE_FILES
    if scope == SCOPE_FILES:
        load_files(inputs)


class CreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            command = args.command
            inputs = command.commandInputs
            styles = adsk.core.DropDownStyles

            scope = inputs.addDropDownCommandInput(
                ID_SCOPE, 'Que exportar', styles.TextListDropDownStyle)
            scope.listItems.add(SCOPE_FILES, False, '')
            scope.listItems.add(SCOPE_PROJECT, True, '')
            scope.listItems.add(SCOPE_ALL, False, '')

            project = inputs.addDropDownCommandInput(
                ID_PROJECT, 'Proyecto', styles.TextListDropDownStyle)
            state['projects'] = list(items(app.data.activeHub.dataProjects))
            state['files'] = []
            state['files_project'] = -1
            active_id = None
            try:
                active_id = app.data.activeProject.id
            except Exception:
                pass
            any_selected = False
            for i, data_project in enumerate(state['projects']):
                is_active = data_project.id == active_id
                any_selected = any_selected or is_active
                project.listItems.add(data_project.name, is_active, '')
            if not any_selected and project.listItems.count:
                project.listItems.item(0).isSelected = True

            inputs.addDropDownCommandInput(
                ID_FILES, 'Ficheros', styles.CheckBoxDropDownStyle)

            inputs.addBoolValueInput(ID_F3D, 'Archivo Fusion (F3D / F3Z)', True, '', True)
            inputs.addBoolValueInput(ID_STEP, 'STEP', True, '', True)

            default_folder = os.path.join(os.path.expanduser('~'), 'FusionLocalBackup')
            inputs.addStringValueInput(ID_FOLDER, 'Carpeta de destino', default_folder)
            inputs.addBoolValueInput(ID_BROWSE, 'Examinar...', False, '', False)
            inputs.addBoolValueInput(
                ID_SKIP, 'Omitir los que ya existen en disco', True, '', False)
            inputs.addTextBoxCommandInput(
                ID_INFO, '',
                'Hub: {}. Fusion abrira cada diseno para exportarlo; '
                'no uses Fusion mientras dura el proceso.'.format(app.data.activeHub.name),
                3, True)

            refresh_visibility(inputs)

            for handler_class, event in (
                    (InputChangedHandler, command.inputChanged),
                    (ValidateHandler, command.validateInputs),
                    (ExecuteHandler, command.execute),
                    (DestroyHandler, command.destroy)):
                handler = handler_class()
                event.add(handler)
                handlers.append(handler)
        except Exception:
            ui.messageBox('Error al crear el dialogo:\n{}'.format(traceback.format_exc()))


class InputChangedHandler(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        try:
            inputs = args.firingEvent.sender.commandInputs
            changed = args.input.id
            if changed in (ID_SCOPE, ID_PROJECT):
                refresh_visibility(inputs)
            elif changed == ID_BROWSE:
                dialog = ui.createFolderDialog()
                dialog.title = 'Carpeta de destino'
                if dialog.showDialog() == adsk.core.DialogResults.DialogOK:
                    inputs.itemById(ID_FOLDER).value = dialog.folder
        except Exception:
            ui.messageBox('Error:\n{}'.format(traceback.format_exc()))


class ValidateHandler(adsk.core.ValidateInputsEventHandler):
    def notify(self, args):
        try:
            inputs = args.firingEvent.sender.commandInputs
            valid = bool(inputs.itemById(ID_FOLDER).value.strip())
            valid = valid and (inputs.itemById(ID_F3D).value or inputs.itemById(ID_STEP).value)
            scope = inputs.itemById(ID_SCOPE).selectedItem.name
            if scope != SCOPE_ALL:
                valid = valid and selected_project_index(inputs) >= 0
            if scope == SCOPE_FILES:
                files = inputs.itemById(ID_FILES).listItems
                valid = valid and any(files.item(i).isSelected for i in range(files.count))
            args.areInputsValid = bool(valid)
        except Exception:
            args.areInputsValid = False


class ExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            inputs = args.command.commandInputs
            scope = inputs.itemById(ID_SCOPE).selectedItem.name
            out_root = os.path.abspath(
                os.path.expanduser(inputs.itemById(ID_FOLDER).value.strip()))
            want_archive = inputs.itemById(ID_F3D).value
            want_step = inputs.itemById(ID_STEP).value
            skip_existing = inputs.itemById(ID_SKIP).value
            project_index = selected_project_index(inputs)
            files = inputs.itemById(ID_FILES).listItems
            selected = [i for i in range(files.count) if files.item(i).isSelected]

            os.makedirs(out_root, exist_ok=True)
            targets = collect_targets(scope, project_index, selected)
            if not targets:
                ui.messageBox('No se ha encontrado ningun fichero que exportar.')
                return

            log, counts, cancelled = run_export(
                targets, out_root, want_archive, want_step, skip_existing)
            log_path = write_log(out_root, log)

            ui.messageBox(
                '{}\n\nExportados: {}\nOmitidos: {}\nCon errores: {}\n\n'
                'Carpeta: {}\nRegistro: {}'.format(
                    'Exportacion cancelada.' if cancelled else 'Exportacion terminada.',
                    counts['ok'], counts['omitido'], counts['error'],
                    out_root, os.path.basename(log_path)),
                CMD_NAME)
        except Exception:
            ui.messageBox('Error durante la exportacion:\n{}'.format(traceback.format_exc()))


class DestroyHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        adsk.terminate()


def run(context):
    global app, ui
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface

        definition = ui.commandDefinitions.itemById(CMD_ID)
        if not definition:
            definition = ui.commandDefinitions.addButtonDefinition(
                CMD_ID, CMD_NAME, CMD_TOOLTIP)

        created = CreatedHandler()
        definition.commandCreated.add(created)
        handlers.append(created)

        definition.execute()
        adsk.autoTerminate(False)
    except Exception:
        if ui:
            ui.messageBox('Error:\n{}'.format(traceback.format_exc()))


def stop(context):
    try:
        definition = ui.commandDefinitions.itemById(CMD_ID)
        if definition:
            definition.deleteMe()
    except Exception:
        pass
