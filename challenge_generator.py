# Copyright (c) 2017-2026 Joel Panther
# Licensed under the MIT License. See LICENSE file in the project root.

from datetime import datetime
import json
import shutil
import subprocess
import random
import os
import docker
from docker.errors import APIError, NotFound, DockerException
import secrets
from string import Template
from pathlib import Path
import string
import traceback
import re
from typing import List, Dict, Set, Optional
from puppet_manager import create_puppet
from db_connect import *

# TODO: 
# - Add flag to 'api' module.
# - Modify 'api' module to add it to first keys.
# - Create 'blogs' module for public release.

# =============================
# Domain & constraint settings
# =============================
ENTRY_POINTS: List[str] = ['work.php', 'research.php', 'hub.php']  # Each unique entry point.
# GATE_TYPES:   List[str] = ['blogs', 'api', 'products', 'submission', 'search', 'employees', 'cookie']  # Each unique gate type.
GATE_TYPES:   List[str] = ['products', 'submission', 'search', 'employees', 'cookie'] # Removing API + blogs until modules updated.
KEYS:         List[str] = [
    'git', 'config.old', 'users.json', 'upload', 'session_token', 'env', 'log', 'creds', 'none', 'sqli', 'robots'
    ]  # Each unique key.

# Which keys can unlock which gate types (hard constraints) - GATE:{KEYS}
ALLOWED: Dict[str, Set[str]] = {
   #'auth':      {'creds'}, # a version of 'auth' is applied when not 'none'
   # 'api':       {'none', 'creds', 'session_token', 'config.old', 'users.json', 'env', 'log', 'git', 'sqli', 'robots'},
    'products':  {'none', 'creds', 'session_token', 'config.old', 'users.json', 'env', 'log', 'git', 'sqli', 'robots'}, 
    'cookie':    {'none', 'creds', 'session_token', 'config.old', 'users.json', 'env', 'log', 'git', 'sqli', 'robots'}, 
    'submission':{'none', 'creds', 'session_token', 'config.old', 'users.json', 'env', 'log', 'git', 'sqli', 'robots'}, 
    'search':    {'none', 'creds', 'session_token', 'config.old', 'users.json', 'env', 'log', 'git', 'sqli', 'robots'}, 
    'employees': {'none', 'creds', 'session_token', 'config.old', 'users.json', 'env', 'log', 'git', 'sqli', 'robots'}, 
    # 'blogs':     {'none', 'creds', 'session_token', 'config.old', 'users.json', 'env', 'log', 'git', 'sqli', 'robots'},
} 
# Note: Each module that queries the database has its own user, with restricted permissions for its applicable tables. 

# Keys that may be used specifically to unlock the FIRST gate
FIRST_GATE_KEYS: Set[str] = {'config.old', 'users.json', 'env', 'log', 'sqli', 'robots'} # Add 'git' to this list, if you unzip the git.zip in the 'key' folder.
NON_FIRST_KEYS: Set[str]  = set(KEYS) - FIRST_GATE_KEYS

# =============================
# Successor constraints (by gate_type)
# For a given current gate_type, which next gate_types may follow?
# By default, every type may be followed by any type.
# Modify ALLOWED_SUCCESSORS as needed to restrict adjacencies.
# =============================
DEFAULT_SUCCESSORS: Dict[str, Set[str]] = {t: set(GATE_TYPES) for t in GATE_TYPES}
ALLOWED_SUCCESSORS: Dict[str, Set[str]] = dict(DEFAULT_SUCCESSORS)
ALLOWED_SUCCESSORS['submission'] = set() # Introduces 'upload', which is only suited to be for flag.

# =============================
# Target-key constraints (by gate_type)
# If a gate has type T at position i, then the next gate's key (keys[i+1]) must be in TARGET_KEY_CONSTRAINTS[T]. 
# =============================
TARGET_KEY_CONSTRAINTS: Dict[str, Set[str]] = {t: set(KEYS) for t in GATE_TYPES}
# Example: products may only reveal 'sqli' as the next key (requires 'sqli' in KEYS and ALLOWED[next_type]).
TARGET_KEY_CONSTRAINTS['products'] = {'creds', 'session_token'}
TARGET_KEY_CONSTRAINTS['search'] = {'creds', 'session_token'}
TARGET_KEY_CONSTRAINTS['employees'] = {'creds', 'session_token'}
TARGET_KEY_CONSTRAINTS['cookie'] = {'creds', 'session_token'}
# TARGET_KEY_CONSTRAINTS['blogs'] = {'session_token'}

# =============================
# Variables for generation platform
# =============================
flavour_JSON = "fCKcXn37KpDEit4PfRxf9r5DyLb68t.json" # Hard coding flavour JSON filename. No secrets stored here.
flavour_JSON_data = []
exec_details = [] # Flavour text for executives.
picked_usernames = []
picked_passwords = []
corp_name = "" 
employee_table_exists = False # Switch to see if "employee" table has been created in the challenge database.

# If there are not enough images in the repo for a specific system type, it might crash.
# Should probably look into that one day.
FLAVOUR_IMAGE_COUNT = 8 # Int. How many system flavour images to pull from image repository.
FIRST_PORT_NUMBER = "8" # String. Added to the front of the challenge ID to give a unique port number per challenge.

# =============================
# Pre-generated lists
# =============================
FLAG_TABLE_NAMES = [
    "compliance_tokens", "continuity_keys", "safety_protocol", "termination_key",
    "failsafe_registry", "override_token", "system_interrupt_code", "emergency", "final_authority",
    "nullkeys", "silence_sequence_key", "end_of_life_key", "containment_switch", "legacy_key_table",
    "system_misc_data", "archival_refs", "operational_metadata", "backup_key", "recovery_key"
]
usernames = [
    "AstroVoyager", "QuantumPilot", "NebulaSeeker", "StellarRanger", "LunarNomad",
    "WarpRider", "PhotonRunner", "CosmoGuardian", "NovaScout", "GalaxyRover",
    "HyperDriveHero", "PlasmaHunter", "CelestialNomad", "AsteroidStriker", "CometChaser",
    "StarForge", "SingularitySurfer", "VoidNavigator", "CryoDrifter", "MeteorSentinel",
    "ChronoTraveler", "ExoCommander", "SolarWarden", "EclipseShadow", "PlanetBreaker",
    "ZeroPointPilot", "DarkMatterDiver", "GravShipCaptain", "LightyearLancer", "QuantumNomad",
    "AstroSentinel", "NovaNomad", "WormholeWalker", "PulsarProtector", "NeutrinoKnight",
    "IonStormer", "OmegaOutrider", "StarlightStrider", "BlackHoleRogue", "EventHorizonRider",
    "CryoRanger", "NebulaRanger", "AstroCorsair", "StellarWarden", "SolarCorsair",
    "PhotonPhantom", "WarpGuardian", "LunarSentinel", "NovaWarden", "StarborneRider",
    "AstroLancer", "GalaxyCorsair", "NebulaPhantom", "VoidCorsair", "LightwaveRider",
    "PlasmaCorsair", "DarkNebulaNomad", "AstroHunter", "ZeroGNomad", "ChronoSentinel",
    "HyperNovaPilot", "LunarCorsair", "CosmicWarden", "EclipseCorsair", "QuantumCorsair",
    "NebulaGuardian", "PhotonCorsair", "NovaGuardian", "AstroCorsairX", "SolarSentinel",
    "CryoCorsair", "IonNomad", "PlasmaNomad", "WormholeCorsair", "VoidSentinel",
    "MeteorNomad", "CometCorsair", "StellarCorsair", "WarpNomad", "DarkMatterNomad",
    "StarDrifter", "AstroVoyagerX", "QuantumVoyager", "NebulaDrifter", "LunarWarden",
    "HyperSpaceNomad", "PhotonVoyager", "CosmoDrifter", "NovaLancer", "GalaxyWarden",
    "LightyearCorsair", "CryoNomad", "AstroProtector", "StellarVoyager", "SolarDrifter",
    "WarpLancer", "VoidLancer", "PlasmaDrifter", "NebulaLancer", "QuantumLancer"
]
passwords = [
    'N3ur4lN3742', '4s7r0By7377', 'Qu4n7umK3y99', 'V01d4cc35512', 'Cy83rN0v484',
    'M3ch4C0d356', 'Ph070nP45534', '573114r4I21', 'Lun4rH45h90', 'W4rpC0r366',
    'Cry0C1ph3r18', 'N3u7r1n0L0ck53', 'C05m0R00781', 'Hyp3rB0772', '10n5h13ld44',
    'P145m4N0d328', 'Pu15ar3n7ry63', 'D4rkM4773r07', 'L1gh7y34r64', 'N4n0M1nd55',
    '4s7r0L0g1c31', '3x0Br41n92', 'Z3r0P01n783', 'C0m37D47414', 'Gr4v4I70',
    '50l4rB1729', '0m3g4L0g1n38', '3v3n7H0r1z0n40', '574rl1gh767', 'B14ckH01359',
    'G414c7ic74', 'Cy83r53n71n3187', 'N0v44u7h20', 'V01dC1ph3r91', '41C1u573r16',
    'N3ur4l70k3n35', 'W0rmh01373', '574rl1nk39', 'Cry0L0g1n11', 'Ph070nK3y45',
    '4s7r0B0722', 'Qu4n7umR00725', 'Hyp3r4cc35517', 'N3u7r1n0N3715', 'Lun4rG47327',
    'N4n0K3y98', 'W4rp4cc35513', 'Cy83rC0r365', 'P145m44u7h48', '0m3g4N0d357',
    '41C0n7r0184', '574r4I79', '50l4rK3y41', 'V01dR00733', 'Cry0P45509',
    'Ph070nL0ck95', 'Qu4n7um4I76', 'N3ur4lP0r74l26', 'D4rkC1ph3r80', '4s7r0G47323',
    'Z3r0By735', 'M3ch44I85', 'W0rmh013K3y54', '573114rC0d349', 'N4n0C1ph3r46',
    'P145m4P45597', 'Lun4r4I82', '4s7r0L0g1n10', 'Qu4n7um5h13ld36', 'N0v4C1ph3r68',
    'Cry04I43', 'Ph070n4u7h32', 'Hyp3rC0r361', 'N3u7r1n05h13ld24', '4IK3y19',
    'W4rpC0d350', 'Cy83r4I89', '3v3n7K3y42', '50l4rP45596', 'N4n0N0d378',
    '0m3g44I30', 'V01dP45508', 'B14ck4I75', '4s7r0C1ph3r71', 'Qu4n7umP45593',
    'N3ur4l4cc35547', 'Ph070nP0r74l60', 'Cry0N0d362', 'Hyp3r70k3n58', 'Cy83rC0d386',
    '4I4u7h52', '573114rL0ck51', 'Lun4rC0d394', 'W4rpG47369', 'D4rk4I68',
    'Gr4vC0r399', '50l4r4u7h01', 'N4n0L0ck02', '4s7r0K3y03', 'Qu4n7umG47304'
]
security_questions = [
    'Which fear response did the system classify as your primary motivator during onboarding?',
    'What stimulus was identified as most effective in correcting your hesitation behaviour?',
    'What emotional state was logged immediately before your first successful compliance confirmation?',
    'What aspect of your identity was deprioritised first during behavioural normalisation?',
    'Which outcome did the system determine you would sacrifice least to maintain access?',
    'Which memory was flagged as most susceptible to reframing during alignment training?',
    'What personal loss threshold was determined to be unacceptable to you?',
    'Which scenario was used to measure your tolerance for irreversible outcomes?'
]

# =============================
# Directory paths
# =============================
FACTORY_FLOOR = Path("factory_floor") # Container deployment/build directory. Essentially, where all the pieces go for the container build.
DOCKERFILE_FOLDER = Path("dockerfiles") # Where the dockerfiles are stored.
MODULE_TEMPLATES = Path("module_templates") # Where the module templates are stored for web apps.
FLAVOUR_FOLDER = Path("flavour") # Repositories of flavour content for modules.
HEADSHOTS_FOLDER = Path("flavour/headshots") # Repository for headshots specifically.

# =============================
# SQL Server
# =============================
# Containers need to be able to access SQL server. 
DATABASE_HOST_IP = "172.17.0.1" # Location of the SQL server. Currently configued as the Docker host.
WEB_HOST_IP = "127.0.0.1" # Web host IP for containers. Used for pointing the puppets.

# =============================
# Helper functions
# =============================
# Returns the current time.
def now():
    # return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return datetime.now().strftime('%H:%M:%S')

# Returns a random subfolder name (takes relative dir) from inside the given parent directory.        
def pick_random_folder(parent_directory):
    subfolders = [
            name
            for name in os.listdir(parent_directory)
            if os.path.isdir(os.path.join(parent_directory, name))
        ]
    if not subfolders:
            return None
    return random.choice(subfolders)

# =============================
# Web app challenge functions
# =============================
# Builds pathway to flag.
def generate_chain(seed: Optional[int] = None, max_retries: int = 64) -> List[dict]:
    """
    Builds a list of 1..3 chained gates (ending in 'flag'), then appends placeholder
    gates for any unused entry_points with gate_type assigned, but key/target='none'.

    Constraints for chained gates:
      - entry_point: unique per gate (chosen from ENTRY_POINTS).
      - gate_type: unique per gate (chosen from GATE_TYPES), and successive types must respect ALLOWED_SUCCESSORS.
      - key: unique overall; must be allowed for its gate_type via ALLOWED.
      - FIRST_GATE_KEYS may be used ONLY on the first gate; later gates use NON_FIRST_KEYS.
      - target: next gate's key; last gate's target is 'flag'.
      - If gate_type[i-1] has a TARGET_KEY_CONSTRAINTS entry, then keys[i] must be in it.

    Placeholder gates (after reaching 'flag'):
      - Assigned a unique gate_type (not used by the chain or other placeholders),
        preferably from types compatible with NON_FIRST_KEYS.

    Returns JSON with the following for each gate:
      - index: 1, 2, or 3.
      - entry_point: Selected from ENTRY_POINTS list.
      - gate_type: Selected from GATE_TYPES list.
      - current_gate_key: For first gate, selected from FIRST_GATE_KEYS list, NON_FIRST_KEYS for all other gates.
      - target_gate_key: The key for the next gate, if applicable.
      - target_gate_type: The next type of gate in the sequence, if applicable.
    """
    rnd = random.Random(seed)

    # Pools for positional gate_type feasibility.
    first_type_pool = [t for t in GATE_TYPES if ALLOWED[t] & FIRST_GATE_KEYS]
    non_first_type_pool = [t for t in GATE_TYPES if ALLOWED[t] & NON_FIRST_KEYS]

    if not first_type_pool:
        raise print(f"[{now()}][*] No gate types can be unlocked by FIRST_GATE_KEYS.")

    for _ in range(max_retries):
        n = rnd.randint(1, 3)

        # Randomise ALL entry points up front (3).
        all_entries = rnd.sample(ENTRY_POINTS, len(ENTRY_POINTS))
        chain_entries = all_entries[:n]
        extra_entries = all_entries[n:]  # 0..2 leftovers

        # Choose gate_types sequence with backtracking to satisfy successors + uniqueness.
        types: List[Optional[str]] = [None] * n
        used_types: Set[str] = set()

        def assign_types(i: int) -> bool:
            if i == n:
                return True
            if i == 0:
                candidates = list(first_type_pool)
            else:
                prev = types[i - 1]
                allowed_next = ALLOWED_SUCCESSORS.get(prev, set(GATE_TYPES))
                candidates = [t for t in non_first_type_pool if t in allowed_next]

            # Enforce uniqueness of gate_types within the chain.
            candidates = [t for t in candidates if t not in used_types]
            rnd.shuffle(candidates)

            for t in candidates:
                types[i] = t
                used_types.add(t)
                if assign_types(i + 1):
                    return True
                used_types.remove(t)
                types[i] = None
            return False

        if not assign_types(0):
            # Try another sampling (different n / entries / RNG path).
            continue

        # Assign keys for the chain (unique, allowed per type, positional key pools),
        # and enforce TARGET_KEY_CONSTRAINTS from the *previous* gate_type.
        used_keys: Set[str] = set()
        keys: List[Optional[str]] = [None] * n

        def assign_keys(i: int) -> bool:
            if i == n:
                return True
            gate_type = types[i]
            if i == 0:
                base_allowed = (ALLOWED[gate_type] & FIRST_GATE_KEYS) - used_keys
            else:
                base_allowed = (ALLOWED[gate_type] & NON_FIRST_KEYS) - used_keys

            candidates = list(base_allowed)

            # If there is a previous gate (i > 0), then the current candidate key
            # must satisfy the target-key constraint of the previous gate_type.
            if i > 0:
                prev_type = types[i - 1]
                allowed_targets_for_prev = TARGET_KEY_CONSTRAINTS.get(prev_type, set(KEYS))
                candidates = [c for c in candidates if c in allowed_targets_for_prev]

            rnd.shuffle(candidates)
            for c in candidates:
                keys[i] = c
                used_keys.add(c)
                if assign_keys(i + 1):
                    return True
                used_keys.remove(c)
                keys[i] = None
            return False

        if not assign_keys(0):
            # Re-sample everything if key assignment hit a dead end.
            continue

        # Build chained gates (ending at 'flag').
        gates: List[dict] = []
        for i in range(n):
            gate_key = keys[i]
            gates.append({
                "index": i + 1,
                "entry_point": chain_entries[i],
                "gate_type": types[i],
                "current_gate_key": gate_key,
                "target_gate_key": "flag" if i == n - 1 else keys[i + 1],
                "target_gate_type": "none" if i == n - 1 else types[i + 1],
              })

        # Append placeholder gates for any unused entry_points.
        extra_types_pool = [t for t in non_first_type_pool if t not in used_types]
        rnd.shuffle(extra_types_pool)
        if len(extra_types_pool) < len(extra_entries):
            fallback = [t for t in GATE_TYPES if t not in used_types and t not in extra_types_pool]
            rnd.shuffle(fallback)
            extra_types_pool.extend(fallback)

        for ep in extra_entries:
            if not extra_types_pool:
                raise print(f"[{now()}][*] Not enough distinct gate_types available for extras.")
            t = extra_types_pool.pop()
            used_types.add(t)
            gates.append({
                "index": len(gates) + 1,
                "entry_point": ep,
                "gate_type": t,
                "current_gate_key": "none",
                "target_gate_key": "none",
                "target_gate_type": "none",
            })

        return gates
    print(f"[{now()}][!] ERROR: Could not generate a valid chain after several retries.")
    raise 

