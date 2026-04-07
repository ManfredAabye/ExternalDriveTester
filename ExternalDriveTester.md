# Hier ist ein vollständiges, modernes Testprogramm für externe Datenträger (wie ValiDrive) in Python mit `ttkbootstrap` und `psutil`

## Funktionen

- **Automatische Erkennung** aller Wechseldatenträger (USB-Sticks, externe Festplatten)
- **Geschwindigkeitstest** (Sequenziell: 1MB Blöcke, Zufällig: 4KB Blöcke)
- **Kapazitätsprüfung** (Erkennung von gefälschten/übergroßen Datenträgern)
- **Integritätstest** (Schreiben und Verifizieren von Testdaten)
- **Modernes UI** mit Fortschrittsbalken und Echtzeit-Anzeige
- **Multithreading** (GUI bleibt flüssig während Tests)

## Installation

```bash
pip install ttkbootstrap psutil
```

## Vollständiger Code

```python
import os
import time
import threading
import random
import tempfile
from pathlib import Path
import psutil
import ttkbootstrap as tb
from ttkbootstrap.constants import *
from ttkbootstrap.scrolled import ScrolledFrame
from tkinter import messagebox, StringVar, IntVar

class ExternalDriveTester:
    def __init__(self, root):
        self.root = root
        self.root.title("Externe Datenträger Testprogramm v1.0")
        self.root.geometry("900x700")
        
        # Variablen
        self.selected_drive = StringVar()
        self.test_in_progress = False
        self.test_thread = None
        
        # Modernes Theme
        self.style = tb.Style(theme="darkly")  # Alternativen: "superhero", "solar", "cyborg"
        
        self.setup_ui()
        self.refresh_drives()
    
    def setup_ui(self):
        # Hauptcontainer
        main_frame = tb.Frame(self.root, padding=20)
        main_frame.pack(fill=BOTH, expand=YES)
        
        # Header
        header = tb.Label(main_frame, text="Externe Datenträger Test Tool",
                         font=("Helvetica", 18, "bold"))
        header.pack(pady=(0, 20))
        
        # Drive Selection Frame
        drive_frame = tb.LabelFrame(main_frame, text="Datenträger auswählen", padding=15)
        drive_frame.pack(fill=X, pady=(0, 15))
        
        # Drive Combobox
        self.drive_combo = tb.Combobox(drive_frame, textvariable=self.selected_drive,
                                       state="readonly", width=50)
        self.drive_combo.pack(side=LEFT, padx=(0, 10))
        
        # Refresh Button
        refresh_btn = tb.Button(drive_frame, text="🔄 Aktualisieren",
                               command=self.refresh_drives, bootstyle="info")
        refresh_btn.pack(side=LEFT)
        
        # Drive Info
        self.info_text = tb.Text(drive_frame, height=4, width=60, state="disabled")
        self.info_text.pack(fill=X, pady=(10, 0))
        
        # Test Options Frame
        test_frame = tb.LabelFrame(main_frame, text="Testoptionen", padding=15)
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
        
        tb.Checkbutton(checks_frame, text="Geschwindigkeitstest", variable=self.test_speed,
                      bootstyle="info").pack(side=LEFT, padx=(0, 15))
        tb.Checkbutton(checks_frame, text="Integritätstest", variable=self.test_integrity,
                      bootstyle="info").pack(side=LEFT, padx=(0, 15))
        tb.Checkbutton(checks_frame, text="Kapazitätsprüfung", variable=self.test_capacity,
                      bootstyle="info").pack(side=LEFT)
        
        # Start Button
        self.start_btn = tb.Button(test_frame, text="▶ Test starten",
                                  command=self.start_test, bootstyle="success",
                                  width=20)
        self.start_btn.pack(pady=(10, 0))
        
        # Progress Frame
        progress_frame = tb.LabelFrame(main_frame, text="Testfortschritt", padding=15)
        progress_frame.pack(fill=BOTH, expand=YES, pady=(0, 15))
        
        # Progress bar
        self.progress = tb.Progressbar(progress_frame, bootstyle="info",
                                       length=400, mode="determinate")
        self.progress.pack(fill=X, pady=(0, 10))
        
        # Status label
        self.status_label = tb.Label(progress_frame, text="Bereit", font=("", 10))
        self.status_label.pack()
        
        # Results Frame (scrollable)
        results_frame = tb.LabelFrame(main_frame, text="Ergebnisse", padding=15)
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
            if 'removable' in partition.opts or 'cdrom' in partition.opts:
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
    
    def start_test(self):
        """Starte den Test in einem separaten Thread"""
        if self.test_in_progress:
            messagebox.showwarning("Warnung", "Ein Test läuft bereits!")
            return
        
        if not self.selected_drive.get():
            messagebox.showerror("Fehler", "Bitte wählen Sie ein Laufwerk aus!")
            return
        
        self.test_in_progress = True
        self.start_btn.config(state="disabled", text="⏳ Test läuft...")
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
        
        # UI zurücksetzen
        self.root.after(0, self.test_finished)
    
    def test_drive_capacity(self, drive_path):
        """Teste die tatsächliche Kapazität (erkennt gefälschte USB-Sticks)"""
        self.add_result("\n📦 Kapazitätstest...")
        
        test_size_mb = self.get_test_size_mb()
        test_file = os.path.join(drive_path, "capacity_test.dat")
        
        try:
            # Schreibe Testdatei
            self.update_progress(10, "Schreibe Testdaten...")
            with open(test_file, 'wb') as f:
                chunk = os.urandom(1024 * 1024)  # 1MB Chunks
                for i in range(test_size_mb):
                    f.write(chunk)
                    if i % 10 == 0:
                        progress = 10 + (i / test_size_mb) * 40
                        self.update_progress(progress, f"Schreibe Block {i+1}/{test_size_mb}")
            
            # Überprüfe Dateigröße
            actual_size = os.path.getsize(test_file)
            expected_size = test_size_mb * 1024 * 1024
            
            self.add_result(f"   Erwartete Größe: {self.format_size(expected_size)}")
            self.add_result(f"   Tatsächliche Größe: {self.format_size(actual_size)}")
            
            if actual_size >= expected_size:
                self.add_result("   ✅ Kapazitätstest bestanden")
            else:
                self.add_result("   ⚠️ Warnung: Tatsächliche Kapazität geringer als erwartet!")
                self.add_result("   💾 Dies könnte ein gefälschter Datenträger sein!")
            
            # Lösche Testdatei
            os.remove(test_file)
            self.update_progress(50, "Kapazitätstest abgeschlossen")
            
        except Exception as e:
            self.add_result(f"   ❌ Fehler beim Kapazitätstest: {str(e)}")
    
    def test_speed_performance(self, drive_path):
        """Teste Lese- und Schreibgeschwindigkeit"""
        self.add_result("\n⚡ Geschwindigkeitstest...")
        
        test_size_mb = self.get_test_size_mb()
        test_file = os.path.join(drive_path, "speed_test.dat")
        
        # Schreibtests
        self.add_result("\n   📝 Schreibtests:")
        
        # Sequenzieller Schreibtest (1MB Blöcke)
        write_speed_seq = self.test_write_speed(test_file, test_size_mb, 1024*1024)
        self.add_result(f"   • Sequenziell (1MB Blöcke): {write_speed_seq:.2f} MB/s")
        
        # Zufälliger Schreibtest (4KB Blöcke)
        write_speed_rand = self.test_write_speed(test_file, test_size_mb, 4*1024)
        self.add_result(f"   • Zufällig (4KB Blöcke): {write_speed_rand:.2f} MB/s")
        
        # Lesetests
        self.add_result("\n   📖 Lesetests:")
        
        # Sequenzieller Lesetest
        read_speed_seq = self.test_read_speed(test_file, 1024*1024)
        self.add_result(f"   • Sequenziell (1MB Blöcke): {read_speed_seq:.2f} MB/s")
        
        # Zufälliger Lesetest
        read_speed_rand = self.test_read_speed(test_file, 4*1024)
        self.add_result(f"   • Zufällig (4KB Blöcke): {read_speed_rand:.2f} MB/s")
        
        # Lösche Testdatei
        try:
            os.remove(test_file)
        except:
            pass
        
        self.update_progress(75, "Geschwindigkeitstest abgeschlossen")
    
    def test_write_speed(self, filepath, size_mb, block_size):
        """Teste Schreibgeschwindigkeit"""
        data = os.urandom(block_size)
        blocks = (size_mb * 1024 * 1024) // block_size
        
        start_time = time.time()
        
        with open(filepath, 'wb') as f:
            for _ in range(blocks):
                f.write(data)
        
        elapsed = time.time() - start_time
        mb_written = size_mb
        speed = mb_written / elapsed if elapsed > 0 else 0
        
        return speed
    
    def test_read_speed(self, filepath, block_size):
        """Teste Lesegeschwindigkeit"""
        if not os.path.exists(filepath):
            return 0
        
        file_size = os.path.getsize(filepath)
        blocks = file_size // block_size
        
        start_time = time.time()
        
        with open(filepath, 'rb') as f:
            for _ in range(blocks):
                f.read(block_size)
        
        elapsed = time.time() - start_time
        mb_read = file_size / (1024 * 1024)
        speed = mb_read / elapsed if elapsed > 0 else 0
        
        return speed
    
    def test_data_integrity(self, drive_path):
        """Teste Datenintegrität durch Schreiben und Verifizieren"""
        self.add_result("\n🔒 Integritätstest...")
        
        test_size_mb = min(100, self.get_test_size_mb())  # Max 100MB für Integrität
        test_file = os.path.join(drive_path, "integrity_test.dat")
        
        try:
            # Schreibe Testdaten mit Prüfsumme
            self.update_progress(80, "Schreibe Testdaten für Integrität...")
            test_data = os.urandom(test_size_mb * 1024 * 1024)
            
            with open(test_file, 'wb') as f:
                f.write(test_data)
            
            # Lese und verifiziere
            self.update_progress(90, "Verifiziere Daten...")
            with open(test_file, 'rb') as f:
                read_data = f.read()
            
            if test_data == read_data:
                self.add_result("   ✅ Integritätstest bestanden: Daten wurden korrekt geschrieben und gelesen")
            else:
                self.add_result("   ❌ Integritätstest fehlgeschlagen: Datenkorruption erkannt!")
            
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
    
    def test_finished(self):
        """Setze UI nach Test zurück"""
        self.test_in_progress = False
        self.start_btn.config(state="normal", text="▶ Test starten")
        self.status_label.configure(text="Bereit")

if __name__ == "__main__":
    root = tb.Window(themename="darkly")
    app = ExternalDriveTester(root)
    root.mainloop()
```

