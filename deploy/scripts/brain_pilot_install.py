"""First installation ONLY. Explicit workflow approval is required to invoke main.

No replacement, deletion or reset. Refuses existing container and shared mounts.
Docker receives only the model key by environment variable NAME, never by argv.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import time

NAME = "superbot-brain-pilot"
DATA = Path("/opt/superbot-desk-data/brain")
BACKUPS = Path("/opt/superbot-brain-backups")


def validate_sha(sha):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ValueError("full_lowercase_sha_required")


def docker_args(sha):
    validate_sha(sha)
    return ["docker", "run", "-d", "--name", NAME,
            "--label", "superbot.component=brain-pilot", "--label", "superbot.sha="+sha,
            "--env", "DESK_MODE=paper", "--env", "DEEPSEEK_API_KEY",
            "--mount", "type=bind,src="+str(DATA)+",dst=/out",
            "--restart", "unless-stopped", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
            "--cpus", "0.5", "--memory", "384m", "--pids-limit", "128",
            "--log-opt", "max-size=5m", "--log-opt", "max-file=3",
            "superbot-brain-pilot:sha-"+sha]


def reject_conflicts(containers, data=DATA):
    target=data.resolve()
    for item in containers:
        if item.get("Name", "").lstrip("/")==NAME:
            raise ValueError("existing_brain_container_no_replacement")
        for mount in item.get("Mounts", []):
            if mount.get("Type")!="bind":
                continue
            source=Path(mount["Source"]).resolve()
            if source==target or source in target.parents or target in source.parents:
                raise ValueError("data_mounted_by_another_container")


def verify_container(item, sha):
    config=item["Config"]; host=item["HostConfig"]
    env=config.get("Env", [])
    if [e for e in env if e.startswith("DESK_MODE=")] != ["DESK_MODE=paper"]:
        raise ValueError("paper_env_mismatch")
    if config.get("Labels",{}).get("superbot.sha")!=sha:
        raise ValueError("image_version_mismatch")
    mounts=item.get("Mounts",[])
    binds=[m for m in mounts if m.get("Type")=="bind"]
    extra=[m for m in mounts if m.get("Type")!="bind" and not (m.get("Type")=="tmpfs" and m.get("Destination")=="/tmp")]
    if extra or len(binds)!=1 or binds[0].get("Source")!=str(DATA) or binds[0].get("Destination")!="/out":
        raise ValueError("mount_isolation_mismatch")
    if (not host.get("ReadonlyRootfs") or host.get("PortBindings")
            or "ALL" not in host.get("CapDrop",[]) or host.get("Privileged")
            or host.get("NetworkMode")=="host"):
        raise ValueError("container_sandbox_mismatch")


def backup(data, destination):
    """Offline directory snapshot with full re-read/hash verification; no secrets."""
    files=[]
    for path in sorted(data.rglob("*")):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError("non_regular_data")
        if path.is_file() and path.name!="writer.lock":
            files.append(path)
    manifest={str(p.relative_to(data)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    with tarfile.open(destination,"x:gz") as archive:
        for path in files:
            archive.add(path,arcname=str(path.relative_to(data)),recursive=False)
    with tarfile.open(destination,"r:gz") as archive:
        actual={m.name:hashlib.sha256(archive.extractfile(m).read()).hexdigest() for m in archive.getmembers()}
    if actual!=manifest:
        raise ValueError("backup_hash_mismatch")
    return manifest


def run(args, timeout=600):
    result=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=timeout)
    if result.returncode:
        # Do not expose Docker inspect/env, subprocess stderr or provider key.
        raise RuntimeError("command_failed:"+args[0])
    return result.stdout


def inspect_all():
    ids=run(["docker","ps","-aq"]).split()
    return json.loads(run(["docker","inspect",*ids])) if ids else []


def install(sha, repo):
    validate_sha(sha)
    if os.getenv("BRAIN_INSTALL_APPROVED")!="yes" or not os.getenv("DEEPSEEK_API_KEY"):
        raise ValueError("approval_and_model_key_required")
    if run(["git","-C",str(repo),"rev-parse","HEAD"]).strip()!=sha:
        raise ValueError("checkout_sha_mismatch")
    # Fixed canonical directory and own container only; no alternate volumes.
    if DATA.resolve()!=DATA:
        raise ValueError("symlinked_data_directory")
    reject_conflicts(inspect_all())
    DATA.mkdir(parents=True,exist_ok=True)
    with (DATA/"writer.lock").open("a") as writer:
        fcntl.flock(writer,fcntl.LOCK_EX|fcntl.LOCK_NB)
        backups=BACKUPS;backups.mkdir(mode=0o700,exist_ok=True)
        stamp=time.strftime("%Y%m%dT%H%M%SZ",time.gmtime())
        backup_path=backups/("preinstall-"+stamp+"-"+sha[:12]+".tar.gz")
        backup(DATA,backup_path)
        print("BRAIN_BACKUP_HASH_VERIFIED=PASS",flush=True)
        run(["docker","build","--label","superbot.sha="+sha,"-f",str(repo/"Dockerfile.brainpilot"),
             "-t","superbot-brain-pilot:sha-"+sha,str(repo)],timeout=900)
        # Serialize installer runs as well as runtime writer. Recheck before creation.
        reject_conflicts(inspect_all())
        fcntl.flock(writer,fcntl.LOCK_UN)
        attempted=False
        try:
            attempted=True
            started_ms=time.time()*1000
            run(docker_args(sha),timeout=120)
            item=json.loads(run(["docker","inspect",NAME]))[0]
            verify_container(item,sha)
            deadline=time.monotonic()+420
            while time.monotonic()<deadline:
                item=json.loads(run(["docker","inspect",NAME]))[0]
                state=item["State"]
                if not state.get("Running"):
                    raise RuntimeError("brain_not_running")
                try:
                    status=json.loads((DATA/"status.json").read_text())
                except (OSError,ValueError):
                    status={}
                if state.get("Health",{}).get("Status")=="healthy" and status.get("ts_ms",0)>=started_ms:
                    break
                time.sleep(5)
            else:
                raise RuntimeError("brain_health_timeout")
            # Own status only; no account values or credentials in deploy output.
            if status.get("mode")!="paper" or status.get("applied") is not False or time.time()*1000-status.get("ts_ms",0)>1800000:
                raise ValueError("brain_status_mismatch")
            if item["State"].get("RestartCount",item.get("RestartCount",0))!=0:
                raise ValueError("brain_restarted_during_install")
            manifest={"sha":sha,"container":NAME,"data":str(DATA),"mode":"paper",
                      "backup":str(backup_path),"installed_utc":stamp}
            (backups/("install-"+stamp+".json")).write_text(json.dumps(manifest,sort_keys=True))
            print("BRAIN_PAPER_ISOLATION_HEALTH=PASS",flush=True)
        except Exception:
            if attempted:
                # Only a container labeled as THIS installation may be stopped.
                try:
                    own=json.loads(run(["docker","inspect",NAME]))[0]
                    if own.get("Config",{}).get("Labels",{}).get("superbot.sha")==sha:
                        run(["docker","stop",NAME],timeout=60)
                except Exception:
                    pass
            raise


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--sha",required=True)
    parser.add_argument("--repo",type=Path,required=True);args=parser.parse_args()
    # Never print command/environment/exception details with model credentials.
    try:
        with open("/opt/superbot-brain-install.lock","a") as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            install(args.sha,args.repo)
    except Exception as exc:
        print("BRAIN_INSTALL_FAILED="+type(exc).__name__,flush=True)
        raise SystemExit(1)


if __name__=="__main__":
    main()
