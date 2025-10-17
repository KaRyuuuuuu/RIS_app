# ===============================
# 📁 Fichier : plugins/chronos/app.py
# 📍 Emplacement : KaRyuuMultiApp/plugins/chronos/app.py
# ===============================

import customtkinter as ctk
from datetime import datetime, timedelta

def build_ui(parent):
    """Construit l'interface du plugin Chronos (calcul des Pit Windows)"""
    frame = ctk.CTkFrame(parent)
    frame.pack(fill="both", expand=True, padx=20, pady=20)

    title = ctk.CTkLabel(frame, text="⏱️ Calculateur de Pit Windows", font=ctk.CTkFont(size=20, weight="bold"))
    title.pack(pady=(0, 15))

    entry = ctk.CTkEntry(frame, placeholder_text="Heure de départ (HH:MM)")
    entry.pack(pady=5)

    combo = ctk.CTkComboBox(frame, values=["6h", "8h", "12h", "25h"])
    combo.set("6h")
    combo.pack(pady=5)

    output = ctk.CTkTextbox(frame, height=200)
    output.pack(fill="both", expand=True, pady=10)

    def calc():
        try:
            start = datetime.strptime(entry.get(), "%H:%M")
            dur_h = int(combo.get().replace("h", ""))
            end = start + timedelta(hours=dur_h)
            cur = start
            i = 1
            output.delete("0.0", "end")
            while cur <= end:
                a = (cur - timedelta(minutes=10)).strftime("%H:%M")
                b = (cur + timedelta(minutes=10)).strftime("%H:%M")
                output.insert("end", f"Fenêtre {i} : {a} → {b}\n")
                cur += timedelta(minutes=40)
                i += 1
        except Exception:
            output.delete("0.0", "end")
            output.insert("end", "⚠️ Format invalide (HH:MM)")

    ctk.CTkButton(frame, text="Calculer", command=calc).pack(pady=5)
