# ExternalDriveTester
# Ein Tool zum Testen von externen Laufwerken (USB-Sticks, SD-Karten, externe Festplatten).
# Funktionen:
# - Kapazitätsprüfung (verifizierte Schreib-/Lese-Tests)
# - Geschwindigkeitsmessung (Schreib-/Lesegeschwindigkeit)
# - Integritätstest (Datenkonsistenzprüfung)
# - Backup/Restore ganzer Laufwerke als ZIP-Archiv
# Konfiguration über externe JSON-Datei (z. B. unterstützte Sprachen, Theme, Testgrößen)
# Fortschrittsanzeige und Ergebnisprotokollierung in der UI
# Autor: Copyright Manfred Zainhofer (08.04.2026)
# Benutzung auf eigene Gefahr. Keine Haftung für Datenverlust oder Schäden.

import os
import sys
import time
import json
import zipfile
import threading
import psutil
import ttkbootstrap as tb
from ttkbootstrap.constants import *  # type: ignore[import-untyped]
from tkinter import ttk, messagebox, StringVar, Canvas, PhotoImage, filedialog, Menu, Toplevel


def resource_path(relative_path: str) -> str:
    """Pfad fuer normale Ausfuehrung und PyInstaller-Onefile."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(getattr(sys, "_MEIPASS"), relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)


def runtime_dir() -> str:
    """Liefert den Pfad, in dem externe Dateien (z. B. config) liegen sollen."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


DEFAULT_CONFIG = {
    "window_title": "External Drive Tester v1.2",
    "window_width": 1050,
    "window_height": 1900,
    "theme": "darkly",
    "language": "de",
    "supported_languages": ["de", "en", "fr", "es"],
    "block_size_mb": 100,
    "test_size_options": ["10 MB", "100 MB", "500 MB", "1 GB", "5 GB"],
    "default_test_size": "100 MB",
    "last_drive": "",
    "last_directory": "",
}

