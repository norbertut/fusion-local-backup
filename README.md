# Fusion Local Backup

*[Leer en español](README.es.md)*

A script for Autodesk Fusion that keeps a local copy of your designs: it takes them out of the cloud and saves them to your disk as F3D/F3Z and STEP.

## What it does

- **Formats:** Fusion archive (F3D, or F3Z when the design has external references) and STEP.
- **Scope:** tick the projects you want to back up, or all the projects in the active hub. The script remembers your selection, so the next backup is open and OK.
- **Structure:** mirrors `Hub / Project / Folders / Design` on disk.
- **Log:** when it finishes it saves an `export_log_DATE.csv` with the result for each file.
- **Incremental:** an index file in the destination folder (`fusion-local-backup.json`) records which version of each design was exported, per format. Later runs only open and export designs that are new or have changed, so keep using the same destination folder. Only the latest version is kept on disk.
- **Renames and moves:** designs are tracked by their Fusion id, so if you rename or move one in Fusion its local files are moved instead of duplicated.
- **Nothing is deleted:** a design removed from Fusion is reported in the log as "not in cloud" and its local copy is kept.
- **Outdated references:** when an assembly uses an older version of a linked part, the log says which one.
- **Safe writes:** each file is exported to a temporary folder and moved when complete, so an interrupted run never leaves a half-written file in place.
- **Language:** the interface is in Spanish when Fusion runs in Spanish, and in English otherwise.

## Installation

1. Download this repository (Code > Download ZIP) and unzip it.
2. In Fusion: **UTILITIES > Add-Ins > Scripts and Add-Ins**.
3. Click **+** and choose "Script or add-in from device".
4. Select the `FusionLocalBackup` folder (the one that contains `FusionLocalBackup.py`).

## Usage

1. Run the script from the scripts list.
2. Tick the projects to back up, or "All projects in the hub".
3. Tick the formats and set the destination folder. The script remembers the last folder you used.
4. Click OK and let Fusion work. It first scans the projects, showing how many files it has found, and then opens, exports and closes each design that needs it.

## Known limitations

- Fusion stays busy for the whole process.
- Only 3D designs (`.f3d`) are exported. Drawings, electronics and other files are skipped and noted in the log.
- "All projects" means every project in the active hub. For another hub, switch to it in the data panel and run the script again.
- **F3Z relies on an undocumented command.** Fusion's public API cannot export F3Z, so the script uses the `data.fileExport` text command. It works (the resulting F3Z has been re-imported into Fusion with its links intact), but an update could break it. If it fails, the error is logged and the STEP is still exported.
- **Each F3Z triggers an email from Autodesk.** The F3Z is packaged in Autodesk's cloud, which sends an "is ready to be downloaded" email for each one. You do not need that link: the file is already saved in the destination folder. F3D and STEP exports send no email.
- **Assemblies duplicate content.** When you export a project with assemblies you get the F3D of each linked part and also the assembly's F3Z, which already contains those same parts. This is expected: each design is available on its own and the assembly is complete in a single file.
- **Assemblies are saved as they are.** An F3Z packs the version of each linked part that the assembly is pinned to, not the latest one. It is exported again when the assembly itself gets a new version, that is, after you open it, accept the update and save.
- Reading version numbers from the cloud takes time: roughly 40 seconds per 100 files. It is still far quicker than opening every design.
- A destination folder exported with an earlier version of the script has no index, so the first incremental run exports everything once.
- STEP files only include visible bodies.

## Roadmap

- Other file types (drawings, electronics, etc.).

## License

MIT. See the `LICENSE` file.
