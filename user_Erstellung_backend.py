# -*- coding: utf-8 -*-
# /mnt/ssd/user_management/user_Erstellung_backend.py
import subprocess
import json
import datetime
import yaml
import os
import csv
import sys

CONFIG_FILE = "/mnt/ssd/user_management/config_studiengang.yaml"
aktuelle_User = "/mnt/ssd/user_management/aktuelle_User.csv"
LOG_FILE = "/mnt/ssd/user_management/omv_user_management.log"

# ------ Ausgabe in die Log-Datei ------
def log_message(message):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"{timestamp} - {message}\n")

def run_command(cmd_list):
    try:
        log_message(f"Aktion ... wird ausgeführt: {' '.join(cmd_list)}")
        result = subprocess.run(cmd_list, capture_output=True, text=True, check=True)
        log_message(f"Aktion erfolgreich: {result.stdout}")
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        log_message(f"Aktion fehlgeschlagen: {e.cmd}")
        log_message(f"Stdout: {e.stdout}")
        log_message(f"Stderr: {e.stderr}")
        raise
    except Exception as e:
        log_message(f"Es ist ein Fehler aufgetreten: {e}")
        raise

def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return yaml.safe_load(f)

def create_user(username, password, studiengang):
    config = load_config()
    studiengang_config = config['studiengaenge'].get(studiengang)

    if not studiengang_config:
        raise ValueError(f"Studiengang '{studiengang}' nicht in der Konfiguration gefunden.")

    # 1. Benutzer in OMV erstellen (gleichzeitig wird ein Linux-User erstellt)
    log_message(f"Nutzer '{username}' wird in OMV erstellt...")
    try:
        run_command(["sudo", "omv-rpc", "User", "create", username, password, "shell=/bin/false"]) # shell=/bin/false für eingeschränkten Zugriff
        log_message(f"'{username}' wurde erfolgreich in OMV erstellt.")
    except Exception as e:
        log_message(f"Fehler beim Erstellen von '{username}': {e}")
        raise
    # 1.5 Gruppen zuweisen
    groups_to_assign = studiengang_config.get('groups', []) # Hole Gruppen aus der Konfiguration, Standard ist leere Liste
    
    for group_name in groups_to_assign:
        try:
            log_message(f"Nutzer '{username}' wird zur Gruppe '{group_name}' hinzugefügt...")
            # omv-rpc Group addmember <groupname> <username>
            run_command(["sudo", "omv-rpc", "Group", "addMember", group_name, username])
            log_message(f"Nutzer '{username}' erfolgreich zur Gruppe '{group_name}' hinzugefügt.")
        except Exception as e:
            log_message(f"WARNUNG: Fehler beim Hinzufügen von '{username}' zur Gruppe '{group_name}': {e}")
            
    # 2. Home-Verzeichnis erstellen und Berechtigungen setzen
    home_path_base = studiengang_config['home_path']
    user_home_dir = os.path.join(home_path_base, username)

    log_message(f"Home directory '{user_home_dir}' wird für '{username}' erstellt...")
    try:
        os.makedirs(user_home_dir, exist_ok=True)
        # Besitzer und Gruppe auf den neuen Benutzer setzen
        run_command(["sudo", "chown", f"{username}:{username}", user_home_dir])
        run_command(["sudo", "chmod", "700", user_home_dir]) # Nur Besitzer darf lesen/schreiben/ausführen
        log_message(f"Home directory '{user_home_dir}' wurde erfolgreich mit entsprechenden Premissions erstellt.")
    except Exception as e:
        log_message(f"Fehler beim setzen der Permissions des Home directory '{user_home_dir}': {e}")
        # Versuch, den zuvor erstellten OMV-Benutzer wieder zu löschen, wenn Home-Verzeichnis fehlschlägt
        delete_user(username, bypass_expiry=True) # bypass_expiry, da er noch nicht in CSV ist
        raise

    # 3. Ablaufdatum berechnen und zur CSV hinzufügen
    expiry_date = (datetime.date.today() + datetime.timedelta(days=studiengang_config['dauer_jahre'] * 365)).strftime("%Y-%m-%d")
    log_message(f"Account von '{username}' wird am {expiry_date} ablaufen.")
    
    users_in_csv = []
    # Zuerst alle vorhandenen Einträge lesen (ohne Header)
    if os.path.exists(aktuelle_User):
        with open(aktuelle_User, 'r', newline='') as csvfile:
            reader = csv.reader(csvfile, delimiter=';') # ACHTUNG: Delimiter von 'aktuelle_User.csv' muss Semikolon sein
            next(reader, None) # Header überspringen
            for row in reader:
                if row and len(row) >= 2:
                    users_in_csv.append(row)

    # Neuen Benutzer hinzufügen
    users_in_csv.append([username, expiry_date])
    
    with open(aktuelle_User, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([username, expiry_date])
    log_message("Nutzer wurde der Liste von aktuellen Nutzern (CSV) hinzugefügt.")

    # 4. OMV Konfiguration anwenden
    log_message("Anwenden der OMV Konfiguration...")
    try:
        run_command(["sudo", "omv-rpc", "Config", "apply"])
        log_message("OMV Konfiguration war erfolgreich.")
    except Exception as e:
        log_message(f"Fehler beim Anwenden der OMV Konfiguration: {e}")
        raise

    log_message(f"Account von '{username}' wurde erfolgreich erstellt!")

def delete_user(username, bypass_expiry=False):
    log_message(f"User '{username}' wird gelöscht...")
    try:
        # Löscht den Benutzer aus OMV und Linux, inkl. Home-Verzeichnis (OMV macht das meist automatisch)
        run_command(["sudo", "omv-rpc", "User", "delete", username, "--force"])
        log_message(f"User '{username}' wurde erfolgreich aus OMV und Linux gelöscht.")

        # Entferne den Benutzer aus der user_expiry.csv
        if not bypass_expiry: # Wenn es ein regulärer Löschvorgang ist, nicht wenn ein Fehler beim Erstellen auftritt
            update_expiry_csv(username)
            log_message(f"Nutzer '{username}' wurde aus aktuelle_User gelöscht.")

        # OMV Konfiguration anwenden
        log_message("Anwenden der OMV Konfiguration...")
        run_command(["sudo", "omv-rpc", "Config", "apply"])
        log_message("OMV Konfiguration war erfolgreich.")
        return True
    except Exception as e:
        log_message(f"'{username}' konnte nicht gelöscht werden: {e}")
        return False

def update_expiry_csv(username_to_remove=None):
    users = []
    if os.path.exists(aktuelle_User):
        with open(aktuelle_User, 'r', newline='') as csvfile:
            reader = csv.reader(csvfile, delimiter=';')
            next(reader, None) # Header überspringen
            for row in reader:
                if row and len(row) >= 2: 
                    if row[0].strip() != username_to_remove: 
                        users.append(row)
    
    with open(aktuelle_User, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile, delimiter=';') 
        writer.writerow(["Name", "Ablaufdatum in YYYY-MM-DD", "Zeile wird beim Lesen ignoriert!"])
        writer.writerows(users)
def check_and_delete_expired_users():
    log_message("Abgelaufene User werden gelöscht.")
    current_date = datetime.date.today()
    users_to_keep = []
    AnzahlGelöschter = 0

    if not os.path.exists(aktuelle_User):
        log_message("CSV aktuelle_User.csv wurde nicht gefunden. Ausführung für heute abgebrochen.")
        return

    with open(aktuelle_User, 'r', newline='') as csvfile:
        reader = csv.reader(csvfile, delimiter=';')
        next(reader, None) # Header überspringen
        for row in reader:
            if not row or len(row) < 2:
                log_message(f"Zeile in der CSV ist nicht richtig formatiert. Bitte überprüfen. Zeile: {row}")
                continue
            
            username = row[0].strip()
            ablaufdatum = row[1].strip()

            try:
                expiry_date = datetime.datetime.strptime(ablaufdatum, "%Y-%m-%d").date()
            except ValueError:
                log_message(f"Datum nicht richtig formatiert. '{username}': '{ablaufdatum}'. Nutzer wird vorerst beibehalten.")
                users_to_keep.append(row)
                continue

            if expiry_date <= current_date:
                log_message(f"Nutzer '{username}' ist seit dem {ablaufdatum} abgelaufen. Wird gelöscht.")
                if delete_user(username, bypass_expiry=True):
                    AnzahlGelöschter += 1
                else:
                    log_message(f"Löschen von '{username}' fehlgeschlagen.")
                    users_to_keep.append(row) # Wenn Löschen fehlschlägt, in Liste belassen
            else:
                users_to_keep.append(row)
    
    # Schreibe die aktualisierte Liste zurück in die CSV
    with open(aktuelle_User, 'w', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Name", "Ablaufdatum in YYYY-MM-DD", "Zeile wird beim Lesen ignoriert!"]) # <--- Header wieder hinzufügen
        writer.writerows(users_to_keep)
    
    log_message(f"Prüfung abgeschlossen. Es wurden {AnzahlGelöschter} Nutzer gelöscht.")


if __name__ == '__main__':
    # Dieser Teil wird ausgeführt, wenn das Skript direkt aufgerufen wird (z.B. vom Cronjob)
    # Erwartet ein Argument für die Aktion
    if len(sys.argv) > 1:
        action = sys.argv[1]
        if action == "create":
            if len(sys.argv) == 5:
                username = sys.argv[2]
                password = sys.argv[3]
                studiengang = sys.argv[4]
                try:
                    create_user(username, password, studiengang)
                except Exception as e:
                    log_message(f"Error bei Nutzererstellung über CLI: {e}")
                    sys.exit(1)
            else:
                log_message("Ausgeführt: python user_Erstellung.py create <username> <password> <studiengang>")
                sys.exit(1)
        elif action == "delete_expired":
            try:
                check_and_delete_expired_users()
            except Exception as e:
                log_message(f"Es ist ein Fehler beim Prüfen nach abgelaufenen Nutzern aufgetreten: {e}")
                sys.exit(1)
        elif action == "get_studiengaenge":
            try:
                config = load_config()
                print(json.dumps(list(config['studiengaenge'].keys())))
            except Exception as e:
                log_message(f"Fehler beim getten der Studiengaenge: {e}")
                sys.exit(1)
        else:
            log_message(f"Unbekannter Befehl: {action}")
            sys.exit(1)
    else:
        log_message("Es wurde keine Aktion mitgegeben. Bitte entweder 'create', 'delete_expired' oder 'get_studiengaenge' angeben.")
        sys.exit(1)

    log_message("Ausführung abgeschlossen.")
