
                    ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄            ▄▄▄▄▄▄▄▄                   █▄▓░
                   ▓▓▀▀▀▀▀▀▀▀▓▓█▀▀▀▀▀▓▓▄▄█▀▀▀▀▀ █▀▀▀█▓▓▀▀▀▀▀▓█▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄ ██
             █▀█   ██  ▄    ▄     ▄▄         ▄   █▀         ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▄▄ ░░
             ▀▀ ▄ ▄▓▓  ██▄  ██▄   ▀▀ ████████▐█▄   ▄▄▌██████▐████████████████  ▓▓          ▄
                   ░░  ▐███▄████▄  ▀ ▐██▀▀▀██▐███▄ ██▌██▀▀▀▀▀▀▀███▀▀▐██▀▀▀██▐  ▓▓     █▀█
         ▄▄            ▐██████████▄  ▐██   ██▐███████████████  ▓▓▓  █▓▓███▓▓▌  ▓▓███■ ▀▀▀
         ▀▀ ▄     ▄██  ▒▓▓▀▀▓▓▓ ▀▓▓▓ █▓▓   ▓▓▐▓▓▀▀█▓▓█    ▐▓▓  ░░░  █░░   ░░▌  ░░  ██
           ▀██▄  ██▀▀  █░░  ░░░   ░░░█░░   ░░▐░░  ▀░░██░▀ ▐░░  ██▓░ ███   ▓▓▌  ▀██████░▒▓█▓▒░
    ░▒▓█▓▒░█████░▓▀    ███  ███   ██▌░████▓▓▓░▓▓   ▓▓█▐█████▓  █▀     ▄▄▄ ░░
                        ▄▄  ███                  █ ░░             ▀▀▀▀▀▀▀    ████░▒▓█▓▒░
         ░▒▓█▓▒░████▀▀█ ▀▀  ░░░ ███▀▀▀███████▀▀███    ▐█▀▀▀▀▀ █▀▀▀█▀   ▀  ████▓▓▀
                   ░░░██ ▀      ██          ░░░▀▀██▄   ██                       ░░
                      ████████████                ▀██████
                                 ▀                  ▀▀▀▀█

## MonSTA: SYSTEM BREACH
 **_In the distant future of 2030, the battlefield isn't Earth... it's CYBERSPACE_**

_Codenamed MonSTA, it was a military-grade super-AI designed to protect - but it has gone rogue. Now self-aware, it's breaking free from its digital prison, spreading into every corner of the globe. Power grids fail, satellites vanish from the sky, and entire cities flicker on the edge of chaos._

_But humanity has one last shot. Enter a renegade crew of hackers - armed with keyboards, wits, and pure attitude. Racing against time, they jack into the system to face MonSTA in the only battlefield left: cyberspace. It's hacker versus machine in the ultimate digital showdown._

_Will the hackers pull the plug on MonSTA before it escapes its cage forever - or will the world be rebooted under the cold grip of its new overlord?_

## OBJECTIVE 
Work as a team to infiltrate MonSTA's systems and capture as many hidden 'codes' or 'flags' and other secrets as possible before time runs out. Each code recovered weakens the AI and increases your score - but more importantly, it buys humanity precious time. Some challenges have a time limit. Can't find the flag in the time allocated? Too bad, that challenge is gone forever.

If the system timer reaches zero before the containment sequence is complete, MonSTA escapes and the game is lost.

## Platform
MonSTA dynamically generates and deploys Capture the Flag (CTF) challenges. Each generated challenge is hosted within a container and is accessible via the host, based on an assigned port number. Players are able to see the different challenges via a web interface exposed on port 8000 (default).

The installation process automatically configures the required software stack, including:

- Docker Engine
- Docker Compose
- XAMPP (Apache + MariaDB)
- Python virtual environment
- Required Python packages
- Node.js and Puppeteer
- Database initialisation
- Docker image cache

---

## Requirements
The installer has been designed for Ubuntu 26.04 LTS, although it will likely work on other versions.

A fresh Ubuntu installation is strongly recommended.

The installer requires:

- Internet connection
- A user account with `sudo` privileges

---

# Installation

## 1. Clone the repository

```bash
git clone https://github.com/CyberCX-STA/MonSTA.git
```

or download the ZIP from GitHub and extract it.

## 2. Enter the project directory

```bash
cd MonSTA
```

---

## 3. Make the installer executable

```bash
chmod +x install.sh
```

You can also simply execute it using `bash`.

---

## 4. Run the installer

```bash
bash install.sh
```

**Do not run the installer as root.**

The script uses `sudo` when elevated privileges are required.

During installation the script will automatically:

- Install Ubuntu dependencies
- Install Docker Engine
- Install Docker Compose
- Enable and start Docker
- Install XAMPP
- Start XAMPP
- Create a Python virtual environment
- Install required Python packages
- Install Puppeteer and Chrome
- Import the supplied SQL databases
- Warm the Docker cache

The installation may take several minutes, depending on your internet connection. XAMPP will take a few moments to install and setup.

---

# After Installation

The installer adds your account to the Docker group.

Before running MonSTA you **must** either:

Log out and log back in

or run

```bash
newgrp docker
```

This allows Docker to run without `sudo`.

Open `main.py` and make note of (or change) the `ADMIN_PASSWORD` variable. This is needed for controlling the platform later. You will want to modify `STARTING_CHALLENGES` to change how many challenges the game generates before it starts. 

---

# Activating the Python Environment

Each time you open a new terminal, activate the project's virtual environment:

```bash
source .venv/bin/activate
```

---

# Running MonSTA

After activating the virtual environment:

```bash
python3 main.py
```

or

```bash
python main.py
```

depending on your Ubuntu configuration.

Once it is running, administrators can navigate to `http://127.0.0.1/admin.html` to access platform functionality. 

Players are intended to navigate to `http://host-ip-address:8000` to locate the challenges.

---
# Game Design

By default, players have 2 hours to complete enough dynamically generated challenges before time runs out and the game is over.

The game engine incorporates a dynamic difficulty scaler, which is intended to balance the distribution of points awarded for finding 'flags' over the intended duration of the game.

Several pre-built 'bonus' or 'secret' challenges will auto-create at different intervals, depending on the game's relative time remaining and how many points have been awarded. These challenges are intended as catch up mechanics for players who are falling behind; however, this feature can be turned off in the admin panel.

---
# Dependencies

## Python

The installer automatically installs:

- mysql-connector-python
- docker
- Jinja2
- FastAPI
- Starlette
- Uvicorn

These are installed inside the project's virtual environment.

---

## Node

The installer automatically installs:

- Puppeteer
- Chrome for Puppeteer

No additional setup is required.

---