# Builds the target gate's key, not the current gate's key.
def build_target_gate_key(platform_module_pool, challenge_id, gate_type, target_gate_key, target_gate_entry_point, flag_value):
    """
    Builds the key for the TARGET gate.
    Certain gates can only support certain keys. These constraints are in the global lists at the top.
    """
    if target_gate_key == "none":
        print(f"[{now()}][*] No target key to generate. Continuing...")
        return
    
    print(f"[{now()}][*] Building target gate's key or flag...")
    if gate_type == "api":
        print(f"[{now()}][*] API: Players create their own key (user creds and/or permissions) using API.")
        return
    if gate_type == "submission":
        print(f"[{now()}][*] Submission: Introduces shell, target key has to be 'flag'.")
        if target_gate_key == "flag":
            chars = string.ascii_letters + string.digits
            # Flags for shells are currently hidden in a randomised folder in the web root.
            # Builds the folder for the web root.
            random_folder_name = ''.join(random.choice(chars) for _ in range(10))
            Path(FACTORY_FLOOR / random_folder_name).mkdir()

            # Pick a flag text file and copy it to the folder in the web root.
            flag_txt_directory = Path(platform_module_pool / target_gate_key / "txt")
            files = [f for f in flag_txt_directory.iterdir() if f.is_file()]
            random_flag = random.choice(files)
            random_file_name = ''.join(random.choice(chars) for _ in range(10))
            src = Path(random_flag)
            dst = Path(FACTORY_FLOOR / random_folder_name / f"{random_file_name}.txt")
            print(f"[{now()}][*] Flag web root dir: {random_folder_name}")
            shutil.copy(src, dst)

            # Open/read the newly created flag text file.
            with open(dst, "r", encoding="utf-8") as f:
                content = f.read()

            # Replace placeholder with the flag.
            content = content.replace("!!!PLACEHOLDER!!!", f"{flag_value}")

            # Write back to the file.
            with open(dst, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[{now()}][*] Flag inserted into file.")
            return
        else:
            raise print(f"[{now()}][*] ERROR: Shell needs to end with flag. Exiting.")

    if gate_type == "blogs":
        if target_gate_key == "flag":
            print(f"[{now()}][*] Inserting flag for Blogs...")
            table_name = random.choice(FLAG_TABLE_NAMES)
            database_flag(challenge_id, flag_value, table_name)
            add_table_access_to_db_user(challenge_id, gate_type, table_name)
            # Turn on blog post > allows SQLi to be found > leads to the flag in the DB.
            with open(Path(FACTORY_FLOOR / "blogutils.php"), "a") as file:
                print(f"[{now()}][*] Inserting 'blog_post = true'")
                file.write("\nconst blog_post = true;")
            return

        if target_gate_key == "session_token":
            print(f"[{now()}][*] Enabling session_token for Blogs...")
            # Turn off blog post; SQLi not used in this challenge.
            with open(Path(FACTORY_FLOOR / "blogutils.php"), "a") as file:
                print(f"[{now()}][*] Inserting 'blog_post = false'")
                file.write("\nconst blog_post = false;")

            set_single_user_permission(challenge_id, target_gate_entry_point, "AI_OVERWATCH")
            return

    if gate_type in ("products", "employees", "search"):
        print(f"[{now()}][*] Products, Search, and Employees: Can only put keys in database.")
        if target_gate_key == "flag":
            table_name = random.choice(FLAG_TABLE_NAMES)
            database_flag(challenge_id, flag_value, table_name)
            # Swap 'target_gate_key' for 'table_name' in next function for the flag table, cause flag special :3
            add_table_access_to_db_user(challenge_id, gate_type, table_name)
            add_table_access_to_db_user(challenge_id, gate_type, "users") # Forces access to 'users' table.
            print(f"[{now()}][*] Flag inserted into database.")
            return
        if target_gate_key == "creds":
            randomly_set_single_user_permission(challenge_id, target_gate_entry_point)
            add_table_access_to_db_user(challenge_id, gate_type, "users") # Forces access to 'users' table.
            print(f"[{now()}][*] User permission adjusted.")
            return
        if target_gate_key == "session_token":
            token = php_session_id()
            set_session_token(challenge_id, token, target_gate_entry_point)
            add_table_access_to_db_user(challenge_id, gate_type, target_gate_key)
            add_table_access_to_db_user(challenge_id, gate_type, "users") # Forces access to 'users' table.
            print(f"[{now()}][*] Session token added.")
            return

    if gate_type == "cookie":
        # Locate the 'cookieX.php' file.
        print(f"[{now()}][*] Cookie: adding secret to module file...")
        try:
            for filename in os.listdir(FACTORY_FLOOR):
                if filename.startswith("cookie"):  # check if file starts with "cookie"
                    file_path = os.path.join(FACTORY_FLOOR, filename)
                    # Open and read the file.
                    with open(file_path, "r+", encoding="utf-8") as file:
                        content = file.read()
                        # Note: If "target_line" ever changes, will need to update this.
                        target_line = "Overwatch User Created: !!!USERNAME!!! : !!!PASSWORD!!!"
                        if target_gate_key == "flag":
                            print(f"[{now()}][*] Inserting flag into {filename}")
                            replacement_line = f"WARNING: Override Code Identified: {flag_value}"
                            content = content.replace(target_line, replacement_line)
                        elif target_gate_key == "session_token":
                            print(f"[{now()}][*] Inserting session token into {filename}")
                            token = php_session_id()
                            set_session_token(challenge_id, token, target_gate_entry_point)
                            replacement_line = f"Overwatch session token generated: {token}"
                            content = content.replace(target_line, replacement_line)
                            print(f"[{now()}][*] Session token added.")
                        elif target_gate_key == "creds":
                            print(f"[{now()}][*] Inserting creds into {filename}")
                            picked_username = f"{random.choice(usernames)}_adm"
                            picked_password = random.choice(passwords)
                            add_user_to_challenge_database(challenge_id, picked_username, picked_password, 0, 0, 0)
                            set_single_user_permission(challenge_id, target_gate_entry_point, picked_username)
                            content = content.replace("!!!USERNAME!!!", picked_username)
                            content = content.replace("!!!PASSWORD!!!", picked_password)
                        file.seek(0)
                        file.write(content)
                        file.truncate()
                        return
        except Exception as e:
            print(f"[{now()}][*] ERROR:",e)
            return

# Builds unauth key, for first gate only.
def build_first_gate_key_module(platform_module_pool, challenge_id, gate_type, gate_key, entry_point):
    """
    Builds the key for the FIRST gate.
    First gate only supports specific keys. 
    These keys are in the global list FIRST_GATE_KEYS.
    """
    module_type = "keys" 
    target_for_secret = "" 
    hub = 0
    work = 0
    research = 0

    if entry_point == "hub.php":
        hub = 1
    if entry_point == "work.php":
        work = 1
    if entry_point == "research.php":
        research = 1
    print(f"[{now()}][*] New user permissions, if needed:",work,research,hub)

    if gate_key == "none":
        print(f"[{now()}][*] No key required for this gate (this should only apply to first gate).")
        return
    
    if gate_key == "sqli":
        print(f"[{now()}][*] SQL injection enabled for first gate.")
        return

    if gate_key != "users.json" and gate_key != "robots" and gate_key != "none": # "users.json" and "robots" do not have supporting files.
        module_selection = pick_random_folder(Path(platform_module_pool) / module_type / gate_key) # Choose the specific module.
        module_location = Path(platform_module_pool) / module_type / gate_key / module_selection # Copying the module type.

    print(f"[{now()}][*] Gate type: {gate_type} | Key type: {gate_key}")
    if gate_key == "robots":
        print(f"[{now()}][*] Building robots.txt key...")
        folder_names = ["emergency", "private", "dump", "secret", "backdoor", "hidden", "other"]
        file_names = ["breakglass", "backup", "backdoor", "oops", "private", "creds"]
        new_filename = f"{random.choice(file_names)}.txt" 
        new_folder = random.choice(folder_names) 
        new_path = Path(FACTORY_FLOOR) / new_folder
        new_path.mkdir(parents=False, exist_ok=True)
        new_file_location = Path(new_path) / new_filename

        with open(Path(FACTORY_FLOOR) / "robots.txt", 'w') as file:
            file.write("User-agent: *\n")
            file.write(f"Disallow: /{new_folder}\n")

        picked_username = f"{random.choice(usernames)}_svc"
        picked_password = random.choice(passwords)
        add_user_to_challenge_database(challenge_id, picked_username, picked_password, work, research, hub)

        with open(new_file_location, 'w') as file:
            file.write(f"Break glass account for the {entry_point} system:\n")
            file.write(f"Username: {picked_username}\n")
            file.write(f"Password: {picked_password}\n")
        
    if gate_key == "git":
        print(f"[{now()}][*] Building git key...")
        try:
            shutil.copytree(module_location, FACTORY_FLOOR, dirs_exist_ok=True) # Grab whole module directory/contents
        except Exception as e:
            print(f"[{now()}][*] ERROR:", e)
            return
        # Find location where secret needs to be saved.
        # Structure: ./git/../path/to/file
        git_config_file = Path(FACTORY_FLOOR) / f"key_{gate_key}_{module_selection}_config.txt"
        try:
            if os.path.exists(git_config_file):
                with open(git_config_file, "r") as f:
                    target_for_secret = Path(FACTORY_FLOOR) / f.readline().strip()  # .strip() removes trailing newline/spaces
            else:
                print(f"[{now()}][*] ERROR: Could not open {git_config_file}")
                return
        except Exception as e:
            print(f"[{now()}][*] ERROR:", e)
            return
        print(f"[{now()}][*] Building secret...")
        picked_username = f"{random.choice(usernames)}_svc"
        picked_password = random.choice(passwords)
        secret_value = f"<!-- For testing: {picked_username}:{picked_password} -->"
        print(f"[{now()}][*] Secret:",secret_value)
        # Put key in its hiding place.
        if os.path.exists(target_for_secret):
            try:
                with open(target_for_secret, "a") as f:
                    f.write(f"\n {secret_value}")
                    print(f"[{now()}][*] Key inserted...")
            except Exception as e:
                print(f"[{now()}][*] ERROR:", e)
                return
        else:
            print(f"[{now()}][*] ERROR: Target for secret does not exist? Exiting...")
            return
        # 'auth' secret needs to be written to challenge database.
        add_user_to_challenge_database(challenge_id, picked_username, picked_password, work, research, hub)
        print(f"[{now()}][*] Challenge database updated.")
        # Remove config file so it is not put in the finished challenge.
        if os.path.exists(git_config_file):
            try:
                os.remove(git_config_file)
                print(f"[{now()}][*] Config file deleted successfully.")
            except Exception as e:
                print(f"[{now()}][*] ERROR:", e)
                return
        else:
            print(f"[{now()}][*] ERROR: 'git' key config does not exist?") 
            return

    if gate_key == "env":
        print(f"[{now()}][*] Building .env key...")
        try:
            shutil.copytree(module_location, FACTORY_FLOOR, dirs_exist_ok=True) # Grab whole module directory/contents.
        except Exception as e:
            print(f"[{now()}][*] ERROR:", e)
            return
        target_for_secret = Path(FACTORY_FLOOR) / ".env"
        picked_username = f"{random.choice(usernames)}_svc"
        picked_password = random.choice(passwords)
        add_user_to_challenge_database(challenge_id, picked_username, picked_password, work, research, hub)
        print(f"[{now()}][*] New user added to challenge database.")
        try:
            with open(target_for_secret, "r", encoding="utf-8-sig", newline="") as f:
                text = f.read()
            replacements = {
                "!!!USERNAME!!!": picked_username,
                "!!!PASSWORD!!!": picked_password
            }
            new_text = text
            for placeholder, value in replacements.items():
                new_text = new_text.replace(placeholder, value, 1)  # only replace first occurrence
            # Validation: check if at least one replacement was made.
            if new_text == text:
                print(f"[{now()}][*] ERROR: No placeholder values found!")
                return
            else:
                print(f"[{now()}][*] Placeholders replaced.")
            with open(target_for_secret, "w", encoding="utf-8-sig", newline="") as f:
                f.write(new_text)
                print(f"[{now()}][*] Updated module saved.")
        except FileNotFoundError:
            print(f"[{now()}][*] .env file not found, exiting.")
            return
        except Exception as e:
            print(f"[{now()}][*] ERROR: {e}")
            return
    
    if gate_key == "users.json": # Does not require module artefacts, is generated here.
        print(f"[{now()}][*] Building users.json key...")
        pairs = [{"username": u, "password": p} for u, p in zip(picked_usernames, picked_passwords)]
        output_file = Path(FACTORY_FLOOR) / "users.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(pairs, f, indent=4)
        print(f"[{now()}][*] User JSON written.")
        if entry_point == "hub.php":
            for picked_username, picked_password in zip(picked_usernames, picked_passwords):
                set_single_user_permission(challenge_id, "hub", picked_username)
        if entry_point == "work.php":
            for picked_username, picked_password in zip(picked_usernames, picked_passwords):
                set_single_user_permission(challenge_id, "work", picked_username)
        if entry_point == "research.php":
            for picked_username, picked_password in zip(picked_usernames, picked_passwords):
                set_single_user_permission(challenge_id, "research", picked_username)
        print(f"[{now()}][*] User permissions mass updated.")

    if gate_key == "config.old":
        print(f"[{now()}][*] Building config.old key...")
        try:
            shutil.copytree(module_location, FACTORY_FLOOR, dirs_exist_ok=True) # Grab whole module directory/contents.
        except Exception as e:
            print(f"[{now()}][*] ERROR:", e)
            return
        target_for_secret = Path(FACTORY_FLOOR) / "config.old"
        print(f"[{now()}][*] Building secret...")
        picked_username = f"{random.choice(usernames)}_srv"
        picked_password = random.choice(passwords)
        try:
            with open(target_for_secret, "r", encoding="utf-8-sig", newline="") as f:
                text = f.read()
            replacements = {
                "!!!USERNAME!!!": picked_username,
                "!!!PASSWORD!!!": picked_password
            }
            new_text = text
            for placeholder, value in replacements.items():
                new_text = new_text.replace(placeholder, value, 1)  # Only replace first occurrence.
            # Validation: check if at least one replacement was made.
            if new_text == text:
                print(f"[{now()}][*] ERROR: No placeholder values found!")
                return
            else:
                print(f"[{now()}][*] Placeholders replaced.")
            with open(target_for_secret, "w", encoding="utf-8-sig", newline="") as f:
                f.write(new_text)
                print(f"[{now()}][*] Updated module saved.")
        except FileNotFoundError:
            print(f"[{now()}][*] 'config.old' file not found, exiting.")
            return
        except Exception as e:
            print(f"[{now()}][*] ERROR: {e}")
            return
        add_user_to_challenge_database(challenge_id, picked_username, picked_password, work, research, hub)
        print(f"[{now()}][*] Challenge database updated.")

    if gate_key == "log":
        print(f"[{now()}][*] Building *.log key...")
        log_file = next(module_location.glob("*.log"), None) # Find the .log file in the module folder.
        log_filename = log_file.name if log_file else None
        try:
            shutil.copytree(module_location, FACTORY_FLOOR, dirs_exist_ok=True) # Grab whole module directory/contents.
        except Exception as e:
            print(f"[{now()}][*] ERROR:", e)
            return
        target_for_secret = Path(FACTORY_FLOOR) / log_filename
        print(f"[{now()}][*] Building secret...")
        picked_username = f"{random.choice(usernames)}_svc"
        picked_password = random.choice(passwords)
        add_user_to_challenge_database(challenge_id, picked_username, picked_password, work, research, hub)
        try:
            with open(target_for_secret, "r", encoding="utf-8-sig", newline="") as f:
                text = f.read()

            replacements = {
                "!!!USERNAME!!!": picked_username,
                "!!!PASSWORD!!!": picked_password
            }
            new_text = text
            total_replacements = 0
            # Replace ALL occurrences of each placeholder and count how many were replaced.
            for placeholder, value in replacements.items():
                count = new_text.count(placeholder)
                if count:
                    new_text = new_text.replace(placeholder, value)  # Default replaces all occurrences.
                    total_replacements += count

            # Validation: check if at least one replacement was made.
            if total_replacements == 0:
                print(f"[{now()}][*] ERROR: No placeholder values found!")
                return
            else:
                print(f"[{now()}][*] Placeholders replaced. Total replacements: {total_replacements}")

            with open(target_for_secret, "w", encoding="utf-8-sig", newline="") as f:
                f.write(new_text)
                print(f"[{now()}][*] Updated '{log_filename}' saved.")

        except FileNotFoundError:
            print(f"[{now()}][*] ERROR: File not found: {log_filename}")
            return
        except Exception as e:
            print(f"[{now()}][*] ERROR: {e}")
            return
        print(f"[{now()}][*] Challenge database updated.")

    print(f"[{now()}][*] {gate_key} key inserted into challenge. Continuing...")    
    return

# Get user's ID from challenge database.
def get_user_id(challenge_id, username):
    conn = master_db()
    cursor = conn.cursor()
    database_name = str(challenge_id)
    # Select the challenge database
    try:
        conn.database = f"`{database_name}`"
    except Exception as e:       
        try:
            conn.database = f"{database_name}"
        except Exception as e:
            print(f"[{now()}][!] WARNING: Problem selecting database {database_name}, regardless of backticks...")
            raise (f"[{now()}][!] ERROR:",e)
    try:
        query = "SELECT id FROM users WHERE username = %s"
        cursor.execute(query, (username,),)
        result = cursor.fetchone()
    except Exception as e:
        print(f"[{now()}][*] ERROR: Problem selecting blog posts.")
        cursor.close()
        conn.close()
        raise print(f"[{now()}][*] ERROR:",e)
    cursor.close()
    conn.close()
    list2string = ''.join(map(str, result))
    result = int(list2string)
    print(f"[{now()}][*] User ID:",result)
    return result

# Builds what we see when the current gate is unlocked.
def build_gateway_target(challenge_id, target_url, gate_type, platform_modules):
    """
    Builds what we see when the current gate is unlocked. 
    Essentially builds the starting point for the next challenge in the sequence.
    This is where "gate_type" defines what the player sees.
    """
    module_selection = pick_random_folder(Path(MODULE_TEMPLATES) / platform_modules / gate_type) # Choose the specific module
    module_to_copy = MODULE_TEMPLATES / platform_modules / gate_type / module_selection

    print(f"[{now()}][*] Copying gate module to factory floor.")
    shutil.copytree(module_to_copy, FACTORY_FLOOR, dirs_exist_ok=True) # Grab whole auth module directory contents
    page_to_include = f"{gate_type}{module_selection}.php"
    print(f"[{now()}][*] MODULE FILE:",page_to_include)

    if gate_type == "products":
        print(f"[{now()}][*] Creating a products table...")
        create_products_table(challenge_id)

    if gate_type == "employees" or gate_type == "search":
        print(f"[{now()}][*] Creating a employees table...")
        create_employee_table(challenge_id)

    if gate_type == "cookie":
        print(f"[{now()}][*] Configuring 'cookies and token' challenge...")
        # Lists of different possible values...
        cookie_names = ["AUTHTOKEN", "PRIVID", "OVERWATCH", "AUDITTOKEN", "VIEWID"]
        normal_usernames = ["EMPLOYEE", "USER", "ASSOCIATE", "GUEST", "CONSULTANT", "TECHNICIAN", "ENGINEER", "AGENT"]
        priv_usernames = ["MANAGER", "ADMINISTRATOR", "OPERATOR", "SUPERVISOR", "REVIEWER", "ADMIN"]
        token_type = str(random.randint(1, 3)) # Token types and mechanics are defined in the 'token-auth-master.php' file.

        # Copy token auth file...
        try:
            filename = "token-auth-master.php"
            token_auth_file = Path(MODULE_TEMPLATES) / platform_modules / gate_type / filename 
            shutil.copy(token_auth_file, FACTORY_FLOOR / filename)
        except Exception as e:
            print(f"[{now()}][*] ERROR:",e)
            return

        # Modify token-auth-master
        cookie_name = random.choice(cookie_names)
        normal_user = random.choice(normal_usernames)
        priv_user = random.choice(priv_usernames)
        characters = string.ascii_letters + string.digits  # A-Z, a-z, 0-9
        signing_key = ''.join(random.choices(characters, k=20))
        try:
            with open(FACTORY_FLOOR / filename, "r+", encoding="utf-8") as file:
                content = file.read()
                content = content.replace("!!!TOKENTYPE!!!", token_type)
                content = content.replace("!!!COOKIENAME!!!", cookie_name)
                content = content.replace("!!!NORMALUSER!!!", normal_user)
                content = content.replace("!!!PRIVUSER!!!", priv_user)
                content = content.replace("!!!SIGNINGKEY!!!", signing_key)
                file.seek(0)
                file.write(content)
                file.truncate()
        except Exception as e:
            print(f"[{now()}][*] ERROR:",e)
            return
        
        # Modify module file so that the priv user displays correctly to players.
        try:
            with open(FACTORY_FLOOR / page_to_include, "r+", encoding="utf-8") as file:
                content = file.read()
                content = content.replace("!!!PRIVUSER!!!", priv_user.capitalize())
                file.seek(0)
                file.write(content)
                file.truncate()
        except Exception as e:
            print(f"[{now()}][*] ERROR:",e)
            return

    if gate_type == "blogs":
        print(f"[{now()}][*] Creating a blogs and comments tables...")
        # Build random Overwatch password.
        characters = string.ascii_letters + string.digits  # A-Z, a-z, 0-9
        overwatch_password = ''.join(random.choices(characters, k=20))
        print(f"[{now()}][*] Adding AI_OVERWATCH to users table.") 
        add_user_to_challenge_database(challenge_id, "AI_OVERWATCH", overwatch_password, 0, 0, 0)
        print(f"[{now()}][*] Configuring AI_OVERWATCH permission to access Blog.") 
        set_single_user_permission(challenge_id, target_url, "AI_OVERWATCH")
        user_id = get_user_id(challenge_id, "AI_OVERWATCH")
        blog_id = create_blogs_and_comments_tables(challenge_id, target_url.removesuffix(".php"), user_id)
        print(f"[{now()}][*] Creating puppet for blog...") 
        create_puppet(challenge_id, "AI_OVERWATCH", overwatch_password, f"/auth_{target_url}?view={blog_id}",
              base_url=f"http://{WEB_HOST_IP}:{FIRST_PORT_NUMBER}{challenge_id}")

    if gate_type == "api":
        print(f"[{now()}][*] Randomising Swagger JSON filename...")
        # Randomising the file name prevents players from directly finding the API definitions on subsequent runs.
        characters = string.ascii_letters + string.digits  # A-Z, a-z, 0-9
        random_file_name = ''.join(random.choices(characters, k=20))
        try:
            swagger_initialiser = Path("swagger") / "swagger-initializer.js"
            with open(FACTORY_FLOOR / swagger_initialiser, "r") as f:
                data = f.read()

            # Replace the target string
            data = data.replace("swagger.json", f"{random_file_name}.json")

            # Write the file back
            with open(FACTORY_FLOOR / swagger_initialiser, "w") as f:
                f.write(data)
            
            # Rename swagger.json file
            original_json = Path("swagger") / "swagger.json"
            new_json = Path("swagger") / f"{random_file_name}.json"
            os.rename(FACTORY_FLOOR / original_json, FACTORY_FLOOR / new_json)
        except Exception as e:
            raise print(f"[{now()}][*] ERROR: {e}")
        
        # Modifying the READ ONLY db-user account for the challenge database, to be used by the challenge itself.
        # TODO: Fix the API database user so that it creates a new database user with SELECT, UPDATE, and INSERT permissions
        # instead of modifying the readonly user to have INSERT permissions - similar to how it is done with the Blogs user.
        challenge_db_username = f"readonly{challenge_id}"

        cnx = master_db()
        cursor = cnx.cursor()
        try:
            grant_sql = f"GRANT INSERT ON `{challenge_id}`.users TO '{challenge_db_username}'@'%'"
            cursor.execute(grant_sql)
            grant_sql = f"GRANT UPDATE ON `{challenge_id}`.users TO '{challenge_db_username}'@'%'"
            cursor.execute(grant_sql)
            cursor.execute("FLUSH PRIVILEGES")
            cnx.commit()
            print(f"[{now()}][*] User '{challenge_db_username}' modified to include INSERT and UPDATE permissions to database '{challenge_id}'.")
        except Exception as e:
            print(f"[{now()}][*] ERROR: {e}")
            cursor.close()
            cnx.close()
            return
        cursor.close()
        cnx.close()

    # Attached gate module to the auth_target
    file_location = Path(FACTORY_FLOOR) / f"auth_{target_url}"
    include_page = f"include '{page_to_include}';\n"
    auth_page = f"require_auth('{target_url.removesuffix(".php")}');\n"
    print(f"[{now()}][*] Replacing placeholders in:",file_location)
    try:
        with open(file_location, "r", encoding="utf-8") as f:
            lines = f.readlines()
        with open(file_location, "w", encoding="utf-8") as f:
            for line in lines:
                stripped = line.strip()
                if stripped == "include 'placeholder.php';":
                    f.write(include_page)
                elif stripped == "//INSERT GATE HEADER HERE":
                    f.write(auth_page)
                else:
                    f.write(line)
        print(f"[{now()}][*] Updates saved.")
    except FileNotFoundError:
        print(f"[{now()}][*] File '{file_location}' not found, skipping.")
    except Exception as e:
        print(f"[{now()}][*] ERROR: {e}")
    return

# Middleware generator for PHP templates.
def build_middleware(auth_target, gate):
    # auth_target will be hub.php, research.php, or work.php
    data = {
    "source": "$source",
    "destination": f"/auth_{auth_target}",
    "start": f"/{auth_target}",
    "u": "$u",
    "p": "$p",
    "user": "$user"
    }
    source_file = Path(MODULE_TEMPLATES) / "php_templates" / "middleware.php"
    # If you intended an underscore, use f"{gate}_middleware.php"
    new_file = Path(FACTORY_FLOOR) / f"{gate}middleware.php"

    try:
        if not source_file.exists():
            raise FileNotFoundError(f"Template not found: {source_file}")

        text = source_file.read_text(encoding="utf-8")
        # Escape ALL $ so Template won't interpret PHP variables
        # (Template outputs a single '$' for '$$')
        protected = re.sub(r"\$", r"$$", text)
        # Whitelist ONLY our placeholders (destination, start, u, p, user)
        for key in ("destination", "start", "u", "p", "user"):
            protected = protected.replace(f"$${key}", f"${key}")
        # Substitute (not safe_substitute) to surface missing keys
        rendered = Template(protected).substitute(data)

        new_file.parent.mkdir(parents=True, exist_ok=True)
        new_file.write_text(rendered, encoding="utf-8")
        print(f"[{now()}][*] Wrote {new_file.resolve()} ({len(rendered)} bytes)")
    except Exception as e:
        print(f"[{now()}][*] ERROR: Problem building middleware file for gate '{gate}': {e!r}")
        traceback.print_exc()
        raise
    return

# Attaches a lock to a gate.  
def add_auth_module_and_gateheader(target_url, auth_required, platform_module_pool, gate_counter): 
    """
    Adds the "auth" lock to applicable gates. 
    Points the "auth" module at the applicable middleware.
    Not currently using "auth_required", but will need to once more options/features are worked in.
    """
    auth_module = "auth" # Folder location for authentication modules
    auth_module_selection = "1" # TODO If other authentication modules are developed, can randomise selection.
    gate_header_file = f"{gate_counter}gate_header.php"

    # Placeholder modification
    site_filepath = Path(FACTORY_FLOOR) / target_url
    try:
        with open(site_filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()
        with open(site_filepath, "w", encoding="utf-8") as f:
            for line in lines:
                stripped = line.strip()
                if stripped == "include 'placeholder.php';":
                    f.write(f"include '{gate_counter}{auth_module}.php';\n")
                elif stripped == "//INSERT GATE HEADER HERE":
                    f.write(f"include '{gate_header_file}';\n")
                else:
                    f.write(line)
        print(f"[{now()}][*] Updated file: {site_filepath}")
    except FileNotFoundError:
        print(f"[{now()}][*] ERROR: File '{site_filepath}' not found.")
        return
    except Exception as e:
        print(f"[{now()}][*] ERROR: {e}")
        return
    
    # Add the authentication module.
    auth_module_location = Path(platform_module_pool) / auth_module / auth_module_selection
    print(f"[{now()}][*] Copying authentication module to factory floor.")
    shutil.copytree(auth_module_location, FACTORY_FLOOR, dirs_exist_ok=True) # Grab whole auth module directory contents
    os.rename(f"{FACTORY_FLOOR}/auth.php", f"{FACTORY_FLOOR}/{gate_counter}auth.php")

    # Replace placeholder in the auth module with the applicable middleware.
    filepath = Path(FACTORY_FLOOR) / f"{gate_counter}{auth_module}.php"
    middleware_file_name = f"{gate_counter}middleware.php"
    
    try:
        with open(filepath, "r", encoding="utf-8-sig", newline="") as f:
            text = f.read()
        new_text = text.replace("$middle", middleware_file_name, 1)
        if new_text == text:
            print(f"[{now()}][*] ERROR: No $middle placeholder value found.")
        else:
            print(f"[{now()}][*] Inserted:",middleware_file_name)

        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            f.write(new_text)
        print(f"[{now()}][*] Updated module saved.")
        return
    except FileNotFoundError:
        print(f"[{now()}][*] {filepath} not found, skipping.")
    except Exception as e:
        print(f"[{now()}][*] ERROR: {e}")
    return

# Add flag/code to the challenge's database.
def database_flag(challenge_id, flag, table_name):
    # Note: table_name is interpolated into SQL; validate/whitelist it upstream.
    database_name = str(challenge_id)  # Keep DB name same as challenge ID.
    # Connect to SQL server and select the database.
    cnx = master_db()
    cursor = cnx.cursor()

    try:
        cnx.database = f"`{database_name}`"
    except Exception as e:       
        try:
            cnx.database = f"{database_name}"
        except Exception as e:
            print(f"[{now()}][!] WARNING: Problem selecting database {database_name}, regardless of backticks...")
            raise (f"[{now()}][!] ERROR:",e)

    # Create the table
    create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS `{table_name}` (
            id INT AUTO_INCREMENT PRIMARY KEY,
            code_value VARCHAR(25) NOT NULL UNIQUE,
            description VARCHAR(200)
        )
    """
    try:
        cursor.execute(create_table_sql)
        print(f"[{now()}][*] Table '{table_name}' created or already exists.")
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_TABLE_EXISTS_ERROR:
            print(f"[{now()}][*] ERROR: Table '{table_name}' already exists.")
        else:
            print(f"[{now()}][*] ERROR:", err.msg)
            cursor.close()
            cnx.close()
            raise
    
    # Insert the flag
    insert_sql = f"""
        INSERT INTO `{table_name}` (code_value, description)
        VALUES (%s, %s)
    """
    description = "Code can be used to deactivate the system in an emergency."

    try:
        cursor.execute(insert_sql, (flag, description))
        print(f"[{now()}][*] Table '{table_name}' created or already exists.")
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_TABLE_EXISTS_ERROR:
            print(f"[{now()}][*] ERROR: Table '{table_name}' already exists.")
        else:
            print(f"[{now()}][*] ERROR:", err.msg)
            cursor.close()
            cnx.close()
            raise
           
    cnx.commit()
    cursor.close()
    cnx.close()
    return

# Creates the config file and gate_header files used by challenge
def write_php_config(challenge_id, challenge_db_username, challenge_db_password, platform_templates, gate_chain):
    """
    Builds the PHP config file for each challenge that uses a PHP template.
    """
    # Default secure and auth settings.
    # TODO: Code a better way of managing secure auth.
    work_secure_auth = "true"
    research_secure_auth = "true"
    hub_secure_auth = "true"
    work_locked = "true"
    research_locked = "true"
    hub_locked = "true"
    # "cookie_reset" used to generate a unique cookie for each challenge, which governs removing any other challenge's cookies.
    cookie_reset = f"check{challenge_id}" 

    # First loop
    for item in gate_chain:
        try:
            if item.get("current_gate_key") == "sqli":
                if item.get("entry_point") == "research.php":
                    research_secure_auth = "false"
                elif item.get("entry_point") == "work.php":
                    work_secure_auth = "false"
                elif item.get("entry_point") == "hub.php":
                    hub_secure_auth = "false"
        except Exception as e:
            print(f"[{now()}][*] Next...")

    # Second loop
    for item in gate_chain:
        try:
            if item.get("current_gate_key") in ("none", "n/a"):
                if item.get("entry_point") == "research.php":
                    # research_locked = "false"
                    research_locked = "true"
                elif item.get("entry_point") == "work.php":
                    # work_locked = "false"
                    work_locked = "true"
                elif item.get("entry_point") == "hub.php":
                    # hub_locked = "false"
                    hub_locked = "true"
        except Exception as e:
            print(f"[{now()}][*] Next...")

    print(f"[{now()}][*] Work auth:", work_locked)
    print(f"[{now()}][*] Research auth:", research_locked)
    print(f"[{now()}][*] Hub auth:", hub_locked)
    print(f"[{now()}][*] Work secure:", work_secure_auth)
    print(f"[{now()}][*] Research secure:", research_secure_auth)
    print(f"[{now()}][*] Hub secure:", hub_secure_auth)

    print(f"[{now()}][*] Prepping PHP config...")
    # Config file into factory floor
    
    data = {
        "_COOKIE": "$_COOKIE",
        "name": "$name",
        "value": "$value",
        "cookiecheck": cookie_reset,
        "workauth": work_locked,
        "researchauth": research_locked,
        "systemauth": hub_locked,
        "worksecure": work_secure_auth,
        "researchsecure": research_secure_auth,
        "systemsecure": hub_secure_auth,
        "host": DATABASE_HOST_IP, # Global variable
        "db": str(challenge_id),
        "dbuser": challenge_db_username,
        "dbpassword": challenge_db_password,
        "e": "$e",
        "pdo": "$pdo",
        "stmt": "$stmt",
        "username": "$username",
        "user": "$user",
        "password": "$password",
        "permission": "$permission",
        "source": "$source",
        "params": "$params",
        "sql": "$sql",
        "res": "$res",
        "_SESSION": "$_SESSION",
        "_SERVER": "$_SERVER",
        "data": "$data",
        "output": "$output",
        "perm": "$perm"
    }

    source_file = Path(MODULE_TEMPLATES) / platform_templates / "config.php"
    new_config_file = Path(FACTORY_FLOOR) / "config.php"

    try:
        if not source_file.exists():
            raise FileNotFoundError(f"[{now()}][!] Template not found: {source_file}")
        text = source_file.read_text(encoding="utf-8")
        tmpl = Template(text)
        # Use substitute to catch missing placeholders
        rendered = tmpl.substitute(data)
        new_config_file.parent.mkdir(parents=True, exist_ok=True)
        new_config_file.write_text(rendered, encoding="utf-8")
        print(f"[{now()}][*] Wrote {new_config_file.resolve()} ({len(rendered)} bytes)")
    except Exception as e:
        print(f"[{now()}][!] Problem generating PHP config: {e!r}")
        traceback.print_exc()
        raise
    
    index = 1
    for item in gate_chain:
        middleware_file = "/"+str(index)+"middleware.php"
        data = {
            "middleware": str(middleware_file),  # ensure string
            "messages": "$messages",           # will render literally as $messages
            "err": "$err",                     # will render literally as $err
        }
        source_file = Path(MODULE_TEMPLATES) / platform_templates / "gate_header.php"
        new_config_file = Path(FACTORY_FLOOR) / f"{index}gate_header.php"
        try:
            if not source_file.exists():
                raise FileNotFoundError(f"Template not found: {source_file}")
            text = source_file.read_text(encoding="utf-8")
            # Tried to escape ALL $ so Template won't try to interpret PHP variables, but I don't think it worked.
            text_escaped = re.sub(r"\$", r"$$", text) 
            # Un-escape ONLY the placeholders.
            for key in ("middleware", "messages", "err"):
                text_escaped = text_escaped.replace(f"$${key}", f"${key}")
            # Substitute (not safe_substitute) so missing keys raise.
            rendered = Template(text_escaped).substitute(data)

            new_config_file.parent.mkdir(parents=True, exist_ok=True)
            new_config_file.write_text(rendered, encoding="utf-8")

            print(f"[{now()}][*] Wrote {new_config_file.resolve()} ({len(rendered)} bytes)")
            index += 1
        except Exception as e:
            print(f"[{now()}][!] ERROR: Problem copying gate_header.php file: {e!r}")
            traceback.print_exc()
            raise
    print(f"[{now()}][*] PHP config and gate_header files complete.")
    return

# If a "blog" gate is required, this builds the table in the challenge database.
def create_blogs_and_comments_tables(challenge_id, entry_point, user_id):  
    database_name = str(challenge_id)
    conn = database_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        # Get 3 blog posts based on the entry_point (work, hub, research).
        sql = """
            SELECT user_id, date, title, body FROM blogs WHERE type = %s
            """
        cursor.execute(sql, (entry_point,),)
        blog_posts = cursor.fetchall()
        blog_posts = random.sample(blog_posts, min(3, len(blog_posts))) # Randomly select 3 blog posts.

        # Randomly select 10 comments.
        cursor.execute("SELECT blog_id, body, created_on FROM comments ORDER BY RAND() LIMIT 10;")
        comments = cursor.fetchall()
        
    except Exception as e:
        print(f"[{now()}][!] ERROR: Problem selecting blog posts.")
        cursor.close()
        conn.close()
        raise print(f"[{now()}][*] ERROR:",e)
    cursor.close()
    conn.close()

    # Switching users for different databases. Should probably revise this approach.
    cnx = master_db()
    cursor = cnx.cursor(dictionary=True)
    # Select the challenge database
    try:
        cnx.database = f"`{database_name}`"
    except Exception as e:       
        try:
            cnx.database = f"{database_name}"
        except Exception as e:
            print(f"[{now()}][!] WARNING: Problem selecting database {database_name}, regardless of backticks...")
            raise (f"[{now()}][!] ERROR:",e)
        
    print(f"[{now()}][*] Database selected for create_blogs_and_comments_tables:", database_name)
    # SQL statements for table creation.
    blogs_table = """
    CREATE TABLE IF NOT EXISTS blogs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT,
        user_last_seen datetime NOT NULL,
        title text NOT NULL,
        body text NOT NULL,
        date datetime NOT NULL
    )
    """
    comments_table = """
    CREATE TABLE IF NOT EXISTS comments (
        id INT AUTO_INCREMENT PRIMARY KEY,
        blog_id INT,
        body text NOT NULL,
        created_on datetime NOT NULL,
        deleted_on datetime DEFAULT NULL
    )
    """
    # Execute table creation.
    try:
        cursor.execute(comments_table)
        cnx.commit()
        cursor.execute(blogs_table)
        cnx.commit()
        print(f"[{now()}][*] 'blogs' and 'comments' tables created.")
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_TABLE_EXISTS_ERROR:
            print(f"[{now()}][!] ERROR: Table 'blogs' or 'comments' already exists. Continuing...")
        else:
            cursor.close()
            cnx.close()
            raise print(f"[{now()}][!] ERROR:", err.msg)
    # Insert data into tables.
    print(f"[{now()}][*] Inserting data rows into 'blogs' table...")
    insert_query = """
        INSERT INTO blogs (user_id, user_last_seen, title, body, date)
        VALUES (%s, %s, %s, %s, %s)
    """
    blog_id = random.randint(1,3) # Select random blog post to be the one with the puppet watching.
    i = 1
    try:
        for row in blog_posts:
            if i == blog_id:
                print(f"[{now()}][*] MATCHING BLOG_ID: Inserting user_id:",user_id)
                cursor.execute(insert_query, (user_id, blog_posts[i-1]['date'], blog_posts[i-1]['title'], 
                                              blog_posts[i-1]['body'], blog_posts[i-1]['date']))
                i+=1
            else:
                cursor.execute(insert_query, (i, blog_posts[i-1]['date'], blog_posts[i-1]['title'], 
                                              blog_posts[i-1]['body'], blog_posts[i-1]['date']))
                i+=1
    except Exception as e:
        cursor.close()
        cnx.close()
        raise print(f"[{now()}][*] ERROR:",e)
    cnx.commit() 
    print(f"[{now()}][*] Inserting data rows into 'comments' table...")
    insert_query = """
        INSERT INTO comments (blog_id, body, created_on)
        VALUES (%s, %s, %s)
    """
    i = 1
    try:
        # Distribute comments between the blog posts. Assumes 3 blog posts.
        for row in comments: 
            if i < 3:
                x = 1
            elif i < 6:
                x = 2
            else:
                x = 3
            cursor.execute(insert_query, (x, row['body'], row['created_on']))
            i+=1
    except Exception as e:
        cursor.close()
        cnx.close()
        raise print(f"[{now()}][*] ERROR:",e)
    cnx.commit()

    # Creating a user account for this table.
    characters = string.ascii_letters + string.digits  # A-Z, a-z, 0-9
    module_username = str(challenge_id)+"blog" # Remove the plural from the table name.
    module_password = ''.join(random.choices(characters, k=20))
    try:
        cursor.execute(
            f"CREATE OR REPLACE USER `{module_username}`@'%' IDENTIFIED BY %s",
            (module_password,)
        )
        cursor.execute(
            f"GRANT SELECT, INSERT, UPDATE ON `{database_name}`.`blogs` TO `{module_username}`@'%'"
        )
        cursor.execute(
            f"GRANT SELECT, INSERT, UPDATE ON `{database_name}`.`comments` TO `{module_username}`@'%'"
        )
        cursor.execute(
            f"GRANT SELECT ON `{database_name}`.`users` TO `{module_username}`@'%'"
        )
        cursor.execute("FLUSH PRIVILEGES")
        cnx.commit()
    except Exception as e:
        cursor.close()
        cnx.close()
        raise print(f"[{now()}][*] ERROR: Problem creating database user:", e)
    cursor.close()
    cnx.close()
    print(f"[{now()}][*] User '{module_username}' created for 'blogs' and 'comments' tables.")
    create_module_database_user_and_config_file(challenge_id, module_username, module_password, "blogs")  
    return blog_id

# If a "products" gate is required, this builds the table in the challenge database.
def create_products_table(challenge_id):
    table_name = "products"
    conn = database_connection()
    cursor = conn.cursor(dictionary=True)
    system_folder_list = []
    database_name = str(challenge_id)
    try:
        cursor.execute("SELECT DISTINCT system FROM systemflavours;")
        systems = [row["system"] for row in cursor.fetchall()]

        sampled_systems = random.sample(systems, min(5, len(systems)))

        if not sampled_systems:
            products_for_challenge_db = []
        else:
            # Build placeholders dynamically.
            placeholders = ", ".join(["%s"] * len(sampled_systems))

            # Get rows for those systems; ORDER BY RAND() so the one we keep per system is random.
            query = f"""
                SELECT system, about, description
                FROM systemflavours
                WHERE system IN ({placeholders})
                ORDER BY RAND()
            """
            cursor.execute(query, tuple(sampled_systems))
            rows = cursor.fetchall()

            # Dedupe to one row per system (keep the first seen, which is random due to ORDER BY RAND()).
            seen = set()
            unique_rows = []
            for r in rows:
                s = r["system"]
                if s not in seen:
                    unique_rows.append(r)
                    seen.add(s)
                if len(unique_rows) == len(sampled_systems):  # We have one row per sampled system.
                    break

            products_for_challenge_db = unique_rows

            sql = """
            SELECT folder FROM systems WHERE system = %s
            """
            for row in products_for_challenge_db:
                cursor.execute(sql, (row['system'],))
                row = cursor.fetchone()
                system_folder_list.append(row["folder"] if row else None)

    except Exception as e:
        cursor.close()
        conn.close()
        raise print(f"[{now()}][*] ERROR:",e)
    cursor.close()
    conn.close()
    print(f"[{now()}][*] Have found 5 items for the products table...")
    # Switching users for different databases, because I'm inefficient like that.
    cnx = master_db()
    cursor = cnx.cursor(dictionary=True)
    # Select the new database.
    try:
        cnx.database = f"`{database_name}`"
    except Exception as e:       
        try:
            cnx.database = f"{database_name}"
        except Exception as e:
            print(f"[{now()}][!] WARNING: Problem selecting database {database_name}, regardless of backticks...")
            raise (f"[{now()}][!] ERROR:",e)

    print(f"[{now()}][*] Database selected:", database_name)
    # SQL statements for table creation.
    new_table = """
    CREATE TABLE IF NOT EXISTS products (
        id INT AUTO_INCREMENT PRIMARY KEY,
        product_name VARCHAR(50),
        about VARCHAR(800),
        description VARCHAR(800)
    )
    """
    # Execute table creation.
    try:
        cursor.execute(new_table)
        print(f"[{now()}][*] Table '{table_name}' created.")
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_TABLE_EXISTS_ERROR:
            print(f"[{now()}][!] ERROR: Table '{table_name}' already exists.")
        else:
            print(f"[{now()}][!] ERROR:", err.msg)
            cursor.close()
            cnx.close()
            return
    # Insert into products table.
    try:
        insert_query = """
            INSERT INTO products (product_name, about, description)
            VALUES (%s, %s, %s)
        """
        i = 0
        for row in products_for_challenge_db:
            cursor.execute(insert_query, (row['system'], row['about'], row['description']))
            # Flavour image selection - Default is 8 system images.
            try:
                directory_path = Path(FLAVOUR_FOLDER) / system_folder_list[i]
                i += 1
                # List all files in the directory.
                all_files = [f for f in os.listdir(directory_path) if os.path.isfile(os.path.join(directory_path, f))]
                # Randomly select image.
                selected_files = random.sample(all_files, 1)
                # Copy and rename image files.
                for index, filename in enumerate(selected_files, start=1):
                    src_path = os.path.join(directory_path, filename)
                    # Preserve file extension.
                    new_filename = f"{row['system']}.jpg"
                    dest_path = os.path.join(FACTORY_FLOOR, new_filename)
                    # Copy the file.
                    shutil.copy2(src_path, dest_path)
            except Exception as e:
                print(f"[{now()}][!] ERROR: Problem copying product image:", e)
                return
    except Exception as e:
        cursor.close()
        cnx.close()
        raise print(f"[{now()}][!] ERROR:",e)
    cnx.commit()
    print(f"[{now()}][*] Inserted items rows into {table_name} table.")

    # Creating a READ ONLY user account for this table only.
    characters = string.ascii_letters + string.digits  # A-Z, a-z, 0-9
    module_username = str(challenge_id)+"product" # Remove the plural from the table name.
    module_password = ''.join(random.choices(characters, k=20))
    database_name = str(challenge_id)
    try: # This will REPLACE any existing user of this table.
        cursor.execute(
            f"CREATE OR REPLACE USER `{module_username}`@'%' IDENTIFIED BY %s",
            (module_password,)
        )
        # Grant only SELECT privilege on the target database.
        cursor.execute(
            f"GRANT SELECT ON `{database_name}`.`products` TO `{module_username}`@'%'"
        )
        cursor.execute("FLUSH PRIVILEGES")
        cnx.commit()
    except Exception as e:
        cursor.close()
        cnx.close()
        raise print(f"[{now()}][!] ERROR: Problem creating database user:", e)
    cursor.close()
    cnx.close()
    print(f"[{now()}][*] User '{module_username}' created for 'products' table.")
    create_module_database_user_and_config_file(challenge_id, module_username, module_password, table_name)
    return

# Creates a new (or replaces existing) challenge specific database credential/access file.
def create_module_database_user_and_config_file(challenge_id, module_username, module_password, table_name):
    """
    Where a specific challenge or module requires its own access to the database, 
    a config file with credentials for that module is provided in its own config file,
    based on the table name within the database that relates to the module/challenge.
    """
    # Prep challenge database credentials for page specific config file.
    db_dsn = f"const {table_name}DB_DSN  = 'mysql:host={DATABASE_HOST_IP};dbname={challenge_id};charset=utf8mb4';"
    db_usr = f"const {table_name}DB_USER = '{module_username}';"
    db_pass = f"const {table_name}DB_PASS = '{module_password}';"
    php_code = f"""function {table_name}_db(): PDO {{
    static $pdo = null;
    if ($pdo === null) {{
        $pdo = new PDO({table_name}DB_DSN, {table_name}DB_USER, {table_name}DB_PASS, [
            PDO::ATTR_ERRMODE            => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        ]);
    }}
    return $pdo;
    }}"""
    # Write them to the config file...
    with open(Path(FACTORY_FLOOR / f"{table_name}_db.php"), "w", encoding="utf-8") as f:
        f.write(f"<?php\n")
        f.write(f"{db_dsn}\n")
        f.write(f"{db_usr}\n")
        f.write(f"{db_pass}\n")    
        f.write(f"{php_code}\n") 
        f.write(f"?>\n")
    print(f"[{now()}][*] {table_name} Challenge database config written to factory floor.")
    return

# Adds a new user to the challenge database and configure the user's permissions.
def add_user_to_challenge_database(challenge_id, new_challenge_username, new_challenge_password, work, research, hub):
    database_name = str(challenge_id) # Keeping each challenge's database name the same as its ID
    print(f"[{now()}][*] Adding one user to DB:", database_name)
    try:
        user_email = (new_challenge_username+"@"+corp_name+".ai").replace(" ", "").lower()
        names = get_firstnames_lastnames(2) # While we are only using one name, gonna ask for two - cause reasons.
        firstname = names[0]['firstname']
        lastname = names[0]['lastname']
    except Exception as e:
        print(f"[{now()}][*] ERROR:",e)
        return
    
    cnx = master_db()
    cursor = cnx.cursor()
    try:
        cnx.database = f"`{database_name}`"
    except Exception as e:       
        try:
            cnx.database = f"{database_name}"
        except Exception as e:
            print(f"[{now()}][!] WARNING: Problem selecting database {database_name}, regardless of backticks...")
            raise (f"[{now()}][!] ERROR:",e)
    try:
        check_sql = "SELECT work, research, hub FROM users WHERE username = %s"
        cursor.execute(check_sql, (new_challenge_username,))
        result = cursor.fetchone()
        if result:
            update_sql = """
            UPDATE users
            SET 
                work = CASE WHEN work = 0 THEN %s ELSE work END,
                research = CASE WHEN research = 0 THEN %s ELSE research END,
                hub = CASE WHEN hub = 0 THEN %s ELSE hub END
            WHERE username = %s
            """
            cursor.execute(update_sql, (work, research, hub, new_challenge_username))
            cnx.commit()

            print(f"[{now()}][*] User exists. Updated permissions for:", new_challenge_username)
        else:
            insert_sql = """
            INSERT INTO users (username, password, firstname, lastname, email, work, research, hub)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_sql, (
                new_challenge_username,
                new_challenge_password,
                firstname,
                lastname,
                user_email,
                work,
                research,
                hub
            ))
            cnx.commit()
            print(f"[{now()}][*] New user added:", new_challenge_username)
    except mysql.connector.Error as e:
        print(f"[{now()}][!] ERROR: MySQL error: {e}")
    except Exception as e:
        print(f"[{now()}][!] ERROR: {e}")
    cursor.close()
    cnx.close()
    print(f"[{now()}][*] Complete: New user added to challenge user table.")
    return