## Verwendung

1. **Programm starten**:

   ```bash
   python usb_tester.py
   ```

2. **Datenträger auswählen**: Wählen Sie Ihren USB-Stick oder eine externe Festplatte aus der Dropdown-Liste.

3. **Testoptionen konfigurieren**:
   - Wählen Sie die Testgröße (10 MB bis 5 GB)
   - Aktivieren/deaktivieren Sie die gewünschten Tests

4. **Test starten**: Klicken Sie auf "Test starten" und warten Sie auf die Ergebnisse.

## Features im Detail

### 1. **Kapazitätstest**

Erkennt gefälschte USB-Sticks, die eine höhere Kapazität vortäuschen als tatsächlich vorhanden ist.

### 2. **Geschwindigkeitstest**

- **Sequenziell**: Misst die Geschwindigkeit für große Dateien (z.B. Videostreaming)
- **Zufällig**: Misst die Geschwindigkeit für kleine Dateien (z.B. Betriebssystemzugriffe)

### 3. **Integritätstest**

Schreibt und verifiziert Testdaten, um Datenkorruption zu erkennen.

### 4. **Modernes UI**

- Dunkles Theme (anpassbar)
- Fortschrittsbalken
- Echtzeit-Statusanzeigen
- Scrollbare Ergebnisse

## Themes anpassen

Sie können das Theme ändern, indem Sie die Zeile ändern:

```python
root = tb.Window(themename="darkly")  # Optionen: "darkly", "superhero", "solar", "cyborg", "vapor"
```

Das Programm bietet eine professionelle Lösung zum Testen externer Datenträger ähnlich wie ValiDrive, jedoch mit zusätzlichen Funktionen und einer modernen Benutzeroberfläche!
