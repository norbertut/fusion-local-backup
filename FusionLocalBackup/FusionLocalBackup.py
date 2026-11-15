# -*- coding: utf-8 -*-
"""
Fusion Local Backup - Local copy of your Autodesk Fusion designs.
Fusion Local Backup - Copia local de tus diseños de Autodesk Fusion.

Phase 1 / Fase 1:
  * Formats: Fusion archive (F3D, or F3Z when the design has external
    references) and STEP.
  * Scope: a group of files, a whole project or every project in the
    active hub.
  * Mirrors the Hub / Project / Folders structure on disk.

Phase 2 / Fase 2:
  * Incremental: an index file in the destination folder records, per
    design and per format, the version already exported. Only new or
    changed designs are opened and exported again.
  * Only the latest version is kept on disk.
  * Interface in English or Spanish, following Fusion's language.

Run it from Fusion: UTILITIES > Add-Ins > Scripts.
"""

import csv
import datetime
import json
import os
import re
import time
import traceback
import zipfile

import adsk.core
import adsk.fusion

CMD_ID = 'fusionLocalBackupCmd'
CMD_NAME = 'Fusion Local Backup'

# Scope options, in the same order as the drop-down list.
SCOPE_FILES = 0
SCOPE_PROJECT = 1
SCOPE_ALL = 2

ID_SCOPE = 'scope'
ID_PROJECT = 'project'
ID_FILES = 'files'
ID_F3D = 'fmtF3d'
ID_STEP = 'fmtStep'
ID_FOLDER = 'outFolder'
ID_BROWSE = 'browse'
ID_FORCE = 'forceExport'
ID_INFO = 'info'

# Maximum seconds to wait for Fusion to finish writing an F3Z.
F3Z_TIMEOUT = 300

# Index kept in the destination folder: what was exported, and which version.
INDEX_NAME = 'fusion-local-backup.json'
# Exports are written here first and moved once complete.
TMP_DIR = '_tmp'
# Remembers the last destination folder between runs.
SETTINGS_PATH = os.path.join(os.path.expanduser('~'), '.fusion-local-backup-settings.json')

app = None
ui = None
handlers = []
lang = 'en'

# State shared between the dialog handlers.
state = {
    'projects': [],      # DataProject, same order as the drop-down
    'files': [],         # (DataFile, [folders]) in list order
    'files_project': -1  # index of the project whose files are loaded
}


# --------------------------------------------------------------------------
# Texts / Textos
# --------------------------------------------------------------------------

