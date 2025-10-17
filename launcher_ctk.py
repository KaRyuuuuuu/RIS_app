# ===============================
# 📁 Fichier : launcher_ctk.py
# 📍 Emplacement : KaRyuuMultiApp/launcher_ctk.py
# ===============================

"""
Launcher "Multi-App" en CustomTkinter (CTk)
- Onglet "Applications" : lance les plugins installés & activés
- Onglet "Boutique" : installe / met à jour / active / désinstalle les plugins
- MAJ à distance via manifest.json (launcher) + catalog.json (plugins)
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import os, sys, json, shutil, zipfile, tempfile, hashlib, urllib.request, configparser

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
DEFAULT_MANIFEST_URL = "https://exemple.github.io/multiapp/manifest.json"
DEFAULT_CATALOG_URL  = "https://exemple.github.io/multiapp/catalog.json"

# =========================
# 📦 Fonctions utilitaires
# =========================
def ensure_dirs():
    os.makedirs(PLUGINS_DIR, exist_ok=True)

def read_local_version():
    if not os.path.exists(VERSION_FILE):
        return "1.0.0"
    return open(VERSION_FILE, "r", encoding="utf-8").read().strip() or "1.0.0"

def write_local_version(v):
    open(VERSION_FILE, "w", encoding="utf-8").write(v)

def ensure_config():
    """Crée config.ini si absent"""
    if not os.path.exists(CONFIG_FILE):
        cfg = configparser.ConfigParser()
        cfg["remote"] = {"manifest_url": DEFAULT_MANIFEST_URL, "catalog_url": DEFAULT_CATALOG_URL}
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            cfg.write(f)

def get_manifest_url():
    ensure_config()
    cfg = configparser.ConfigParser(); cfg.read(CONFIG_FILE, encoding="utf-8")
    return cfg.get("remote", "manifest_url", fallback=DEFAULT_MANIFEST_URL)

def get_catalog_url():
    ensure_config()
    cfg = configparser.ConfigParser(); cfg.read(CONFIG_FILE, encoding="utf-8")
    return cfg.get("remote", "catalog_url", fallback=DEFAULT_CATALOG_URL)

def compare_versions(a, b):
    """Compare les versions a/b (format x.y.z)"""
    pa = [int(x) for x in a.split(".") if x.isdigit()] + [0]*3
    pb = [int(x) for x in b.split(".") if x.isdigit()] + [0]*3
    return (pa > pb) - (pa < pb)

# =========================
# 🌐 Réseau / téléchargement
# =========================
def http_get_json(url):
    with urllib.request.urlopen(url) as r:
        return json.loads(r.read().decode("utf-8"))

def http_download(url, path):
    with urllib.request.urlopen(url) as r, open(path, "wb") as f:
        shutil.copyfileobj(r, f)

def unzip_to(zip_path, target_dir):
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(target_dir)

# =========================
# 🔌 Plugins locaux
# =========================
def list_plugins():
    if not os.path.exists(PLUGINS_DIR): return []
    return [d for d in os.listdir(PLUGINS_DIR) if os.path.isdir(os.path.join(PLUGINS_DIR, d))]

def plugin_version(name):
    vfile = os.path.join(PLUGINS_DIR, name, "version.txt")
    return open(vfile).read().strip() if os.path.exists(vfile) else "0.0.0"

def plugin_set_version(name, v):
    open(os.path.join(PLUGINS_DIR, name, "version.txt"), "w").write(v)

def installed_load():
    return json.load(open(INSTALLED_STATE, "r")) if os.path.exists(INSTALLED_STATE) else {}

def installed_save(state):
    json.dump(state, open(INSTALLED_STATE, "w"), indent=2)

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
# 🧩 Boutique (CTk Frame)
# =========================
class Marketplace(ctk.CTkFrame):
    def __init__(self, master, refresh_callback):
        super().__init__(master)
        self.refresh_callback = refresh_callback
        self.catalog = {"apps": []}

        self.label = ctk.CTkLabel(self, text="📦 Catalogue d'applications", font=ctk.CTkFont(size=18, weight="bold"))
        self.label.pack(pady=(10, 5))

        self.listbox = tk.Listbox(self, height=15, bg="#1e1e1e", fg="white")
        self.listbox.pack(fill="both", expand=True, padx=10, pady=5)

        btn_frame = ctk.CTkFrame(self)
        btn_frame.pack(pady=5)
        ctk.CTkButton(btn_frame, text="🔄 Actualiser", command=self.load_catalog).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="⬇️ Installer", command=self.install_selected).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="🗑️ Désinstaller", command=self.uninstall_selected).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="⚙️ Activer/Désactiver", command=self.toggle_selected).pack(side="left", padx=5)

        self.load_catalog()

    def load_catalog(self):
        try:
            self.catalog = http_get_json(get_catalog_url())
            self.refresh_view()
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de charger le catalogue : {e}")

    def refresh_view(self):
        self.listbox.delete(0, tk.END)
        for app in self.catalog.get("apps", []):
            name = app["name"]
            remote_v = app["version"]
            local_v = plugin_version(name)
            line = f"{name} — v{remote_v}"
            if compare_versions(local_v, remote_v) < 0:
                line += " (MAJ dispo)"
            if plugin_enabled(name):
                line += " ✅"
            self.listbox.insert(tk.END, line)

    def get_selected(self):
        sel = self.listbox.curselection()
        if not sel: return None
        line = self.listbox.get(sel[0])
        return line.split(" — ")[0]

    def install_selected(self):
        name = self.get_selected()
        if not name: return
        app = next((a for a in self.catalog["apps"] if a["name"] == name), None)
        if not app: return
        try:
            tmp = tempfile.mkdtemp()
            zpath = os.path.join(tmp, f"{name}.zip")
            http_download(app["url"], zpath)
            unzip_to(zpath, os.path.join(PLUGINS_DIR, name))
            plugin_set_version(name, app["version"])
            st = installed_load(); st[name] = {"enabled": True}; installed_save(st)
            messagebox.showinfo("Installé", f"{name} installé avec succès !")
            self.refresh_view(); self.refresh_callback()
        except Exception as e:
            messagebox.showerror("Erreur", str(e))

    def uninstall_selected(self):
        name = self.get_selected()
        if not name: return
        if messagebox.askyesno("Confirmer", f"Désinstaller {name} ?"):
            uninstall_plugin(name)
            messagebox.showinfo("OK", f"{name} supprimé.")
            self.refresh_view(); self.refresh_callback()

    def toggle_selected(self):
        name = self.get_selected()
        if not name: return
        cur = plugin_enabled(name)
        set_plugin_enabled(name, not cur)
        self.refresh_view(); self.refresh_callback()

# =========================
# 🖥️ Fenêtre principale CTk
# =========================
class Launcher(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("🐉 KaRyuu Multi-App Launcher")
        self.geometry("900x600")

        self.nb = ctk.CTkTabview(self)
        self.nb.pack(fill="both", expand=True, padx=10, pady=10)

        # Onglet principal
        self.tab_apps = self.nb.add("🚀 Applications")
        self.tab_store = self.nb.add("🛒 Boutique")

        # Liste des plugins à gauche
        self.listbox = tk.Listbox(self.tab_apps, height=20, bg="#202020", fg="white")
        self.listbox.pack(side="left", fill="y", padx=10, pady=10)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)

        self.frame_content = ctk.CTkFrame(self.tab_apps)
        self.frame_content.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        self.store = Marketplace(self.tab_store, self.refresh_plugins)
        self.store.pack(fill="both", expand=True)

        ensure_dirs()
        self.refresh_plugins()

    def refresh_plugins(self):
        self.listbox.delete(0, tk.END)
        for name in list_plugins():
            if plugin_enabled(name):
                v = plugin_version(name)
                self.listbox.insert(tk.END, f"{name} (v{v})")

    def on_select(self, e=None):
        if not self.listbox.curselection(): return
        line = self.listbox.get(self.listbox.curselection()[0])
        name = line.split(" ")[0]
        self.open_plugin(name)

    def open_plugin(self, name):
        for w in self.frame_content.winfo_children(): w.destroy()
        try:
            if APP_ROOT not in sys.path: sys.path.insert(0, APP_ROOT)
            mod = __import__(f"plugins.{name}.app", fromlist=["app"])
            if hasattr(mod, "build_ui"):
                mod.build_ui(self.frame_content)
            else:
                ctk.CTkLabel(self.frame_content, text=f"{name} n’a pas de build_ui()").pack()
        except Exception as e:
            ctk.CTkLabel(self.frame_content, text=f"Erreur plugin : {e}", text_color="red").pack()

if __name__ == "__main__":
    app = Launcher()
    app.mainloop()
