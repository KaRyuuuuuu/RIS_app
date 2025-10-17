# ===============================
# 📁 Fichier : launcher_ctk.py
# 📍 Emplacement : KaRyuuMultiApp/launcher_ctk.py
# ===============================

"""
Launcher "Multi-App" en CustomTkinter (CTk) — UI améliorée
- Onglet "Applications" : liste des plugins activés + panneau de prévisualisation
- Onglet "Boutique" : cartes plugins (install/maj/désinstalle/enable) + barre de progression
- Onglet "Paramètres" : changer manifest/catalog + forcer vérif MAJ du launcher
- Téléchargements asynchrones (thread) + barre de statut
- Messages d’erreur plus clairs et non-bloquants
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import os, sys, json, shutil, zipfile, tempfile, urllib.request, configparser, threading
from functools import partial

# =========================
# 🎨 Thème CTk
# =========================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# =========================
# ⚙️ Constantes & chemins
# =========================
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
PLUGINS_DIR = os.path.join(APP_ROOT, "plugins")
VERSION_FILE = os.path.join(APP_ROOT, "app_version.txt")
CONFIG_FILE = os.path.join(APP_ROOT, "config.ini")
INSTALLED_STATE = os.path.join(APP_ROOT, "installed.json")

# URLs distantes (à modifier par tes liens GitHub Pages)
DEFAULT_MANIFEST_URL = "https://karyuuuuuu.github.io/RIS_app/manifest.json"
DEFAULT_CATALOG_URL  = "https://karyuuuuuu.github.io/RIS_app/catalog.json"

# =========================
# 📦 Utilitaires fichiers
# =========================
def ensure_dirs():
    os.makedirs(PLUGINS_DIR, exist_ok=True)

def read_local_version():
    if not os.path.exists(VERSION_FILE):
        return "1.0.0"
    return open(VERSION_FILE, "r", encoding="utf-8").read().strip() or "1.0.0"

def write_local_version(v):
    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        f.write(v)

def ensure_config():
    if not os.path.exists(CONFIG_FILE):
        cfg = configparser.ConfigParser()
        cfg["remote"] = {"manifest_url": DEFAULT_MANIFEST_URL, "catalog_url": DEFAULT_CATALOG_URL}
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            cfg.write(f)

def _cfg():
    ensure_config()
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_FILE, encoding="utf-8")
    return cfg

def get_manifest_url():
    return _cfg().get("remote", "manifest_url", fallback=DEFAULT_MANIFEST_URL)

def get_catalog_url():
    return _cfg().get("remote", "catalog_url", fallback=DEFAULT_CATALOG_URL)

def set_urls(manifest_url: str, catalog_url: str):
    cfg = _cfg()
    if "remote" not in cfg:
        cfg["remote"] = {}
    cfg["remote"]["manifest_url"] = manifest_url.strip() or DEFAULT_MANIFEST_URL
    cfg["remote"]["catalog_url"] = catalog_url.strip() or DEFAULT_CATALOG_URL
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        cfg.write(f)

def compare_versions(a, b):
    """Compare a vs b (x.y.z). Retourne -1 si a<b, 0 si égal, 1 si a>b."""
    def parse(v):
        parts = []
        for x in v.split("."):
            try:
                parts.append(int(x))
            except:
                parts.append(0)
        while len(parts) < 3:
            parts.append(0)
        return parts[:3]
    pa, pb = parse(a), parse(b)
    return (pa > pb) - (pa < pb)

# =========================
# 🌐 Réseau / téléchargement
# =========================
def http_get_json(url):
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read().decode("utf-8"))

def http_download_to(url, dest_path, progress_cb=None, chunk_size=1024*128):
    """
    Télécharge url -> dest_path avec retour de progression (0..1).
    """
    with urllib.request.urlopen(url) as r, open(dest_path, "wb") as f:
        total = r.length if hasattr(r, "length") and r.length else None
        downloaded = 0
        while True:
            chunk = r.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if progress_cb and total:
                progress_cb(min(downloaded/total, 1.0))

def unzip_to(zip_path, target_dir):
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir, ignore_errors=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(target_dir)

# =========================
# 🔌 Plugins locaux
# =========================
def list_plugins():
    if not os.path.exists(PLUGINS_DIR): return []
    return sorted([d for d in os.listdir(PLUGINS_DIR) if os.path.isdir(os.path.join(PLUGINS_DIR, d))])

def plugin_version(name):
    vfile = os.path.join(PLUGINS_DIR, name, "version.txt")
    return open(vfile, encoding="utf-8").read().strip() if os.path.exists(vfile) else "0.0.0"

def plugin_set_version(name, v):
    os.makedirs(os.path.join(PLUGINS_DIR, name), exist_ok=True)
    with open(os.path.join(PLUGINS_DIR, name, "version.txt"), "w", encoding="utf-8") as f:
        f.write(v)

def installed_load():
    return json.load(open(INSTALLED_STATE, "r", encoding="utf-8")) if os.path.exists(INSTALLED_STATE) else {}

def installed_save(state):
    with open(INSTALLED_STATE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def plugin_enabled(name):
    return installed_load().get(name, {}).get("enabled", True)

def set_plugin_enabled(name, enabled):
    state = installed_load()
    if name not in state: state[name] = {}
    state[name]["enabled"] = enabled
    installed_save(state)

def uninstall_plugin(name):
    shutil.rmtree(os.path.join(PLUGINS_DIR, name), ignore_errors=True)
    st = installed_load()
    if name in st: del st[name]
    installed_save(st)

# =========================
# 🧩 Composant carte plugin
# =========================
class PluginCard(ctk.CTkFrame):
    """
    Petite carte avec : nom, version locale/distante, état (activé), boutons Installer/MAJ/Désinstaller,
    et un switch "Activer".
    """
    def __init__(self, master, app_data, get_remote_version, on_refresh, statusbar):
        super().__init__(master, corner_radius=16, border_width=1)
        self.app_data = app_data
        self.get_remote_version = get_remote_version
        self.on_refresh = on_refresh
        self.statusbar = statusbar
        self.name = app_data.get("name", "Unknown")
        self.remote_v = app_data.get("version", "0.0.0")
        self.url = app_data.get("url", "")

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)

        title = ctk.CTkLabel(self, text=f"🧩 {self.name}", font=ctk.CTkFont(size=16, weight="bold"))
        title.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 0))

        # Versions
        local_v = plugin_version(self.name)
        ver_text = f"Locale: v{local_v} • Distant: v{self.remote_v}"
        color = "light green" if compare_versions(local_v, self.remote_v) >= 0 else "orange"
        self.ver_lbl = ctk.CTkLabel(self, text=ver_text, text_color=color)
        self.ver_lbl.grid(row=1, column=0, sticky="w", padx=12)

        # Progress
        self.progress = ctk.CTkProgressBar(self)
        self.progress.set(0)
        self.progress.grid(row=2, column=0, sticky="ew", padx=12, pady=(6, 0))
        self.progress.grid_remove()

        # Buttons row
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=3, column=0, sticky="ew", padx=8, pady=8)
        btn_row.grid_columnconfigure((0,1,2,3), weight=0)
        btn_row.grid_columnconfigure(4, weight=1)

        self.install_btn = ctk.CTkButton(btn_row, text="⬇️ Installer", command=self.install)
        self.update_btn  = ctk.CTkButton(btn_row, text="🔄 Mettre à jour", command=self.install)
        self.remove_btn  = ctk.CTkButton(btn_row, text="🗑️ Désinstaller", fg_color="#943", hover_color="#b55", command=self.remove)
        self.enable_sw   = ctk.CTkSwitch(btn_row, text="Activer", command=self.toggle_enable)

        # State
        installed = os.path.exists(os.path.join(PLUGINS_DIR, self.name))
        if not installed:
            self.install_btn.grid(row=0, column=0, padx=6)
        else:
            if compare_versions(plugin_version(self.name), self.remote_v) < 0:
                self.update_btn.grid(row=0, column=0, padx=6)
            self.remove_btn.grid(row=0, column=1, padx=6)
            self.enable_sw.grid(row=0, column=2, padx=6)
            self.enable_sw.select() if plugin_enabled(self.name) else self.enable_sw.deselect()

    def set_progress_visible(self, visible: bool):
        if visible:
            self.progress.grid()
        else:
            self.progress.grid_remove()

    def _run_in_thread(self, target):
        t = threading.Thread(target=target, daemon=True)
        t.start()

    def install(self):
        """Installer ou mettre à jour (même bouton)."""
        def _task():
            try:
                self.set_progress_visible(True)
                tmp = tempfile.mkdtemp()
                zpath = os.path.join(tmp, f"{self.name}.zip")
                self.statusbar.set_text(f"Téléchargement {self.name}…")
                http_download_to(self.url, zpath, progress_cb=self.progress.set)
                self.statusbar.set_text(f"Décompression {self.name}…")
                unzip_to(zpath, os.path.join(PLUGINS_DIR, self.name))
                plugin_set_version(self.name, self.remote_v)
                st = installed_load(); st[self.name] = {"enabled": True}; installed_save(st)
                self.statusbar.ok(f"{self.name} installé/mis à jour ✔")
                self.on_refresh()
            except Exception as e:
                self.statusbar.error(f"Erreur install {self.name} : {e}")
                messagebox.showerror("Erreur", f"Impossible d’installer {self.name}.\n{e}")
            finally:
                self.set_progress_visible(False)
                self.progress.set(0)
        self._run_in_thread(_task)

    def remove(self):
        if not messagebox.askyesno("Confirmer", f"Désinstaller {self.name} ?"):
            return
        try:
            uninstall_plugin(self.name)
            self.statusbar.ok(f"{self.name} désinstallé ✔")
            self.on_refresh()
        except Exception as e:
            self.statusbar.error(f"Erreur désinstallation : {e}")
            messagebox.showerror("Erreur", str(e))

    def toggle_enable(self):
        set_plugin_enabled(self.name, self.enable_sw.get() == 1)
        self.on_refresh()

# =========================
# 🧃 Barre de statut
# =========================
class StatusBar(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.label = ctk.CTkLabel(self, text="Prêt.", anchor="w")
        self.label.pack(fill="x", padx=10, pady=4)

    def set_text(self, text): self.label.configure(text=text)
    def ok(self, text): self.label.configure(text=f"✅ {text}")
    def error(self, text): self.label.configure(text=f"❌ {text}")

# =========================
# 🛒 Marketplace (UI refaite)
# =========================
class Marketplace(ctk.CTkFrame):
    def __init__(self, master, refresh_callback, statusbar):
        super().__init__(master)
        self.refresh_callback = refresh_callback
        self.statusbar = statusbar
        self.catalog = {"apps": []}

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(10, 0))
        ctk.CTkLabel(header, text="📦 Catalogue d’applications", font=ctk.CTkFont(size=18, weight="bold")).pack(side="left")

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.pack(side="right")
        self.search_var = tk.StringVar()
        self.search = ctk.CTkEntry(right, placeholder_text="Rechercher…", textvariable=self.search_var, width=220)
        self.search.pack(side="left", padx=6)
        ctk.CTkButton(right, text="🔄 Actualiser", command=self.load_catalog).pack(side="left", padx=6)

        self.canvas = ctk.CTkScrollableFrame(self)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=10)

        self.search_var.trace_add("write", lambda *_: self.refresh_view())
        self.load_catalog()

    def load_catalog(self):
        try:
            self.statusbar.set_text("Chargement du catalogue…")
            self.catalog = http_get_json(get_catalog_url())
            self.refresh_view()
            self.statusbar.ok("Catalogue chargé")
        except Exception as e:
            self.statusbar.error("Impossible de charger le catalogue")
            messagebox.showerror("Erreur", f"Impossible de charger le catalogue : {e}")

    def refresh_view(self):
        for w in self.canvas.winfo_children():
            w.destroy()
        query = (self.search_var.get() or "").lower().strip()
        apps = self.catalog.get("apps", [])
        if query:
            apps = [a for a in apps if query in a.get("name", "").lower()]
        if not apps:
            ctk.CTkLabel(self.canvas, text="Aucun résultat.").pack(pady=10)
            return
        # Grille 2 colonnes
        cols = 2
        for i, app in enumerate(apps):
            card = PluginCard(self.canvas, app, lambda: app.get("version","0.0.0"), self.refresh_callback, self.statusbar)
            r, c = divmod(i, cols)
            card.grid(row=r, column=c, padx=6, pady=6, sticky="nsew")
            self.canvas.grid_columnconfigure(c, weight=1)

# =========================
# ⚙️ Onglet paramètres
# =========================
class SettingsTab(ctk.CTkFrame):
    def __init__(self, master, statusbar):
        super().__init__(master)
        self.statusbar = statusbar

        ctk.CTkLabel(self, text="⚙️ Paramètres", font=ctk.CTkFont(size=18, weight="bold")).pack(anchor="w", padx=12, pady=(12,4))

        form = ctk.CTkFrame(self, corner_radius=12)
        form.pack(fill="x", padx=12, pady=8)

        self.manifest_var = tk.StringVar(value=get_manifest_url())
        self.catalog_var  = tk.StringVar(value=get_catalog_url())

        row1 = ctk.CTkFrame(form, fg_color="transparent"); row1.pack(fill="x", padx=10, pady=6)
        ctk.CTkLabel(row1, text="Manifest URL (Launcher) :", width=200, anchor="w").pack(side="left")
        ctk.CTkEntry(row1, textvariable=self.manifest_var).pack(side="left", fill="x", expand=True, padx=6)

        row2 = ctk.CTkFrame(form, fg_color="transparent"); row2.pack(fill="x", padx=10, pady=6)
        ctk.CTkLabel(row2, text="Catalog URL (Plugins) :", width=200, anchor="w").pack(side="left")
        ctk.CTkEntry(row2, textvariable=self.catalog_var).pack(side="left", fill="x", expand=True, padx=6)

        btns = ctk.CTkFrame(self, fg_color="transparent"); btns.pack(fill="x", padx=12, pady=8)
        ctk.CTkButton(btns, text="💾 Enregistrer", command=self.save).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="🔍 Vérifier MAJ Launcher", command=self.check_update).pack(side="left", padx=6)

        # Version
        self.ver_lbl = ctk.CTkLabel(self, text=f"Version locale : v{read_local_version()}")
        self.ver_lbl.pack(anchor="w", padx=12, pady=(0,12))

    def save(self):
        try:
            set_urls(self.manifest_var.get(), self.catalog_var.get())
            self.statusbar.ok("Paramètres enregistrés ✔")
        except Exception as e:
            self.statusbar.error(f"Erreur enregistrement : {e}")
            messagebox.showerror("Erreur", str(e))

    def check_update(self):
        try:
            manifest = http_get_json(get_manifest_url())
            remote_v = manifest.get("version", "0.0.0")
            local_v  = read_local_version()
            cmp = compare_versions(local_v, remote_v)
            if cmp < 0:
                messagebox.showinfo("Mise à jour", f"Nouvelle version dispo : v{remote_v}\n(Actuel : v{local_v})\n\nMet à jour tes fichiers via ton système de distribution (ex: zip GitHub Pages).")
            else:
                messagebox.showinfo("À jour", f"Tu es à jour ! v{local_v}")
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de vérifier la MAJ : {e}")

# =========================
# 🖥️ Fenêtre principale CTk
# =========================
class Launcher(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("🐉 KaRyuu Multi-App Launcher")
        self.geometry("1024x680")
        ensure_dirs()

        # Header
        header = ctk.CTkFrame(self)
        header.pack(fill="x")
        ctk.CTkLabel(header, text="🐉 KaRyuu Multi-App", font=ctk.CTkFont(size=20, weight="bold")).pack(side="left", padx=10, pady=10)
        self.top_right = ctk.CTkFrame(header, fg_color="transparent"); self.top_right.pack(side="right", padx=10)
        ctk.CTkButton(self.top_right, text="🧹 Nettoyer cache plugins", command=self.clean_cache).pack(side="right", padx=6)

        # Tabs
        self.nb = ctk.CTkTabview(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=(0,10))

        self.tab_apps = self.nb.add("🚀 Applications")
        self.tab_store = self.nb.add("🛒 Boutique")
        self.tab_settings = self.nb.add("⚙️ Paramètres")

        # Applications tab layout
        left = ctk.CTkFrame(self.tab_apps)
        left.pack(side="left", fill="y", padx=(10,6), pady=10)
        right = ctk.CTkFrame(self.tab_apps)
        right.pack(side="left", fill="both", expand=True, padx=(6,10), pady=10)

        # Left — search + list
        ctk.CTkLabel(left, text="Plugins activés", font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=10, pady=(10,4))
        self.search_enabled_var = tk.StringVar()
        self.search_enabled = ctk.CTkEntry(left, placeholder_text="Rechercher…", textvariable=self.search_enabled_var, width=240)
        self.search_enabled.pack(padx=10, pady=(0,6))
        self.search_enabled_var.trace_add("write", lambda *_: self.refresh_plugins())

        self.list_enabled = tk.Listbox(left, height=22, bg="#202020", fg="white", highlightthickness=0, selectbackground="#444")
        self.list_enabled.pack(fill="y", padx=10, pady=(0,6))
        self.list_enabled.bind("<<ListboxSelect>>", self.on_select)

        self.btn_refresh = ctk.CTkButton(left, text="🔄 Rafraîchir", command=self.refresh_plugins)
        self.btn_refresh.pack(padx=10, pady=(0,10), fill="x")

        # Right — plugin content
        self.frame_content = ctk.CTkFrame(right)
        self.frame_content.pack(fill="both", expand=True, padx=10, pady=10)
        ctk.CTkLabel(self.frame_content, text="Sélectionne un plugin à gauche pour l’ouvrir ici.",
                     text_color="#aaa").pack(pady=12)

        # Store
        self.statusbar = StatusBar(self)
        self.store = Marketplace(self.tab_store, self.refresh_plugins, self.statusbar)
        self.store.pack(fill="both", expand=True)

        # Settings
        self.settings = SettingsTab(self.tab_settings, self.statusbar)
        self.settings.pack(fill="both", expand=True)

        # Statusbar
        self.statusbar.pack(fill="x", padx=10, pady=(0,10))

        self.refresh_plugins()

    # ===== Apps tab logic
    def refresh_plugins(self):
        self.list_enabled.delete(0, tk.END)
        q = (self.search_enabled_var.get() or "").lower().strip()
        for name in list_plugins():
            if not plugin_enabled(name):
                continue
            v = plugin_version(name)
            label = f"{name} (v{v})"
            if q and q not in name.lower():
                continue
            self.list_enabled.insert(tk.END, label)

    def on_select(self, _=None):
        if not self.list_enabled.curselection(): return
        line = self.list_enabled.get(self.list_enabled.curselection()[0])
        name = line.split(" ")[0]
        self.open_plugin(name)

    def open_plugin(self, name):
        # Clear panel
        for w in self.frame_content.winfo_children():
            w.destroy()
        # Header with actions
        head = ctk.CTkFrame(self.frame_content, fg_color="transparent")
        head.pack(fill="x", pady=(6,0))
        ctk.CTkLabel(head, text=f"🧩 {name}", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=6)
        # Small action row
        row = ctk.CTkFrame(self.frame_content, fg_color="transparent")
        row.pack(fill="x", padx=6, pady=6)
        ctk.CTkButton(row, text="🔁 Recharger", command=partial(self._reload_plugin, name)).pack(side="left", padx=4)
        ctk.CTkButton(row, text="🗑️ Désactiver", fg_color="#943", hover_color="#b55",
                      command=lambda: (set_plugin_enabled(name, False), self.refresh_plugins(), self._show_hint())).pack(side="left", padx=4)

        # Content host
        host = ctk.CTkFrame(self.frame_content, corner_radius=12, border_width=1)
        host.pack(fill="both", expand=True, padx=6, pady=6)

        # Load plugin UI
        try:
            if APP_ROOT not in sys.path:
                sys.path.insert(0, APP_ROOT)
            mod = __import__(f"plugins.{name}.app", fromlist=["app"])
            if hasattr(mod, "build_ui"):
                mod.build_ui(host)
            else:
                ctk.CTkLabel(host, text=f"{name} n’a pas de build_ui()", text_color="orange").pack(pady=12)
        except Exception as e:
            ctk.CTkLabel(host, text=f"Erreur plugin : {e}", text_color="red").pack(pady=12)

    def _reload_plugin(self, name):
        # simple reload: relance l’ouverture
        self.open_plugin(name)

    def _show_hint(self):
        for w in self.frame_content.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.frame_content, text="Plugin désactivé. Rafraîchis la liste à gauche.",
                     text_color="#aaa").pack(pady=12)

    # ===== Misc
    def clean_cache(self):
        # Supprime dossiers temporaires laissés par Windows s’il y en a (prudent)
        removed = 0
        for d in os.listdir(tempfile.gettempdir()):
            if d.lower().startswith("tmp") and len(d) > 3:
                path = os.path.join(tempfile.gettempdir(), d)
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path, ignore_errors=True)
                        removed += 1
                except:
                    pass
        self.statusbar.ok(f"Cache nettoyé ({removed} dossiers)")

if __name__ == "__main__":
    app = Launcher()
    app.mainloop()