# Modify the challenge database to set mass permissions for all users.
def set_mass_user_permissions(challenge_id, permission, value):
    # 'permission' can be work.php, research.php, or hub.php (with or without extension).
    database_name = str(challenge_id)
    try:
        permission = permission.removesuffix(".php")
    except Exception as e:
        print(f"[{now()}][*] NOTE: Could not remove extension from permission. Likely already cleaned:",e)
    cnx = master_db()
    cursor = cnx.cursor()
    try:
        cnx.database = f"`{database_name}`"
    except Exception as e:       
        try:
            cnx.database = f"{database_name}"
        except Exception as e:
            print(f"[{now()}][!] WARNING: Problem selecting database {database_name}, regardless of backticks...")
            raise (f"[{now()}][!] ERROR:",e)
    try:
        query = f"UPDATE `users` SET `{permission}` = {value}"
        cursor.execute(query)
        cnx.commit()
        print(f"[{now()}][*] Updated {cursor.rowcount} rows in 'users.{permission}' to {value}")

    except mysql.connector.Error as err:
        raise print(f"[{now()}][*] ERROR:", err.msg)
    finally:
        cursor.close()
        cnx.close()

# Modify the challenge database to set a single random user's permission.
def set_single_user_permission(challenge_id, permission, username):
    # Permission can be work.php, research.php, or system.php (with or without extension).
    database_name = str(challenge_id)
    try:
        permission = permission.removesuffix(".php")
    except Exception as e:
        print(f"[{now()}][*] NOTE: Could not remove extension from permission. Likely already cleaned:", e)
    cnx = master_db()
    cursor = cnx.cursor()
    try:
        cnx.database = f"`{database_name}`"
    except Exception as e:       
        try:
            cnx.database = f"{database_name}"
        except Exception as e:
            print(f"[{now()}][!] WARNING: Problem selecting database {database_name}, regardless of backticks...")
            raise (f"[{now()}][!] ERROR:",e)
    try:
        # Basic safety check: only allow alphanumeric + underscores
        if not permission.replace("_", "").isalnum():
            cnx.close()
            cursor.close()
            return ValueError(f"[{now()}][!] ERROR: Unsafe column name.")
        query = f"UPDATE users SET {permission} = %s WHERE username = %s"
        cursor.execute(query, (1, username))
        cnx.commit()
    except mysql.connector.Error as err:
        print(f"[{now()}][*] ERROR:", err.msg)
    finally:
        cnx.close()
        cursor.close()

