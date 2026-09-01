# Copyright (c) 2017-2026 Joel Panther
# SPDX-License-Identifier: MIT
# Licensed under the MIT License. 

# Requires fastapi. Developed using v0.115.11-3
# Requires NodeJS. Developed using v20.18.1
# Requires puppeteer. Developed using v24.23.0
# Developed/tested using Python 3.13.3

# ===========================================================
# Regular challenges have the challenge_id range of 1 to 900.
# Secrets start with a challenge_id range of 901-999.
# Secrets between 901-949 are stand alone.
# Secrets between 950-999 require a PHP frontend.
# ===========================================================

from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
import asyncio
import docker
import re
import os
import mimetypes
import uvicorn
import random
import string
import shutil
import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional
from DynamicDifficulty import DynamicDifficultyScaler
from puppet_manager import terminate_puppet
from challenge_generator import createChallenge
from timer_service import start_hostname_timer
from db_connect import *

# TODO:
# Merge the provision_secret and provision_challenge functions.

# =============================
# Class objects
# =============================
dds = DynamicDifficultyScaler() # Create dynamic difficulty scaler
pool = ProcessPoolExecutor(max_workers=1)

# =============================
# Game engine variables
# =============================
STARTING_CHALLENGES = 20 # Change to set number of challenges to generate when a new game starts.
ADMIN_PASSWORD = "pg49kNKexFbx" # You will want to change this before you go live.

clients = set() # HTTP clients for web interface.
game_state = "standby" # Default: standby. Other states include: running, win, lose.
secrets_exhausted = False # Switch to disable secret generation. False = build secrets, True = don't build secrets.
flagcounter = 0 # Used in testing.

# Control flags for deploy_secret_check() 
worker_stop_event = asyncio.Event()
worker_task = None

# Web interface artefacts.
templates = Jinja2Templates(directory="templates")
mimetypes.add_type("application/javascript", ".mjs")

# =============================
# Optional: Custom flags
# =============================
# Custom flags are optional.
# Place custom flags in the 'CUSTOM_FLAG_LIST' list.
# Game will generate randomised flags if no custom flags in list or when list exhausted.
custom_flag_pool = [] # Initialise list. Leave empty. 
CUSTOM_FLAG_LIST = [] # Place hard-coded custom flags here. Optional.

# =============================
# Global timer artefacts
# =============================
TIMER_START = 7200  # Default new game starting time on the clock (in seconds).
SAVE_INTERVAL = 60  # Modify to set autosave intervals (in seconds).
timer_task: asyncio.Task | None = None # Tracks instances of timed challenges.
clock_reset_event = asyncio.Event() # Shared event to signal a timer reset/stop. 
timer_value = TIMER_START # Tracks current timer value. Updated by engine.
visible_total = TIMER_START # Total play time that has been visible to players. Updated by engine.
progress_value = 0  # 0-100%. Default is 0 (new game).

# =============================
# Filename + directory paths
# =============================
CHALLENGES_FILE = Path("deployed_challenges.json") # Where the current challenges are saved for reference.
SAVESTATE_FILE_PATH = Path("game_state.json") # Full game state save file.
PROGRESS_FILE_PATH = Path("progress.json") # Only tracks time and points.
os.makedirs("music", exist_ok=True) # Put optional music MP3 files here.
os.makedirs("puppet_logs", exist_ok=True) # Puppet logs live here.

# Duplicates anything written to console to a log file.
class Tee:
    def __init__(self, filename, mode="a", stream=None):
        self.stream = stream or sys.stdout
        self.file = open(filename, mode, buffering=1, encoding="utf-8")

    def write(self, message):
        self.stream.write(message)
        self.file.write(message)

    def flush(self):
        self.stream.flush()
        self.file.flush()

    def isatty(self):
        return self.stream.isatty()

    def close(self):
        self.file.close()

    def __getattr__(self, name):
        return getattr(self.stream, name)

# Returns the current time.
def now():
    # return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return datetime.now().strftime('%H:%M:%S')

# Returns custom flag, if applicable.
def get_custom_flag():
    """
    If custom flags have been implemented, this function returns one from the custom_flag_pool list. 
    The flag is then removed from the list, so it is not used again.
    """
    global custom_flag_pool
    if not custom_flag_pool: # Check if list is empty
        return ""
    flag = str(custom_flag_pool[0])
    del custom_flag_pool[0]
    return str(flag)

# Check to see if engine needs to automatically provision a secret challenge.
async def deploy_secret_check():
    """
    Checks to see if conditions have been met for a secret challenge to be provisioned.
    If conditions are met, a secret challenge is provisioned.
    If conditions not met, waits 5 minutes and checks again.
    If all secret challenges have been provisioned, function stops checking.
    """
    worker_stop_event.clear() # Clear the stop signal when starting.
    while not worker_stop_event.is_set():
        await asyncio.sleep(300) # 5 minutes.
        time_reward = int(round(dds.calculate_time_reward()))
        print(f"[{now()}][*] Deploy secret check? Time Reward is currently:",time_reward)
        if time_reward >= 5:
            print(f"[{now()}][*] Attempting to build new secret/bonus challenge...")
            if secrets_exhausted == True:
                print(f"[{now()}][!] No more secrets can be generated for this game, secrets exchuasted.")
                print(f"[{now()}][*] Stopping 'deploy_secret_checks' task/thread...")
                worker_stop_event.set()
            else:
                print(f"[{now()}][*] Building new secret/bonus challenge...")
                values = provision_secret()
                if values is not None:
                    domain, system_name, challenge_id, corporation, challenge_username, challenge_password = values
                    await broadcast_new_challenge(
                    system_name, challenge_id, domain, corporation,
                    challenge_username, challenge_password)
                    await asyncio.sleep(0) # Flush
                    print(f"[{now()}][*] Secret build complete.")
                else:
                    print(f"[{now()}][!] WARNING: No secret challenge to build.")
        
# Creates the task for deploy_secret_check().
def start_secret_check_task():
    global worker_task
    # print(f"[{now()}][*] Starting 'deploy_secret_checks' task/thread...")
    if worker_task and not worker_task.done():
        return  # Already running.
    # Create background asyncio task.
    worker_task = asyncio.create_task(deploy_secret_check())

