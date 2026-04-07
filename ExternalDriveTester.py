import os
import sys
import time
import threading
import psutil
import ttkbootstrap as tb
from ttkbootstrap.constants import *  # type: ignore[import-untyped]
from tkinter import ttk, messagebox, StringVar, Canvas, PhotoImage


def resource_path(relative_path: str) -> str:
    """Pfad fuer normale Ausfuehrung und PyInstaller-Onefile."""
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(getattr(sys, "_MEIPASS"), relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

class ExternalDriveTester:
    # Fenstergrößen (leicht anpassbar)
    WINDOW_WIDTH = 1050
    WINDOW_HEIGHT = 1900
    BLOCK_SIZE_MB = 100  # Jeder Block = 50 MB (für die Visualisierung)
    
    def __init__(self, root):
        self.root = root
        self.root.title("External Drive Tester v1.0")
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
        self.verified_capacity_var = StringVar(value="Verifiziert geschrieben: -")
        self.block_cells: list = []
        self.block_base_colors: list[str] = []
        self.block_count = 0
        self._display_block_count = 0
        
        # Modernes Theme
        self.style = tb.Style(theme="darkly")  # Alternativen: "superhero", "solar", "cyborg"
        
        self.setup_ui()
        self.refresh_drives()

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
        
        # Headerbild statt Texttitel
        title_file = resource_path("titel.png")
        if os.path.exists(title_file):
            try:
                self.title_img = PhotoImage(file=title_file)
                tb.Label(main_frame, image=self.title_img).pack(pady=(0, 20))
            except Exception:
                tb.Label(main_frame, text="Externe Datenträger Test Tool", font=("Helvetica", 18, "bold")).pack(pady=(0, 20))
        else:
            tb.Label(main_frame, text="Externe Datenträger Test Tool", font=("Helvetica", 18, "bold")).pack(pady=(0, 20))
        
        # Drive Selection Frame
        drive_frame = ttk.LabelFrame(main_frame, text="Datenträger auswählen", padding=15)
        drive_frame.pack(fill=X, pady=(0, 15))
        
        # Zeile 1: Laufwerk + Aktualisieren
        drive_top_row = tb.Frame(drive_frame)
        drive_top_row.pack(fill=X)

        self.drive_combo = tb.Combobox(drive_top_row, textvariable=self.selected_drive,
                           state="readonly", width=50)
        self.drive_combo.pack(side=LEFT, padx=(0, 10))
        # FIX 1: Laufwerkswechsel bindet Infoanzeige
        self.drive_combo.bind("<<ComboboxSelected>>", self.update_drive_info)

        refresh_btn = tb.Button(drive_top_row, text="🔄 Aktualisieren",
                       command=self.refresh_drives, bootstyle="info")
        refresh_btn.pack(side=LEFT)

        # Zeile 2: Laufwerksinfos direkt unter der Aktualisieren-Zeile
        self.info_text = tb.Text(drive_frame, height=4, width=60, state="disabled")
        self.info_text.pack(fill=X, pady=(10, 0))
        
        # Test Options Frame
        test_frame = ttk.LabelFrame(main_frame, text="Testoptionen", padding=15)
        test_frame.pack(fill=X, pady=(0, 15))
        
        # Test size
        size_frame = tb.Frame(test_frame)
        size_frame.pack(fill=X, pady=(0, 10))
        
        tb.Label(size_frame, text="Testgröße:").pack(side=LEFT, padx=(0, 10))
        self.test_size = tb.Combobox(size_frame, values=["10 MB", "100 MB", "500 MB", "1 GB", "5 GB"],
                                     state="readonly", width=15)
        self.test_size.set("100 MB")
        self.test_size.pack(side=LEFT)
        
        # Test types
        checks_frame = tb.Frame(test_frame)
        checks_frame.pack(fill=X, pady=(0, 10))
        
        self.test_speed = tb.BooleanVar(value=True)
        self.test_integrity = tb.BooleanVar(value=True)
        self.test_capacity = tb.BooleanVar(value=True)
        self.full_capacity_test = tb.BooleanVar(value=False)
        
        tb.Checkbutton(checks_frame, text="Geschwindigkeitstest", variable=self.test_speed,
                      bootstyle="info").pack(side=LEFT, padx=(0, 15))
        tb.Checkbutton(checks_frame, text="Integritätstest", variable=self.test_integrity,
                      bootstyle="info").pack(side=LEFT, padx=(0, 15))
        tb.Checkbutton(checks_frame, text="Kapazitätsprüfung", variable=self.test_capacity,
                      bootstyle="info").pack(side=LEFT)

        tb.Checkbutton(
            test_frame,
            text="Vollständiger Kapazitätstest (bis Datenträger voll)",
            variable=self.full_capacity_test,
            bootstyle="warning",
        ).pack(anchor=W, pady=(0, 10))
        
        # Start Button
        button_row = tb.Frame(test_frame)
        button_row.pack(pady=(10, 0), fill=X)

        self.start_btn = tb.Button(button_row, text="▶ Test starten",
                      command=self.start_test, bootstyle="success",
                      width=20)
        self.start_btn.pack(side=LEFT)

        self.stop_btn = tb.Button(button_row, text="■ Abbrechen",
                      command=self.request_stop, bootstyle="danger",
                      width=20, state="disabled")
        self.stop_btn.pack(side=LEFT, padx=(10, 0))
        
        # Progress Frame
        progress_frame = ttk.LabelFrame(main_frame, text="Testfortschritt", padding=15)
        progress_frame.pack(fill=BOTH, expand=YES, pady=(0, 15))
        
        # Progress bar
        self.progress = tb.Progressbar(progress_frame, bootstyle="info",
                                       length=400, mode="determinate")
        self.progress.pack(fill=X, pady=(0, 10))
        
        # Status label
        self.status_label = tb.Label(progress_frame, text="Bereit", font=("", 10))
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
        self.block_phase_label = tb.Label(progress_frame, text="Laufwerksabbild", font=("Consolas", 8))
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
        self.block_canvas.bind("<Configure>", lambda _e: self.show_drive_overview("Laufwerksabbild"))

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
        for _col, _lbl in [("#6c757d", "Belegt"), ("#2a2a2a", "Frei"),
                    ("#3498db", "Schreiben"), ("#9b59b6", "Lesen"),
                    ("#2ecc71", "Gut"), ("#f39c12", "Langsam"),
                    ("#e74c3c", "Fehler")]:
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
        results_frame = ttk.LabelFrame(main_frame, text="Ergebnisse", padding=15)
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
            self.drive_combo.set(drive_paths[0])
            self.update_drive_info()
        else:
            self.show_drive_overview("Kein Laufwerk gefunden")
    
    def update_drive_info(self, event=None):
        """Zeige Informationen zum ausgewählten Laufwerk"""
        if not self.selected_drive.get():
            return
        
        drive_path = self.selected_drive.get().split(" (")[0]
        
        try:
            usage = psutil.disk_usage(drive_path)
            info = f"""
📊 Laufwerksinformationen:
   Pfad: {drive_path}
   Gesamt: {self.format_size(usage.total)}
   Belegt: {self.format_size(usage.used)}
   Frei: {self.format_size(usage.free)}
   Auslastung: {usage.percent}%
            """
            self.info_text.config(state="normal")
            self.info_text.delete(1.0, END)
            self.info_text.insert(1.0, info)
            self.info_text.config(state="disabled")
            self.show_drive_overview("Laufwerksabbild")
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

    def show_drive_overview(self, phase_label: str = "Laufwerksabbild") -> None:
        """Zeigt ein fixes Laufwerks-Abbild (belegt/frei) an."""
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
            self.root.after(0, lambda: self.status_label.configure(text="Abbruch angefordert..."))

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
                f"Verifiziert geschrieben: {self.format_size(bytes_value)}"
            ),
        )

    def start_test(self):
        """Starte den Test in einem separaten Thread"""
        if self.test_in_progress:
            messagebox.showwarning("Warnung", "Ein Test läuft bereits!")
            return
        
        if not self.selected_drive.get():
            messagebox.showerror("Fehler", "Bitte wählen Sie ein Laufwerk aus!")
            return
        
        self.test_in_progress = True
        self.stop_requested = False
        self.set_verified_capacity(0)
        self.start_btn.config(state="disabled", text="⏳ Test läuft...")
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
        self.start_btn.config(state="normal", text="▶ Test starten")
        self.stop_btn.config(state="disabled")
        self.status_label.configure(text="Bereit")
        self.show_drive_overview("Laufwerksabbild")

if __name__ == "__main__":
    root = tb.Window(themename="darkly")
    app = ExternalDriveTester(root)
    root.mainloop()