TEXTS = {
    'tooltip': {
        'en': 'Exports designs to F3D/F3Z and STEP by files, project or hub.',
        'es': 'Exporta diseños a F3D/F3Z y STEP por ficheros, proyecto o hub.'},
    'scope': {'en': 'What to export', 'es': 'Qué exportar'},
    'scope_files': {'en': 'Selected files', 'es': 'Ficheros seleccionados'},
    'scope_project': {'en': 'One project', 'es': 'Un proyecto'},
    'scope_all': {
        'en': 'Everything (all projects in the hub)',
        'es': 'Todo (todos los proyectos del hub)'},
    'project': {'en': 'Project', 'es': 'Proyecto'},
    'files': {'en': 'Files', 'es': 'Ficheros'},
    'fmt_archive': {
        'en': 'Fusion archive (F3D / F3Z)',
        'es': 'Archivo Fusion (F3D / F3Z)'},
    'out_folder': {'en': 'Destination folder', 'es': 'Carpeta de destino'},
    'browse': {'en': 'Browse...', 'es': 'Examinar...'},
    'force': {
        'en': 'Export again even if up to date',
        'es': 'Exportar de nuevo aunque esté al día'},
    'info': {
        'en': 'Hub: {}. Fusion will open each design to export it; '
              'do not use Fusion while the process is running.',
        'es': 'Hub: {}. Fusion abrirá cada diseño para exportarlo; '
              'no uses Fusion mientras dura el proceso.'},
    'cancel': {'en': 'Cancel', 'es': 'Cancelar'},
    'preparing': {'en': 'Preparing...', 'es': 'Preparando...'},
    'progress': {'en': '%v of %m\n{}', 'es': '%v de %m\n{}'},
    'not_3d': {
        'en': 'Not a 3D design (.{})',
        'es': 'No es un diseño 3D (.{})'},
    'up_to_date': {'en': 'Up to date (v{})', 'es': 'Al día (v{})'},
    'moved': {
        'en': 'Renamed or moved in Fusion; local files moved',
        'es': 'Renombrado o movido en Fusion; ficheros locales movidos'},
    'outdated_refs': {
        'en': ' | Uses outdated references: {}',
        'es': ' | Usa referencias desactualizadas: {}'},
    'gone_detail': {
        'en': 'No longer in the cloud; the local copy is kept',
        'es': 'Ya no existe en la nube; se conserva la copia local'},
    'no_design': {
        'en': 'The document does not contain a design',
        'es': 'El documento no contiene un diseño'},
    'err_archive': {'en': 'Archive: {}', 'es': 'Archivo: {}'},
    'err_step': {'en': 'STEP: {}', 'es': 'STEP: {}'},
    'partial_ok': {'en': ' (succeeded: {})', 'es': ' (correcto: {})'},
    'f3d_failed': {
        'en': 'Fusion could not create the F3D',
        'es': 'Fusion no pudo crear el F3D'},
    'step_failed': {
        'en': 'Fusion could not create the STEP',
        'es': 'Fusion no pudo crear el STEP'},
    'f3z_failed': {
        'en': 'The F3Z was not generated (data.fileExport returned nothing)',
        'es': 'No se generó el F3Z (comando data.fileExport sin resultado)'},
    'status_ok': {'en': 'ok', 'es': 'ok'},
    'status_skipped': {'en': 'skipped', 'es': 'omitido'},
    'status_error': {'en': 'error', 'es': 'error'},
    'status_gone': {'en': 'not in cloud', 'es': 'no está en la nube'},
    'log_header': {
        'en': ['status', 'file', 'detail'],
        'es': ['estado', 'fichero', 'detalle']},
    'nothing_found': {
        'en': 'No files to export were found.',
        'es': 'No se ha encontrado ningún fichero que exportar.'},
    'done': {'en': 'Export finished.', 'es': 'Exportación terminada.'},
    'cancelled': {'en': 'Export cancelled.', 'es': 'Exportación cancelada.'},
    'summary': {
        'en': '{}\n\nExported: {}\nUp to date or skipped: {}\nWith errors: {}\n'
              'No longer in the cloud: {}\n\nFolder: {}\nLog: {}',
        'es': '{}\n\nExportados: {}\nAl día u omitidos: {}\nCon errores: {}\n'
              'Ya no están en la nube: {}\n\nCarpeta: {}\nRegistro: {}'},
    'err_dialog': {
        'en': 'Error creating the dialog:\n{}',
        'es': 'Error al crear el diálogo:\n{}'},
    'err_export': {
        'en': 'Error during the export:\n{}',
        'es': 'Error durante la exportación:\n{}'},
    'err_generic': {'en': 'Error:\n{}', 'es': 'Error:\n{}'},
}


def t(key):
    """Returns a text in the active language (English as fallback)."""
    entry = TEXTS[key]
    return entry.get(lang, entry['en'])


