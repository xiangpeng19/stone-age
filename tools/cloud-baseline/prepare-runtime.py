#!/usr/bin/env python3
"""Prepare empty fixtures only. This script does not start any service."""
from pathlib import Path
import argparse
import re
import shutil

src = Path.cwd()
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, default=src / "baseline-runtime")
args = parser.parse_args()
run = args.output.resolve()
if run.exists():
    raise SystemExit("Refusing to reuse an existing runtime directory")
for name in (
    "saac/char", "saac/char_sleep", "saac/log", "saac/mail",
    "saac/db/int", "saac/db/string", "saac/data/family",
    "saac/data/fmpointdir", "saac/data/fmsmemodir",
    "gmsv/data", "gmsv/log", "gmsv/Dengon", "gmsv/Schedule",
    "gmsv/data/autopk"
):
    (run / name).mkdir(parents=True, exist_ok=True)

def copy_file(relative):
    original = src / relative
    if original.is_symlink() or not original.is_file():
        raise SystemExit("Missing or symlink source: " + relative)
    destination = run / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(original, destination)

for name in ("saac/saacjt.exe", "gmsv/gmsvjt.exe"):
    copy_file(name)  # Only after the source build has completed successfully.

for folder in ("map", "npc"):
    original = src / "gmsv/data" / folder
    if any(p.is_symlink() for p in original.rglob("*")):
        raise SystemExit("Symlink in static data")
    shutil.copytree(original, run / "gmsv/data" / folder)

required = (
    "itemset.txt inv.txt appear.txt titlename.txt titleconfig.txt "
    "encount.txt enemybase.txt enemy.txt group1.txt magic.txt attmagic.bin "
    "petskill.txt itematom.txt effect.txt question.txt"
).split()
optional_static = (
    "ride.txt leaderride.txt gambleitems.txt skillcode.txt itemquitparty.txt"
).split()
for name in required + optional_static:
    copy_file("gmsv/data/" + name)
for name in ("mapset.txt", "battlemap.txt", "mapwarp.txt"):
    if not (run / "gmsv/data/map" / name).is_file():
        raise SystemExit("Missing required map data: " + name)

# Fresh empty administration/log configuration; no historical accounts.
for name in ("gmsv/data/gmset.txt", "gmsv/log/log.cf"):
    (run / name).write_text("", encoding="utf-8")

config = {}
for line in (src / "gmsv/setup.cf").read_text(encoding="utf-8-sig").splitlines():
    if line.lstrip().startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    key = key.strip()
    if re.fullmatch(r"[A-Za-z0-9_]+", key):
        config[key] = value.strip()
config.update({
    "debuglevel": "0", "acserv": "127.0.0.1", "acservport": "19300",
    "acpasswd": "fixture-only", "port": "19065",
    "gameservname": "baseline", "gameservid": "baseline", "QQ": "0",
    "topdir": ".", "storedir": "../saac/char", "logdir": "./log",
    "logconfname": "log.cf", "gmsetfile": "./data/gmset.txt",
    "chatmagicpasswd": "disabled", "chatmagiccdkeycheck": "1",
    "reuseaddr": "0", "enableservice": "0"
})
for key in ("apid", "apport", "msname", "msport", "npcaddress", "nsport"):
    config.pop(key, None)
(run / "gmsv/setup.cf").write_text(
    "".join(f"{key}={value}\n" for key, value in config.items()),
    encoding="utf-8"
)
(run / "saac/acserv.cf").write_text("""sql_IP 127.0.0.1
sql_Port 13306
sql_ID root
sql_PS
sql_DataBase sa
sql_Table user_table
sql_LOCK user_lock
sql_NAME Name
sql_PASS Pass
AutoReg 0
port 19300
pass fixture-only
logdir log
chardir char
dbdir db
maildir mail
familydir data/family
fmpointdir data/fmpointdir
fmsmemodir data/fmsmemodir
rotate_interval 604800
Total_Charlist 3600
Expired_mail 600
Del_Family_or_Member 3600
Write_Family 600
""", encoding="utf-8")
print("Prepared:", run)
print("No service started. Database and network isolation still required.")