# Kills the task for deploy_secret_check().
def stop_secret_check_task():
    global worker_task
    print(f"[{now()}][*] Stopping 'deploy_secret_checks' task/thread...")
    try:
        worker_stop_event.set() # Tells the loop to stop.
    except Exception as e:
        print(f"[{now()}][!] WARNING: {e}") # Probably not running.
    try:
        if worker_task is None: # No worker has been started.
            return
        if worker_task.done(): # Worker exists but has already finished.
            return
    except Exception as e:
        print(f"[{now()}][!] WARNING: {e}") # Probably not running.

# Build music manifest JSON file.
def create_music_manifest(music_dir="music"):
    """
    Scans the given directory recursively for .mp3 files
    and writes their relative paths to a JSON manifest.
    """
    output_file = os.path.join(music_dir, "tracks.json")
    mp3_files = []

    # Ensure the directory exists.
    if not os.path.isdir(music_dir):
        print(f"[{now()}][!] ERROR: Directory '{music_dir}' not found.")
        return

    # Walk through the directory and subdirectories.
    for root, dirs, files in os.walk(music_dir):
        for file in files:
            if file.lower().endswith(".mp3"):
                rel_path = os.path.relpath(os.path.join(root, file), start=os.getcwd())
                mp3_files.append(rel_path.replace("\\", "/"))

    # Write the list to a JSON file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(mp3_files, f, indent=2)

    print(f"[{now()}][*] Manifest created: {output_file} ({len(mp3_files)} tracks)")

# Remove challenge from challenge JSON file.
def delete_system_by_challenge_id(challenge_id, backup: bool = True):
    """
    Delete system entries matching 'challenge_id' from JSON file.
    Args:
        challenge_id: The challenge_id to remove (int or str).
        backup: If True, writes a .bak copy before modifying.
    """
    json_path = CHALLENGES_FILE
    if not json_path.exists():
        print(f"[{now()}][!] ERROR: No such file: {json_path}")
        raise 

    # Load JSON.
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict) or "domains" not in data or not isinstance(data["domains"], list):
        print(f"[{now()}][!] ERROR: Unexpected JSON structure. Top-level 'domains' list is required.")
        raise

    # Normalise for comparison (handle int/str mismatches).
    target = str(challenge_id)

    removed_total = 0
    for domain in data["domains"]:
        systems = domain.get("systems")
        if not isinstance(systems, list):
            continue

        kept = []
        removed_here = 0
        for s in systems:
            # Only treat dicts with 'challenge_id' as candidates.
            cid = str(s.get("challenge_id")) if isinstance(s, dict) and "challenge_id" in s else None
            if cid is not None and cid == target:
                removed_here += 1
            else:
                kept.append(s)

        if removed_here:
            domain["systems"] = kept
            removed_total += removed_here

    # If nothing was removed, do not rewrite the file.
    if removed_total == 0:
        print(f"[{now()}][*] ERROR: No challenge removed from JSON?")
        return

    # Optional backup.
    if backup:
        shutil.copy2(json_path, json_path.with_suffix(json_path.suffix + ".bak"))

    # Write updated JSON (pretty-printed).
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    #return removed_total
    return