def load_i18n() -> dict:
    """Lädt Übersetzungen aus externer i18n.json mit robustem Fallback."""
    i18n_path = os.path.join(runtime_dir(), "i18n.json")
    fallback = {lang: {} for lang in DEFAULT_CONFIG["supported_languages"]}

    if not os.path.exists(i18n_path):
        return fallback

    try:
        with open(i18n_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return fallback

    if not isinstance(data, dict):
        return fallback

    normalized: dict = {}
    for lang, values in data.items():
        if not isinstance(lang, str) or not isinstance(values, dict):
            continue
        key = lang.strip().lower()
        if not key:
            continue
        normalized[key] = {str(k): str(v) for k, v in values.items()}

    return normalized or fallback


I18N = load_i18n()


def load_theme_name() -> str:
    """Lädt den Theme-Namen frühzeitig, bevor das Hauptfenster erzeugt wird."""
    config_path = os.path.join(runtime_dir(), "ExternalDriveTester.config.json")
    theme = str(DEFAULT_CONFIG["theme"])
    if not os.path.exists(config_path):
        return theme
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            candidate = loaded.get("theme")
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    except Exception:
        pass
    return theme

class ExternalDriveTester:
    # Fenstergrößen (leicht anpassbar)
    WINDOW_WIDTH = 1050
    WINDOW_HEIGHT = 1900
    BLOCK_SIZE_MB = 100  # Jeder Block = 50 MB (für die Visualisierung)
    
    def __init__(self, root):
        self.root = root
        self.config_path = os.path.join(runtime_dir(), "ExternalDriveTester.config.json")
        self.config = self.load_config()

        self.WINDOW_WIDTH = int(self.config["window_width"])
        self.WINDOW_HEIGHT = int(self.config["window_height"])
        self.BLOCK_SIZE_MB = int(self.config["block_size_mb"])
        self.theme_name = str(self.config["theme"])
        self.language = str(self.config["language"])
        self.supported_languages = list(self.config["supported_languages"])
        self.test_size_values = list(self.config["test_size_options"])
        self.default_test_size = str(self.config["default_test_size"])
        self.language_var = StringVar(value=self.language)

        self.root.title(str(self.config["window_title"]))
        self.root.geometry(f"{self.WINDOW_WIDTH}x{self.WINDOW_HEIGHT}")
        self.window_icon_img = None
        self.title_img = None

        # Fenstersymbol setzen (Windows-Titlebar zeigt zuverlaessig .ico)
        self.set_window_icon()
        
        # Variablen
        self.selected_drive = StringVar()
        self.test_in_progress = False
        self.test_thread = None
        self.stop_requested = False
        self.verified_capacity_var = StringVar(value=f"{self.t('ui_verified_written')}: -")
        self.block_cells: list = []
        self.block_base_colors: list[str] = []
        self.block_count = 0
        self._display_block_count = 0
        
        # Modernes Theme
        self.style = tb.Style(theme=self.theme_name)
        
        self.setup_ui()
        self.create_menu()
        self.refresh_drives()

    def t(self, key: str, **kwargs) -> str:
        """Liefert lokalisierten Text anhand der aktiven Sprache."""
        lang_map = I18N.get(self.language, I18N["de"])
        text = lang_map.get(key, I18N["de"].get(key, key))
        if kwargs:
            try:
                return text.format(**kwargs)
            except Exception:
                return text
        return text

    def create_menu(self) -> None:
        """Erzeugt die Menüleiste mit den wichtigsten Funktionen."""
        menu_bar = Menu(self.root)

        file_menu = Menu(menu_bar, tearoff=0)
        file_menu.add_command(label=self.t("menu_backup"), command=self.backup_selected_drive)
        file_menu.add_command(label=self.t("menu_restore"), command=self.restore_backup_to_drive)
        file_menu.add_separator()
        file_menu.add_command(label=self.t("menu_open_config"), command=self.open_config_file)
        file_menu.add_separator()
        file_menu.add_command(label=self.t("menu_exit"), command=self.root.destroy)
        menu_bar.add_cascade(label=self.t("menu_file"), menu=file_menu)

        test_menu = Menu(menu_bar, tearoff=0)
        test_menu.add_command(label=self.t("menu_test_start"), command=self.start_test)
        test_menu.add_command(label=self.t("menu_test_stop"), command=self.request_stop)
        test_menu.add_separator()
        test_menu.add_checkbutton(label=self.t("menu_speed"), variable=self.test_speed)
        test_menu.add_checkbutton(label=self.t("menu_integrity"), variable=self.test_integrity)
        test_menu.add_checkbutton(label=self.t("menu_capacity"), variable=self.test_capacity)
        test_menu.add_checkbutton(label=self.t("menu_full_capacity"), variable=self.full_capacity_test)
        menu_bar.add_cascade(label=self.t("menu_test"), menu=test_menu)

        tools_menu = Menu(menu_bar, tearoff=0)
        tools_menu.add_command(label=self.t("menu_refresh_drives"), command=self.refresh_drives)
        tools_menu.add_command(label=self.t("menu_refresh_map"), command=lambda: self.show_drive_overview(self.t("ui_drive_map")))
        tools_menu.add_separator()
        tools_menu.add_command(label=self.t("menu_reload_config"), command=self.reload_config)
        tools_menu.add_command(label=self.t("menu_reset_config"), command=self.reset_config_to_defaults)
        tools_menu.add_separator()
        tools_menu.add_command(label=self.t("menu_clear_results"), command=self.clear_results)
        tools_menu.add_command(label=self.t("menu_clear_log"), command=self.clear_progress_log)
        menu_bar.add_cascade(label=self.t("menu_tools"), menu=tools_menu)

        help_menu = Menu(menu_bar, tearoff=0)
        help_menu.add_command(label=self.t("menu_about"), command=self.show_about)
        menu_bar.add_cascade(label=self.t("menu_help"), menu=help_menu)

        language_menu = Menu(menu_bar, tearoff=0)
        language_entries = [
            ("de", self.t("lang_de")),
            ("en", self.t("lang_en")),
            ("fr", self.t("lang_fr")),
            ("es", self.t("lang_es")),
        ]
        for code, label in language_entries:
            if code in self.supported_languages and code in I18N:
                language_menu.add_radiobutton(
                    label=label,
                    value=code,
                    variable=self.language_var,
                    command=lambda c=code: self.change_language(c),
                )
        menu_bar.add_cascade(label=self.t("menu_language"), menu=language_menu)

        self.root.config(menu=menu_bar)

    def change_language(self, lang_code: str) -> None:
        """Wechselt die Sprache, speichert sie und baut die UI neu auf."""
        if lang_code == self.language:
            return
        if self.test_in_progress:
            messagebox.showwarning(self.t("msg_warning"), self.t("msg_running_operation"))
            self.language_var.set(self.language)
            return
        if lang_code not in I18N:
            self.language_var.set(self.language)
            return

        self.language = lang_code
        self.language_var.set(lang_code)
        self.config["language"] = lang_code
        self.save_config(self.config)
        self._rebuild_ui_for_language_change()

    def _rebuild_ui_for_language_change(self) -> None:
        """Erstellt sichtbare UI-Elemente mit der neuen Sprache neu."""
        selected_drive = self.selected_drive.get() if hasattr(self, "selected_drive") else ""
        selected_test_size = self.test_size.get() if hasattr(self, "test_size") else ""
        speed = self.test_speed.get() if hasattr(self, "test_speed") else True
        integrity = self.test_integrity.get() if hasattr(self, "test_integrity") else True
        capacity = self.test_capacity.get() if hasattr(self, "test_capacity") else True
        full_capacity = self.full_capacity_test.get() if hasattr(self, "full_capacity_test") else False

        for child in self.root.winfo_children():
            child.destroy()

        self.setup_ui()
        self.create_menu()
        self.refresh_drives()

        self.test_speed.set(speed)
        self.test_integrity.set(integrity)
        self.test_capacity.set(capacity)
        self.full_capacity_test.set(full_capacity)

        if selected_test_size and selected_test_size in self.test_size_values:
            self.test_size.set(selected_test_size)

        if selected_drive:
            for value in self.drive_combo["values"]:
                if str(value).startswith(f"{selected_drive} ("):
                    self.drive_combo.set(str(value))
                    self.selected_drive.set(str(value))
                    self.update_drive_info()
                    break

    def get_selected_drive_path(self) -> str:
        """Liefert den aktuell gewählten Laufwerkspfad oder leeren String."""
        selected = self.selected_drive.get().strip()
        if not selected:
            return ""
        return selected.split(" (")[0]

    def clear_results(self) -> None:
        """Leert das Ergebnisfenster."""
        self.results_text.config(state="normal")
        self.results_text.delete(1.0, END)
        self.results_text.config(state="disabled")

    def clear_progress_log(self) -> None:
        """Leert das Fortschrittslog."""
        self.progress_log.config(state="normal")
        self.progress_log.delete(1.0, END)
        self.progress_log.config(state="disabled")

    def open_config_file(self) -> None:
        """Öffnet die externe JSON-Konfiguration im Standardeditor."""
        if not os.path.exists(self.config_path):
            self.save_config(dict(DEFAULT_CONFIG))
        try:
            if os.name == "nt":
                os.startfile(self.config_path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f'open "{self.config_path}"')
            else:
                os.system(f'xdg-open "{self.config_path}"')
        except Exception as e:
            messagebox.showerror("Fehler", f"Konfigurationsdatei konnte nicht geöffnet werden:\n{e}")

    def reload_config(self) -> None:
        """Lädt die Konfiguration neu und übernimmt live-anwendbare Werte."""
        old_language = self.language
        self.config = self.load_config()
        self.root.title(str(self.config["window_title"]))
        self.BLOCK_SIZE_MB = int(self.config["block_size_mb"])
        self.language = str(self.config["language"])
        self.supported_languages = list(self.config["supported_languages"])
        self.language_var.set(self.language)
        self.test_size_values = list(self.config["test_size_options"])
        self.default_test_size = str(self.config["default_test_size"])
        self.test_size.configure(values=self.test_size_values)
        if self.test_size.get() not in self.test_size_values:
            self.test_size.set(self.default_test_size)
        self.verified_capacity_var.set(f"{self.t('ui_verified_written')}: -")
        if self.language != old_language:
            self._rebuild_ui_for_language_change()
        else:
            self.show_drive_overview(self.t("ui_drive_map"))
        messagebox.showinfo(
            self.t("msg_config_reloaded_title"),
            self.t("msg_config_reloaded"),
        )

    def reset_config_to_defaults(self) -> None:
        """Schreibt Standardwerte in die Konfigurationsdatei."""
        if not messagebox.askyesno(
            self.t("msg_confirm"),
            self.t("msg_reset_config"),
        ):
            return
        self.save_config(dict(DEFAULT_CONFIG))
        self.reload_config()

    def backup_selected_drive(self) -> None:
        """Sichert den Inhalt des ausgewählten Laufwerks in eine ZIP-Datei."""
        drive_path = self.get_selected_drive_path()
        if not drive_path:
            messagebox.showerror(self.t("msg_error"), self.t("msg_choose_drive"))
            return

        default_name = f"backup_{drive_path.replace(':', '').replace('\\\\', '')}_{time.strftime('%Y%m%d_%H%M%S')}.zip"
        last_dir = str(self.config.get("last_directory", ""))
        initial_save_dir = last_dir if last_dir and os.path.isdir(last_dir) else os.path.join(os.path.expanduser("~"), "Documents")
        if not os.path.isdir(initial_save_dir):
            initial_save_dir = runtime_dir()
        target_zip = filedialog.asksaveasfilename(
            title="Backup speichern unter",
            defaultextension=".zip",
            initialdir=initial_save_dir,
            initialfile=default_name,
            filetypes=[("ZIP-Archiv", "*.zip")],
        )
        if not target_zip:
            return

        chosen_dir = os.path.dirname(os.path.abspath(target_zip))
        if os.path.isdir(chosen_dir):
            self.config["last_directory"] = chosen_dir
            self.save_config(self.config)

        target_zip = target_zip.strip()
        if not target_zip.lower().endswith(".zip"):
            target_zip = target_zip + ".zip"

        # Vermeidet Abhängigkeit vom aktuellen Arbeitsverzeichnis, das evtl. nicht mehr existiert.
        if os.path.isabs(target_zip):
            target_zip_abs = os.path.normpath(target_zip)
        else:
            target_zip_abs = os.path.normpath(os.path.join(runtime_dir(), target_zip))

        target_parent = os.path.dirname(target_zip_abs)
        if target_parent and not os.path.exists(target_parent):
            try:
                os.makedirs(target_parent, exist_ok=True)
            except Exception as e:
                messagebox.showerror(self.t("msg_error"), f"Backup-Zielordner konnte nicht erstellt werden:\n{e}")
                return

        self.add_result(f"🗄️ Starte Backup von {drive_path} nach {target_zip_abs}")
        try:
            total_items, total_bytes = self._scan_backup_content(drive_path)
            self.add_result(
                f"   Zu sichern: {total_items} Einträge, {self.format_size(total_bytes)}"
            )

            saved = 0
            skipped = 0
            saved_bytes = 0

            drive_total = psutil.disk_usage(drive_path).total
            with zipfile.ZipFile(target_zip_abs, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
                meta = json.dumps({"drive_total": drive_total, "drive_path": drive_path})
                zf.writestr("_backup_meta.json", meta)
                for root_dir, dirs, files in os.walk(drive_path):
                    rel_root = os.path.relpath(root_dir, drive_path)

                    # Leere Verzeichnisse als eigene ZIP-Einträge sichern.
                    if rel_root != "." and not dirs and not files:
                        zf.writestr(rel_root.replace("\\", "/") + "/", "")
                        saved += 1
                        self._update_backup_progress(saved, total_items)
                        continue

                    for name in files:
                        full_path = os.path.join(root_dir, name)
                        if os.path.abspath(full_path) == target_zip_abs:
                            # Falls das Backup auf demselben Laufwerk liegt, darf es nicht mitgesichert werden.
                            continue
                        rel_path = os.path.relpath(full_path, drive_path)
                        arcname = rel_path.replace("\\", "/")

                        try:
                            file_size = os.path.getsize(full_path)
                            zf.write(full_path, arcname=arcname)
                            saved += 1
                            saved_bytes += file_size
                        except Exception:
                            skipped += 1
                        self._update_backup_progress(saved + skipped, total_items)

            self.add_result(
                f"✅ Backup erfolgreich erstellt ({saved} gesichert, {skipped} übersprungen, {self.format_size(saved_bytes)})"
            )
            messagebox.showinfo(
                "Backup",
                f"Backup erfolgreich erstellt.\nGesichert: {saved}\nÜbersprungen: {skipped}",
            )
        except Exception as e:
            self.add_result(f"❌ Backup fehlgeschlagen: {e}")
            messagebox.showerror("Backup-Fehler", str(e))

    def restore_backup_to_drive(self) -> None:
        """Stellt ein ZIP-Backup auf dem ausgewählten Laufwerk wieder her."""
        drive_path = self.get_selected_drive_path()
        if not drive_path:
            messagebox.showerror(self.t("msg_error"), self.t("msg_choose_drive"))
            return

        last_dir = str(self.config.get("last_directory", ""))
        initial_open_dir = last_dir if last_dir and os.path.isdir(last_dir) else os.path.join(os.path.expanduser("~"), "Documents")
        source_zip = filedialog.askopenfilename(
            title="Backup auswählen",
            initialdir=initial_open_dir,
            filetypes=[("ZIP-Archiv", "*.zip")],
        )
        if not source_zip:
            return

        chosen_dir = os.path.dirname(os.path.abspath(source_zip))
        if os.path.isdir(chosen_dir):
            self.config["last_directory"] = chosen_dir
            self.save_config(self.config)

        if not messagebox.askyesno(
            "Wiederherstellen",
            "Backup auf dem Laufwerk wiederherstellen?\n"
            "Bestehende Dateien werden überschrieben.",
        ):
            return

        # --- Laufwerksgrößen-Prüfung ---
        try:
            with zipfile.ZipFile(source_zip, "r") as zf_check:
                if "_backup_meta.json" in zf_check.namelist():
                    meta = json.loads(zf_check.read("_backup_meta.json").decode("utf-8"))
                    backup_total = meta.get("drive_total", 0)
                    target_total = psutil.disk_usage(drive_path).total
                    if backup_total > 0:
                        ratio = abs(target_total - backup_total) / backup_total
                        if ratio > 0.10:
                            proceed = messagebox.askyesno(
                                "Laufwerksgröße weicht ab",
                                f"Das Backup wurde von einem Laufwerk mit {self.format_size(backup_total)} erstellt.\n"
                                f"Das Ziel-Laufwerk hat {self.format_size(target_total)}.\n\n"
                                "Die Größen weichen um mehr als 10\u202F% ab.\n"
                                "Trotzdem fortfahren?",
                            )
                            if not proceed:
                                return
        except Exception:
            pass  # Ältere Backups ohne Metadaten – kein Fehler

        self.add_result(f"📥 Starte Restore von {source_zip} nach {drive_path}")
        try:
            with zipfile.ZipFile(source_zip, "r") as zf:
                members = zf.infolist()
                if not members:
                    raise RuntimeError("ZIP-Archiv ist leer")

                restored = 0
                skipped = 0
                for idx, member in enumerate(members, start=1):
                    if member.filename == "_backup_meta.json":
                        continue
                    try:
                        self._safe_extract_member(zf, member, drive_path)
                        restored += 1
                    except Exception:
                        skipped += 1

                    progress = int((idx / len(members)) * 100)
                    self.update_progress(progress, f"Restore {idx}/{len(members)}")

            self.add_result(
                f"✅ Restore erfolgreich abgeschlossen ({restored} wiederhergestellt, {skipped} übersprungen)"
            )
            messagebox.showinfo(
                "Restore",
                f"Backup wurde wiederhergestellt.\nWiederhergestellt: {restored}\nÜbersprungen: {skipped}",
            )
            self.refresh_drives()
        except Exception as e:
            self.add_result(f"❌ Restore fehlgeschlagen: {e}")
            messagebox.showerror("Restore-Fehler", str(e))

    def _scan_backup_content(self, drive_path: str) -> tuple[int, int]:
        """Ermittelt Anzahl und Gesamtgröße der sicherbaren Einträge."""
        total_items = 0
        total_bytes = 0
        for root_dir, dirs, files in os.walk(drive_path):
            if os.path.relpath(root_dir, drive_path) != "." and not dirs and not files:
                total_items += 1
            for name in files:
                full_path = os.path.join(root_dir, name)
                try:
                    total_bytes += os.path.getsize(full_path)
                    total_items += 1
                except Exception:
                    pass
        return total_items, total_bytes

    def _update_backup_progress(self, current: int, total: int) -> None:
        """Aktualisiert den Fortschritt während des Backups."""
        if total <= 0:
            self.update_progress(0, "Backup wird vorbereitet...")
            return
        pct = int((current / total) * 100)
        self.update_progress(pct, f"Backup {current}/{total}")

    def _clear_drive_contents(self, drive_path: str) -> None:
        """Löscht alle Inhalte eines Laufwerks vor der Wiederherstellung."""
        for item in os.listdir(drive_path):
            full = os.path.join(drive_path, item)
            try:
                if os.path.isdir(full) and not os.path.islink(full):
                    for root_dir, dirs, files in os.walk(full, topdown=False):
                        for fname in files:
                            os.remove(os.path.join(root_dir, fname))
                        for dname in dirs:
                            os.rmdir(os.path.join(root_dir, dname))
                    os.rmdir(full)
                else:
                    os.remove(full)
            except Exception:
                # Einzelne geschützte Systemdateien können auf Wechseldatenträgern nicht löschbar sein.
                continue

    def _safe_extract_member(self, zf: zipfile.ZipFile, member: zipfile.ZipInfo, target_dir: str) -> None:
        """Extrahiert ZIP-Eintrag sicher in das Zielverzeichnis (ohne Path Traversal)."""
        normalized_name = member.filename.replace("\\", "/")
        if normalized_name.startswith("/") or ".." in normalized_name.split("/"):
            raise ValueError(f"Unsicherer ZIP-Pfad: {member.filename}")

        destination = os.path.abspath(os.path.join(target_dir, normalized_name))
        target_base = os.path.abspath(target_dir)
        try:
            if os.path.commonpath([target_base, destination]) != target_base:
                raise ValueError(f"ZIP-Eintrag außerhalb Zielpfad: {member.filename}")
        except ValueError:
            raise ValueError(f"ZIP-Eintrag außerhalb Zielpfad: {member.filename}")

        if member.is_dir() or normalized_name.endswith("/"):
            os.makedirs(destination, exist_ok=True)
            return

        os.makedirs(os.path.dirname(destination), exist_ok=True)
        with zf.open(member, "r") as src, open(destination, "wb") as dst:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                dst.write(chunk)

    def show_about(self) -> None:
        """Zeigt eine kurze Programminfo an."""
        app_title = self.t("ui_title")
        about_title = self.t("about_title", app_title=app_title)
        about_text = self.t("about_text", app_title=app_title, config_path=self.config_path)

        about_win = Toplevel(self.root)
        about_win.title(about_title)
        about_win.transient(self.root)
        about_win.resizable(False, False)

        container = tb.Frame(about_win, padding=14)
        container.pack(fill=BOTH, expand=YES)

        title_candidates = [
            "titel.png",
            "ExternalDriveTesterTR.png",
            "ExternalDriveTester1.png",
        ]
        for candidate in title_candidates:
            title_file = resource_path(candidate)
            if not os.path.exists(title_file):
                continue
            try:
                about_win._title_img = PhotoImage(file=title_file)  # type: ignore[attr-defined]
                tb.Label(container, image=about_win._title_img).pack(anchor=W, pady=(0, 10))  # type: ignore[attr-defined]
                break
            except Exception:
                continue

        tb.Label(
            container,
            text=about_text,
            justify=LEFT,
            anchor=W,
            wraplength=640,
        ).pack(fill=BOTH, expand=YES)

        tb.Button(
            container,
            text=self.t("about_close"),
            command=about_win.destroy,
            bootstyle="secondary",
            width=14,
        ).pack(anchor=E, pady=(12, 0))

        about_win.grab_set()
        about_win.focus_set()

    def load_config(self) -> dict:
        """Lädt Konfiguration aus JSON und fällt bei Fehlern auf Defaults zurück."""
        config = dict(DEFAULT_CONFIG)

        if not os.path.exists(self.config_path):
            self.save_config(config)
            return config

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
        except Exception:
            self.save_config(config)
            return config

        if not isinstance(loaded, dict):
            self.save_config(config)
            return config

        if isinstance(loaded.get("window_title"), str) and loaded["window_title"].strip():
            config["window_title"] = loaded["window_title"].strip()

        for key in ("window_width", "window_height", "block_size_mb"):
            value = loaded.get(key)
            if isinstance(value, (int, float)):
                config[key] = max(1, int(value))

        if isinstance(loaded.get("theme"), str) and loaded["theme"].strip():
            config["theme"] = loaded["theme"].strip()

        supported_languages = loaded.get("supported_languages")
        if isinstance(supported_languages, list):
            normalized_langs = [str(v).strip().lower() for v in supported_languages if str(v).strip()]
            valid_langs = [v for v in normalized_langs if v in I18N]
            if valid_langs:
                config["supported_languages"] = valid_langs

        language = loaded.get("language")
        if isinstance(language, str) and language.strip().lower() in I18N:
            config["language"] = language.strip().lower()

        if config["language"] not in config["supported_languages"]:
            config["language"] = config["supported_languages"][0]

        options = loaded.get("test_size_options")
        if isinstance(options, list):
            normalized = [str(v).strip() for v in options if str(v).strip()]
            if normalized:
                config["test_size_options"] = normalized

        default_size = loaded.get("default_test_size")
        if isinstance(default_size, str) and default_size.strip():
            config["default_test_size"] = default_size.strip()

        if config["default_test_size"] not in config["test_size_options"]:
            config["default_test_size"] = config["test_size_options"][0]

        if isinstance(loaded.get("last_drive"), str):
            config["last_drive"] = loaded["last_drive"].strip()

        if isinstance(loaded.get("last_directory"), str):
            config["last_directory"] = loaded["last_directory"].strip()

        return config

    def save_config(self, config: dict) -> None:
        """Schreibt die Konfiguration als editierbare JSON-Datei."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def set_window_icon(self):
        """Setzt das Fenstersymbol fuer Titlebar und Taskleiste."""
        ico_file = resource_path("icon.ico")
        png_file = resource_path("window.png")

        # Auf Windows ist iconbitmap mit .ico am zuverlaessigsten fuer die Titelleiste.
        if os.name == "nt" and os.path.exists(ico_file):
            try:
                self.root.iconbitmap(default=ico_file)
                return
            except Exception:
                pass

        # Fallback: PNG fuer Umgebungen, die iconphoto unterstuetzen.
        if os.path.exists(png_file):
            try:
                self.window_icon_img = PhotoImage(file=png_file)
                self.root.iconphoto(True, self.window_icon_img)
            except Exception:
                self.window_icon_img = None
    
    def setup_ui(self):
        # Hauptcontainer
        main_frame = tb.Frame(self.root, padding=20)
        main_frame.pack(fill=BOTH, expand=YES)
        
        # Headerbild statt Texttitel (mit robuster Dateisuche)
        title_candidates = [
            "titel.png",
            "ExternalDriveTesterTR.png",
            "ExternalDriveTester1.png",
        ]
        loaded_title = False
        for candidate in title_candidates:
            title_file = resource_path(candidate)
            if not os.path.exists(title_file):
                continue
            try:
                self.title_img = PhotoImage(file=title_file)
                tb.Label(main_frame, image=self.title_img).pack(pady=(0, 20))
                loaded_title = True
                break
            except Exception:
                continue

        if not loaded_title:
            tb.Label(main_frame, text=self.t("ui_title"), font=("Helvetica", 18, "bold")).pack(pady=(0, 20))
        
        # Drive Selection Frame
        drive_frame = ttk.LabelFrame(main_frame, text=self.t("ui_drive_select"), padding=15)
        drive_frame.pack(fill=X, pady=(0, 15))
        
        # Zeile 1: Laufwerk + Aktualisieren
        drive_top_row = tb.Frame(drive_frame)
        drive_top_row.pack(fill=X)

        self.drive_combo = tb.Combobox(drive_top_row, textvariable=self.selected_drive,
                           state="readonly", width=50)
        self.drive_combo.pack(side=LEFT, padx=(0, 10))
        # FIX 1: Laufwerkswechsel bindet Infoanzeige
        self.drive_combo.bind("<<ComboboxSelected>>", self.update_drive_info)

        refresh_btn = tb.Button(drive_top_row, text=self.t("ui_refresh"),
                       command=self.refresh_drives, bootstyle="info")
        refresh_btn.pack(side=LEFT)

        # Zeile 2: Laufwerksinfos direkt unter der Aktualisieren-Zeile
        self.info_text = tb.Text(drive_frame, height=4, width=60, state="disabled")
        self.info_text.pack(fill=X, pady=(10, 0))
        
        # Test Options Frame
        test_frame = ttk.LabelFrame(main_frame, text=self.t("ui_test_options"), padding=15)
        test_frame.pack(fill=X, pady=(0, 15))
        
        # Test size
        size_frame = tb.Frame(test_frame)
        size_frame.pack(fill=X, pady=(0, 10))
        
        tb.Label(size_frame, text=self.t("ui_test_size")).pack(side=LEFT, padx=(0, 10))
        self.test_size = tb.Combobox(size_frame, values=self.test_size_values,
                                     state="readonly", width=15)
        self.test_size.set(self.default_test_size)
        self.test_size.pack(side=LEFT)
        
        # Test types
        checks_frame = tb.Frame(test_frame)
        checks_frame.pack(fill=X, pady=(0, 10))
        
        self.test_speed = tb.BooleanVar(value=True)
        self.test_integrity = tb.BooleanVar(value=True)
        self.test_capacity = tb.BooleanVar(value=True)
        self.full_capacity_test = tb.BooleanVar(value=False)
        
        tb.Checkbutton(checks_frame, text=self.t("menu_speed"), variable=self.test_speed,
                      bootstyle="info").pack(side=LEFT, padx=(0, 15))
        tb.Checkbutton(checks_frame, text=self.t("menu_integrity"), variable=self.test_integrity,
                      bootstyle="info").pack(side=LEFT, padx=(0, 15))
        tb.Checkbutton(checks_frame, text=self.t("menu_capacity"), variable=self.test_capacity,
                      bootstyle="info").pack(side=LEFT)

        tb.Checkbutton(
            test_frame,
            text=self.t("ui_full_capacity"),
            variable=self.full_capacity_test,
            bootstyle="warning",
        ).pack(anchor=W, pady=(0, 10))
        
        # Start Button
        button_row = tb.Frame(test_frame)
        button_row.pack(pady=(10, 0), fill=X)

        self.start_btn = tb.Button(button_row, text=self.t("ui_start"),
                      command=self.start_test, bootstyle="success",
                      width=20)
        self.start_btn.pack(side=LEFT)

        self.stop_btn = tb.Button(button_row, text=self.t("ui_stop"),
                      command=self.request_stop, bootstyle="danger",
                      width=20, state="disabled")
        self.stop_btn.pack(side=LEFT, padx=(10, 0))
        
        # Progress Frame
        progress_frame = ttk.LabelFrame(main_frame, text=self.t("ui_progress"), padding=15)
        progress_frame.pack(fill=BOTH, expand=YES, pady=(0, 15))
        
        # Progress bar
        self.progress = tb.Progressbar(progress_frame, bootstyle="info",
                                       length=400, mode="determinate")
        self.progress.pack(fill=X, pady=(0, 10))
        
        # Status label
        self.status_label = tb.Label(progress_frame, text=self.t("ui_ready"), font=("", 10))
        self.status_label.pack()

        # Dauerhafte Anzeige der verifizierten Nutzkapazität
        self.verified_capacity_label = tb.Label(
            progress_frame,
            textvariable=self.verified_capacity_var,
            font=("Consolas", 10, "bold"),
            bootstyle="info",
        )
        self.verified_capacity_label.pack(anchor=W, pady=(4, 0))

        # Block Map – Phasenbeschriftung
        self.block_phase_label = tb.Label(progress_frame, text=self.t("ui_drive_map"), font=("Consolas", 8))
        self.block_phase_label.pack(anchor=W, pady=(8, 2))

        # Block Map – Canvas mit Scrollbar
        canvas_frame = tb.Frame(progress_frame)
        canvas_frame.pack(fill=BOTH, expand=YES, pady=(0, 4))
        
        self.block_canvas = Canvas(canvas_frame, bg="#1e1e2e",
                                   highlightthickness=1, highlightbackground="#555555")
        scrollbar = tb.Scrollbar(canvas_frame, command=self.block_canvas.yview)
        self.block_canvas.config(yscrollcommand=scrollbar.set)
        
        self.block_canvas.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.block_canvas.bind("<Configure>", lambda _e: self.show_drive_overview(self.t("ui_drive_map")))

        # Legende
        legend_frame = tb.Frame(progress_frame)
        legend_frame.pack(anchor=W, pady=(0, 6))
        
        # Progress log mit Scrollbar
        log_frame = tb.Frame(progress_frame)
        log_frame.pack(fill=BOTH, expand=YES, pady=(8, 0))
        
        self.progress_log = tb.Text(log_frame, height=6, wrap="word",
                                    state="disabled", font=("Consolas", 8))
        scrollbar = tb.Scrollbar(log_frame, command=self.progress_log.yview)
        self.progress_log.config(yscrollcommand=scrollbar.set)
        
        self.progress_log.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar.pack(side=RIGHT, fill=Y)
        legend_items = [
            ("#6c757d", self.t("legend_used")),
            ("#2a2a2a", self.t("legend_free")),
            ("#3498db", self.t("legend_writing")),
            ("#9b59b6", self.t("legend_reading")),
            ("#2ecc71", self.t("legend_good")),
            ("#f39c12", self.t("legend_slow")),
            ("#e74c3c", self.t("legend_error")),
        ]
        for _col, _lbl in legend_items:
            _f = tb.Frame(legend_frame)
            _f.pack(side=LEFT, padx=(0, 10))
            swatch = Canvas(
                _f,
                width=14,
                height=14,
                bg="#1e1e2e",
                highlightthickness=1,
                highlightbackground="#7a7a7a",
                bd=0,
            )
            swatch.create_rectangle(2, 2, 12, 12, fill=_col, outline=_col)
            swatch.pack(side=LEFT, padx=(0, 4))
            tb.Label(_f, text=_lbl, font=("", 7)).pack(side=LEFT)

        # Results Frame (scrollable)
        results_frame = ttk.LabelFrame(main_frame, text=self.t("ui_results"), padding=15)
        results_frame.pack(fill=BOTH, expand=YES)
        
        self.results_text = tb.Text(results_frame, height=12, wrap="word",
                                   state="disabled", font=("Consolas", 9))
        scrollbar = tb.Scrollbar(results_frame, command=self.results_text.yview)
        self.results_text.configure(yscrollcommand=scrollbar.set)
        
        self.results_text.pack(side=LEFT, fill=BOTH, expand=YES)
        scrollbar.pack(side=RIGHT, fill=Y)
    
    def refresh_drives(self):
        """Erkenne alle Wechseldatenträger"""
        drives = []
        for partition in psutil.disk_partitions():
            # FIX 2: Auf Windows werden USB-Sticks nicht immer als 'removable' markiert
            is_removable = 'removable' in partition.opts or 'cdrom' in partition.opts
            is_windows_external = (
                os.name == 'nt'
                and partition.fstype
                and partition.mountpoint.upper() != 'C:\\'
                and partition.mountpoint.upper() != os.environ.get('SystemDrive', 'C:').upper() + '\\'
            )
            if is_removable or is_windows_external:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    drives.append({
                        'path': partition.mountpoint,
                        'total': usage.total,
                        'free': usage.free,
                        'device': partition.device
                    })
                except:
                    pass
        
        drive_paths = [f"{d['path']} ({self.format_size(d['total'])})" for d in drives]
        self.drive_combo['values'] = drive_paths
        
        if drive_paths:
            last = str(self.config.get("last_drive", "")).rstrip("\\").rstrip("/")
            matched = next((v for v in drive_paths if v.split(" (")[0].rstrip("\\").rstrip("/") == last), None) if last else None
            selected = matched or drive_paths[0]
            self.selected_drive.set(selected)
            self.drive_combo.set(selected)
            drive_path = selected.split(" (")[0]
            self.config["last_drive"] = drive_path
            self.save_config(self.config)
            self.update_drive_info()
        else:
            self.show_drive_overview(self.t("status_no_drive"))
    
    def update_drive_info(self, event=None):
        """Zeige Informationen zum ausgewählten Laufwerk"""
        if not self.selected_drive.get():
            return
        
        drive_path = self.selected_drive.get().split(" (")[0]
        if event is not None:
            self.config["last_drive"] = drive_path
            self.save_config(self.config)
        
        try:
            usage = psutil.disk_usage(drive_path)
            info = f"""
{self.t("ui_drive_info_title")}
    {self.t("ui_drive_info_path")}: {drive_path}
    {self.t("ui_drive_info_total")}: {self.format_size(usage.total)}
    {self.t("ui_drive_info_used")}: {self.format_size(usage.used)}
    {self.t("ui_drive_info_free")}: {self.format_size(usage.free)}
    {self.t("ui_drive_info_usage")}: {usage.percent}%
            """
            self.info_text.config(state="normal")
            self.info_text.delete(1.0, END)
            self.info_text.insert(1.0, info)
            self.info_text.config(state="disabled")
            self.show_drive_overview(self.t("ui_drive_map"))
        except:
            pass
    
    def format_size(self, bytes):
        """Formatiere Bytes in lesbare Größe"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes < 1024.0:
                return f"{bytes:.2f} {unit}"
            bytes /= 1024.0
        return f"{bytes:.2f} PB"
    
    def add_result(self, text):
        """Füge Ergebnis zum Textfeld hinzu"""
        self.results_text.config(state="normal")
        self.results_text.insert(END, f"{text}\n")
        self.results_text.see(END)
        self.results_text.config(state="disabled")

    # ------------------------------------------------------------------
    # Block-Karte
    # ------------------------------------------------------------------

    def show_drive_overview(self, phase_label: str = "") -> None:
        """Zeigt ein fixes Laufwerks-Abbild (belegt/frei) an."""
        if not phase_label:
            phase_label = self.t("ui_drive_map")
        self.root.after(0, lambda: self._draw_block_map(phase_label))

    def init_block_map(self, n_blocks: int, phase_label: str = "") -> None:
        """Initialisiert die Testzuordnung und zeichnet das Laufwerks-Abbild neu."""
        import threading as _threading
        self.block_count = n_blocks
        self._display_block_count = 0
        self.block_cells = []
        self.block_base_colors = []
        event = _threading.Event()
        self.root.after(0, lambda: [self._draw_block_map(phase_label), event.set()])
        event.wait(timeout=3.0)

    def _draw_block_map(self, phase_label: str) -> None:
        """Zeichnet das Laufwerks-Abbild neu (nur im Hauptthread)."""
        self.block_canvas.delete("all")
        self.block_cells = []
        self.block_base_colors = []
        self.block_phase_label.config(text=phase_label)

        canvas_width = self.block_canvas.winfo_width()
        if canvas_width < 10:
            canvas_width = 840

        drive_path = self.selected_drive.get().split(" (")[0] if self.selected_drive.get() else ""
        used_ratio = 0.0
        if drive_path:
            try:
                usage = psutil.disk_usage(drive_path)
                if usage.total > 0:
                    used_ratio = usage.used / usage.total
            except Exception:
                used_ratio = 0.0

        CELL = 10
        cols = max(1, canvas_width // CELL)
        
        # Blockanzahl basierend auf Datenträgergröße
        if drive_path:
            try:
                usage = psutil.disk_usage(drive_path)
                total_gb = usage.total / (1024 ** 3)
                display = max(100, int(total_gb * 1024 / self.BLOCK_SIZE_MB))
            except Exception:
                display = 100
        else:
            display = 100
        
        rows = (display + cols - 1) // cols

        # Berechne Höhe und setze Scroll-Region
        content_height = rows * CELL + 6
        max_visible_height = 150  # Maximale sichtbare Höhe
        self.block_canvas.configure(height=min(content_height, max_visible_height))
        self.block_canvas.config(scrollregion=self.block_canvas.bbox("all") or (0, 0, canvas_width, content_height))
        
        used_cells = int(display * used_ratio)

        for i in range(display):
            c = i % cols
            r = i // cols
            base_color = "#6c757d" if i < used_cells else "#2a2a2a"
            rect = self.block_canvas.create_rectangle(
                c * CELL + 2,  r * CELL + 3,
                c * CELL + 13, r * CELL + 14,
                fill=base_color, outline=""
            )
            self.block_cells.append(rect)
            self.block_base_colors.append(base_color)

        # Setze Scroll-Region nach dem Zeichnen
        self.block_canvas.config(scrollregion=self.block_canvas.bbox("all"))
        self._display_block_count = display

    def color_block(self, block_idx: int, state: str) -> None:
        """Färbt einen Block ein (thread-safe via root.after)."""
        COLORS = {
            "writing": "#3498db",
            "reading": "#9b59b6",
            "good":    "#2ecc71",
            "slow":    "#f39c12",
            "error":   "#e74c3c",
            "untested":"#3d3d3d",
        }
        if self.block_count <= 0 or self._display_block_count <= 0:
            return
        display_idx = int((block_idx + 1) / self.block_count * self._display_block_count) - 1
        display_idx = min(display_idx, self._display_block_count - 1)
        display_idx = max(display_idx, 0)
        color = COLORS.get(state, "#3d3d3d")
        if 0 <= display_idx < len(self.block_cells):
            cell = self.block_cells[display_idx]
            self.root.after(0, lambda c=cell, col=color:
                            self.block_canvas.itemconfig(c, fill=col))

    def request_stop(self):
        """Fordert einen sicheren Abbruch des laufenden Tests an."""
        if self.test_in_progress:
            self.stop_requested = True
            self.root.after(0, lambda: self.status_label.configure(text=self.t("status_abort_requested")))

    def check_abort(self):
        """Wirft eine Ausnahme, wenn der Nutzer den Abbruch angefordert hat."""
        if self.stop_requested:
            raise InterruptedError("Test wurde durch den Nutzer abgebrochen")

    def make_test_chunk(self, block_index: int, chunk_size: int = 1024 * 1024) -> bytes:
        """Erzeugt deterministische Testdaten für reproduzierbare Verifikation."""
        seed = block_index.to_bytes(8, "little")
        pattern = seed + bytes([block_index % 251]) * 32
        repeats = (chunk_size // len(pattern)) + 1
        return (pattern * repeats)[:chunk_size]

    def set_verified_capacity(self, bytes_value: int) -> None:
        """Aktualisiert die sichtbare Anzeige der verifizierten Kapazität."""
        self.root.after(
            0,
            lambda: self.verified_capacity_var.set(
                f"{self.t('ui_verified_written')}: {self.format_size(bytes_value)}"
            ),
        )

    def start_test(self):
        """Starte den Test in einem separaten Thread"""
        if self.test_in_progress:
            messagebox.showwarning(self.t("msg_warning"), self.t("msg_running_operation"))
            return
        
        if not self.selected_drive.get():
            messagebox.showerror(self.t("msg_error"), self.t("msg_choose_drive"))
            return
        
        self.test_in_progress = True
        self.stop_requested = False
        self.set_verified_capacity(0)
        self.start_btn.config(state="disabled", text=self.t("status_test_running"))
        self.stop_btn.config(state="normal")
        self.results_text.config(state="normal")
        self.results_text.delete(1.0, END)
        self.results_text.config(state="disabled")
        self.progress['value'] = 0
        
        self.test_thread = threading.Thread(target=self.run_tests, daemon=True)
        self.test_thread.start()
    
    def run_tests(self):
        """Führe die ausgewählten Tests durch"""
        drive_path = self.selected_drive.get().split(" (")[0]
        
        self.add_result("=" * 60)
        self.add_result(f"🚀 Starte Test auf Laufwerk: {drive_path}")
        self.add_result("=" * 60)
        
        try:
            # Kapazitätstest
            if self.test_capacity.get():
                self.test_drive_capacity(drive_path)

            # Geschwindigkeitstest
            if self.test_speed.get():
                self.test_speed_performance(drive_path)

            # Integritätstest
            if self.test_integrity.get():
                self.test_data_integrity(drive_path)

            self.add_result("\n" + "=" * 60)
            self.add_result("✅ Test abgeschlossen!")
            self.add_result("=" * 60)
        except InterruptedError:
            self.add_result("\n⚠️ Test abgebrochen.")
        except Exception as e:
            self.add_result(f"\n❌ Unerwarteter Fehler: {e}")
        
        # UI zurücksetzen
        self.root.after(0, self.test_finished)
    
    def test_drive_capacity(self, drive_path):
        """Teste die tatsächliche Kapazität (erkennt gefälschte USB-Sticks)"""
        self.add_result("\n📦 Kapazitätstest...")

        usage = psutil.disk_usage(drive_path)
        free_mb = max(1, usage.free // (1024 * 1024))
        full_mode = self.full_capacity_test.get()
        test_size_mb = free_mb if full_mode else self.get_test_size_mb()
        test_size_mb = min(test_size_mb, free_mb)

        if full_mode:
            self.add_result("   Modus: Vollständiger Test bis Datenträger voll")
            self.add_result(f"   Frei vor Test: {self.format_size(usage.free)}")
        else:
            self.add_result(f"   Modus: Stichprobe ({test_size_mb} MB)")

        test_file = os.path.join(drive_path, "capacity_test.dat")
        self.init_block_map(test_size_mb, "📦 Kapazitätstest – Schreiben")

        written_blocks = 0
        verified_blocks = 0

        try:
            # Schreibe Testdatei
            self.update_progress(10, "Schreibe Testdaten...")
            with open(test_file, 'wb') as f:
                i = 0
                while i < test_size_mb:
                    self.check_abort()
                    chunk = self.make_test_chunk(i)
                    self.color_block(i, "writing")
                    f.write(chunk)
                    self.color_block(i, "good")
                    written_blocks += 1

                    if i % 10 == 0:
                        progress = 10 + (i / max(1, test_size_mb)) * 40
                        self.update_progress(progress, f"Schreibe Block {i+1}/{test_size_mb}")
                    i += 1

            # Verifiziere Testdatei
            self.init_block_map(max(1, written_blocks), "📦 Kapazitätstest – Verifikation")
            self.update_progress(55, "Verifiziere Testdaten...")
            with open(test_file, 'rb') as f:
                for i in range(written_blocks):
                    self.check_abort()
                    self.color_block(i, "reading")
                    expected = self.make_test_chunk(i)
                    got = f.read(1024 * 1024)
                    if got == expected:
                        verified_blocks += 1
                        self.color_block(i, "good")
                    else:
                        self.color_block(i, "error")

                    if i % 10 == 0:
                        progress = 55 + (i / max(1, written_blocks)) * 35
                        self.update_progress(progress, f"Verifiziere Block {i+1}/{written_blocks}")
            
            # Überprüfe Dateigröße
            actual_size = os.path.getsize(test_file)
            expected_size = written_blocks * 1024 * 1024
            
            self.add_result(f"   Erwartete Größe: {self.format_size(expected_size)}")
            self.add_result(f"   Tatsächliche Größe: {self.format_size(actual_size)}")
            self.add_result(f"   Verifiziert geschrieben: {self.format_size(verified_blocks * 1024 * 1024)}")
            self.set_verified_capacity(verified_blocks * 1024 * 1024)
            
            if verified_blocks == written_blocks and actual_size >= expected_size:
                self.add_result("   ✅ Kapazitätstest bestanden")
            elif verified_blocks > 0:
                self.add_result("   ⚠️ Teilweise verifiziert: mögliche Kapazitätsmanipulation")
            else:
                self.add_result("   ❌ Keine verifizierbare Schreibkapazität festgestellt")
            
            self.update_progress(50, "Kapazitätstest abgeschlossen")
        except OSError as e:
            # Typischer Endzustand im Vollmodus: Datenträger voll
            no_space = (getattr(e, "errno", None) == 28) or (getattr(e, "winerror", None) == 112)
            if full_mode and no_space:
                self.add_result("   ℹ️ Datenträger ist vollgelaufen. Starte Verifikation der geschriebenen Daten...")
                try:
                    self.init_block_map(max(1, written_blocks), "📦 Kapazitätstest – Verifikation")
                    with open(test_file, 'rb') as f:
                        for i in range(written_blocks):
                            self.check_abort()
                            self.color_block(i, "reading")
                            expected = self.make_test_chunk(i)
                            got = f.read(1024 * 1024)
                            if got == expected:
                                verified_blocks += 1
                                self.color_block(i, "good")
                            else:
                                self.color_block(i, "error")

                    self.add_result(f"   Verifiziert geschrieben: {self.format_size(verified_blocks * 1024 * 1024)}")
                    self.set_verified_capacity(verified_blocks * 1024 * 1024)
                    if verified_blocks < written_blocks:
                        self.add_result("   ⚠️ Warnung: Nicht alle geschriebenen Blöcke sind verifizierbar")
                    else:
                        self.add_result("   ✅ Vollständiger Kapazitätstest verifiziert")
                except Exception as verify_err:
                    self.add_result(f"   ❌ Verifikation fehlgeschlagen: {verify_err}")
                    self.set_verified_capacity(verified_blocks * 1024 * 1024)
            else:
                self.add_result(f"   ❌ Fehler beim Kapazitätstest: {str(e)}")
                self.set_verified_capacity(verified_blocks * 1024 * 1024)
        except Exception as e:
            self.add_result(f"   ❌ Fehler beim Kapazitätstest: {str(e)}")
            self.set_verified_capacity(verified_blocks * 1024 * 1024)
        finally:
            try:
                if os.path.exists(test_file):
                    os.remove(test_file)
            except Exception:
                pass
    
    def test_speed_performance(self, drive_path):
        """Teste Lese- und Schreibgeschwindigkeit"""
        self.add_result("\n⚡ Geschwindigkeitstest...")
        
        test_size_mb = self.get_test_size_mb()
        test_file = os.path.join(drive_path, "speed_test.dat")
        
        # Schreibtests
        self.add_result("\n   📝 Schreibtests:")
        
        # Sequenzieller Schreibtest (1MB Blöcke)
        self.init_block_map(test_size_mb, "⚡ Seq. Schreiben (1 MB-Blöcke)")
        write_speed_seq = self.test_write_speed(test_file, test_size_mb, 1024*1024,
                                                color_cb=lambda i, s: self.color_block(i, s))
        self.add_result(f"   • Sequenziell (1MB Blöcke): {write_speed_seq:.2f} MB/s")
        
        # Zufälliger Schreibtest (4KB Blöcke)
        self.init_block_map(test_size_mb, "⚡ Rnd. Schreiben (4 KB-Blöcke)")
        write_speed_rand = self.test_write_speed(test_file, test_size_mb, 4*1024,
                                                  color_cb=lambda i, s: self.color_block(i, s))
        self.add_result(f"   • Zufällig (4KB Blöcke): {write_speed_rand:.2f} MB/s")
        
        # Lesetests
        self.add_result("\n   📖 Lesetests:")
        
        # Sequenzieller Lesetest
        self.init_block_map(test_size_mb, "⚡ Seq. Lesen (1 MB-Blöcke)")
        read_speed_seq = self.test_read_speed(test_file, 1024*1024,
                                               color_cb=lambda i, s: self.color_block(i, s))
        self.add_result(f"   • Sequenziell (1MB Blöcke): {read_speed_seq:.2f} MB/s")
        
        # Zufälliger Lesetest
        self.init_block_map(test_size_mb, "⚡ Rnd. Lesen (4 KB-Blöcke)")
        read_speed_rand = self.test_read_speed(test_file, 4*1024,
                                               color_cb=lambda i, s: self.color_block(i, s))
        self.add_result(f"   • Zufällig (4KB Blöcke): {read_speed_rand:.2f} MB/s")
        
        # Lösche Testdatei
        try:
            os.remove(test_file)
        except:
            pass
        
        self.update_progress(75, "Geschwindigkeitstest abgeschlossen")
    
    def test_write_speed(self, filepath, size_mb, block_size, color_cb=None):
        """Teste Schreibgeschwindigkeit"""
        data = os.urandom(block_size)
        total_bytes = size_mb * 1024 * 1024
        blocks = total_bytes // block_size
        last_mb = -1
        
        start_time = time.time()
        
        with open(filepath, 'wb') as f:
            for i in range(blocks):
                self.check_abort()
                t0 = time.time()
                f.write(data)
                elapsed_block = time.time() - t0
                
                if color_cb is not None:
                    mb_pos = (i * block_size) // (1024 * 1024)
                    if mb_pos != last_mb:
                        last_mb = mb_pos
                        spd = (block_size / (1024 * 1024)) / elapsed_block if elapsed_block > 0 else 999
                        state = "good" if spd > 10 else ("slow" if spd > 2 else "error")
                        color_cb(mb_pos, state)
        
        elapsed = time.time() - start_time
        speed = size_mb / elapsed if elapsed > 0 else 0
        return speed
    
    def test_read_speed(self, filepath, block_size, color_cb=None):
        """Teste Lesegeschwindigkeit"""
        if not os.path.exists(filepath):
            return 0
        
        file_size = os.path.getsize(filepath)
        blocks = file_size // block_size
        last_mb = -1
        
        start_time = time.time()
        
        with open(filepath, 'rb') as f:
            for i in range(blocks):
                self.check_abort()
                t0 = time.time()
                f.read(block_size)
                elapsed_block = time.time() - t0
                
                if color_cb is not None:
                    mb_pos = (i * block_size) // (1024 * 1024)
                    if mb_pos != last_mb:
                        last_mb = mb_pos
                        spd = (block_size / (1024 * 1024)) / elapsed_block if elapsed_block > 0 else 999
                        state = "good" if spd > 10 else ("slow" if spd > 2 else "error")
                        color_cb(mb_pos, state)
        
        elapsed = time.time() - start_time
        mb_read = file_size / (1024 * 1024)
        speed = mb_read / elapsed if elapsed > 0 else 0
        return speed
    
    def test_data_integrity(self, drive_path):
        """Teste Datenintegrität durch Schreiben und Verifizieren"""
        self.add_result("\n🔒 Integritätstest...")
        
        test_size_mb = min(100, self.get_test_size_mb())  # Max 100MB für Integrität
        test_file = os.path.join(drive_path, "integrity_test.dat")
        CHUNK_SIZE = 1024 * 1024  # 1 MB pro Block
        
        try:
            # Schreibe Testdaten block-weise
            self.init_block_map(test_size_mb, "🔒 Integritätstest – Schreiben")
            self.update_progress(80, "Schreibe Testdaten für Integrität...")
            chunks = []
            with open(test_file, 'wb') as f:
                for i in range(test_size_mb):
                    self.check_abort()
                    chunk = os.urandom(CHUNK_SIZE)
                    chunks.append(chunk)
                    self.color_block(i, "writing")
                    f.write(chunk)
                    self.color_block(i, "good")
            
            # Lese und verifiziere block-weise
            self.init_block_map(test_size_mb, "🔒 Integritätstest – Verifizierung")
            self.update_progress(90, "Verifiziere Daten...")
            errors = 0
            with open(test_file, 'rb') as f:
                for i, original in enumerate(chunks):
                    self.check_abort()
                    self.color_block(i, "reading")
                    read_chunk = f.read(CHUNK_SIZE)
                    if read_chunk == original:
                        self.color_block(i, "good")
                    else:
                        self.color_block(i, "error")
                        errors += 1
            
            if errors == 0:
                self.add_result("   ✅ Integritätstest bestanden: Daten wurden korrekt geschrieben und gelesen")
            else:
                self.add_result(f"   ❌ Integritätstest fehlgeschlagen: {errors} Block(s) mit Datenkorruption!")
            
            # Lösche Testdatei
            os.remove(test_file)
            
        except Exception as e:
            self.add_result(f"   ❌ Fehler beim Integritätstest: {str(e)}")
        
        self.update_progress(100, "Alle Tests abgeschlossen")
    
    def get_test_size_mb(self):
        """Konvertiere Testgröße in MB"""
        size_str = self.test_size.get()
        value = int(size_str.split()[0])
        unit = size_str.split()[1]
        
        if unit == "GB":
            return value * 1024
        elif unit == "MB":
            return value
        else:
            return 100  # default
    
    def update_progress(self, value, status):
        """Aktualisiere Fortschrittsbalken und Status"""
        self.root.after(0, lambda: self.progress.configure(value=value))
        self.root.after(0, lambda: self.status_label.configure(text=status))
        
        # Append to progress log
        def append_log():
            self.progress_log.config(state="normal")
            self.progress_log.insert(END, f"[{int(value)}%] {status}\n")
            self.progress_log.see(END)  # Auto-scroll to bottom
            self.progress_log.config(state="disabled")
        
        self.root.after(0, append_log)
    
    def test_finished(self):
        """Setze UI nach Test zurück"""
        self.test_in_progress = False
        self.start_btn.config(state="normal", text=self.t("ui_start"))
        self.stop_btn.config(state="disabled")
        self.status_label.configure(text=self.t("ui_ready"))
        self.show_drive_overview(self.t("ui_drive_map"))

if __name__ == "__main__":
    root = tb.Window(themename=load_theme_name())
    app = ExternalDriveTester(root)
    root.mainloop()
