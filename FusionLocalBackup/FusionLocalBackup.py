# -*- coding: utf-8 -*-
"""
Fusion Local Backup - Local copy of your Autodesk Fusion designs.
Fusion Local Backup - Copia local de tus diseños de Autodesk Fusion.

Phase 1 / Fase 1:
  * Formats: Fusion archive (F3D, or F3Z when the design has external
    references) and STEP.
  * Scope: one or several projects, or every project in the active hub.
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
import shutil
import time
import traceback
import zipfile

import adsk.core
import adsk.fusion

CMD_ID = 'fusionLocalBackupCmd'
CMD_NAME = 'Fusion Local Backup'

ID_ALL = 'allProjects'
ID_PROJECTS = 'projects'
ID_F3D = 'fmtF3d'
ID_STEP = 'fmtStep'
ID_FOLDER = 'outFolder'
ID_BROWSE = 'browse'
ID_FORCE = 'forceExport'
ID_INFO = 'info'

# Maximum seconds to wait for an F3Z requested from Autodesk.
F3Z_TIMEOUT = 600
# F3Z requests allowed to be on their way at the same time.
MAX_PENDING_F3Z = 5

# Index kept in the destination folder: what was exported, and which version.
INDEX_NAME = 'fusion-local-backup.json'
# Exports are written here first and moved once complete.
# Fusion's own file types other than 3D designs. They cannot be downloaded
# as they are and are not backed up yet (drawings, electronics...).
NATIVE_EXTENSIONS = {'f2d', 'f2t', 'f3t', 'f3z', 'fbrd', 'fsch', 'flbr', 'fprj',
                     'f3e', 'fcam', 'cam360'}
# A file uploaded with one of these extensions can clash with what the script
# exports from a design of the same name.
EXPORT_EXTENSIONS = {'.f3d', '.f3z', '.step'}
RESOURCE_LOG_EVERY = 100     # designs opened between resource notes in the log
TMP_DIR = '_tmp'
MARKER_NAME = 'current.txt'
# Remembers the last destination folder between runs.
SETTINGS_PATH = os.path.join(os.path.expanduser('~'), '.fusion-local-backup-settings.json')

app = None
ui = None
handlers = []
lang = 'en'

# State shared between the dialog handlers.
state = {
    'projects': []       # DataProject, same order as the list
}


# --------------------------------------------------------------------------
# Texts / Textos
# --------------------------------------------------------------------------

TEXTS = {
    'tooltip': {
        'en': 'Local backup of your designs as F3D/F3Z and STEP, by project.',
        'es': 'Copia local de tus diseños en F3D/F3Z y STEP, por proyectos.'},
    'all_projects': {
        'en': 'All projects in the hub',
        'es': 'Todos los proyectos del hub'},
    'projects': {'en': 'Select the projects', 'es': 'Selecciona los proyectos'},
    'scanning': {
        'en': 'Scanning project {}...\n{} files found',
        'es': 'Rastreando el proyecto {}...\n{} ficheros encontrados'},
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
    'waiting_f3z': {
        'en': 'Waiting for {} F3Z from Autodesk...',
        'es': 'Esperando {} F3Z de Autodesk...'},
    'progress': {'en': '%v of %m\n{}', 'es': '%v de %m\n{}'},
    'not_3d': {
        'en': 'Fusion file type not backed up yet (.{})',
        'es': 'Tipo de fichero de Fusion que aún no se copia (.{})'},
    'up_to_date': {'en': 'Up to date (v{})', 'es': 'Al día (v{})'},
    'file_copied': {'en': 'File copied as is (v{})', 'es': 'Fichero copiado tal cual (v{})'},
    'err_download': {'en': 'Download: {}', 'es': 'Descarga: {}'},
    'download_failed': {
        'en': 'Fusion could not download the file',
        'es': 'Fusion no pudo descargar el fichero'},
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
    'scan_error': {
        'en': 'Could not be read from the cloud; not backed up in this run ({})',
        'es': 'No se pudo leer de la nube; no se ha copiado en esta ejecución ({})'},
    'status_ok': {'en': 'ok', 'es': 'ok'},
    'status_skipped': {'en': 'skipped', 'es': 'omitido'},
    'status_error': {'en': 'error', 'es': 'error'},
    'status_gone': {'en': 'not in cloud', 'es': 'no está en la nube'},
    'status_note': {'en': 'note', 'es': 'aviso'},
    'resources': {
        'en': 'Fusion resources: GDI {}/{}, USER {}/{}, handles {}, memory {} MB',
        'es': 'Recursos de Fusion: GDI {}/{}, USER {}/{}, identificadores {}, memoria {} MB'},
    'interrupted': {
        'en': 'The previous run stopped unexpectedly while working on this design',
        'es': 'La ejecución anterior se interrumpió de forma inesperada mientras trabajaba en este diseño'},
    'duration': {'en': 'duration', 'es': 'duración'},
    'log_header': {
        'en': ['status', 'file', 'detail'],
        'es': ['estado', 'fichero', 'detalle']},
    'nothing_found': {
        'en': 'No files to export were found.',
        'es': 'No se ha encontrado ningún fichero que exportar.'},
    'done': {'en': 'Export finished.', 'es': 'Exportación terminada.'},
    'cancelled': {'en': 'Export cancelled.', 'es': 'Exportación cancelada.'},
    'summary': {
        'en': '{}\n\nExported: {}\nUp to date or skipped: {}\nRenamed or moved: {}\n'
              'With errors: {}\nNo longer in the cloud: {}\nDuration: {}\n\n'
              'Folder: {}\nLog: {}',
        'es': '{}\n\nExportados: {}\nAl día u omitidos: {}\nRenombrados o movidos: {}\n'
              'Con errores: {}\nYa no están en la nube: {}\nDuración: {}\n\n'
              'Carpeta: {}\nRegistro: {}'},
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


def fetch(getter, attempts=3):
    """Calls the cloud, retrying: the data service fails now and then."""
    for attempt in range(attempts):
        try:
            return getter()
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(1.5)
            adsk.doEvents()


def fusion_resources():
    """Windows resources used by the Fusion process, or None when they cannot
    be read (Mac, or any failure). Fusion does not give back all the memory
    and handles of the documents it opens and closes; the figures go to the
    log as a diagnostic for very long backups."""
    if os.name != 'nt':
        return None
    try:
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.windll.kernel32
        user = ctypes.windll.user32
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        process = kernel.GetCurrentProcess()
        user.GetGuiResources.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        user.GetGuiResources.restype = wintypes.DWORD

        handles = wintypes.DWORD()
        kernel.GetProcessHandleCount.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.GetProcessHandleCount(process, ctypes.byref(handles))

        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD),
                        ('PageFaultCount', wintypes.DWORD),
                        ('PeakWorkingSetSize', ctypes.c_size_t),
                        ('WorkingSetSize', ctypes.c_size_t),
                        ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
                        ('QuotaPagedPoolUsage', ctypes.c_size_t),
                        ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                        ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                        ('PagefileUsage', ctypes.c_size_t),
                        ('PeakPagefileUsage', ctypes.c_size_t)]
        counters = Counters()
        counters.cb = ctypes.sizeof(Counters)
        psapi = ctypes.windll.psapi
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb)

        limits = {'gdi': 10000, 'user': 10000}     # Windows defaults
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Windows')
            for name, value in (('gdi', 'GDIProcessHandleQuota'),
                                ('user', 'USERProcessHandleQuota')):
                try:
                    limits[name] = int(winreg.QueryValueEx(key, value)[0])
                except Exception:
                    pass
        except Exception:
            pass

        return {'gdi': int(user.GetGuiResources(process, 0)),
                'user': int(user.GetGuiResources(process, 1)),
                'gdi_limit': limits['gdi'], 'user_limit': limits['user'],
                'handles': int(handles.value),
                'memory_mb': int(counters.PagefileUsage >> 20)}
    except Exception:
        return None


def scan_items(get_collection, where, problems):
    """Yields the items of a cloud collection. What cannot be read after
    several attempts is noted in problems and skipped, so that one bad
    item does not abort the whole backup."""
    try:
        collection = fetch(get_collection)
        count = fetch(lambda: collection.count)
    except Exception as exc:
        problems.append((where, str(exc)))
        return
    for i in range(count):
        try:
            item = fetch(lambda: collection.item(i))
        except Exception as exc:
            problems.append(('{} [{}/{}]'.format(where, i + 1, count), str(exc)))
            continue
        if item:
            yield item


def walk_folder(folder, parts, problems):
    """Walks a data folder and yields (DataFile, [folders])."""
    where = '/'.join(parts)
    for data_file in scan_items(lambda: folder.dataFiles, where, problems):
        yield data_file, parts
    for sub in scan_items(lambda: folder.dataFolders, where, problems):
        try:
            name = sanitize(fetch(lambda: sub.name))
        except Exception as exc:
            problems.append((where, str(exc)))
            continue
        for result in walk_folder(sub, parts + [name], problems):
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


def plain_file_name(data_file):
    """Local name of a file that is not Fusion's own (image, SVG, PDF...).
    In the hub its name normally carries the extension already."""
    name = sanitize(data_file.name)
    if not os.path.splitext(name)[1]:
        extension = extension_of(data_file)
        if extension:
            name += '.' + extension
    return name


def unique_file(folder, file_name, used, used_files):
    """Like unique_base, for a file copied as it is: no two files with the
    same name, and no clash with the F3D/F3Z/STEP exported from a design."""
    stem, extension = os.path.splitext(file_name)
    exported = extension.lower() in EXPORT_EXTENSIONS

    def taken(candidate_stem):
        if os.path.join(folder, candidate_stem + extension).lower() in used_files:
            return True
        return exported and os.path.join(folder, candidate_stem).lower() in used

    candidate = stem
    n = 2
    while taken(candidate):
        candidate = '{} ({})'.format(stem, n)
        n += 1
    remember_file(folder, candidate + extension, used, used_files)
    return candidate + extension


def remember_file(folder, file_name, used, used_files):
    stem, extension = os.path.splitext(file_name)
    used_files.add(os.path.join(folder, file_name).lower())
    if extension.lower() in EXPORT_EXTENSIONS:
        used.add(os.path.join(folder, stem).lower())     # designs keep away


def forget_file(folder, file_name, used, used_files):
    stem, extension = os.path.splitext(file_name)
    used_files.discard(os.path.join(folder, file_name).lower())
    if extension.lower() in EXPORT_EXTENSIONS:
        used.discard(os.path.join(folder, stem).lower())


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


def launch_f3z(job_dir):
    """
    Asks Fusion to export the active document as F3Z into job_dir.

    The public API has no F3Z export, so this uses the undocumented text
    command 'data.fileExport'. The command returns at once: Autodesk packs
    the F3Z in the cloud and Fusion downloads it into job_dir some seconds
    later, even if the document has been closed in the meantime. Each
    request gets its own folder because Fusion picks the file name.
    """
    os.makedirs(job_dir, exist_ok=True)
    app.executeTextCommand('data.fileExport f3z "{}"'.format(job_dir))


def arrived_f3z(job_dir):
    """Path of the finished F3Z in job_dir, or None while it is on its way."""
    try:
        names = [n for n in os.listdir(job_dir) if n.lower().endswith('.f3z')]
        if not names:
            return None
        path = os.path.join(job_dir, names[0])
        # A zip only opens once it has been written to the end.
        if not zipfile.is_zipfile(path):
            return None
        with zipfile.ZipFile(path) as archive:
            archive.namelist()
        return path
    except Exception:
        return None


# --------------------------------------------------------------------------
# Main process
# --------------------------------------------------------------------------

def collect_targets(projects):
    """
    Walks the given projects and returns (targets, prefixes).

    targets: list of (DataFile, [hub, project, folders...]).
    prefixes: the 'hub/project' paths that were fully walked.
    Returns (None, None) when the user cancels. Walking a large project
    takes a while, so progress is shown from the start.
    """
    hub_name = sanitize(app.data.activeHub.name)
    targets = []
    prefixes = []
    problems = []     # (path, error) of what could not be read

    progress = ui.createProgressDialog()
    progress.cancelButtonText = t('cancel')
    progress.isCancelButtonShown = True
    progress.isBackgroundTranslucent = False
    progress.show(CMD_NAME, t('scanning').format('', 0), 0, max(len(projects), 1), 0)

    try:
        for position, project in enumerate(projects):
            progress.progressValue = position
            progress.message = t('scanning').format(project.name, len(targets))
            adsk.doEvents()
            prefix = [hub_name, sanitize(project.name)]
            before = len(problems)
            try:
                root = fetch(lambda: project.rootFolder)
            except Exception as exc:
                problems.append(('/'.join(prefix), str(exc)))
                continue
            for data_file, parts in walk_folder(root, prefix, problems):
                targets.append((data_file, parts))
                if len(targets) % 5 == 0:
                    progress.message = t('scanning').format(project.name, len(targets))
                    adsk.doEvents()
                    if progress.wasCancelled:
                        return None, None, None
            if progress.wasCancelled:
                return None, None, None
            # A project that was not read in full is left out of the check
            # for designs deleted in the cloud, to avoid false reports.
            if len(problems) == before:
                prefixes.append('/'.join(prefix))
    finally:
        progress.hide()
    return targets, prefixes, problems


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


def run_export(targets, out_root, want_archive, want_step, force, prefixes=None,
               scan_problems=None, log_path=None):
    log = []          # (status key, path, detail)
    counts = {'ok': 0, 'skipped': 0, 'error': 0, 'gone': 0, 'moved': 0}

    def record(status, where, detail=''):
        log.append((status, where, detail))
        counts[status] += 1
        # Written line by line: if Fusion closes halfway, the log survives.
        append_log(log_path, [t('status_' + status), where, detail])

    # A marker left behind means the previous run did not reach its end
    # (Fusion closed, power cut...). Say which design it was working on.
    tmp_dir = os.path.join(out_root, TMP_DIR)
    marker = os.path.join(tmp_dir, MARKER_NAME)
    try:
        with open(marker, encoding='utf-8') as handle:
            interrupted = handle.read().strip()
        if interrupted:
            append_log(log_path, [t('status_note'), interrupted, t('interrupted')])
    except Exception:
        pass

    for where, detail in scan_problems or []:
        record('error', where, t('scan_error').format(detail))

    def report(where, version, done, errors, outdated, moved):
        """Writes the log line of a design once all its exports are settled."""
        if errors:
            detail = '; '.join(errors)
            if done:
                detail += t('partial_ok').format(', '.join(done))
            record('error', where, detail)
            return
        detail = '{} (v{})'.format(', '.join(done), version)
        if outdated:
            detail += t('outdated_refs').format(', '.join(outdated))
        if moved:
            detail += ' | ' + t('moved')
        record('ok', where, detail)

    index = load_index(out_root)
    designs = index['designs']
    used = set()          # folder/base of the designs, to keep names unique
    used_files = set()    # folder/name of the files copied as they are
    for known in designs.values():
        if known.get('kind') == 'file':
            remember_file(entry_folder(out_root, known), known['base'], used, used_files)
        else:
            used.add(os.path.join(entry_folder(out_root, known), known['base']).lower())
    seen = set()
    shutil.rmtree(tmp_dir, ignore_errors=True)   # leftovers of an interrupted run
    pending = []      # F3Z requested from Autodesk and not yet received
    launched = [0]

    progress = ui.createProgressDialog()
    progress.cancelButtonText = t('cancel')
    progress.isCancelButtonShown = True
    progress.isBackgroundTranslucent = False
    progress.show(CMD_NAME, t('preparing'), 0, max(len(targets), 1), 0)

    def drop_previous(entry, folder, file_name):
        # A design can switch between F3D and F3Z: drop the old one.
        previous = (entry.get('archive') or {}).get('file')
        if previous and previous != file_name:
            try:
                os.remove(os.path.join(folder, previous))
            except OSError:
                pass

    def settle(job, f3z_path=None, error=None):
        """Finishes a pending F3Z. False when the file is not movable yet."""
        entry = job['entry']
        if f3z_path:
            file_name = job['base'] + '.f3z'
            final_path = os.path.join(job['folder'], file_name)
            try:
                os.replace(f3z_path, final_path)
            except OSError:
                return False
            drop_previous(entry, job['folder'], file_name)
            entry['archive'] = {'version': job['version'], 'file': file_name,
                                'contains': f3z_contents(final_path, job['id'])}
            designs[job['id']] = entry
            save_index(out_root, index)
            job['done'].insert(0, 'F3Z')
        else:
            job['errors'].insert(0, t('err_archive').format(error))
        shutil.rmtree(job['dir'], ignore_errors=True)
        report(job['where'], job['version'], job['done'], job['errors'],
               job['outdated'], job['moved'])
        return True

    def collect():
        """Puts in place the F3Z files that have arrived."""
        for job in list(pending):
            path = arrived_f3z(job['dir'])
            if path:
                if settle(job, f3z_path=path):
                    pending.remove(job)
            elif time.time() - job['started'] > F3Z_TIMEOUT:
                settle(job, error=t('f3z_failed'))
                pending.remove(job)

    def wait_until_pending(limit):
        """Waits until at most `limit` F3Z requests are still on their way."""
        collect()
        while len(pending) > limit:
            progress.message = t('waiting_f3z').format(len(pending))
            adsk.doEvents()
            time.sleep(0.5)
            collect()

    def copy_plain_file(data_file, parts, name, where):
        file_id = data_file.id
        version = data_file.versionNumber
        seen.add(file_id)
        folder = os.path.join(out_root, *parts)
        path = '/'.join(parts)
        entry = designs.get(file_id)
        if entry and entry.get('kind') != 'file':
            entry = None
        moved = False

        if entry and (entry['path'] != path or entry['name'] != name):
            # Renamed or moved in Fusion: the local file follows.
            old_folder = entry_folder(out_root, entry)
            old_file = os.path.join(old_folder, entry['base'])
            forget_file(old_folder, entry['base'], used, used_files)
            new_name = unique_file(folder, plain_file_name(data_file), used, used_files)
            os.makedirs(folder, exist_ok=True)
            if os.path.exists(old_file):
                os.replace(old_file, os.path.join(folder, new_name))
            else:
                entry.pop('file', None)
            entry.update(name=name, path=path, base=new_name)
            save_index(out_root, index)
            moved = True
            counts['moved'] += 1
        if not entry:
            entry = {'kind': 'file', 'name': name, 'path': path,
                     'base': unique_file(folder, plain_file_name(data_file),
                                         used, used_files)}

        final_path = os.path.join(folder, entry['base'])
        info = entry.get('file')
        if (not force and info and info.get('version') == version
                and os.path.exists(final_path)):
            detail = t('up_to_date').format(version)
            if moved:
                detail += ' | ' + t('moved')
            record('skipped', where, detail)
            return

        os.makedirs(folder, exist_ok=True)
        os.makedirs(tmp_dir, exist_ok=True)
        # Downloaded under a plain temporary name: Fusion garbles accents
        # and dots when it writes the name itself.
        launched[0] += 1
        tmp_path = os.path.join(
            tmp_dir, 'download_{}{}'.format(launched[0], os.path.splitext(entry['base'])[1]))
        def download():
            if not data_file.download(tmp_path, None) or not os.path.exists(tmp_path):
                raise RuntimeError(t('download_failed'))
        fetch(download, 2)
        os.replace(tmp_path, final_path)
        entry['file'] = {'version': version}
        designs[file_id] = entry
        save_index(out_root, index)
        detail = t('file_copied').format(version)
        if moved:
            detail += ' | ' + t('moved')
        record('ok', where, detail)

    def note_resources(usage):
        append_log(log_path, [t('status_note'), '', t('resources').format(
            usage['gdi'], usage['gdi_limit'], usage['user'], usage['user_limit'],
            usage['handles'], usage['memory_mb'])])

    cancelled = False
    opened = 0
    logged_at = -1
    for position, (data_file, parts) in enumerate(targets):
        adsk.doEvents()
        if progress.wasCancelled:
            cancelled = True
            break
        collect()

        # Fusion's own resources, noted now and then: if Fusion closes in the
        # middle of a long backup, the log shows how worn the session was.
        if opened != logged_at and opened % RESOURCE_LOG_EVERY == 0:
            logged_at = opened
            usage = fusion_resources()
            if usage:
                note_resources(usage)

        name = data_file.name
        where = '/'.join(parts + [name])
        progress.progressValue = position
        progress.message = t('progress').format(where)
        try:
            os.makedirs(tmp_dir, exist_ok=True)
            with open(marker, 'w', encoding='utf-8') as handle:
                handle.write(where)
        except Exception:
            pass

        extension = extension_of(data_file)
        if extension in NATIVE_EXTENSIONS:
            record('skipped', where, t('not_3d').format(extension))
            continue
        if extension != 'f3d':
            # Not a Fusion file (image, SVG, DXF, PDF, an uploaded STEP...):
            # copied as it is, with the same version check as the designs.
            try:
                copy_plain_file(data_file, parts, name, where)
            except Exception as exc:
                record('error', where, t('err_download').format(exc))
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
                counts['moved'] += 1
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
            opened += 1
            design = adsk.fusion.Design.cast(
                doc.products.itemByProductType('DesignProductType'))
            if not design:
                record('skipped', where, t('no_design'))
                continue

            done = []
            errors = []
            job = None

            if need_archive:
                try:
                    if has_external_references(doc, data_file):
                        # Requested now and picked up later: Autodesk takes a
                        # while to pack it and there is no need to wait idle.
                        wait_until_pending(MAX_PENDING_F3Z - 1)
                        progress.message = t('progress').format(where)
                        launched[0] += 1
                        job_dir = os.path.join(tmp_dir, 'f3z_{}'.format(launched[0]))
                        launch_f3z(job_dir)
                        job = {'id': design_id, 'entry': entry, 'folder': folder,
                               'base': base, 'version': version, 'where': where,
                               'dir': job_dir, 'started': time.time()}
                    else:
                        tmp_path = os.path.join(tmp_dir, base + '.f3d')
                        export_f3d(design, tmp_path)
                        file_name = base + '.f3d'
                        os.replace(tmp_path, os.path.join(folder, file_name))
                        drop_previous(entry, folder, file_name)
                        entry['archive'] = {'version': version, 'file': file_name}
                        done.append('F3D')
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

            outdated = outdated_references(doc)
            if job:
                job.update(done=done, errors=errors, outdated=outdated, moved=moved)
                pending.append(job)
            else:
                report(where, version, done, errors, outdated, moved)
        except Exception as exc:
            record('error', where, str(exc))
        finally:
            if doc:
                try:
                    doc.close(False)
                except Exception:
                    pass

    # Also after a cancel: the F3Z already requested are on their way.
    wait_until_pending(0)

    # Designs in the index that were not found in the projects just walked.
    if prefixes and not cancelled:
        for design_id, entry in designs.items():
            if design_id in seen:
                continue
            if any(entry['path'] == p or entry['path'].startswith(p + '/') for p in prefixes):
                record('gone', entry['path'] + '/' + entry['name'], t('gone_detail'))

    shutil.rmtree(tmp_dir, ignore_errors=True)
    progress.hide()
    return log, counts, cancelled


def format_duration(seconds):
    seconds = int(round(seconds))
    return '{:d}:{:02d}:{:02d}'.format(seconds // 3600, seconds % 3600 // 60, seconds % 60)


def start_log(out_root):
    """Creates the log of this run, with its header, and returns its path."""
    stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    path = os.path.join(out_root, 'export_log_{}.csv'.format(stamp))
    with open(path, 'w', newline='', encoding='utf-8-sig') as handle:
        csv.writer(handle, delimiter=';').writerow(t('log_header'))
    return path


def append_log(path, row):
    """Adds a line to the log right away. Never breaks the backup."""
    if not path:
        return
    try:
        with open(path, 'a', newline='', encoding='utf-8') as handle:
            csv.writer(handle, delimiter=';').writerow(row)
    except Exception:
        pass


# --------------------------------------------------------------------------
# Dialog
# --------------------------------------------------------------------------

def selected_projects(inputs):
    """Projects chosen in the dialog."""
    if inputs.itemById(ID_ALL).value:
        return list(state['projects'])
    listed = inputs.itemById(ID_PROJECTS).listItems
    return [state['projects'][i] for i in range(listed.count) if listed.item(i).isSelected]


class CreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            command = args.command
            inputs = command.commandInputs
            settings = load_settings()

            state['projects'] = list(items(app.data.activeHub.dataProjects))

            # Start from the last selection; the first time, from the active project.
            remembered = settings.get('projects')
            if remembered is None:
                try:
                    remembered = [app.data.activeProject.id]
                except Exception:
                    remembered = []
            all_projects = bool(settings.get('all', False))

            inputs.addBoolValueInput(ID_ALL, t('all_projects'), True, '', all_projects)
            projects = inputs.addDropDownCommandInput(
                ID_PROJECTS, t('projects'), adsk.core.DropDownStyles.CheckBoxDropDownStyle)
            for data_project in state['projects']:
                projects.listItems.add(data_project.name, data_project.id in remembered, '')
            projects.isVisible = not all_projects

            inputs.addBoolValueInput(ID_F3D, t('fmt_archive'), True, '', True)
            inputs.addBoolValueInput(ID_STEP, 'STEP', True, '', True)

            default_folder = settings.get('folder') or os.path.join(
                os.path.expanduser('~'), 'FusionLocalBackup')
            inputs.addStringValueInput(ID_FOLDER, t('out_folder'), default_folder)
            browse = inputs.addBoolValueInput(ID_BROWSE, ' ', False, '', False)
            browse.text = t('browse')
            inputs.addBoolValueInput(ID_FORCE, t('force'), True, '', False)
            inputs.addTextBoxCommandInput(
                ID_INFO, '', t('info').format(app.data.activeHub.name), 3, True)

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
            if changed == ID_ALL:
                inputs.itemById(ID_PROJECTS).isVisible = not inputs.itemById(ID_ALL).value
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
            valid = valid and bool(selected_projects(inputs))
            args.areInputsValid = bool(valid)
        except Exception:
            args.areInputsValid = False


class ExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            inputs = args.command.commandInputs
            out_root = os.path.abspath(
                os.path.expanduser(inputs.itemById(ID_FOLDER).value.strip()))
            want_archive = inputs.itemById(ID_F3D).value
            want_step = inputs.itemById(ID_STEP).value
            force = inputs.itemById(ID_FORCE).value
            all_projects = inputs.itemById(ID_ALL).value
            projects = selected_projects(inputs)

            os.makedirs(out_root, exist_ok=True)
            listed = inputs.itemById(ID_PROJECTS).listItems
            save_settings({
                'folder': out_root,
                'all': all_projects,
                'projects': [state['projects'][i].id for i in range(listed.count)
                             if listed.item(i).isSelected]})

            started = time.time()
            targets, prefixes, problems = collect_targets(projects)
            if targets is None:
                ui.messageBox(t('cancelled'), CMD_NAME)
                return
            if not targets and not problems:
                ui.messageBox(t('nothing_found'))
                return

            log_path = start_log(out_root)
            log, counts, cancelled = run_export(
                targets, out_root, want_archive, want_step, force, prefixes,
                problems, log_path)
            duration = time.time() - started
            append_log(log_path, [t('duration'), '', format_duration(duration)])

            ui.messageBox(
                t('summary').format(
                    t('cancelled') if cancelled else t('done'),
                    counts['ok'], counts['skipped'], counts['moved'], counts['error'],
                    counts['gone'], format_duration(duration), out_root,
                    os.path.basename(log_path)),
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