# Removes challenge artefacts after it has been removed by the engine.
def challenge_cleanup(challenge_id):
    print(f"[{now()}][*] Removing puppet, if applicable...")
    terminate_puppet(challenge_id)
    delete_system_by_challenge_id(challenge_id)
    print(f"[{now()}][*] Removing database, if applicable...")
    try:
        conn = master_db()
        cursor = conn.cursor()
        cursor.execute(f"DROP DATABASE `{challenge_id}`")
        conn.commit()

    except mysql.connector.Error as e:
        print(f"[{now()}][!] WARNING: Maybe no database used in this challenge?: {e}")
    print(f"[{now()}][*] Removing users...")
    try:
        cursor.execute(f"DROP USER `readonly{challenge_id}`@``")
        conn.commit()
    except mysql.connector.Error as e:
        print(f"[{now()}][!] ERROR: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    print(f"[{now()}][*] Removing container...")
    client = docker.from_env() # Connect to Docker.
    name = f"challenge{challenge_id}"
    # Remove container with matching "name".
    try:
        containers = client.containers.list(all=True, filters={"name": name})
        if not containers:
            print(f"[{now()}][*] No container found with name '{name}'")
        for container in containers:
            print(f"[{now()}][*] Stopping container: {container.name} ({container.id[:12]})")
            try:
                container.stop()
            except docker.errors.APIError as e: 
                print(f"[{now()}][!] WARNING: Could not stop container: {e}")
            print(f"[{now()}][*] Removing container: {container.name}")
            container.remove(force=True)
    except docker.errors.APIError as e: 
        print(f"[{now()}][!] Error finding/removing container: {e}")

    print(f"[{now()}][*] Updating pool status...")
    try:
        conn = database_connection()
        cursor = conn.cursor()
        if int(challenge_id) >= 900: # If it has an ID that aligns with a secret...
            sql = """
            UPDATE `secret`
            SET `deployed` = '0',
                `complete` = '1',
                `flag` = '',
                `container` = ''
            WHERE `id` = %s
            """
        else: 
            sql = """
            UPDATE `pool`
            SET `deployed` = '0',
                `complete` = '1',
                `flag` = '',
                `container` = ''
            WHERE `id` = %s
            """
        cursor.execute(sql, (challenge_id,))
        conn.commit()
    except mysql.connector.Error as err:
        print(f"[{now()}][!] ERROR: {err}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
    
    # Remove Docker image(s) with matching name.
    try:
        images = client.images.list(name=name)
        if not images:
            print(f"[{now()}][!] WARNING: No image found with name '{name}'")
        for image in images:
            tags = ", ".join(image.tags) if image.tags else image.short_id
            print(f"[{now()}][*] Removing image: {tags}")
            client.images.remove(image.id, force=True)
    except docker.errors.APIError as e:
        print(f"[{now()}][!] Error removing image: {e}")
        return
    except Exception as e:
        print(f"[{now()}][!] ERROR: {e}")
        return

    print(f"[{now()}][*] Challenge has been removed.")
    return

# Validate submitted code against known flags in challenge database.
def code_attempt(challenge_id, submitted_code, system_name):
    conn = database_connection()
    clean_code = re.sub(r'[^A-Za-z0-9]', '', submitted_code) # Removes unsafe/unused characters from flag submission.
    print(f"[{now()}][*] Cleaned attempt:", clean_code)

    if system_name == "data corruption detected": # Check to see if secret challenge.
        print(f"[{now()}][*] Validating SECRET for", challenge_id)
        query = "SELECT 1 FROM secret WHERE id = %s AND flag = %s LIMIT 1;"
    else:
        print(f"[{now()}][*] Validating code for", challenge_id)
        query = "SELECT 1 FROM pool WHERE id = %s AND flag = %s LIMIT 1;"

    try:
        cur = conn.cursor()
        cur.execute(query, (int(challenge_id), clean_code))
        row = cur.fetchone()
        cur.close()
        return row is not None

    except Exception as e:
        print(f"[{now()}][!] ERROR:", e)
        return False
    
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

# Append a new challenge to JSON file for distribution to clients.
def append_system(domain, name, folder, system_id, corporation, challenge_id, challenge_username, challenge_password):
    """
    When a challenge is provisioned, its details are recorded in a JSON file.
    This JSON file is distributed to clients that visit the main CTF web server to help populate web page.
    This function appends a given system under its domain in a JSON file.

    JSON structure:
    {
      "domains": [
        {
          "domain": "...",
          "systems": [
            {
              "name": "...",
              "folder": "...",
              "system_id": "...",
              "corporation": "...",
              "challenge_id": "...",
              "username": "...",
              "password": "..."
            }
          ]
        },
        ...
      ]
    }
    """
    print(f"[{now()}][*] Data to save:", domain, name, folder, system_id, corporation, challenge_id, challenge_username, challenge_password)

    # Load existing data or initialise new structure.
    if CHALLENGES_FILE.exists():
        try:
            data = json.loads(CHALLENGES_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"[{now()}][*] File empty or corrupt, starting fresh.")
            data = {"domains": []}
    else:
        data = {"domains": []}

    # Ensure top-level shape.
    if not isinstance(data, dict) or "domains" not in data or not isinstance(data["domains"], list):
        data = {"domains": []}

    # Find (or create) the domain entry.
    domain_entry: Dict[str, Any] | None = next(
        (d for d in data["domains"] if d.get("domain") == domain),
        None
    )
    if domain_entry is None:
        domain_entry = {"domain": domain, "systems": []}
        data["domains"].append(domain_entry)

    # Build the challenge record.
    system_record = {
        "name": name,
        "folder": folder,
        "system_id": system_id,
        "corporation": corporation,
        "challenge_id": challenge_id,
        "username": challenge_username,
        "password": challenge_password,
    }
    print(f"[{now()}][*] Record to save:", system_record)

    # Append the new challenge.
    domain_entry["systems"].append(system_record)

    # Write back.
    tmp_file = CHALLENGES_FILE.with_suffix(".tmp")
    tmp_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_file.replace(CHALLENGES_FILE)
    print(f"[{now()}][*] Challenge data saved to JSON.")
    return

# Select a new secret/special/bonus challenge.
def provision_secret(challenge_type="secret"):
    """
    The challenge_type="secret" is for the challenge generator,
    so it knows what type of challenge it needs to build.
    This function forces the creation of a secret challenge.
    """
    global secrets_exhausted
    if secrets_exhausted == True:
        print(f"[{now()}][!] WARNING: Building a secret challenge was attempted, but secrets are exchausted.")
        return
    
    conn = database_connection()
    cursor = conn.cursor()
    print(f"[{now()}][*] Building a secret challenge...")
    
    cursor.execute("""
    SELECT id, type, flag
    FROM secret
    WHERE deployed = 0 AND complete = 0
    ORDER BY RAND()
    LIMIT 1
    """)
    row = cursor.fetchone() # Fetch secret challenge scenario from pool.

    if row:
        challenge_id, secret_type, flag_value, = row
        print(f"[{now()}][*] Secret ID:", challenge_id)
        print(f"[{now()}][*] Secret Type:", secret_type)
    else:
        cursor.close()
        conn.close()
        print(f"[{now()}][!] WARNING: No more secrets available.")
        secrets_exhausted = True # Switch to stop provisioning more secret challenges.
        return
    
    # Checks for valid custom flags.
    if flag_value == "": 
        flag_value = str(get_custom_flag())

    # Some secrets have hard-coded flags. For others, will need to generate flag.
    if flag_value == "": 
        # Generate the flag, only using ASCII letters and digits.
        characters = string.ascii_letters + string.digits  # A-Z, a-z, 0-9
        flag_value = ''.join(random.choices(characters, k=20))
        print(f"[{now()}][*] {challenge_id} assigned flag: {flag_value}")

    # Grab a random corporation.
    query = "SELECT name FROM corporations ORDER BY RAND() LIMIT 1"
    cursor.execute(query)
    namerow = cursor.fetchone()
    corporation = str(namerow[0])
    
    # Pre-filled secret variables for challenge generator.
    domain = "secret"
    system_name = "secret"
    folder = "secret"
    system_id = "0"

    # Create the new challenge.
    container_id, challenge_username, challenge_password = createChallenge(
        domain, system_name, folder, system_id, corporation, challenge_id, flag_value, cursor, challenge_type)

    # Update database to record flag, container_id, and deployment status of secret challenge.
    cursor.execute("""
        UPDATE secret
        SET deployed = 1, flag = %s, container = %s
        WHERE id = %s
    """, (flag_value, container_id, challenge_id))
    conn.commit()
    print(f"[{now()}][*] {challenge_id} container saved to database.")
    cursor.close()
    conn.close()

    print(f"[{now()}][*] Saving secret challenge to JSON for persistence.")
    append_system(domain, system_name, folder, system_id, corporation, challenge_id, challenge_username, challenge_password)
    print(f"[{now()}][*] SUCCESS: Secret challenge build completed!")
    return domain, system_name, challenge_id, secret_type, challenge_username, challenge_password

# Select a new challenge from the available pool.
def provision_challenge(challenge_type="none"):
    """
    Function determines which challenge to build and passes variables to the challenge_generator class. 
    The challenge_type parameter is used when calling the challenge generator via createChallenge(...).
    Supported values:
     - none (the challenge generator will randomly select a challenge type to make)
     - web (web application challenge)
     - ssh (challenge with an entry point via SSH)
     - secret (secret/bonus challenge)
    """
    flag_value = ""
    conn = database_connection()
    cursor = conn.cursor()
    
    print(f"[{now()}][*] Building a challenge...")
    cursor.execute("""
    SELECT id, corporation, system
    FROM pool
    WHERE deployed = 0
    ORDER BY RAND()
    LIMIT 1
    """)
    row = cursor.fetchone() # Fetch challenge scenario from pool.

    if row:
        challenge_id, corporation, system_id = row
        # print(f"[{now()}][*] Challenge ID:", challenge_id)
        # print(f"[{now()}][*] Corporation:", corporation)
        # print(f"[{now()}][*] System ID:", system_id)
    else:
        print(f"[{now()}][!] WARNING: Problem building challenge. No available challenges.")
        cursor.close()
        conn.close()
        return

    cursor.execute("""
        SELECT system, folder, domain
        FROM systems
        WHERE id = %s
        LIMIT 1
    """, (system_id,))
    q2 = cursor.fetchone() # Fetch details on the challenge.

    if q2:
        system_name, folder, domain = q2
        # print(f"[{now()}][*] System Name:", system_name)
        # print(f"[{now()}][*] System Folder:", folder)
        # print(f"[{now()}][*] Domain:", domain)
    else:
        print(f"[{now()}][!] ERROR: Problem locating information for System ID:", system_id)
        raise
    
    # Checks for a valid custom flag.
    if flag_value == "": 
        flag_value = str(get_custom_flag())
    
    # Generate the flag, using only ASCII letters and digits.
    if flag_value == "":
        characters = string.ascii_letters + string.digits  # A-Z, a-z, 0-9
        flag_value = ''.join(random.choices(characters, k=20))
    print(f"[{now()}][*] {challenge_id} assigned flag: {flag_value}")

    # Create the new challenge.
    container_id, challenge_username, challenge_password = createChallenge(
        domain, system_name, folder, system_id, corporation, challenge_id, flag_value, cursor, challenge_type)

    # Update database to record flag, container_id, and deployment status.
    cursor.execute("""
        UPDATE pool
        SET deployed = 1, flag = %s, container = %s
        WHERE id = %s
    """, (flag_value, container_id, challenge_id))
    conn.commit()
    print(f"[{now()}][*] {challenge_id} container saved to database.")
    cursor.close()
    conn.close()

    print(f"[{now()}][*] Saving challenge to JSON for persistence...")
    append_system(domain, system_name, folder, system_id, corporation, challenge_id, challenge_username, challenge_password)
    print(f"[{now()}][*] SUCCESS: Challenge build completed!")
    return domain, system_name, challenge_id, corporation, challenge_username, challenge_password

# Save the current timer and progress/points values to a JSON file.
def save_progress():
    """
    The dds.save_state(...) function likely replaces this function,
    but its kept here until its verified there are no consequences to
    it being removed. Only saves current timer value and points.
    Can possibly retire this function.
    """
    global timer_value, visible_total, progress_value
    data = {
        "timer_value": timer_value,
        "visible_total": visible_total,
        "progress_value": progress_value
    }
    with open(PROGRESS_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

# Load current game's timer and progress/points from JSON file. 
def load_progress():
    """
    The dds.load_state(...) function likely replaces this function,
    but its kept here until its verified there are no consequences to
    it being removed. Only saves current timer value and points.
    Can possibly retire this function.
    """
    global timer_value, visible_total, progress_value
    print(f"[{now()}][*] Attempting to load previous game state from JSON file...")
    if not os.path.exists(PROGRESS_FILE_PATH):
        print(f"[{now()}][*] File '{PROGRESS_FILE_PATH}' not found. Skipping load.")
        return False
    try:
        with open(PROGRESS_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[{now()}][!] ERROR: Error reading '{PROGRESS_FILE_PATH}': {e}")
        return False

    # Extract variables from JSON.
    timer_value = data.get("timer_value")
    visible_total = data.get("visible_total")
    progress_value = data.get("progress_value")
    return True

# Changes format of time from an int to a string.
def format_time(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02}:{minutes:02}:{secs:02}"

# Starts countdown timer and transmits time to clients.
async def countdown_timer():
    """
    This function controls the countdown timer and updates game state
    and clients based on time remaining on the clock.
    Server is the authority on time. 

    Every second, this function checks the global 'timer_value' variable.
    - If timer_value <= 0, the "lose" state is triggered.
    - While timer_value > 0, clients are sent current time.
    
    This function also triggers the auto-save function when 
    last_save_counter >= SAVE_INTERVAL.
    """
    print(f"[{now()}][*] Countdown timer starting...")
    global timer_value, visible_total
    last_save_counter = 0
    clock_reset_event.clear() # Ensure it starts.
    try:
        while not clock_reset_event.is_set():
            await asyncio.sleep(1)
            if timer_value <= 0:
                await win_or_lose("lose")
                clock_reset_event.clear()
                return
            if timer_value > 0:
                timer_value -= 1
                visible_total += 1
                dds.set_visible_time(remaining=timer_value/60, total=visible_total/60)
                last_save_counter += 1
                timer_percent = int((TIMER_START - timer_value) / TIMER_START * 100)
               # await update_banner({"type": "containment_banner", "value": timer_percent}) # Aesthetic function.
                await broadcast_to_clients({"type": "containment_banner", "value": timer_percent}) # Aesthetic function.
                if last_save_counter >= SAVE_INTERVAL:
                    dds.save_state()
                    save_progress()
                    last_save_counter = 0 # Reset counter for auto saving.
                await broadcast_current_timer_value() # Send current time to clients.
    except asyncio.CancelledError:
        raise
    finally:
        clock_reset_event.clear() # Ensure the next start begins.
        print(f"[{now()}][*] Countdown timer loop exited.")

# Broadcasts current countdown timer value to clients. Server is authority on time.
async def broadcast_current_timer_value():
    time_str = format_time(timer_value)   
    timer_percent = int((TIMER_START - timer_value) / TIMER_START * 100)    
    await broadcast_to_clients({
        "type": "tick",
        "time": time_str,
        "timer_percent": timer_percent,
        "progress": progress_value
    })

# When a new challenge is created, broadcast notify clients.
async def broadcast_new_challenge(system_name, challenge_id, domain, corporation, challenge_username, challenge_password):
    print(f"[{now()}][*] Broadcasting new challenge...")
    await broadcast_to_clients({
        "type": "newchallenge",
        "system_name": system_name,
        "challenge_id": challenge_id,
        "domain": domain,
        "corporation": corporation,
        "username": challenge_username,
        "password": challenge_password
    })

# When a challenge is removed, broadcast notify clients.
async def broadcast_remove_challenge(challenge_id, system_name, corporation):
    print(f"[{now()}][*] Broadcsting challenge removal...")
    await broadcast_to_clients({
        "type": "remove",
        "challenge_id": challenge_id,
        "system_name": system_name,
        "corporation": corporation
    })

# Broadcast a JSON payload to clients.
async def broadcast_to_clients(payload: dict):
    for client in clients.copy():
        try:
            await client.send_json(payload)
        except:
            clients.remove(client)

# Prepare contents of CHALLENGES_FILE into a payload to be sent to new clients, if applicable.
def current_init_payload():
    try:
        with open(CHALLENGES_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f) # Parse the JSON into a Python dict.
    except FileNotFoundError:
        print(f"[{now()}][!] WARNING: Prior game JSON file not found: {CHALLENGES_FILE}")
        payload = {}
    except json.JSONDecodeError as e:
        print(f"[{now()}][!] ERROR: Invalid JSON in {CHALLENGES_FILE}: {e}")
        payload = {}
    payload.setdefault("type", "init")
    return payload

# Deletes all old artefacts and resets clock + timer + progress.
def force_new_game():
    """
    Function resets game back to a default state.
    It performs the following:
    - Deletes the progress file.
    - Deletes the save state file.
    - Deletes the challenges file.
    - Removes all challenge databases from DBMS.
    - Removes all challenge database users from DBMS.
    - Deletes all challenge containers from Docker.
    - Deletes all challenge container images from Docker.
    - Resets timer_value, progress_value, visible_total, secrets_exhausted, and flagcounter.
    - Resets engine database to default state.
    
    This function intentionally does NOT modify the "game_state" global variable.
    """
    print(f"[{now()}][*] Forcing new game, deleting/resetting all artefacts...")
    
    # Delete progress file.
    try:
        os.remove(PROGRESS_FILE_PATH)
        print(f"[{now()}][*] File '{PROGRESS_FILE_PATH}' deleted successfully.")
    except FileNotFoundError:
        print(f"[{now()}][!] ERROR: File '{PROGRESS_FILE_PATH}' not found.")
    except PermissionError:
        print(f"[{now()}][!] ERROR: Permission denied: Cannot delete '{PROGRESS_FILE_PATH}'.")
    except OSError as e:
        print(f"[{now()}][!] ERROR: Problem deleting file '{PROGRESS_FILE_PATH}': {e}")
    
    # Delete savestate file.
    try:
        os.remove(SAVESTATE_FILE_PATH)
        print(f"[{now()}][*] File '{SAVESTATE_FILE_PATH}' deleted successfully.")
    except FileNotFoundError:
        print(f"[{now()}][!] ERROR: File '{SAVESTATE_FILE_PATH}' not found.")
    except PermissionError:
        print(f"[{now()}][!] ERROR: Permission denied: Cannot delete '{SAVESTATE_FILE_PATH}'.")
    except OSError as e:
        print(f"[{now()}][!] ERROR: Problem deleting file '{SAVESTATE_FILE_PATH}': {e}")
    
    # Delete challenges file.
    try:
        os.remove(CHALLENGES_FILE)
        print(f"[{now()}][*] File '{CHALLENGES_FILE}' deleted successfully.")
    except FileNotFoundError:
        print(f"[{now()}][!] ERROR: File '{CHALLENGES_FILE}' not found.")
    except PermissionError:
        print(f"[{now()}][!] ERROR: Permission denied: Cannot delete '{CHALLENGES_FILE}'.")
    except OSError as e:
        print(f"[{now()}][!] ERROR: Problem deleting file '{CHALLENGES_FILE}': {e}")
    
    # Purge challenge databases from DBMS.
    pattern = re.compile(r"^\d{1,3}")
    print(f"[{now()}][*] Removing challenge databases...")
    try:
        conn = master_db()
        cursor = conn.cursor()

        cursor.execute("SHOW DATABASES") # Fetch all databases.
        databases = cursor.fetchall()

        for (db_name,) in databases:
            # Skip system and engine databases.
            if db_name in ["labrandor", "information_schema", "mysql", "performance_schema", "sys"]:
                continue
            # Check if database starts with 1–3 digits (1-999).
            if pattern.match(db_name):
                print(f"[{now()}][*] Deleting database: {db_name}")
                cursor.execute(f"DROP DATABASE `{db_name}`")        
        conn.commit()

    except mysql.connector.Error as err:
        print(f"[{now()}][!] SQL ERROR: {err}")
    except Exception as err:
        print(f"[{now()}][!] ERROR: {err}")
    
    # Purge challenge databases users from DBMS.    
    print(f"[{now()}][*] Removing challenge database users...")
    try:
        cursor.execute("SELECT user, host FROM mysql.user")
        users = cursor.fetchall()

        for row in users:
            username, host = row

            username = username.decode("utf-8", errors="ignore") if isinstance(username, (bytes, bytearray)) else str(username)
            host = host.decode("utf-8", errors="ignore") if isinstance(host, (bytes, bytearray)) else str(host)

            if not username:
                continue
            # If a challenge creates a table with its own user, add the table's base username here.
            if (username.startswith("readonly")) or (username.endswith("employee")) or (username.endswith("blog")) or (username.endswith("product")):
                print(f"[{now()}][*] Dropping user: '{username}'@'{host}'")
                cursor.execute(f"DROP USER `{username}`@`{host}`")

        conn.commit()

    except mysql.connector.Error as err:
        print(f"[{now()}][!] SQL ERROR: {err}")
    except Exception as err:
        print(f"[{now()}][!] ERROR: {err}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    # Remove Docker containers and images.   
    print(f"[{now()}][*] Removing challenge Docker containers...")
    client = docker.from_env() # Connect to Docker.
    try:
        # client.ping() # Connectivity check.
        # Remove containers whose *name* starts with "challenge".
        for c in client.containers.list(all=True, filters={"name": "challenge"}):
            if c.name and c.name.startswith("challenge"):
                try:
                    print(f"[{now()}][*] Removing container: {c.name}")
                    c.remove(force=True) # Stops if running.
                except NotFound:
                    pass
                except APIError as e:
                    print(f"[{now()}][!] ERROR: Container remove error ({c.name}): {getattr(e, 'explanation', e)}")

        # Remove Docker images whose repository starts with "challenge".
        for img in client.images.list(all=True):
            tags = img.tags or []
            if any(tag.split(":", 1)[0].startswith("challenge") for tag in tags):
                try:
                    print(f"[{now()}][*] Removing image: {img.id[:12]} {tags}")
                    client.images.remove(image=img.id, force=True, noprune=False)
                except NotFound:
                    pass
                except APIError as e:
                    print(f"[{now()}][!] WARNING: Image removal error ({img.id[:12]}): {getattr(e, 'explanation', e)}")

    except APIError as e:
        print(f"[{now()}][!] ERROR: Docker API Error: {getattr(e, 'explanation', err)}")
    except Exception as e:
        print(f"[{now()}][!] ERROR: {e}")

    # Resetting engine's database back to the default state.
    print(f"[{now()}][*] Resetting the pool of challenges...")
    sql = """
    UPDATE `pool`
    SET `deployed` = 0,
        `complete` = 0,
        `flag` = "",
        `container` = ""
    WHERE 1
    """
    sql2 = """
    UPDATE `secret`
    SET `deployed` = 0,
        `complete` = 0,
        `flag` = "",
        `container` = ""
    WHERE 1
    """
    # Certain secret challenges have hard-coded flags.
    secret901 = """
    UPDATE `secret`
    SET `deployed` = 0,
        `complete` = 0,
        `flag` = "HAL9000",
        `container` = ""
    WHERE `id` = "901"
    """
    secret902 = """
    UPDATE `secret`
    SET `deployed` = 0,
        `complete` = 0,
        `flag` = "MOTHER",
        `container` = ""
    WHERE `id` = "902"
    """
    # Disabling this secret until it is fixed. Can remove this query after challenge has been fixed.
    secret955 = """
    UPDATE `secret`
    SET `deployed` = 1,
        `complete` = 1,
        `flag` = "",
        `container` = ""
    WHERE `id` = "955"
    """
    try:
        conn = database_connection()
        cursor = conn.cursor()
        cursor.execute(sql) # Reset "pool" table.
        cursor.execute(sql2) # Reset "secret" table.
        cursor.execute(secret901) # Certain secret challenges have hard-coded flags.
        cursor.execute(secret902) # Certain secret challenges have hard-coded flags.
        cursor.execute(secret955) # If this secret is fixed, remove this line.
        conn.commit()
    except Exception as e:
        print(f"[{now()}][!] ERROR: Failed to update 'pool' or 'secret' table. Details: {e}")
    finally:
        cursor.close()
        conn.close()
    
    # Reset timers, counters, and progress.
    global timer_value, progress_value, visible_total, secrets_exhausted, flagcounter
    timer_value = TIMER_START
    visible_total = TIMER_START
    progress_value = 0
    secrets_exhausted = False 
    flagcounter = 0 # Used in testing.
    stop_secret_check_task() # Stop task from previous game.
    print(f"[{now()}][*] Done.")
    return

# Sets visible time, total time, and progress of game in the DDS.
def start_game():
    dds.set_visible_time_remaining(int(timer_value/60))
    dds.set_visible_total_time(int(visible_total/60))
    dds.set_progress(int(progress_value))
    return

# Build X starting challenges.
def build_challenges():
    """
    When a new game is triggered, this function builds X number of
    challenges based on the value of 'STARTING_CHALLENGES'.
    """
    for i in range(STARTING_CHALLENGES):
        print(f"[{now()}][*] Building new challenge: ",i)
        values = provision_challenge("web") # Forcing "web" challenges.
        if values is None:
            print(f"[{now()}][!] ERROR: Problem building challenge. Maybe try again?")
    print(f"[{now()}][*] Initial challenge builds complete.")
    return

# Admin functions.
async def admin_function(secret, command):
    global game_state, timer_value, visible_total, secrets_exhausted, flagcounter, custom_flag_pool
    print(f"[{now()}][*] Admin command recieved...")
    if secret != ADMIN_PASSWORD:
        return
    
    if command == "start_new_game":
        print(f"[{now()}][*] Forcing new game...")
        custom_flag_pool = CUSTOM_FLAG_LIST.copy()
        force_new_game()
        build_challenges()
        start_game()
        game_state = "running"
        await broadcast_to_clients({"type": "reload-page"})

    if command == "force_win":
        print(f"[{now()}][*] Forcing Win screen, current game not affected...")
        game_state = "win"
        await broadcast_to_clients({"type": "reload-page"})
    
    if command == "force_lose":
        print(f"[{now()}][*] Forcing Lose screen, current game not affected...")
        game_state = "lose"
        await broadcast_to_clients({"type": "reload-page"})

    if command == "continue_current_game":
        game_state = "running"
        print(f"[{now()}][*] Loading saved game...")
        # Try to load time and progress file.
        current_game = load_progress()
        # Load the existing DDS state, if available.
        if not dds.load_state(SAVESTATE_FILE_PATH) and current_game == False:
            print(f"[{now()}][!] WARNING: No prior saved game. Starting new game, resetting timers and progress...")
            force_new_game()
        start_game()
        game_state = "running"
        await broadcast_to_clients({"type": "reload-page"})
    
    if command == "title_screen":
        print(f"[{now()}][*] Return to title screen...")
        game_state = "standby"
        print(f"[{now()}][*] Forcing client page reloads...")
        await broadcast_to_clients({"type": "reload-page"})
        print(f"[{now()}][*] Saving game...")
        dds.save_state()
        save_progress()
        
    if command == "new_challenge":
        print(f"[{now()}][*] Building new challenge...")
        values = provision_challenge("web")
        if values is not None:
            domain, system_name, challenge_id, corporation, challenge_username, challenge_password = values
            await broadcast_new_challenge(
                    system_name, challenge_id, domain, corporation,
                    challenge_username, challenge_password
                )
            await asyncio.sleep(0) # Flush
        if values is None:
            print(f"[{now()}][!] ERROR: Problem building new challenge. No new challenges available?")
    
    if command == "new_bonus_challenge":
        print(f"[{now()}][*] Attempting to build new secret/bonus challenge...")
        if secrets_exhausted == True:
            print(f"[{now()}][!] No more secrets can be generated for this game, secrets exchuasted.")
        else:
            print(f"[{now()}][*] Building new secret/bonus challenge...")
            values = provision_secret()
            if values is not None:
                domain, system_name, challenge_id, corporation, challenge_username, challenge_password = values
                await broadcast_new_challenge(
                system_name, challenge_id, domain, corporation,
                challenge_username, challenge_password)
                await asyncio.sleep(0) # Flush
                print(f"[{now()}][*] Secret build complete.")
        
    if command == "force_flag_found": 
        flagcounter += 1
        print(f"[{now()}][*] Simulating passage of time...")
        passage_of_time = random.randint(5, 45) # Random time between 5 minutes and 45 minutes.
        print(f"[{now()}][*] Time to find:", passage_of_time, "minutes") 
        passage_of_time = passage_of_time*60 # Convert minutes to seconds.

        timer_value -= passage_of_time # Simulate passage of time by removing time from timer.
        visible_total += passage_of_time # Simulate passage of time by adding time to overall clock.
        print(f"[{now()}][*] Simulating flag found at:", format_time(timer_value), "minutes")

        dds.set_visible_time(remaining=timer_value/60, total=visible_total/60)
        dds.update_milestone_value()

        print(f"[{now()}][*] Simulating new flag found.")
        time_bonus = int(dds.complete_milestone())
        print(f"[{now()}][*] Bonus time (in minutes):",time_bonus)
        time_bonus = int(time_bonus*60)
        print(f"[{now()}][*] Bonus time (in seconds):",time_bonus)
        timer_value += time_bonus
        visible_total += time_bonus

        # Send to DDS in minutes, not seconds.
        dds.set_visible_time(remaining=timer_value/60, total=visible_total/60)
        dds.update_milestone_value()
        print(dds.get_game_state())

        # Get the current progress.
        await determine_progress()
        print("Flag count:", flagcounter)
        # Save game after flag found.
        dds.save_state()
        save_progress()
        await broadcast_current_timer_value() 

    if command == "remove_time": 
        print("[!] Removing 10 minutes")
        passage_of_time = 10
        passage_of_time = passage_of_time*60

        timer_value -= passage_of_time
        visible_total += passage_of_time
        
        dds.set_visible_time(remaining=timer_value/60, total=visible_total/60)
        dds.update_milestone_value()
        
        # Save game after time adjustment.
        dds.save_state()
        save_progress()
        await broadcast_current_timer_value() 

    if command == "add_time": 
        print("[!] Adding 10 minutes")
        passage_of_time = 10
        #print(f"[{now()}][*] Time to find:", passage_of_time, "minutes")
        passage_of_time = passage_of_time*60

        timer_value += passage_of_time
        visible_total += passage_of_time
        
        dds.set_visible_time(remaining=timer_value/60, total=visible_total/60)
        dds.update_milestone_value()
        
        # Save game after time adjustment
        dds.save_state()
        save_progress()
        await broadcast_current_timer_value() 
    
    if command == "stop_bonus": 
        secrets_exhausted = True
        print("[!] Secrets have been disabled.")

# When a challenge fails, notify clients.
async def broadcast_failed_challenge(system_name, challenge_id, domain, corporation):
    print(f"[{now()}][*] Broadcsting failed challenge...")
    await broadcast_to_clients({
        "type": "failedchallenge",
        "system_name": system_name,
        "challenge_id": challenge_id,
        "domain": domain,
        "corporation": corporation
    })

# Challenge with a time failed or otherwise elapsed time.
async def challenge_out_of_time(hostname):
    print(f"[{now()}][*] Attempting to purge time lapsed challenge in container:", hostname)
    try:
        conn = database_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, system, corporation FROM pool WHERE container = %s LIMIT 1",
            (hostname,),
        )
        row = cursor.fetchone()
        if not row:
            print(f"[{now()}][*] No container found; assuming challenge is complete.")
            return

        challenge_id = row[0]
        system_id = row[1]
        corporation = row[2]
        print(f"[{now()}][*] Hostname provides:", challenge_id, system_id, corporation)
        cursor.execute(
            "SELECT domain, system FROM systems WHERE id = %s LIMIT 1",
            (system_id,),
        )
        row2 = cursor.fetchone()
        if not row2:
            print(f"[{now()}][!] WARNING: Could not find system information during time lapsed challenge removal.")
            return
        
        domain = row2[0]
        system_name = row2[1]
        print(f"[{now()}][*] Hostname provides:", domain, system_name)
    except:
        print(f"[{now()}][!] ERROR: Warning locating {hostname}, a challenge that is out of time. Possible database error?")
    finally:
        challenge_cleanup(challenge_id)
        await broadcast_failed_challenge(system_name, challenge_id, domain, corporation)
        cursor.close()
        conn.close()
        print(f"[{now()}][*] Time lapsed challenge removal complete.")

# Updates game_state based on "win" or "lose". Sends update to clients. Triggers force_new_game().
async def win_or_lose(status):
    global game_state
    if status == "win":
        game_state = "win"
    if status == "lose":
        game_state = "lose"
    await broadcast_to_clients({"type": "reload-page"})
    force_new_game()

# Checks the current progress of the game. If players have >= 100 points, it triggers win_or_lose(...).
async def determine_progress():
    global progress_value, game_state
    progress_value = int(dds.get_progress())
    if progress_value >= 100:
        await win_or_lose("win")

# Initialisation function for server's blocking tasks at startup.
def blocking_init_work():
    """
    This function executes blocking, synchronous functions in a 
    seperate thread/process pool, so they do not freeze the asyncio 
    event loop.

    This function is called as:
        await loop.run_in_executor(pool, blocking_init_work)

    The tasks/functions included typically hold up server responding
    to initial client requests. 
    """
    print(f"[{now()}][*] Starting new game...")
    force_new_game() # Forces game artefacts to be reset.
    build_challenges() # Builds initial starting challenges.
    start_game() # Starts the game.

async def post_startup_work(app: FastAPI):
    global timer_task, game_state
    clock_reset_event.set()
    await asyncio.sleep(0) # Let startup fully complete.
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(pool, blocking_init_work) # Execute blocking functions in their own thread.
    app.state.init_result = result
    app.state.init_done = True

    # Cancel any stuck task immediately.
    if timer_task and not timer_task.done():
        print(f"[{now()}][*] Killing old timer task...")
        timer_task.cancel()
    timer_task = asyncio.create_task(countdown_timer()) # Start fresh timer.
    start_secret_check_task() # Start fresh secret check task.

    game_state = "running"
    print(f"[{now()}][*] Game startup finished. Forcing client web page reloads...")
    await asyncio.sleep(0) # Flush.
    await broadcast_to_clients({"type": "reload-page"})

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.init_done = False
    app.state.startup_task = asyncio.create_task(post_startup_work(app))
    print(f"[{now()}][*] Server ready.")
    yield
    # Shutdown logic.
    print(f"[{now()}][*] Saving game...")
    dds.save_state()
    save_progress()
    print(f"[{now()}][*] Save complete!")
    task = getattr(app.state, "bg_task", None)
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    pool.shutdown(wait=False, cancel_futures=True)
    print(f"[{now()}][*] It is now safe to turn off your computer.")

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/music", StaticFiles(directory="music"), name="music")
app.mount("/sfx", StaticFiles(directory="sfx"), name="sfx")

@app.get("/", response_class=HTMLResponse)
async def get_home(request: Request):
    if game_state == "standby":
        return templates.TemplateResponse("title.html", {"request": request})
    if game_state == "running":
        return templates.TemplateResponse("index.html", {"request": request})
    if game_state == "win":
        return templates.TemplateResponse("win.html", {"request": request})
    if game_state == "lose":
        return templates.TemplateResponse("lose.html", {"request": request})
    
@app.get("/admin.html", response_class=HTMLResponse)
async def get_admin(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global timer_value, visible_total, flagcounter, server_ip
    await websocket.accept()
    # Send current challenges in JSON to new clients/connections.
    await websocket.send_text(json.dumps(current_init_payload())) 
    clients.add(websocket) # Track the clients for future broadcasts.

    # Correct challenge code/flag found. Done in a new thread.
    async def success_flow(data: Dict[str, Any]):
        try:
            # Remove old challenge and broadcast the removal to clients.
            await asyncio.to_thread(challenge_cleanup, data["challenge_id"]) # New thread.
            await broadcast_remove_challenge(
                data["challenge_id"], data["system_name"], data["corporation"]
            )
            await asyncio.sleep(0) # Flush.
        except Exception as e:
            print(f"[{now()}][!] ERROR:", e)
    
    # Provision new challenge after old challenge removed. Done in a new thread/task to reduce wait time.
    async def replace_challenge():
        try:
            def _provision(): # Executed in new thread to prevent blocking.
                # Provision new challenge.
                return provision_challenge() 
            values = await asyncio.to_thread(_provision) # New thread.
            if values is not None:
                domain, system_name, challenge_id, corporation, challenge_username, challenge_password = values
                # Broadcast new challenge.
                await broadcast_new_challenge(
                system_name, challenge_id, domain, corporation, challenge_username, challenge_password)
            await asyncio.sleep(0) # Flush.
        except Exception as e:
            print(f"[{now()}][!] ERROR:", e)

    try:
        while True:
            raw = await websocket.receive_text()
            # print(f"[{now()}][*] WS Payload:", raw)
            try:
                parsed: Any = json.loads(raw)
            except json.JSONDecodeError:
                data: Dict[str, Any] = {"type": "legacy_text", "text": raw}
            else:
                if isinstance(parsed, dict):
                    data = parsed
                else:
                    # Valid JSON, but not an object?
                    data = {"type": "legacy_json", "payload": parsed}

            mtype = data.get("type")
            try:
                # Client has sent a flag to the server to be checked.
                if mtype =="code_submit":
                    result = code_attempt(data["challenge_id"], data["submitted_code"], data["system_name"])
                    print(f"[{now()}][*] Result:", result)
                    print(f"[{now()}][*] Sending result to client...")
                    # Respond to the specific client; do not send a broadcast.
                    await websocket.send_json({"type": "code_submit_ack","challenge_id": data["challenge_id"],"response": result})
                    await asyncio.sleep(0)
                    if result == True: # Flag was correct!
                        print(f"[{now()}][*] Challenge complete! Removing old challenge...")
                        asyncio.create_task(success_flow(data))
                        print(f"[{now()}][*] Flag found at:", format_time(timer_value), "minutes")

                        # Send to DDS in minutes, not seconds.
                        dds.set_visible_time(remaining=timer_value/60, total=visible_total/60)
                        dds.update_milestone_value()
                        time_bonus = int(dds.complete_milestone())
                        print(f"[{now()}][*] Bonus time (in minutes):",time_bonus)
                        time_bonus = int(time_bonus*60)
                        print(f"[{now()}][*] Bonus time (in seconds):",time_bonus)
                        timer_value += time_bonus
                        visible_total += time_bonus

                        # Send to DDS in minutes, not seconds.
                        dds.set_visible_time(remaining=timer_value/60, total=visible_total/60)
                        dds.update_milestone_value() # Running update again before we print game state.
                        print(dds.get_game_state()) # Print current DDS game state.
                        await determine_progress() # Get the current progress.
                        print(f"[{now()}][*] Flag count: {flagcounter}")
                        dds.save_state()
                        save_progress()
                        await broadcast_current_timer_value()

                        print(f"[{now()}][*] Creating replacement challenge...")
                        asyncio.create_task(replace_challenge())
                # SSH challenge has sent an initial login notification to the server.
                elif mtype == "ssh_login":
                    print(f"[{now()}][*] SSH login detected. Starting timer, if applicable.")
                    await start_hostname_timer(data["hostname"], on_done=challenge_out_of_time)
                # Client has sent an admin command to the server.
                elif mtype == "admin_command":
                    await admin_function(data["secret"], data["action"])

            except Exception as e:
                await websocket.send_json({"type": "error", "error": "invalid_payload", "details": e.errors()})
    except:
        clients.remove(websocket)

if __name__ == "__main__":
    log = Tee("program.log") # Logging.
    sys.stdout = log # Sending output to log file.
    sys.stderr = log # Sending errors to log file.
    create_music_manifest()

    # Check for database connection.
    try:
        conn = database_connection()
        conn.close()
    except Exception as e:
        print(f"[{now()}][*] ERROR: Database connection failed: {e}")
        sys.exit(1) 
    
    # Check that Docker is running.
    try:
        client = docker.from_env()
        client.ping()
    except Exception as e:
        print(f"[{now()}][*] ERROR: Unable to connect to Docker. Is it running?: {e}")
        sys.exit(1)

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)