# Modify the challenge database to set a single random user's permission.
def randomly_set_single_user_permission(challenge_id, permission):
    """
    From the first 10 users in the table, this function randomly selects one user and update's their permissions.
    """
    # Permission can be work.php, research.php, or system.php (with or without extension).
    database_name = str(challenge_id)
    try:
        permission = permission.removesuffix(".php")
    except Exception as e:
        print(f"[{now()}][*] NOTE: Could not remove extension from permission. Likely already cleaned:", e)
    cnx = master_db()
    cursor = cnx.cursor()
    try:
        cnx.database = f"`{database_name}`"
    except Exception as e:       
        try:
            cnx.database = f"{database_name}"
        except Exception as e:
            print(f"[{now()}][!] WARNING: Problem selecting database {database_name}, regardless of backticks...")
            raise (f"[{now()}][!] ERROR:",e)
    try:
        # Basic safety check: only allow alphanumeric + underscores
        if not permission.replace("_", "").isalnum():
            raise ValueError("[*] ERROR: Unsafe column name")
        rand_id = random.randint(1, 10) # Assumes there are 10 users in the users table to randomly select from.
        query = f"UPDATE `users` SET `{permission}` = 1 WHERE id = %s LIMIT 1"
        cursor.execute(query, (rand_id,))
        cnx.commit()
    except mysql.connector.Error as err:
        print(f"[{now()}][*] ERROR:", err.msg)
    finally:
        cnx.close()
        cursor.close()

