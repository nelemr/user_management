# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, messagebox
import paramiko
import json

# --- Konfiguration für SSH-Verbindung zum Raspberry Pi ---
PI_HOST = "192.168.1.100" # IP-Adresse deines Raspberry Pis
PI_USER = "bosch"      # Der Benutzer auf dem Pi, der die Skripte ausführen darf (aus Teil 1)
# Wenn der Pi-Benutzer kein Passwort hat (nicht empfohlen für SSH) oder über SSH-Keys authentifiziert wird
# Wenn du ein Passwort benötigst, musst du es hier eintragen oder in der GUI abfragen.
# Für Produktivsysteme ist SSH-Key-Authentifizierung dringend empfohlen!
PI_PASSWORD = "robert" # NUR für Testzwecke, besser ist SSH-Key!
# -----------------------------------------------------------

class UserCreatorGUI:
    def __init__(self, master):
        self.master = master
        master.title("OMV Benutzer Erstellung")
        master.geometry("400x300")

        self.ssh_client = paramiko.SSHClient()
        self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            self.ssh_client.connect(hostname=PI_HOST, username=PI_USER, password=PI_PASSWORD) # Optional: key_filename='/path/to/your/ssh/key'
            self.studiengaenge = self._get_studiengaenge_from_pi()
            self.create_widgets()
        except paramiko.AuthenticationException:
            messagebox.showerror("Fehler", "SSH Authentifizierung fehlgeschlagen. Bitte Benutzernamen/Passwort prüfen oder SSH-Key einrichten.")
            master.destroy()
        except paramiko.SSHException as e:
            messagebox.showerror("Fehler", f"SSH Verbindung fehlgeschlagen: {e}")
            master.destroy()
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Laden der Studiengänge vom Pi: {e}")
            master.destroy()

    def _get_studiengaenge_from_pi(self):
        # Ruft das Backend-Skript auf, um die Liste der Studiengänge zu erhalten
        stdin, stdout, stderr = self.ssh_client.exec_command("python3 /mnt/ssd/user_management/user_Erstellung_backend.py get_studiengaenge")
        error = stderr.read().decode().strip()
        if error:
            raise Exception(f"Fehler beim Abrufen der Studiengänge: {error}")
        studiengaenge_json = stdout.read().decode().strip()
        return json.loads(studiengaenge_json)

    def create_widgets(self):
        # Labels
        ttk.Label(self.master, text="Benutzername:").grid(row=0, column=0, padx=10, pady=5, sticky="w")
        ttk.Label(self.master, text="Passwort:").grid(row=1, column=0, padx=10, pady=5, sticky="w")
        ttk.Label(self.master, text="Passwort (wiederholen):").grid(row=2, column=0, padx=10, pady=5, sticky="w")
        ttk.Label(self.master, text="Studiengang:").grid(row=3, column=0, padx=10, pady=5, sticky="w")

        # Entry fields
        self.username_entry = ttk.Entry(self.master)
        self.username_entry.grid(row=0, column=1, padx=10, pady=5, sticky="ew")

        self.password_entry = ttk.Entry(self.master, show="*")
        self.password_entry.grid(row=1, column=1, padx=10, pady=5, sticky="ew")

        self.password_confirm_entry = ttk.Entry(self.master, show="*")
        self.password_confirm_entry.grid(row=2, column=1, padx=10, pady=5, sticky="ew")

        # Studiengang Dropdown
        self.studiengang_var = tk.StringVar(self.master)
        if self.studiengaenge:
            self.studiengang_var.set(self.studiengaenge[0]) # Erster Studiengang als Standard
            self.studiengang_menu = ttk.OptionMenu(self.master, self.studiengang_var, self.studiengaenge[0], *self.studiengaenge)
        else:
            self.studiengang_menu = ttk.OptionMenu(self.master, self.studiengang_var, "Keine Studiengänge gefunden")
            self.studiengang_menu["state"] = "disabled" # Deaktivieren, wenn keine Studiengänge
        self.studiengang_menu.grid(row=3, column=1, padx=10, pady=5, sticky="ew")

        # Create button
        self.create_button = ttk.Button(self.master, text="Benutzer erstellen", command=self.create_user_action)
        self.create_button.grid(row=4, column=0, columnspan=2, pady=10)

        # Status label
        self.status_label = ttk.Label(self.master, text="", foreground="blue")
        self.status_label.grid(row=5, column=0, columnspan=2, pady=5)

    def create_user_action(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        password_confirm = self.password_confirm_entry.get()
        studiengang = self.studiengang_var.get()

        if not username or not password or not studiengang:
            messagebox.showwarning("Eingabefehler", "Alle Felder müssen ausgefüllt sein.")
            return

        if password != password_confirm:
            messagebox.showwarning("Eingabefehler", "Die Passwörter stimmen nicht überein.")
            return
        
        if not self.studiengaenge or studiengang not in self.studiengaenge:
            messagebox.showwarning("Eingabefehler", "Ungültiger Studiengang ausgewählt.")
            return

        self.status_label.config(text="Erstelle Benutzer...", foreground="blue")
        self.master.update_idletasks()

        try:
            command = f"python3 /mnt/ssd/user_management/user_Erstellung_backend.py create \"{username}\" \"{password}\" \"{studiengang}\""
            stdin, stdout, stderr = self.ssh_client.exec_command(command)
            
            # Ausgabe und Fehler lesen
            output = stdout.read().decode().strip()
            error = stderr.read().decode().strip()

            if error:
                messagebox.showerror("Fehler", f"Fehler bei der Benutzererstellung auf dem Pi:\n{error}\n{output}")
                self.status_label.config(text="Fehler!", foreground="red")
            else:
                messagebox.showinfo("Erfolg", f"Benutzer '{username}' erfolgreich erstellt und für '{studiengang}' konfiguriert.")
                self.status_label.config(text="Benutzer erfolgreich erstellt!", foreground="green")
                # Felder zurücksetzen
                self.username_entry.delete(0, tk.END)
                self.password_entry.delete(0, tk.END)
                self.password_confirm_entry.delete(0, tk.END)
                if self.studiengaenge:
                    self.studiengang_var.set(self.studiengaenge[0])
                else:
                    self.studiengang_var.set("Keine Studiengänge gefunden")

        except paramiko.SSHException as e:
            messagebox.showerror("SSH Fehler", f"SSH-Verbindungsfehler: {e}")
            self.status_label.config(text="SSH Fehler!", foreground="red")
        except Exception as e:
            messagebox.showerror("Fehler", f"Ein unerwarteter Fehler ist aufgetreten: {e}")
            self.status_label.config(text="Fehler!", foreground="red")

    def __del__(self):
        # Sicherstellen, dass die SSH-Verbindung beim Beenden geschlossen wird
        if self.ssh_client:
            self.ssh_client.close()

if __name__ == "__main__":
    root = tk.Tk()
    app = UserCreatorGUI(root)
    root.mainloop()
