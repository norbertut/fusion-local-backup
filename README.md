# Fusion Local Backup

*[Leer en español](README.es.md)*

A script for Autodesk Fusion that keeps a local copy of your designs: it takes them out of the cloud and saves them to your disk as F3D/F3Z and STEP.

## What it does (phase 1)

- **Formats:** Fusion archive (F3D, or F3Z when the design has external references) and STEP.
- **Scope:** a group of files in a project, a whole project, or every project in the active hub.
- **Structure:** mirrors `Hub / Project / Folders / Design` on disk.
- **Log:** when it finishes it saves an `export_log_DATE.csv` with the result for each file.
- **Resume:** the "Skip files that already exist on disk" option lets you continue an interrupted export.
- **Language:** the interface is in Spanish when Fusion runs in Spanish, and in English otherwise.

## Installation

1. Download this repository (Code > Download ZIP) and unzip it.
2. In Fusion: **UTILITIES > Add-Ins > Scripts and Add-Ins**.
3. Click **+** and choose "Script or add-in from device".
4. Select the `FusionLocalBackup` folder (the one that contains `FusionLocalBackup.py`).

## Usage

1. Run the script from the scripts list.
2. Choose what to export: selected files, one project, or everything.
3. Tick the formats and set the destination folder.
4. Click OK and let Fusion work. It opens each design, exports it and closes it.

## Known limitations

- Fusion stays busy for the whole process.
- Only 3D designs (`.f3d`) are exported. Drawings, electronics and other files are skipped and noted in the log.
- "Everything" means every project in the active hub. For another hub, switch to it in the data panel and run the script again.
- **F3Z relies on an undocumented command.** Fusion's public API cannot export F3Z, so the script uses the `data.fileExport` text command. It works (the resulting F3Z has been re-imported into Fusion with its links intact), but an update could break it. If it fails, the error is logged and the STEP is still exported.
- **Each F3Z triggers an email from Autodesk.** The F3Z is packaged in Autodesk's cloud, which sends an "is ready to be downloaded" email for each one. You do not need that link: the file is already saved in the destination folder. F3D and STEP exports send no email.
- **Assemblies duplicate content.** When you export a project with assemblies you get the F3D of each linked part and also the assembly's F3Z, which already contains those same parts. This is expected: each design is available on its own and the assembly is complete in a single file.
- The "skip existing" option only checks that a file with that name exists. It does not detect designs changed since the last export.
- STEP files only include visible bodies.

## Roadmap

- Phase 2: incremental export (only what has changed since last time, based on the version number).
- Later: other file types (drawings, electronics, etc.).

## License

MIT. See the `LICENSE` file.