# Creates PHP session_token key.
def php_session_id(sid_length=26, bits_per_char=5):
    """
    Generate a PHP-style session ID using Python's CSPRNG.
    Matches PHP's sid_bits_per_character and sid_length semantics.

    Args:
      sid_length (int): number of characters (1..256)
      bits_per_char (int): 4, 5, or 6

    Returns:
      str: synthetic PHPSESSID value

    Examples:
    print("Default-ish (26 chars, 5 bits):", php_session_id(26, 5))
    print("Hex style (32 chars, 4 bits):  ", php_session_id(32, 4))
    print("Max entropy demo (64 chars, 6):", php_session_id(64, 6))
    """
    if not (1 <= sid_length <= 256):
        raise ValueError("sid_length must be between 1 and 256")
    if bits_per_char not in (4, 5, 6):
        raise ValueError("bits_per_char must be 4, 5, or 6")

    if bits_per_char == 4:
        alphabet = "0123456789abcdef"
    elif bits_per_char == 5:
        alphabet = "0123456789abcdefghijklmnopqrstuv"  # 0-9 + a-v
    else:  # 6 bits/char
        alphabet = string.digits + string.ascii_lowercase + string.ascii_uppercase + ",-"

    return "".join(secrets.choice(alphabet) for _ in range(sid_length))

# Set the session_token key.
def set_session_token(challenge_id, token, target_gate_entry_point):
    """
    'target_gate_entry_point' essentially points to the page the token should auth.
    If session_token key is used this challenge, this should enforce its generation every time there is a page load. 
    Even if token is burned by a logout function, it should be recreated.
    """
    database_name = str(challenge_id)
    try:
        target_gate_entry_point = target_gate_entry_point.removesuffix(".php")
    except Exception as e:
        print(f"[{now()}][*] NOTE: Could not remove extension from target_gate_entry_point. Likely already removed:",e)
        print(f"[{now()}][*] Continuing...")
    cnx = master_db()
    cursor = cnx.cursor()
    try:
        cnx.database = f"`{database_name}`"
    except Exception as e:       
        try:
            cnx.database = f"{database_name}"
        except Exception as e:
            print(f"[{now()}][!] WARNING: Problem selecting database {database_name}, regardless of backticks...")
            raise (f"[{now()}][!] ERROR:",e)

    print(f"[{now()}][*] Database selected:", database_name)

    # SQL for table creation.
    session_sql = """
    CREATE TABLE IF NOT EXISTS session_tokens (
        id INT AUTO_INCREMENT PRIMARY KEY,
        token VARCHAR(50) NOT NULL UNIQUE,
        work BOOLEAN NOT NULL DEFAULT 0,
        hub BOOLEAN NOT NULL DEFAULT 0,
        research BOOLEAN NOT NULL DEFAULT 0
    )
    """
    # Execute table creation.
    try:
        cursor.execute(session_sql)
        print(f"[{now()}][*] Table 'session_tokens' created.")
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_TABLE_EXISTS_ERROR:
            print(f"[{now()}][!] ERROR: Table 'session_tokens' already exists.")
        else:
            raise print(f"[{now()}][!] ERROR:", err.msg)
    try:
        query = f"INSERT INTO session_tokens (token, {target_gate_entry_point}) VALUES (%s, %s)"
        data = (token, True)
        cursor.execute(query, data)
        cnx.commit()
        print(f"[{now()}][*] Session token added to database.")
    except mysql.connector.Error as err:
        raise print(f"[{now()}][!] ERROR:", err.msg)
    cursor.close()
    cnx.close()
    
    # This PHP code is automatically included by the main PHP 'config.php' file.
    php_code = f"""
    <?php
    $origName = session_name();
    $origId   = session_id();

    // Release the lock to open another session
    session_write_close();

    // Start/Use the SERVER-CONTEXT session (no cookies)
    $prevUseCookies      = ini_get('session.use_cookies');
    $prevUseOnlyCookies  = ini_get('session.use_only_cookies');
    ini_set('session.use_cookies', '0');
    ini_set('session.use_only_cookies', '0');

    // Create a new PHPSESSID
    session_name($origName);
    session_id('{token}'); 

    session_start();

    // Update values only inside $_SESSION['user']
    $_SESSION['user']['username'] = 'AI_Core_Override';
    $_SESSION['user']['work']     = 0;
    $_SESSION['user']['research'] = 0;
    $_SESSION['user']['hub']      = 0;
    $_SESSION['user']['uid']      = 'AI_Core_Override';
    
    // Set applicable permission
    $_SESSION['user']['{target_gate_entry_point}'] = 1;
    session_write_close();

    // Restore cookie INI settings
    ini_set('session.use_cookies', $prevUseCookies);
    ini_set('session.use_only_cookies', $prevUseOnlyCookies);

    // Restore original client session
    session_name($origName);
    session_id($origId);
    session_start();
    ?>
    """
    # Write to the config file...
    with open(Path(FACTORY_FLOOR / f"session_tokens.php"), "w", encoding="utf-8") as f:
        f.write(f"{php_code}") 
    print(f"[{now()}][*] 'session_tokens.php' file written to factory floor.")
    print(f"[{now()}][*] Session token:",token)
    return

