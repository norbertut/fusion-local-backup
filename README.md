# Fusion Local Backup

*[Leer en español](README.es.md)*

A script for Autodesk Fusion that keeps a local copy of your designs: it takes them out of the cloud and saves them to your disk as F3D/F3Z and STEP.

New here? The **[user guide](docs/guide.md)** walks you through installation, the first backup and keeping it current.

## What it does

- **Formats:** Fusion archive (F3D, or F3Z when the design has external references) and STEP.
- **Scope:** tick the projects you want to back up, or all the projects in the active hub. The script remembers your selection, so the next backup is open and OK.
- **Structure:** mirrors `Hub / Project / Folders / Design` on disk.
- **Log:** when it finishes it saves an `export_log_DATE.csv` with the result for each file and the total duration.
- **Incremental:** an index file in the destination folder (`fusion-local-backup.json`) records which version of each design was exported, per format. Later runs only open and export designs that are new or have changed, so keep using the same destination folder. Only the latest version is kept on disk.
- **Renames and moves:** designs are tracked by their Fusion id, so if you rename or move one in Fusion its local files are moved instead of duplicated.
- **Nothing is deleted:** a design removed from Fusion is reported in the log as "not in cloud" and its local copy is kept.
- **Outdated references:** when an assembly uses an older version of a linked part, the log says which one.
- **F3Z in the background:** Autodesk packs each F3Z in the cloud, which takes tens of seconds. The script requests it, moves on to the next design and puts each F3Z in place when it arrives, with at most 5 requests on their way.
- **Safe writes:** each file is exported to a temporary folder and moved when complete, so an interrupted run never leaves a half-written file in place.
- **Language:** the interface is in Spanish when Fusion runs in Spanish, and in English otherwise.

## Installation

Download the ZIP of the [latest release](https://github.com/norbertut/fusion-local-backup/releases/latest) and unzip it. Inside is the `FusionLocalBackup` folder, which is the script. There are two ways to install it:

**Option A: in Fusion's scripts folder.** Fusion picks it up directly.

1. Copy the `FusionLocalBackup` folder into Fusion's scripts folder:
   - Windows: `%appdata%\Autodesk\Autodesk Fusion 360\API\Scripts`
   - Mac: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts`
2. In Fusion, open **UTILITIES > Add-Ins > Scripts and Add-Ins**. The script is already in the list; if not, restart Fusion.

**Option B: in any folder you like.**

1. Put the `FusionLocalBackup` folder somewhere permanent. Fusion runs it from there, so do not move or delete it afterwards.
2. In Fusion, open **UTILITIES > Add-Ins > Scripts and Add-Ins**.
3. Click **+**, choose the option to add from your device and select the `FusionLocalBackup` folder.

## Usage

1. In that same window, click the ▶ icon next to FusionLocalBackup.
2. Under "Select the projects", tick the ones to back up, or tick "All projects in the hub".
3. Tick the formats and set the destination folder. The script remembers the last folder you used.
4. Click OK and let Fusion work. It first scans the projects, showing how many files it has found, and then opens, exports and closes each design that needs it. At the end it waits for any F3Z still on its way.
5. To keep the backup current, run it again with the same destination folder: it only exports what is new or changed.

The "Export again even if up to date" box forces everything selected to be regenerated. You can cancel at any time: what has been exported is recorded and the next run carries on from there.

## How long it takes

There is no figure that holds for everyone: it depends on how powerful the computer is, on the connection and on the size of the designs.

- **First backup of a project:** this is the slow one, because every design has to be opened once, and each takes several seconds. A project with hundreds of files can take quite a while, and one with thousands, hours; best left to run on its own. If you cancel it, the next run carries on where it stopped.
- **Later backups:** these are quick, because only the projects are scanned and the new or changed designs opened.

The log and the final message show how long each run took, so after the first backup you will know what to expect on your computer.

## Known limitations

- Fusion stays busy for the whole process.
- Only 3D designs (`.f3d`) are exported. Drawings, electronics and other files are skipped and noted in the log.
- "All projects" means every project in the active hub. For another hub, switch to it in the data panel and run the script again.
- **F3Z relies on an undocumented command.** Fusion's public API cannot export F3Z, so the script uses the `data.fileExport` text command. It works (the resulting F3Z has been re-imported into Fusion with its links intact), but an update could break it. If it fails, the error is logged and the STEP is still exported.
- **Each F3Z triggers an email from Autodesk.** The F3Z is packaged in Autodesk's cloud, which sends an "is ready to be downloaded" email for each one. You do not need that link: the file is already saved in the destination folder. F3D and STEP exports send no email. If you have many assemblies, set up a mail filter for those messages.
- **Assemblies duplicate content.** When you export a project with assemblies you get the F3D of each linked part and also the assembly's F3Z, which already contains those same parts. This is expected: each design is available on its own and the assembly is complete in a single file.
- **Assemblies are saved as they are.** An F3Z packs the version of each linked part that the assembly is pinned to, not the latest one. It is exported again when the assembly itself gets a new version, that is, after you open it, accept the update and save.
- Always use the same destination folder. If you pick another one, or a folder without the index file, a new full backup is made.
- STEP files only include visible bodies.

## Roadmap

- Other file types (drawings, electronics, etc.).

## License

MIT. See the `LICENSE` file.