def detect_language():
    """Spanish when Fusion runs in Spanish, English otherwise."""
    try:
        user_language = app.preferences.generalPreferences.userLanguage
        if user_language == adsk.core.UserLanguages.SpanishLanguage:
            return 'es'
    except Exception:
        pass
    return 'en'


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def sanitize(name):
    """Turns a Fusion name into a valid file/folder name."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name or '')
    name = name.strip().rstrip('.')
    return name or '_'


def items(collection):
    """Iterates a Fusion API collection safely."""
    for i in range(collection.count):
        item = collection.item(i)
        if item:
            yield item


def walk_folder(folder, parts):
    """Walks a data folder and yields (DataFile, [folders])."""
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
    """True when the design links other designs (needs F3Z, not F3D)."""
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
    """Keeps two designs with the same name from overwriting each other."""
    candidate = base
    n = 2
    while os.path.join(folder, candidate).lower() in used:
        candidate = '{} ({})'.format(base, n)
        n += 1
    used.add(os.path.join(folder, candidate).lower())
    return candidate


# --------------------------------------------------------------------------
# Exporters
# --------------------------------------------------------------------------

def export_f3d(design, path):
    mgr = design.exportManager
    options = mgr.createFusionArchiveExportOptions(path)
    if not mgr.execute(options):
        raise RuntimeError(t('f3d_failed'))


def export_step(design, path):
    mgr = design.exportManager
    options = mgr.createSTEPExportOptions(path)
    if not mgr.execute(options):
        raise RuntimeError(t('step_failed'))


def export_f3z(folder, base):
    """
    Exports the active document as F3Z.

    The public API has no F3Z export, so this uses the undocumented text
    command 'data.fileExport'. Fusion picks the file name, so the new or
    modified F3Z is detected and renamed.
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
        # Finished once the size stops growing.
        if size > 0 and size == last_size:
            break
        last_size = size
    else:
        produced = None if last_size <= 0 else produced

    if not produced:
        raise RuntimeError(t('f3z_failed'))

    target = os.path.join(folder, base + '.f3z')
    source = os.path.join(folder, produced)
    if os.path.normcase(source) != os.path.normcase(target):
        os.replace(source, target)
    return target


# --------------------------------------------------------------------------
# Main process
# --------------------------------------------------------------------------

def collect_targets(scope, project_index, selected_file_indexes):
    """Returns a list of (DataFile, [hub, project, folders...])."""
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


def scanned_prefixes(scope, project_index):
    """'hub/project' prefixes fully walked in this run (None for loose files)."""
    if scope == SCOPE_FILES:
        return None
    hub_name = sanitize(app.data.activeHub.name)
    if scope == SCOPE_PROJECT:
        projects = [state['projects'][project_index]]
    else:
        projects = state['projects']
    return ['{}/{}'.format(hub_name, sanitize(p.name)) for p in projects]


def load_settings():
    try:
        with open(SETTINGS_PATH, encoding='utf-8') as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(settings):
    try:
        with open(SETTINGS_PATH, 'w', encoding='utf-8') as handle:
            json.dump(settings, handle, ensure_ascii=False, indent=1)
    except Exception:
        pass


def load_index(out_root):
    """
    Reads the index of the destination folder.

    Shape: {"format": 1, "designs": {<design id>: {
        "name": Fusion name, "path": "hub/project/folders", "base": file name
        without extension, "archive": {"version", "file", "contains"},
        "step": {"version", "file"}}}}
    """
    path = os.path.join(out_root, INDEX_NAME)
    if os.path.exists(path):
        try:
            with open(path, encoding='utf-8') as handle:
                data = json.load(handle)
            if isinstance(data.get('designs'), dict):
                return data
        except Exception:
            pass
        # Unreadable index: keep it aside and start a new one.
        os.replace(path, path + '.bad')
    return {'format': 1, 'designs': {}}