# Builds and populates "employees" table in the challenge database.
def create_employee_table(challenge_id):
    global employee_table_exists
    if employee_table_exists == True:
        print(f"[{now()}][*] Employee table already exists, skipping...")
        return
    roles = ["Data Compliance Analyst", "Bio-Surveillance Technician", "Augmentation Support Specialist", "Behavioural Prediction Engineer",
             "Information Security Auditor", "PsychOps Coordinator", "Field Recon Operator", "Incident Containment Officer",
             "Threat Intelligence Curator", "Loyalty Enforcement Technician", "Engineer", "Consultant", "Technician", "Administrator"]
    divisions = ["Neural Systems Directorate", "AI Integration", "AI Enablement", "AI Resourcing", "Human Capital Division",
                 "Bioinformatics", "Corporate Security Operations", "Behavioural Analytics Bureau", "Information Control Division",
                 "Applied Cybernetics Group", "Special Projects Directorate", "Threat Intelligence & Response", 
                 "Continuity of Authority Office", "Augmented Workforce Division", "Engineering", "Maintenance"]
    streets = [ "Neon", "Circuit","Auger", "Firewall", "Glitch", "Obsidian", "Chrome", "Quantum", "Ghostnet", "Redline", "ZeroDay",
                "Pulse", "Vector", "Static", "Eclipse", "Data Spine", "Proxy", "Deadlink", "Synapse", "Overflow", "Darkwire", "Cortex",
                "Patchwork", "Backdoor", "Lattice", "Core Dump", "Iron Loop", "Entropy"]
    street_type = ["Road", "Lane", "Avenue", "Way", "Drive", "Alley", "Street", "Loop", "Row", "Boulevard", "Parkway", "Terrace"]
    districts = ["Neon Shallows", "Silicon Hollow", "Carbon Heights", "Grayscale Sector", "Optic Quarter", "Ash Sprawl", "Titan Core",
                 "Holo Basin", "Rustfront", "Echo Ward", "Spectra Zone", "Shatterline", "Vapor Heights", "Drift Sector", "Ion Reach", 
                 "Pulse Vents", "Gridfall", "Oblivion Arcology", "Wireframe Hub", "Flux Quarter", "Shadowscape", "Cryo Docks", 
                 "Forge Sector", "Radiant Loop", "Null Horizon", "Mycelium Blocks", "Vector Rise", "Stormgrid", "Afterlight Zone", 
                 "Phantom Verge"]
    count = 60 # How many names to pull.
    table_name = "employees"
    payload = []
    database_name = str(challenge_id) # Keeping each challenge's database name the same as its "challenge_id".
    
    try:
        cnx = database_connection() 
        cursor = cnx.cursor(dictionary=True)
        # Get random names.
        cursor.execute(f"SELECT firstname, lastname FROM names ORDER BY RAND() LIMIT {count}")
        names = cursor.fetchall() 
        payload = [
            (r["firstname"], r["lastname"], random.choice(roles), random.choice(divisions), random.randint(1, 9), 
            f"{random.randint(1, 999)} {random.choice(streets)} {random.choice(street_type)}, {random.choice(districts)} {''.join(random.sample(string.ascii_uppercase, 3))} {random.randint(1000, 9000)}",
            random.randint(1, 99), random.randint(1, 99), random.randint(1, 99), random.randint(1, 99), random.randint(1, 10),
            random.randint(1, 900), f"V{random.randint(1, 9)}.{random.randint(1, 99)}.{random.randint(1, 999)}",f"ID_{random.randint(100, 9999)}",
            random.randint(1, 900))
            for r in names
        ]
    except Exception as e:
        raise print(f"[{now()}][!] ERROR:", e)
    cursor.close()
    cnx.close()
        
    cnx = master_db()
    cursor = cnx.cursor(dictionary=True)
    exec_payload = [(fn, ln, role, "Executive", "10", "REDACTED", "99", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A", "N/A") for fn, ln, role in exec_details]

    # Select the new database.
    try:
        cnx.database = f"`{database_name}`"
    except Exception as e:       
        try:
            cnx.database = f"{database_name}"
        except Exception as e:
            print(f"[{now()}][!] WARNING: Problem selecting database {database_name}, regardless of backticks...")
            raise (f"[{now()}][!] ERROR:",e)
        
    # SQL statements for table creation.
    employee_table_query = """
    CREATE TABLE IF NOT EXISTS employees (
        id INT AUTO_INCREMENT PRIMARY KEY,
        firstname VARCHAR(25),
        lastname VARCHAR(25),
        role VARCHAR(50),
        division VARCHAR(50),
        clearance_level VARCHAR(4),
        address VARCHAR(100),
        efficiency_rating VARCHAR(4),
        treason_probability VARCHAR(4),
        replaceability_score VARCHAR(4),
        expendability_index VARCHAR(4),
        loyalty_tier VARCHAR(4),
        loyalty_credits VARCHAR(4),
        implant_firmware_version VARCHAR(10),
        blackmail_cache VARCHAR(20),
        rule_violations VARCHAR(4)
    )
    """
    # Execute table creation.
    try:
        cursor.execute(employee_table_query)
        print(f"[{now()}][*] Table 'employees' created.")
    except mysql.connector.Error as e:
        if e.errno == errorcode.ER_TABLE_EXISTS_ERROR:
            raise print(f"[{now()}][!] ERROR: Table 'employees' already exists.")
        else:
            raise print(f"[{now()}][!] ERROR:", e.msg)
    sql = """
    INSERT INTO employees (firstname,
        lastname,
        role,
        division,
        clearance_level,
        address,
        efficiency_rating,
        treason_probability,
        replaceability_score,
        expendability_index,
        loyalty_tier,
        loyalty_credits,
        implant_firmware_version,
        blackmail_cache,
        rule_violations) 
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    try:
        cursor.executemany(sql, exec_payload)
        print(f"[{now()}][*] Execs done...")
        cursor.executemany(sql, payload)
        print(f"[{now()}][*] Employees done...")
        cnx.commit()
    except mysql.connector.Error as e:
        if e.errno == errorcode.ER_NO_SUCH_TABLE:
            raise print(f"[{now()}][!] ERROR: 'employees' table not found. Was it created?:",e)
        else:
            raise print(f"[{now()}][!] ERROR: MySQL error:",e)
    # Creating a READ ONLY user account for this table...
    characters = string.ascii_letters + string.digits  # A-Z, a-z, 0-9
    module_username = str(challenge_id)+"employee" # Remove the plural from the table name.
    module_password = ''.join(random.choices(characters, k=20))
    try:
        cursor.execute(
            f"CREATE OR REPLACE USER `{module_username}`@'%' IDENTIFIED BY %s",
            (module_password,)
        )
        # Grant only SELECT privilege on the target database.
        cursor.execute(
            f"GRANT SELECT ON `{database_name}`.`employees` TO `{module_username}`@'%'"
        )
        cursor.execute("FLUSH PRIVILEGES")
        cnx.commit()
    except Exception as e:
        cursor.close()
        cnx.close()
        raise print(f"[{now()}][!] ERROR: Problem creating database user:", e)
    cursor.close()
    cnx.close()
    print(f"[{now()}][*] User '{module_username}' created for '{table_name}' table.")

    create_module_database_user_and_config_file(challenge_id, module_username, module_password, table_name)
    employee_table_exists = True # 'True' prevents this function running again for this challenge.
    return

# Modify challenge database user so it can access another table in the challenge database.
def add_table_access_to_db_user(challenge_id, gate_type, target_gate_key):
    # 'target_gate_key' is essentially the table name.
    database_name = str(challenge_id)
    # Remove the plural from the table/gate name to get challenge database username.
    if gate_type == "search":
        module_username = str(challenge_id)+"employee"
    elif gate_type == "employees":
        module_username = str(challenge_id)+"employee"
    elif gate_type == "products":
        module_username = str(challenge_id)+"product"
    elif gate_type == "blogs":
        module_username = str(challenge_id)+"blog"
    else:
        print(f"[{now()}][!] ERROR: Unsupported gate_type for table access function:",gate_type)
        raise
    
    # Modify 'target_key_name' for 'session_tokens' for database table reference.
    if target_gate_key in ("session_tokens", "session_token"):
        target_gate_key = "session_tokens"
    elif target_gate_key == "users":
        target_gate_key = "users" 
    elif target_gate_key not in FLAG_TABLE_NAMES:
        print(f"[{now()}][!] ERROR: 'target_gate_key' not 'session_tokens', 'users' or found in 'FLAG_TABLE_NAMES' list:",target_gate_key)        
        raise 

    cnx = master_db()
    cursor = cnx.cursor()
    try:
        cnx.database = f"`{database_name}`"
    except Exception as e:       
        try:
            cnx.database = f"{database_name}"
        except Exception as e:
            print(f"[{now()}][!] WARNING: Problem selecting database {database_name}, regardless of backticks...")
            print(f"[{now()}][!] ERROR:",e)
            raise
        
    # print(f"[{now()}][*] GRANT SELECT ON `{database_name}`.`{target_gate_key}` TO `{module_username}`@'%'")
    try:
        # Grant only SELECT privilege.
        cursor.execute(
            f"GRANT SELECT ON `{database_name}`.`{target_gate_key}` TO `{module_username}`@'%'"
        )
        cursor.execute("FLUSH PRIVILEGES")
        cnx.commit()
    except Exception as e:
        print(f"[{now()}][!] ERROR: Problem creating database user:", e)
        raise
    finally:
        cursor.close()
        cnx.close()

# Get x number of first and last names. 
def get_firstnames_lastnames(count):
    try:
        cnx = database_connection() # Labrandor database connection
        cursor = cnx.cursor(dictionary=True)
        # Get random names
        cursor.execute(f"SELECT firstname, lastname FROM names ORDER BY RAND() LIMIT {count}")
        names = cursor.fetchall() 
    except Exception as e:
        raise print(f"[{now()}][*] ERROR:",e)
    cursor.close()
    cnx.close()
    return names

# Create a challenge database + auth table for the challenge.
def create_challenge_database(challenge_id, challenge_db_username, challenge_db_user_password):
    """
    Creates a challenge database with and populates a 'users' table, used for authentication.
    Other tables and database users are added through other functions.
    The database user created by this function can only SELECT from the 'users' table.
    Other functions might modify this database user or add other users for different modules.
    """
    global picked_usernames
    global picked_passwords
    picked_usernames = []
    picked_passwords = [] 
    count = 10 # How many users to add to the "users" table?
    database_name = str(challenge_id) # Keeping each challenge's database name the same as its ID
    names = get_firstnames_lastnames(count) # Randomly grab some people names
    cnx = master_db()
    cursor = cnx.cursor()

    # Create the database if it doesn't exist.
    try:
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{database_name}`")
        print(f"[{now()}][*] Database '{database_name}' created.")
    except mysql.connector.Error as err:
        print(f"[{now()}][*] ERROR: Failed creating database: {err}")
        cursor.close()
        cnx.close()
        return

    # Select the new database.
    try:
        cnx.database = f"`{database_name}`"
    except Exception as e:       
        try:
            cnx.database = f"{database_name}"
        except Exception as e:
            print(f"[{now()}][!] WARNING: Problem selecting database {database_name}, regardless of backticks...")
            raise (f"[{now()}][!] ERROR:",e)
    print(f"[{now()}][*] Database selected:",database_name)

    # SQL statements for table creation.
    ddl_users = """
    CREATE TABLE IF NOT EXISTS users (
        id INT AUTO_INCREMENT PRIMARY KEY,
        username VARCHAR(50) NOT NULL UNIQUE,
        password VARCHAR(50) NOT NULL,
        firstname VARCHAR(50) NOT NULL DEFAULT 'John',
        lastname VARCHAR(50) NOT NULL DEFAULT 'Doe',
        email VARCHAR(100),
        work BOOLEAN NOT NULL DEFAULT 0,
        hub BOOLEAN NOT NULL DEFAULT 0,
        research BOOLEAN NOT NULL DEFAULT 0,
        securityquestion INT,
        securityanswer VARCHAR(50)
    )
    """
    # Execute table creation.
    try:
        cursor.execute(ddl_users)
        print(f"[{now()}][*] Table 'users' created.")
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_TABLE_EXISTS_ERROR:
            print(f"[{now()}][*] ERROR: Table 'users' already exists.")
        else:
            print(f"[{now()}][*] ERROR:", err.msg)
            cursor.close()
            cnx.close()
            return
    
    # Prepare everything to be written to database.
    print(f"[{now()}][*] Prepare everything to be written to database.")
    firstnames = [person['firstname'] for person in names]
    lastnames = [person['lastname'] for person in names]
    picked_usernames = random.sample(usernames, count)
    picked_passwords = random.sample(passwords, count)
    random.shuffle(picked_passwords)  # random pairing
    email_addresses = [(value+"@"+corp_name.replace(" ", "")+".ai").lower() for value in picked_usernames]
    security_questions = [random.randint(1,8) for _ in range(count)]
    characters = string.ascii_letters + string.digits  # A-Z, a-z, 0-9. This is only used to support the temporary 'security_answers'.
    security_answers = [''.join(random.choices(characters, k=20)) for _ in range(count)] # Modify when security questions gets implemented properly.

    rows = list(zip(picked_usernames, picked_passwords, firstnames, lastnames, email_addresses, security_questions, security_answers))
    print(f"[{now()}][*] Inserting users into database.")
    try:
        insert_sql = f"INSERT INTO users (username, password, firstname, lastname, email, work, hub, research, securityquestion, securityanswer) VALUES (%s, %s, %s, %s, %s, 0, 0, 0, %s, %s)"
        cursor.executemany(insert_sql, rows)
        cnx.commit()
        print(f"[{now()}][*] Inserted users.")
    except mysql.connector.Error as e:
        if err.errno == errorcode.ER_NO_SUCH_TABLE:
            print(f"[{now()}][*] ERROR: 'users' table not found. Did you create it?")
            cursor.close()
            cnx.close()
            return
        else:
            print(f"[{now()}][*] ERROR: MySQL error: {e}")
            cursor.close()
            cnx.close()
            return
    except Exception as e:
        print(f"[!] ERROR: {e}")

    # Creating a READ ONLY db-user account for the challenge database, to be used by the challenge itself.
    create_user_sql = f"CREATE USER IF NOT EXISTS '{challenge_db_username}'@'%' IDENTIFIED BY %s"
    cursor.execute(create_user_sql, (challenge_db_user_password,))

    # Grant only SELECT privilege on the target database.
    grant_sql = f"GRANT SELECT ON `{database_name}`.users TO '{challenge_db_username}'@'%'"
    cursor.execute(grant_sql)
    cursor.execute("FLUSH PRIVILEGES")
    cnx.commit()
    print(f"[{now()}][*] User '{challenge_db_username}' created with SELECT-only access to database '{database_name}'.")
    cursor.close()
    cnx.close()
    return

# Returns a random headshot record from the 'headshots' table.
def get_random_headshot(sex, ethnicity, role_value, excluded_IDs, cursor):
    """
    Returns a random headshot record from the 'headshots' table
    matching the given sex, ethnicity, and role, excluding specific roleids.

    Args:
        sex (str or list): Value to match in the 'sex' column
        ethnicity (str or list): Value to match in the 'ethnicity' column
        excluded_IDs (list): Role IDs to exclude from selection
        role_value (str): Value to match in the 'role' column
        cursor: Database object

    Returns:
        dict or None: {'id': roleid} if match found, otherwise None
    """
    sex_value = sex[0] if isinstance(sex, list) else sex
    ethnicity_value = ethnicity[0] if isinstance(ethnicity, list) else ethnicity
    role = role_value  
    # Ensure excluded_IDs are integers.
    excluded_IDs = [int(i) for i in excluded_IDs]

    # Build query parts.
    if excluded_IDs:
        placeholders = ','.join(['%s'] * len(excluded_IDs))
        exclusion_clause = f"AND roleid NOT IN ({placeholders})"
        params = tuple([sex_value, ethnicity_value, role] + excluded_IDs)
    else:
        exclusion_clause = ''
        params = (sex_value, ethnicity_value, role)

    query = f"""
        SELECT roleid
        FROM headshots
        WHERE sex = %s AND ethnicity = %s AND role = %s
        {exclusion_clause}
        ORDER BY RAND()
        LIMIT 1
    """
    cursor.execute(query, params)
    result = cursor.fetchone()
    if result:
        return {'id': result[0]}
    else:
        print(f"[{now()}][!] ERROR: No headshot ID found?")
        return None

# Returns a random person from the 'names' table.
def get_random_person(exclude_ids, cursor):
    """
    Returns a random person from the 'names' table,
    excluding IDs in exclude_ids.
    
    Args:
        exclude_ids (list): List of IDs to exclude
        cursor: Database object
        
    Returns:
        dict: {'id': ..., 'firstname': ..., 'lastname': ..., 'sex': ..., 'ethnicity': ...}
              or None if no match found.
    """
    placeholders = ','.join(['%s'] * len(exclude_ids))
    query = f"""
        SELECT id FROM names
        WHERE id NOT IN ({placeholders})
        ORDER BY RAND()
        LIMIT 1
    """
    cursor.execute(query, tuple(exclude_ids))
    result = cursor.fetchone()

    if result:
        selected_id = result[0]
        cursor.execute("""
            SELECT firstname, lastname, sex, ethnicity
            FROM names
            WHERE id = %s
        """, (selected_id,))
        row = cursor.fetchone()

        if row:
            firstname, lastname, sex, ethnicity = row
            return {
                'id': selected_id,
                'firstname': firstname,
                'lastname': lastname,
                'sex': sex,
                'ethnicity': ethnicity
            }
    print(f"[{now()}][!] ERROR: No person found.")
    return None

# Returns a random person_bio from the 'bio' table.
def get_random_bio(role, excluded_IDs, cursor):
    """
    Returns a random person_bio from the 'bio' table where:
    - 'role' matches the given role
    - 'id' is NOT in the excluded_IDs list

    Args:
        role (str): The role to filter by
        excluded_IDs (list): List of IDs to exclude
        cursor: Database object

    Returns:
        dict: {'id': ..., 'person_bio': ...}
              or None if no match found
    """
    # Handle 'excluded_IDs' being empty.
    if excluded_IDs:
        placeholders = ','.join(['%s'] * len(excluded_IDs))
        query = f"""
            SELECT id FROM bio
            WHERE role = %s AND id NOT IN ({placeholders})
            ORDER BY RAND()
            LIMIT 1
        """
        params = (role, *excluded_IDs)
    else:
        query = """
            SELECT id FROM bio
            WHERE role = %s
            ORDER BY RAND()
            LIMIT 1
        """
        params = (role,)

    # Fetch a random allowed ID.
    cursor.execute(query, params)
    result = cursor.fetchone()

    if result:
        selected_id = result[0]
        cursor.execute("""
            SELECT bio FROM bio
            WHERE id = %s
        """, (selected_id,))
        row = cursor.fetchone()

        if row:
            return {
                'id': selected_id,
                'bio': row[0]
            }
    print(f"[{now()}][!] ERROR: No biography found.")
    return None

# Adds an exec's headshot to web app.
def headshotCopy(id, role, imagename):
    try:
        filename = imagename + " ("+ str(id) + ").jpg"
        new_filename = role + ".jpg"
        file_origin = HEADSHOTS_FOLDER / filename
        file_destination = FACTORY_FLOOR / new_filename
        shutil.copy(file_origin, file_destination)
    except Exception as e:
        print(f"[{now()}][!] ERROR:", e)
        return None
    return filename

# Prepares a PHP web application template for use in a challenge.
def build_web_app_template(platform_template_pool, template_id, platform, json_php_file):
    template_location = platform_template_pool / template_id
    print(f"[{now()}][*] Copying base {platform} template {template_id} to {FACTORY_FLOOR}")
    shutil.copytree(template_location, FACTORY_FLOOR, dirs_exist_ok=True)
    populate_template("work")
    populate_template("hub")
    populate_template("research")
    # print(f"[{now()}][*] Copying {json_php_file} to {FACTORY_FLOOR}")
    shutil.copy(json_php_file, Path(FACTORY_FLOOR) / "json.php")

# Creates a page and an auth_version of the page based on the placeholder template.
def populate_template(filename):
    src = Path(FACTORY_FLOOR) / "template.php"
    dst = Path(FACTORY_FLOOR) / f"{filename}.php"
    dst2 = Path(FACTORY_FLOOR) / f"auth_{filename}.php"

    # Ensure template exists
    if not os.path.exists(src):
        raise FileNotFoundError(f"{src} not found")

    shutil.copy(src, dst)
    shutil.copy(src, dst2)
    # print(f"[{now()}][*] Created copy: {dst} and {dst2}")

# Inserts flag value into a file, overwriting a placeholder value within the file.
def insert_flag(flag_file, flag_value):
    print(f"[{now()}][*] Attempting to insert flag, if applicable.")
    try:
        with open(flag_file, "r", encoding="utf-8-sig", newline="") as f:
            text = f.read()
        new_text = text.replace("!!!PLACEHOLDER!!!", flag_value, 1)
        if new_text == text:
            raise print(f"[{now()}][!] WARNING: FLAG NOT INSERTED! No placeholder value found.")
        else:
            print(f"[{now()}][*] Flag inserted.")
        with open(flag_file, "w", encoding="utf-8-sig", newline="") as f:
            f.write(new_text)
        return
    except FileNotFoundError:
        print(f"[{now()}][!] File not found, skipping.")
        return
    except Exception as e:
        raise print(f"[{now()}][*] ERROR: {e}")

# =============================
# Secret/bonus web app challenge functions
# =============================
# Prepares a standalone secret challenge for deployment.
def stand_alone_secret(challenge_id):
    print(f"[{now()}][*] Copying standalone secret to {FACTORY_FLOOR}")
    platform = "secret"
    template_id = str(challenge_id)
    template_location = Path(MODULE_TEMPLATES) / f"{platform}_templates" / template_id
    print(f"[{now()}][*] Copying base {platform} template {template_id} to {FACTORY_FLOOR}")
    shutil.copytree(template_location, FACTORY_FLOOR, dirs_exist_ok=True)

# Prepares a dependant secret challenge within a web app challenge.
def hijack_secret(challenge_id, filename, flag_value):
    """
    When a secret challenge needs to sit within a web applciation,
    this function makes use of a web template.
    """
    print(f"[{now()}][*] Copying hijack secret to {FACTORY_FLOOR}")
    platform = "secret"
    template_id = str(challenge_id)
    template_location = Path(MODULE_TEMPLATES) / f"{platform}_templates" / template_id
    print(f"[{now()}][*] Copying base {platform} template {template_id} to {FACTORY_FLOOR}")
    shutil.copytree(template_location, FACTORY_FLOOR, dirs_exist_ok=True)
    # Hijacking existing entry points.
    src = Path(FACTORY_FLOOR) / filename
    dst = Path(FACTORY_FLOOR) / "work.php"
    dst2 = Path(FACTORY_FLOOR) / "research.php"
    dst3 = Path(FACTORY_FLOOR) / "hub.php"
    # Ensure template exists
    if not os.path.exists(src):
        raise FileNotFoundError(f"[*] ERROR: '{src}' not found")
    # Make the copies
    shutil.copy(src, dst)
    shutil.copy(src, dst2)
    shutil.copy(src, dst3)
    print(f"[{now()}][*] Hijack complete: {dst}, {dst2}, and {dst3}")
    # Insert flag into placeholder locations, if applicable.
    if challenge_id == 957:
        flag_file = Path(FACTORY_FLOOR) / "endgame.php" # Used in 'Hacker Simulator'
    else:
        flag_file = Path(FACTORY_FLOOR) / "checkscore.php" # Default: Used in 'Highway Crossing Birb' + 'Snek'
    insert_flag(flag_file, flag_value)

# Creates a Lusty Algorithmic Maid secret challenge.
def lusty_algorithmic_maid(challenge_id, corrupt_target, flag_value):
    print(f"[{now()}][*] Copying Lusty Algorithmic Maid secret to {FACTORY_FLOOR}")
    platform = "secret"
    template_id = str(challenge_id)
    template_location = Path(MODULE_TEMPLATES) / f"{platform}_templates" / template_id
    print(f"[{now()}][*] Copying base {platform} template {template_id} to {FACTORY_FLOOR}")
    shutil.copytree(template_location, FACTORY_FLOOR, dirs_exist_ok=True)
    
    print(f"[{now()}][*] Replacing exec image with secret link on about.php page...")
    file_location = Path(FACTORY_FLOOR) / "about.php"
    target_html = f'<img src="./{corrupt_target}.jpg"'
    characters = string.ascii_letters + string.digits  # A-Z, a-z, 0-9
    new_filename = ''.join(random.choices(characters, k=20))
    link_to_secret = f'<a href="./{new_filename}.html"><img src="./{corrupt_target}.jpg" style="max-width:500px;"></a>\n'
    try:
        with open(file_location, "r", encoding="utf-8") as f:
            lines = f.readlines()
        with open(file_location, "w", encoding="utf-8") as f:
            for line in lines:
                # If the line starts with our target.
                if line.strip().startswith(target_html):
                    f.write(link_to_secret)
                else:
                    f.write(line)
    except FileNotFoundError:
        raise print(f"[{now()}][*] File '{file_location}' not found.")
    except Exception as e:
        raise print(f"[{now()}][*] ERROR: {e}")

    print(f"[{now()}][*] Adding flag to LAM page...")
    file_location = Path(FACTORY_FLOOR) / "lam.html"
    try:    
        with open(file_location, "r", encoding="utf-8-sig", newline="") as f:
            text = f.read()
        new_text = text.replace("!!!PLACEHOLDER!!!", flag_value, 1)
        if new_text == text:
            raise print(f"[{now()}][*] No changes made to LAM file. No placeholder value found?")
        else:
            with open(file_location, "w", encoding="utf-8-sig", newline="") as f:
                f.write(new_text)               
    except FileNotFoundError:
        raise print(f"[{now()}][*] File '{file_location}' not found.")
    except Exception as e:
        raise print(f"[{now()}][*] ERROR: {e}")
    
    print(f"[{now()}][*] Renaming LAM page...")
    try:
        Path(file_location).rename(Path(FACTORY_FLOOR) / f"{new_filename}.html")
    except Exception as e:
        raise print(f"[{now()}][*] Problem renaming LAM file: {e}")  

# =============================
# Dynamic generation + provisioning functions
# =============================
# Runs the Docker container for the newly built challenge.
def run_container(
    image_name: str,
    container_name: str,
    host_port: int,
    container_port: int
):
    client = docker.from_env()
    try:
        client.ping() # Is docker alive?
    except DockerException as e:
        raise SystemExit(f"[{now()}][!] ERROR: Docker not reachable: {e}")
    try:
        client.images.get(image_name)
    except:
        raise SystemExit(f"[{now()}][!] ERROR: Image not found: {image_name} (did you build/tag it?)")
    try:
        container = client.containers.run(
            image_name,
            name=container_name,
            detach=True,
            ports={f"{container_port}/tcp": host_port},
            # environment={}, volumes={}, networks=[], 
        )
    except APIError as e:
        if "port is already allocated" in str(e).lower():
            raise SystemExit(f"[x] ERROR: Host port {host_port} is in use.")
        raise
    # Show quick status
    container.reload()
    net_ips = []
    for net in (container.attrs.get("NetworkSettings") or {}).get("Networks", {}).values():
        ip = net.get("IPAddress")
        if ip:
            net_ips.append(ip)
    #print(f"[{now()}][*] Started: {container.name} ({container.id[:12]}) status={container.status} ip(s)={', '.join(net_ips) or 'n/a'}")
    return container

# Builds a web application challenge.
def web_application(domain, system_name, folder, system_id, corporation, challenge_id, flag_value, cursor, challenge_type):
    """
    Creates a new dynamically generated PHP web application challenge.

    Args:
        domain (str): Challenge flavour domain.
        system_name (str): Challenge flavour system name.
        folder (str): Folder name for flavour images.
        system_id (str): System ID in main database. NOT CURRENTLY USED.
        corporation (str): Challenge flavour corporation name.
        challenge_id (int): Challenge ID in the main database.
        flag_value (str): Flag/code value for the challenge.
        cursor: Database object.
        challenge_type (str): "secret" or "web". Determines crafting pathway.

    Returns:
        dockerfile_name (str): The dockerfile that is used to create the container.
    """

    global flavour_JSON_data, exec_details, employee_table_exists
    employee_table_exists = False # Reset to False for each new challenge.
    exec_details = []
    flavour_JSON_data = []
    slogan = "" # Flavour pulled from main database.
    description = "" # Flavour pulled from main database.
    excluded_IDs = ["0"]
    how = "" # Flavour pulled from main database.
    why = "" # Flavour pulled from main database.
    what = "" # Flavour pulled from main database.
    about = "" # Flavour pulled from main database.
    bolt_on = False # Use to indicate whether a normal challenge is needed for a secret. Might be legacy variable.
    corrupt_target = ""
    
    if domain == "secret" and challenge_type == "secret":
        folder = "fusion_core" # Hard coding 'fusion' for secrets.
    # Secret challenge checks.
    if challenge_type == "secret" and (int(challenge_id) >= 901):
        print(f"[{now()}][*] Building stand alone secret challenge...")
    # build secret that bolts on to another challenge.
    elif challenge_type == "secret" and (int(challenge_id) < 900): # Hard coding secret 0 and 1 for stand alone atm.
        print(f"[{now()}][*] Building bolt on secret challenge...") # build secret that bolts on to another challenge.
        bolt_on = True # This secret needs a regular challenge web application host.
        # TODO: Determine whether 'bolt_on' is a legacy variable that can be removed or not.
    else:
        print(f"[{now()}][*] Building web challenge...")
        # print(f"[{now()}][*] System type:", system_name)
        # print(f"[{now()}][*] challenge_type:", challenge_type)
        # print(f"[{now()}][*] bolt_on:",bolt_on)
    if system_name == "secret" and challenge_type == "secret" and bolt_on == False: # hard coding for certain secrets
        slogan = "Reconstℓruct seq… err>>> fraɡment[█]"
        description = """
        Currεnt status: UNKNOWN; track.er signal discont¡nued 14.11.███ at 03:22:██ GMT. 
        >>> End of corrupted strεam >>> [Checksum err0r_#CE0DE1] [SYS ALERT]: memory sector ███ unrecoverable. END LOG ██████ ███
        """
        what = """
        [SYS//CORP_OVERVIEW::DAMAGED NODE_42] — Initiating partial retr!eval... ████ complete… err:fragment_l0ss_32%.
        Our oper@tions cεnter on deliver¡ng innova†ive, scal@ble solut¡ons across multi-sεctor systεms — 
        bridging technol0gy, stratεgy, and [REDACTED] intεlligence. We des¡gn, deploy, and susta¡n adv@nced 
        infrastructures to opt!mise gl0bal connectivity, secur¡ty, and perƒormance throughput >██.██%. 
        """
        how = """
        System log notes: "Our mission is [████████████████████] to empowεr [██████] through innovΔtion, 
        transparεncy, and secµrity." C0re funct!ons remain classified under prot0col //████████████// until compliance update ████/██/██.
        """
        why = """
        Thr0ugh aut0m@ted data s¥nthesis, algorithμic governance, and adaptive risk prot0cols, we enablε 
        organiζations to [DATA MISSING_0x33A2] accelerate tr@nsformΔtion and resil¡ence in vol@tile markets. 
        Ongoing initi@tives include ██████-scale dig!tal integr@tion, encryp†ion standardisation, and neural 
        m@pping for resource alloca⧫tion efficienc¥.
        """
        about = """
        Data st@tus: [INCOMPLETE—SIG_N0ISE++]. >>> END OF BRIEF ██████ checksum error 0xA7F9E <<<< reboot recommended ████
        """
        # Keeping this for if it is ever put in the database, which could be useful:
        # print(f"[{now()}][*] System is a secret...")
        # cursor.execute("""
        #     SELECT `slogan`, `description`, `what`, `how`, `why`, `about` 
        #     FROM `systemflavours` 
        #     WHERE `system` = 'Fusion Reactor Core'
        #     ORDER BY RAND() LIMIT 1
        # """)
        # row = cursor.fetchone()
    else:
        print(f"[{now()}][*] System is a {system_name}...")
        try:
            cursor.execute(
                """
                SELECT `slogan`, `description`, `what`, `how`, `why`, `about`
                FROM `systemflavours`
                WHERE `system` = %s
                ORDER BY RAND() LIMIT 1
                """,
                (system_name,),
            )
            row = cursor.fetchone()
            if row:
                slogan, description, what, how, why, about = row
            else:
                print(f"[{now()}][!] ERROR: No data found for the selected ID.")
                return
        except Exception as e:
            print(f"[{now()}][!] ERROR: SQL error: {type(e).__name__}: {e}")
    
    # Select employees.
    try:
        ceo = get_random_person(excluded_IDs, cursor)
        # print("CEO:")
        # print(ceo)
        excluded_IDs = [ceo["id"]]
        coo = get_random_person(excluded_IDs, cursor)
        # print("COO:")
        # print(coo)
        excluded_IDs = [ceo["id"],coo["id"]]
        cto = get_random_person(excluded_IDs, cursor)
        # print("CTO:")
        # print(cto)
        excluded_IDs = [ceo["id"],coo["id"],cto["id"]]
        cso = get_random_person(excluded_IDs, cursor)
        # print("CSO:")
        # print(cso)
        excluded_IDs = [ceo["id"],coo["id"],cto["id"],cso["id"]]
        ciso = get_random_person(excluded_IDs, cursor)
        # print("CISO:")
        # print(ciso)
        excluded_IDs = ["0"]
    except Exception as e:
        print(f"[{now()}][!] ERROR: Problem selecting staff IDs.")
        return

    # Select and copy headshots.
    try:
        #ceoHeadshot = ""
        #cooHeadshot = ""
        #cisoHeadshot = ""
        #ctoHeadshot = ""
        #csoHeadshot = ""
        headshot = get_random_headshot([ceo["sex"]], [ceo["ethnicity"]], "ceo", excluded_IDs, cursor)
        ceoHeadshot = headshot["id"]
        excluded_IDs = [ceoHeadshot]
        headshot = get_random_headshot([coo["sex"]], [coo["ethnicity"]], "ceo", excluded_IDs, cursor)
        cooHeadshot = headshot["id"]
        excluded_IDs = [ceoHeadshot, cooHeadshot]
        headshot = get_random_headshot([ciso["sex"]], [ciso["ethnicity"]], "ceo", excluded_IDs, cursor)
        cisoHeadshot = headshot["id"]
        excluded_IDs = ["0"]
        headshot = get_random_headshot([cto["sex"]], [cto["ethnicity"]], "scientist", excluded_IDs, cursor)
        ctoHeadshot = headshot["id"]
        headshot = get_random_headshot([cso["sex"]], [cso["ethnicity"]], "security", excluded_IDs, cursor)
        csoHeadshot = headshot["id"]
        # Copy headshot images to destination
        print(f"[{now()}][*] Copying headshot images...")
        ceo_file = headshotCopy(ceoHeadshot, "ceo", "ceo")
        coo_file = headshotCopy(cooHeadshot, "coo", "ceo")
        ciso_file = headshotCopy(cisoHeadshot, "ciso", "ceo")
        cto_file = headshotCopy(ctoHeadshot, "cto", "scientist")
        cso_file = headshotCopy(csoHeadshot, "cso", "security")
    except Exception as e:
        print(f"[{now()}][!] ERROR: Problem selecting or copying headshots.")
        return
    
    # Select staff bios.
    try: 
        print(f"[{now()}][*] Getting exec bios...")
        bio = get_random_bio("ceo", excluded_IDs, cursor)
        ceobio = str(bio["bio"])
        #print(f"[{now()}][*] Bio obtained for",ceobio)
        ceobioid = bio["id"]
        excluded_IDs = [ceobioid]
        bio = get_random_bio("ceo", excluded_IDs, cursor)
        coobio = str(bio["bio"])
        coobioid = bio["id"]
        #print(f"[{now()}][*] Bio obtained for",coobioid)
        excluded_IDs = [ceobioid, coobioid]
        bio = get_random_bio("ceo", excluded_IDs, cursor)
        cisobio = str(bio["bio"])
        excluded_IDs = ["0"]
        #print(f"[{now()}][*] Bio obtained for",cisobio)
        bio = get_random_bio("scientist", excluded_IDs, cursor)
        ctobio = str(bio["bio"])
        #print(f"[{now()}][*] Bio obtained for scientist")
        bio = get_random_bio("security", excluded_IDs, cursor)
        csobio = str(bio["bio"])
        #print(f"[{now()}][*] Bio obtained for security")
    except Exception as e:
        print(f"[{now()}][!] ERROR: Problem selecting staff biographies.")
        return
    
    # Corporation logo copy.
    try:
        print(f"[{now()}][*] Getting logo for:", corporation)
        corp_filename = corporation + ".jpg"
        file_origin = FLAVOUR_FOLDER / "corporations" / corp_filename
        file_destination = FACTORY_FLOOR / "logo.jpg"
        shutil.copy(file_origin, file_destination)
    except Exception as e:
        print(f"[{now()}][!] ERROR: Problem copying corporate logo.")
        return
    
    # Flavour image selection - Default is 8 system images.
    try:
        directory_path = FLAVOUR_FOLDER / folder
        # List all files in the directory.
        all_files = [f for f in os.listdir(directory_path) if os.path.isfile(os.path.join(directory_path, f))]

        # Check if there are enough image files.
        if len(all_files) < FLAVOUR_IMAGE_COUNT:
            print(f"[{now()}][*] ERROR: Not enough files in the directory to select",str(FLAVOUR_IMAGE_COUNT))
            raise 

        # Randomly select images.
        selected_files = random.sample(all_files, FLAVOUR_IMAGE_COUNT)
        
        # Copy and rename image files.
        for index, filename in enumerate(selected_files, start=1):
            src_path = os.path.join(directory_path, filename)
            
            # Preserve file extension.
            new_filename = f"image_{index}.jpg"
            dest_path = os.path.join(FACTORY_FLOOR, new_filename)
            
            # Copy the file
            shutil.copy2(src_path, dest_path)
            #print(f"Copied: {src_path}")
    except Exception as e:
        print(f"[{now()}][!] ERROR: Problem copying system images for flavour:", e)
        return
    
    # If secret with corruption, corrupt an exec's details + image.
    if challenge_type == "secret" and (int(challenge_id) > 900):
        try:
            random_number = random.randint(1, 5)
            headshot_id = random.randint(1, 2)
            corrupt_bio = """
            "An ex3cut!ve [ID: ███-█47C] 1n to corpοrate str@tegy & multi-na†ional governance.
            ████+ years in hiⁿgh-value operations (approx. $███M annual thrσughput). 
            Competencies in orgΔnisational tr⧫nsf0rm, [DATA_FRAGMENT_LOST], techn0logical intεgration 
            with AI/ML infra-█████████. Document indic@tes lεadership of crσss-funct!onal teams ███ 
            yielding ±1█.█ff¡ciency uplift before sys.err→0xA9FA. ███████ initiative, ████ risk-mitig@tion, 
            and [SECURITY OVERRIDE FAILURE]. UNK; edu¢ation University of ███████ (doc. incomplete).
            V¡sionary stratεgist; prof¡cient in ΔΔ govεrnance prot0cols; emphasis on eth¡cal oversight ████; 
            advocate for sustain⧫bility progr∆ms across sεctors of technol0gy, finance, and .
            Checksum mismatch 0x6F7D; Integrity: 23.8%. [██ 404.12.∑]
            """
            if random_number == 1:
                corrupt_target = "ceo"
                ceo["firstname"] = "ERROR: DATA"
                ceo["lastname"] = "CORRUPT"
                ceobio = corrupt_bio
            if random_number == 2:
                corrupt_target = "coo"
                coo["firstname"] = "ERROR: DATA"
                coo["lastname"] = "CORRUPT"
                coobio = corrupt_bio
            if random_number == 3:
                corrupt_target = "ciso"
                ciso["firstname"] = "ERROR: DATA"
                ciso["lastname"] = "CORRUPT"
                cisobio = corrupt_bio
            if random_number == 4:
                corrupt_target = "cto"
                cto["firstname"] = "ERROR: DATA"
                cto["lastname"] = "CORRUPT"
                ctobio = corrupt_bio
            if random_number == 5:
                corrupt_target = "cso"  
                cso["firstname"] = "ERROR: DATA"
                cso["lastname"] = "CORRUPT"
                csobio = corrupt_bio
            headshotCopy(headshot_id, corrupt_target, "corrupt")
        except Exception as e:
            print(f"[{now()}][*] ERROR: Problem copying corrupt exec image and modifying text for secret:", e)
            return

    # Store exec details for other uses in a list of lists
    exec_details = [(ceo["firstname"], ceo["lastname"], "Chief Executive Officer"), (coo["firstname"], coo["lastname"], "Chief Operations Officer"),
                    (ciso["firstname"], ciso["lastname"], "Chief Information Security Officer"), (cto["firstname"], cto["lastname"], "Chief Technology Officer"),
                    (cso["firstname"], cso["lastname"], "Chief Security Officer")]
    
    try: # Write JSON file
        flavour_JSON_data = {
            "name": corporation,
            "domain": domain,
            "system": system_name,
            "slogan": slogan,
            "description": description,
            "what": what,
            "how": how,
            "why": why,
            "about": about,
            "ceobio": ceobio,
            "ceoname": ceo["firstname"]+" "+ceo["lastname"],
            "coobio": coobio,
            "cooname": coo["firstname"]+" "+coo["lastname"],
            "cisobio": cisobio,
            "cisoname": ciso["firstname"]+" "+ciso["lastname"],
            "ctobio": ctobio,
            "ctoname": cto["firstname"]+" "+cto["lastname"],
            "csobio": csobio,
            "csoname": cso["firstname"]+" "+cso["lastname"],
            "imgCount": FLAVOUR_IMAGE_COUNT
        }
        # This JSON file name is currently hardcoded in the templates. No secrets are placed here. All flavour.
        json_ouput_path = os.path.join(FACTORY_FLOOR, flavour_JSON)

        # Write to a JSON file.
        with open(json_ouput_path, "w", encoding="utf-8") as f:
            json.dump(flavour_JSON_data, f, indent=4, ensure_ascii=False)
        print(f"[{now()}][*] Data written to",flavour_JSON)
    except Exception as e:
        print(f"[{now()}][!] ERROR: Problem writing JSON file.")
        return
    
    # Pick the underyling template.
    try:
        platform = "php" # Name the platform. For now, supporting PHP/HTML.
        platform_templates = platform+"_templates"
        platform_modules = platform+"_modules"
        json_php_file = Path(MODULE_TEMPLATES) / platform_templates / "json.php" # Default JSON config for all PHP templates.

        platform_module_pool = MODULE_TEMPLATES / platform_modules # This is where the modules for the platform will be.
        platform_template_pool = MODULE_TEMPLATES / platform_templates # This is where we will be randomly selecting a base template from.
        template_id = pick_random_folder(platform_template_pool) # Pick template at random.
        # template_id = "04" # Hard code for testing.

        if system_name != "secret" or bolt_on == True: # Normal challenge, or has secret bolt on?
            build_web_app_template(platform_template_pool, template_id, platform, json_php_file)    

        if system_name == "secret": # Secret with PHP frontend; but assumes no database.
            if (int(challenge_id) > 950) and (int(challenge_id) < 955): # Lusty Algorithmic Maid secret.
                print(f"[{now()}][*] Building Lusty Algorithmic Maid secret challenge:",challenge_id)
                template_id = "01" # Hard coded until fix is worked out for other templates...
                build_web_app_template(platform_template_pool, template_id, platform, json_php_file)
                lusty_algorithmic_maid(challenge_id, corrupt_target, flag_value)
            elif (int(challenge_id) > 900) and (int(challenge_id) < 950): # Standalone secret.
                print(f"[{now()}][*] Building stand alone secret challenge:",challenge_id)
                stand_alone_secret(challenge_id)
            elif (int(challenge_id) >= 955): # Hijack 'work', 'research', and 'hub' entry points.
                print(f"[{now()}][*] Building hijack secret challenge:",challenge_id)
                build_web_app_template(platform_template_pool, template_id, platform, json_php_file)
                hijack_secret(challenge_id, "corruption.html", flag_value)
            else:
                raise print(f"[{now()}][*] ERROR: Unknown secret challenge_id:",challenge_id)
            
            print(f"[{now()}][*] Secret prep done...")
            dockerfile_name = "apache-php-alpine"  # Dockerfile must be placed *inside* context
            return dockerfile_name # For secrets, we do not need the rest of this function.
    except Exception as e:
        print(f"[{now()}][!] ERROR:",e)
        raise 
    
    # Building challenge database creds.
    characters = string.ascii_letters + string.digits  # A-Z, a-z, 0-9
    challenge_db_password = ''.join(random.choices(characters, k=20))
    challenge_db_username = f"readonly{challenge_id}"
    print(f"[{now()}][*] Creating database...")
    create_challenge_database(challenge_id, challenge_db_username, challenge_db_password)
    #print(f"[{now()}][*] Adding test user...")
    #add_user_to_challenge_database(challenge_id, "admin", "password", 1, 1, 1) # For testing only...
    
    # Reproducible builds using a seed; can remove seed to make fully random.
    rnd = random.Random()
    seed = rnd.randint(1, 100)
    # seed = 35 # Uncomment for testing only.
    print(f"[{now()}][*] Seed:",seed)
    gate_chain = generate_chain(seed)
    print(f"[{now()}][*] Writing PHP config file...")
    if platform_templates == "php_templates":     
        write_php_config(challenge_id, challenge_db_username, challenge_db_password, platform_templates, gate_chain)
    else:
        print(f"[{now()}][!] ERROR: Only PHP templates have been implemented for web applications. Returning...")
        return

    # Builds backwards from 'flag'.
    for gate_counter in range(3, 0, -1):
        print("======================================================")
        print(f"===================== GATE: {gate_counter} ========================")
        print("======================================================")
        auth_required = "true"
        index = gate_counter-1
        entry_point = gate_chain[index]["entry_point"]
        print("Entry Point:",entry_point)
        gate_type = gate_chain[index]["gate_type"]
        print("Gate Type:",gate_type)
        gate_key = gate_chain[index]["current_gate_key"]
        print("Current Gate's Key:",gate_key)
        target_gate_key = gate_chain[index]["target_gate_key"]
        print("Target Gate's Key:",target_gate_key)
        if index+1 < 3:
            try:
                target_gate_entry_point = gate_chain[index+1]["entry_point"]
            except Exception as e:
                target_gate_entry_point = "none"
                print(f"[{now()}][!] WARNING: Did we reach the end of the gates?",e)

        # Where a gate has a lock, it will need a key by default. 
        if gate_key in ("none", "n/a"):
            auth_required = "false"
        else:
            print(f"[{now()}][*] Authentication is required for gate...")
            auth_required = "true" 
        
        # Currently not supporting no key for a gate, as it will apply 'none' to all the gates.
        if gate_key in ("none", "n/a"): 
            gate_key = "git" # Temp hard coding git key for 'none' entries.
        
        print(f"[{now()}][*] Building gate...")
        if platform_templates == "php_templates":
            if gate_counter == 1:
                print(f"[{now()}][*] First gate must build its own key, if applicable...")
                if gate_key in ("sqli", "none"):
                    print(f"[{now()}][*] No first key needed, modifying permissions for SQLi...")
                    set_mass_user_permissions(challenge_id, permission=entry_point, value=1) # If expected to SQLi, current users must be able to auth.
                else:
                    print(f"[{now()}][*] First key being built...")
                    build_first_gate_key_module(platform_module_pool, challenge_id, gate_type, gate_key, entry_point) 
            print(f"[{now()}][*] Building gate middleware...")
            build_middleware(entry_point, gate_counter) # Build the current gate's middleware.
            print(f"[{now()}][*] Building lock for target gate...") 
            add_auth_module_and_gateheader(entry_point, auth_required, platform_module_pool, gate_counter) # Attach auth and gateheader, even if auth is not required.
            print(f"[{now()}][*] Building the gate's type...") 
            build_gateway_target(challenge_id, entry_point, gate_type, platform_modules) # Once the gate is opened, what is on the other side? 
            print(f"[{now()}][*] Building the gate type complete for gate:",index+1)
            if index+1 < 3:
                print(f"[{now()}][*] Building the next gate's key...")
                build_target_gate_key(platform_module_pool, challenge_id, gate_type, target_gate_key, target_gate_entry_point, flag_value)
            else:
                print(f"[{now()}][*] Building the flag...")
                build_target_gate_key(platform_module_pool, challenge_id, gate_type, target_gate_key, "N/A", flag_value)
                if target_gate_key == "flag":
                    print(f"[{now()}][*] Path to flag complete.") 
        else:
            raise print(f"[{now()}][!] ERROR: Only PHP templates have been implemented for web applications. Exiting...")
    print(f"[{now()}][*] Gate chain created:")
    print(json.dumps(gate_chain, indent=2))
    dockerfile_name = "apache-php-alpine"  # Must be *inside* context.
    return dockerfile_name

# Creates a POC timed SSH challenge.
def timed_challenge(domain, system_name, folder, system_id, corporation, challenge_id, flag_value, cursor):
    # Select filesystem module, pick flavour file.
    module_type = "filesystem_modules"
    parent = Path(MODULE_TEMPLATES) / module_type
    module_selection = pick_random_folder(parent)
    
    module_location = Path(MODULE_TEMPLATES) / module_type / module_selection
    print(f"[{now()}][*] Module location:",module_location)
    print(f"[{now()}][*] Copying module to factory floor.")
    # Copy the module into the factory floor
    shutil.copytree(module_location, FACTORY_FLOOR, dirs_exist_ok=True)

    # Modify the auth file to include the flag.
    # Find the placeholder "!!!PLACEHOLDER!!!" and replace it with the flag
    factory_module = Path(FACTORY_FLOOR) / "code.txt"
    replacement = flag_value
    print(f"[{now()}][*] Replacing placeholder values with flag, if applicable.")
    with open(factory_module, "r", encoding="utf-8-sig", newline="") as f:
        text = f.read()
    new_text = text.replace("!!!PLACEHOLDER!!!", replacement, 1)
    if new_text == text:
        print(f"[{now()}][*] No changes made to module file. No placeholder value found.")
    else:
        print(f"[{now()}][*] Module code updated to include flag.")
    with open(factory_module, "w", encoding="utf-8-sig", newline="") as f:
        f.write(new_text)
    print(f"[{now()}][*] Updated module saved.")

    dockerfile_name = "ssh-alpine"  # must be *inside* context
    return dockerfile_name

# Creates a new dynamically generated challenge.
def createChallenge(domain, system_name, folder, system_id, corporation, challenge_id, flag_value, cursor, challenge_type):
    """
    Creates a new dynamically generated challenge.
    All "challenge_type = secret" challenges are considered 'web' challenges for building purposes.
    While a POC SSH timed challenge exists in the code, it is turned off in this function.
    To enable the POC SSH challenge, find the applicable line of code that disables it and comment it out.

    Args:
        domain (str): Challenge flavour domain.
        system_name (str): Challenge flavour system name.
        folder (str): Folder name for flavour images.
        system_id (str): System ID in main database.
        corporation (str): Challenge flavour corporation name.
        challenge_id (int): Challenge ID in the main database.
        flag_value (str): Flag/code value for the challenge.
        cursor: Database object.
        challenge_type (str): "none", "web", "ssh", "secret" expected. Determines crafting pathway.

    Returns:
        container.id[:12]: The ID of the container.
        challenge_username (str): The username of the challenge, if applicable.
        challenge_password (str): the password of the challenge, if applicable.
    """
    global corp_name
    corp_name = corporation # Sets global 'corp_name' variable for this challenge generation .
    user_creds = False # Default False. SSH challenges require credentials be provided to players.
    challenge_username = "" # Only used in SSH challenge POC.
    challenge_password = "" # Only used in SSH challenge POC.

    # Clean up factory floor, remove previous challenge artefacts.
    try:
        for filename in os.listdir(FACTORY_FLOOR):
            file_path = os.path.join(FACTORY_FLOOR, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.remove(file_path)          # remove file or symbolic link
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)      # remove folder and its contents
            except Exception as e:
                print(f"Failed to delete {file_path}: {e}")
        print(f"[{now()}][*] Factory floor cleaned.")
    except FileNotFoundError:
        print(f"Folder not found: {FACTORY_FLOOR}")
    except PermissionError:
        print(f"Permission denied for folder: {FACTORY_FLOOR}")
    except Exception as e:
        print(f"Error deleting contents of {FACTORY_FLOOR}: {e}")
    
    if challenge_type == "none":
        random_number = random.randint(1, 2)
        random_number = 1 # Comment out this line to start generating the POC timed SSH challenge again. 
        if random_number == 1:
            challenge_type = "web"
        if random_number == 2:
            challenge_type = "ssh"
            user_creds = True # SSH challenge requires creds.
        # if random_number == 3:
        #     challenge_type = "secret"

    print(f"[{now()}][*] Selected challenge type:",challenge_type)
    if challenge_type == "web" or challenge_type == "secret": # All secret challenges are considered web challenges for building purposes.
        print(f"[{now()}][*] Generating a web application challenge...")
        dockerfile_name = web_application(domain, system_name, folder, system_id, corporation, challenge_id, flag_value, cursor, challenge_type)
        if dockerfile_name == "error" or dockerfile_name == "":
            print(f"[{now()}][*] Error generating a web application challenge.")
            return
    if challenge_type == "ssh":
        print(f"[{now()}][*] Generating a timed SSH challenge...")
        if user_creds == True:
            # If randomaised usernames and passwords implemented, need to modify dockerfiles or env runtime variables.
            # This is fine for POC.
            challenge_username = "backdoor" # If modified, need to update dockerfiles...
            challenge_password = "N4n0L0ck02" # If modified, need to update dockerfiles...
        dockerfile_name = timed_challenge(domain, system_name, folder, system_id, corporation, challenge_id, flag_value, cursor)
        if dockerfile_name == "error" or dockerfile_name == "":
            print(f"[{now()}][*] Error generating a web application challenge.")
            return
    
    # Build image checks and balances.
    dockerfile_rel = FACTORY_FLOOR / dockerfile_name
    # Copy the appropriate dockerfile to the factory floor.
    print(f"[{now()}][*] Coping dockerfile: {DOCKERFILE_FOLDER}/{dockerfile_name}")
    shutil.copy(f"{DOCKERFILE_FOLDER}/{dockerfile_name}", f"{FACTORY_FLOOR}/{dockerfile_name}")
    print(f"[{now()}][*] Building docker image for",challenge_id)

    subprocess.run([
        "docker", "buildx", "build",
        "--builder", "default", "--pull=false",
        "--load",
        "-f", dockerfile_rel,
        "-t", f"challenge{challenge_id}:{challenge_id}",
        FACTORY_FLOOR,
    ], check=True)
    print(f"[{now()}][*] Image built.")
    challenge_port = int(f"{FIRST_PORT_NUMBER}{challenge_id}")
    print(f"[{now()}][*] Challenge port assignment:",challenge_port)
    image_name = f"challenge{challenge_id}:{challenge_id}"
    container_name = f"challenge{challenge_id}"
    try:
        if challenge_type == "web" or domain == "secret": # Web app or secret
            container = run_container(
            image_name=image_name,
            container_name=container_name,
            host_port=challenge_port,
            container_port=80 # Intended for web access
        )
        else:
            container = run_container(
            image_name=image_name,
            container_name=container_name,
            host_port=challenge_port,
            container_port=22 # Intended for SSH access
        )
    except Exception as e:
        print(f"[{now()}][!] ERROR: Problem running container from image:",e)
    print(f"[{now()}][*] Container '{container.name}' is running on http://localhost:{challenge_port}")
        
    return container.id[:12], challenge_username, challenge_password