def save_index(out_root, index):
    path = os.path.join(out_root, INDEX_NAME)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as handle:
        json.dump(index, handle, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def f3z_contents(path, design_id):
    """Referenced designs packed inside an F3Z, as {name: version}."""
    contents = {}
    try:
        with zipfile.ZipFile(path) as archive:
            data = json.loads(archive.read('DesignDescription.json').decode('utf-8'))
        for graph in data['designDescription']['designGraphs']:
            for obj in graph['designObjects']:
                if obj.get('lineage') != design_id:
                    contents[obj.get('displayName', '?')] = obj.get('version')
    except Exception:
        pass
    return contents


def outdated_references(doc):
    """References of the open document that are not at their latest version."""
    notes = []
    try:
        refs = doc.documentReferences
        for i in range(refs.count):
            ref = refs.item(i)
            if ref.isOutOfDate:
                notes.append('{} v{} -> v{}'.format(
                    ref.dataFile.name, ref.version, ref.dataFile.latestVersionNumber))
    except Exception:
        pass
    return notes


def entry_folder(out_root, entry):
    return os.path.join(out_root, *entry['path'].split('/'))


def relocate(out_root, entry, parts, name, used):
    """Moves the local files of a design renamed or moved in Fusion."""
    old_folder = entry_folder(out_root, entry)
    used.discard(os.path.join(old_folder, entry['base']).lower())
    new_folder = os.path.join(out_root, *parts)
    new_base = unique_base(new_folder, sanitize(name), used)
    os.makedirs(new_folder, exist_ok=True)
    for fmt in ('archive', 'step'):
        info = entry.get(fmt)
        if not info:
            continue
        old_file = os.path.join(old_folder, info['file'])
        new_name = new_base + os.path.splitext(info['file'])[1]
        if os.path.exists(old_file):
            os.replace(old_file, os.path.join(new_folder, new_name))
            info['file'] = new_name
        else:
            del entry[fmt]
    entry['name'] = name
    entry['path'] = '/'.join(parts)
    entry['base'] = new_base


def run_export(targets, out_root, want_archive, want_step, force, prefixes=None):
    log = []          # (status key, path, detail)
    counts = {'ok': 0, 'skipped': 0, 'error': 0, 'gone': 0}

    def record(status, where, detail=''):
        log.append((status, where, detail))
        counts[status] += 1

    index = load_index(out_root)
    designs = index['designs']
    used = set(os.path.join(entry_folder(out_root, e), e['base']).lower()
               for e in designs.values())
    seen = set()
    tmp_dir = os.path.join(out_root, TMP_DIR)

    progress = ui.createProgressDialog()
    progress.cancelButtonText = t('cancel')
    progress.isCancelButtonShown = True
    progress.isBackgroundTranslucent = False
    progress.show(CMD_NAME, t('preparing'), 0, max(len(targets), 1), 0)

    cancelled = False
    for position, (data_file, parts) in enumerate(targets):
        adsk.doEvents()
        if progress.wasCancelled:
            cancelled = True
            break

        name = data_file.name
        where = '/'.join(parts + [name])
        progress.progressValue = position
        progress.message = t('progress').format(where)

        if extension_of(data_file) != 'f3d':
            record('skipped', where, t('not_3d').format(extension_of(data_file)))
            continue

        design_id = data_file.id
        version = data_file.versionNumber
        seen.add(design_id)
        folder = os.path.join(out_root, *parts)
        entry = designs.get(design_id)
        moved = False

        doc = None
        try:
            if entry and (entry['path'] != '/'.join(parts) or entry['name'] != name):
                relocate(out_root, entry, parts, name, used)
                save_index(out_root, index)
                moved = True
            if not entry:
                entry = {'name': name, 'path': '/'.join(parts),
                         'base': unique_base(folder, sanitize(name), used)}
            base = entry['base']

            def needs(fmt):
                info = entry.get(fmt)
                if force or not info or info.get('version') != version:
                    return True
                return not os.path.exists(os.path.join(folder, info['file']))

            need_archive = want_archive and needs('archive')
            need_step = want_step and needs('step')
            if not need_archive and not need_step:
                detail = t('up_to_date').format(version)
                if moved:
                    detail += ' | ' + t('moved')
                record('skipped', where, detail)
                continue

            os.makedirs(folder, exist_ok=True)
            os.makedirs(tmp_dir, exist_ok=True)
            doc = app.documents.open(data_file, True)
            design = adsk.fusion.Design.cast(
                doc.products.itemByProductType('DesignProductType'))
            if not design:
                record('skipped', where, t('no_design'))
                continue

            done = []
            errors = []

            if need_archive:
                try:
                    if has_external_references(doc, data_file):
                        tmp_path = export_f3z(tmp_dir, base)
                        file_name = base + '.f3z'
                    else:
                        tmp_path = os.path.join(tmp_dir, base + '.f3d')
                        export_f3d(design, tmp_path)
                        file_name = base + '.f3d'
                    final_path = os.path.join(folder, file_name)
                    os.replace(tmp_path, final_path)
                    # A design can switch between F3D and F3Z: drop the old one.
                    previous = (entry.get('archive') or {}).get('file')
                    if previous and previous != file_name:
                        try:
                            os.remove(os.path.join(folder, previous))
                        except OSError:
                            pass
                    info = {'version': version, 'file': file_name}
                    if file_name.endswith('.f3z'):
                        info['contains'] = f3z_contents(final_path, design_id)
                    entry['archive'] = info
                    done.append(file_name[-3:].upper())
                except Exception as exc:
                    errors.append(t('err_archive').format(exc))

            if need_step:
                try:
                    tmp_path = os.path.join(tmp_dir, base + '.step')
                    export_step(design, tmp_path)
                    os.replace(tmp_path, os.path.join(folder, base + '.step'))
                    entry['step'] = {'version': version, 'file': base + '.step'}
                    done.append('STEP')
                except Exception as exc:
                    errors.append(t('err_step').format(exc))

            if done:
                designs[design_id] = entry
                save_index(out_root, index)

            if errors:
                detail = '; '.join(errors)
                if done:
                    detail += t('partial_ok').format(', '.join(done))
                record('error', where, detail)
            else:
                detail = '{} (v{})'.format(', '.join(done), version)
                outdated = outdated_references(doc)
                if outdated:
                    detail += t('outdated_refs').format(', '.join(outdated))
                if moved:
                    detail += ' | ' + t('moved')
                record('ok', where, detail)
        except Exception as exc:
            record('error', where, str(exc))
        finally:
            if doc:
                try:
                    doc.close(False)
                except Exception:
                    pass

    # Designs in the index that were not found in the projects just walked.
    if prefixes and not cancelled:
        for design_id, entry in designs.items():
            if design_id in seen:
                continue
            if any(entry['path'] == p or entry['path'].startswith(p + '/') for p in prefixes):
                record('gone', entry['path'] + '/' + entry['name'], t('gone_detail'))

    try:
        os.rmdir(tmp_dir)
    except OSError:
        pass

    progress.hide()
    return log, counts, cancelled


def write_log(out_root, log):
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    path = os.path.join(out_root, 'export_log_{}.csv'.format(stamp))
    with open(path, 'w', newline='', encoding='utf-8-sig') as handle:
        writer = csv.writer(handle, delimiter=';')
        writer.writerow(t('log_header'))
        for status, where, detail in log:
            writer.writerow([t('status_' + status), where, detail])
    return path


# --------------------------------------------------------------------------
# Dialog
# --------------------------------------------------------------------------

def selected_index(inputs, input_id):
    item = inputs.itemById(input_id).selectedItem
    return item.index if item else -1


def load_files(inputs):
    """Loads the designs of the chosen project into the list."""
    index = selected_index(inputs, ID_PROJECT)
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
    scope = selected_index(inputs, ID_SCOPE)
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

            # Added in the same order as SCOPE_FILES, SCOPE_PROJECT, SCOPE_ALL.
            scope = inputs.addDropDownCommandInput(
                ID_SCOPE, t('scope'), styles.TextListDropDownStyle)
            scope.listItems.add(t('scope_files'), False, '')
            scope.listItems.add(t('scope_project'), True, '')
            scope.listItems.add(t('scope_all'), False, '')

            project = inputs.addDropDownCommandInput(
                ID_PROJECT, t('project'), styles.TextListDropDownStyle)
            state['projects'] = list(items(app.data.activeHub.dataProjects))
            state['files'] = []
            state['files_project'] = -1
            active_id = None
            try:
                active_id = app.data.activeProject.id
            except Exception:
                pass
            any_selected = False
            for data_project in state['projects']:
                is_active = data_project.id == active_id
                any_selected = any_selected or is_active
                project.listItems.add(data_project.name, is_active, '')
            if not any_selected and project.listItems.count:
                project.listItems.item(0).isSelected = True

            inputs.addDropDownCommandInput(
                ID_FILES, t('files'), styles.CheckBoxDropDownStyle)

            inputs.addBoolValueInput(ID_F3D, t('fmt_archive'), True, '', True)
            inputs.addBoolValueInput(ID_STEP, 'STEP', True, '', True)

            default_folder = load_settings().get('folder') or os.path.join(
                os.path.expanduser('~'), 'FusionLocalBackup')
            inputs.addStringValueInput(ID_FOLDER, t('out_folder'), default_folder)
            inputs.addBoolValueInput(ID_BROWSE, t('browse'), False, '', False)
            inputs.addBoolValueInput(ID_FORCE, t('force'), True, '', False)
            inputs.addTextBoxCommandInput(
                ID_INFO, '', t('info').format(app.data.activeHub.name), 3, True)

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
            ui.messageBox(t('err_dialog').format(traceback.format_exc()))


class InputChangedHandler(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        try:
            inputs = args.firingEvent.sender.commandInputs
            changed = args.input.id
            if changed in (ID_SCOPE, ID_PROJECT):
                refresh_visibility(inputs)
            elif changed == ID_BROWSE:
                dialog = ui.createFolderDialog()
                dialog.title = t('out_folder')
                if dialog.showDialog() == adsk.core.DialogResults.DialogOK:
                    inputs.itemById(ID_FOLDER).value = dialog.folder
        except Exception:
            ui.messageBox(t('err_generic').format(traceback.format_exc()))


class ValidateHandler(adsk.core.ValidateInputsEventHandler):
    def notify(self, args):
        try:
            inputs = args.firingEvent.sender.commandInputs
            valid = bool(inputs.itemById(ID_FOLDER).value.strip())
            valid = valid and (inputs.itemById(ID_F3D).value or inputs.itemById(ID_STEP).value)
            scope = selected_index(inputs, ID_SCOPE)
            if scope != SCOPE_ALL:
                valid = valid and selected_index(inputs, ID_PROJECT) >= 0
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
            scope = selected_index(inputs, ID_SCOPE)
            out_root = os.path.abspath(
                os.path.expanduser(inputs.itemById(ID_FOLDER).value.strip()))
            want_archive = inputs.itemById(ID_F3D).value
            want_step = inputs.itemById(ID_STEP).value
            force = inputs.itemById(ID_FORCE).value
            project_index = selected_index(inputs, ID_PROJECT)
            files = inputs.itemById(ID_FILES).listItems
            selected = [i for i in range(files.count) if files.item(i).isSelected]

            os.makedirs(out_root, exist_ok=True)
            save_settings({'folder': out_root})
            targets = collect_targets(scope, project_index, selected)
            if not targets:
                ui.messageBox(t('nothing_found'))
                return

            log, counts, cancelled = run_export(
                targets, out_root, want_archive, want_step, force,
                scanned_prefixes(scope, project_index))
            log_path = write_log(out_root, log)

            ui.messageBox(
                t('summary').format(
                    t('cancelled') if cancelled else t('done'),
                    counts['ok'], counts['skipped'], counts['error'],
                    counts['gone'], out_root, os.path.basename(log_path)),
                CMD_NAME)
        except Exception:
            ui.messageBox(t('err_export').format(traceback.format_exc()))


class DestroyHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        adsk.terminate()


def run(context):
    global app, ui, lang
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        lang = detect_language()

        # Recreated on every run so the texts follow the current language.
        definition = ui.commandDefinitions.itemById(CMD_ID)
        if definition:
            definition.deleteMe()
        definition = ui.commandDefinitions.addButtonDefinition(
            CMD_ID, CMD_NAME, t('tooltip'))

        created = CreatedHandler()
        definition.commandCreated.add(created)
        handlers.append(created)

        definition.execute()
        adsk.autoTerminate(False)
    except Exception:
        if ui:
            ui.messageBox(t('err_generic').format(traceback.format_exc()))


def stop(context):
    try:
        definition = ui.commandDefinitions.itemById(CMD_ID)
        if definition:
            definition.deleteMe()
    except Exception:
        pass
