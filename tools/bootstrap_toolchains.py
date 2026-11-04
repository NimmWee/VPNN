"""Install pinned, checksum-verified developer tools inside this project."""
from __future__ import annotations
import concurrent.futures
import hashlib
import json
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
import time

ROOT = Path(__file__).resolve().parents[1]
DOWNLOADS = ROOT / "downloads"
SDK = ROOT / ".toolchains"

def read_json(url):
    with urllib.request.urlopen(url, timeout=45) as response:
        return json.load(response)

def sha(path, algorithm):
    digest = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def install(item):
    destination = ROOT / item["destination"]
    archive = DOWNLOADS / item["filename"]
    algorithm, checksum = item["algorithm"], item["checksum"]
    if not archive.exists() or sha(archive, algorithm) != checksum:
        partial = archive.with_suffix(archive.suffix + ".part")
        print("Downloading " + item["name"], flush=True)
        request = urllib.request.Request(item["url"], method="HEAD")
        with urllib.request.urlopen(request, timeout=45) as response:
            count = int(response.headers["Content-Length"])
        chunks = DOWNLOADS / (item["filename"] + ".chunks")
        chunks.mkdir(exist_ok=True)
        chunk_size = 16 * 1024 * 1024
        ranges = [(i, start, min(start + chunk_size, count) - 1) for i, start in enumerate(range(0, count, chunk_size))]

        def download_chunk(part):
            index, start, end = part
            path = chunks / f"{index:05}.bin"
            expected = end - start + 1
            if path.exists() and path.stat().st_size == expected:
                return path
            for attempt in range(3):
                try:
                    request = urllib.request.Request(item["url"], headers={"Range": f"bytes={start}-{end}"})
                    with urllib.request.urlopen(request, timeout=90) as response, path.open("wb") as stream:
                        if response.status != 206 or not response.headers.get("Content-Range", "").startswith(f"bytes {start}-{end}/"):
                            raise RuntimeError("Server did not honour byte range")
                        while block := response.read(1024 * 1024):
                            stream.write(block)
                    if path.stat().st_size != expected:
                        raise RuntimeError("Incomplete download")
                    return path
                except Exception:
                    if attempt == 2:
                        raise

        completed = 0
        last_progress = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as workers:
            for path in workers.map(download_chunk, ranges):
                completed += path.stat().st_size
                if time.monotonic() - last_progress > 20:
                    print(f"{item['name']}: {completed * 100 // count}%", flush=True)
                    last_progress = time.monotonic()
        with partial.open("wb") as stream:
            for index, _, _ in ranges:
                with (chunks / f"{index:05}.bin").open("rb") as source:
                    for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
                        stream.write(block)
        if sha(partial, algorithm) != checksum:
            raise RuntimeError("Checksum mismatch: " + item["name"])
        partial.replace(archive)
        print("Verified " + item["name"] + f" ({count} bytes)", flush=True)
    if item.get("extract") is False:
        return
    marker = destination / (".vpnn-" + item["name"].lower().replace(" ", "-") + ".json")
    if marker.exists() and json.loads(marker.read_text())["checksum"] == checksum:
        print("Already installed " + item["name"], flush=True)
        return
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        strip_prefix = item.get("strip_prefix", "")
        if strip_prefix == "__first__":
            roots = {x.filename.split("/")[0] for x in bundle.infolist() if x.filename}
            if len(roots) != 1:
                raise RuntimeError("Expected one archive root")
            strip_prefix = roots.pop() + "/"
        for member in bundle.infolist():
            name = member.filename
            prefix = strip_prefix
            if prefix:
                if not name.startswith(prefix):
                    continue
                name = name[len(prefix):]
            if not name:
                continue
            target = (destination / name).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise RuntimeError("Unsafe archive member")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as source, target.open("wb") as stream:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        stream.write(block)
    marker.write_text(json.dumps(item, indent=2), encoding="utf-8")
    print("Installed " + item["name"], flush=True)

def main():
    DOWNLOADS.mkdir(exist_ok=True)
    SDK.mkdir(exist_ok=True)
    lock_path = ROOT / "toolchains.lock.json"
    if lock_path.exists():
        items = json.loads(lock_path.read_text(encoding="utf-8"))["tools"]
    else:
        releases = read_json("https://storage.googleapis.com/flutter_infra_release/releases/releases_windows.json")
        flutter = next(x for x in releases["releases"] if x["channel"] == "stable" and x["version"] == "3.47.6" and x.get("dart_sdk_arch") == "x64")
        packages = read_json("https://api.azul.com/metadata/v1/zulu/packages/?java_version=17&os=windows&arch=x86&hw_bitness=64&archive_type=zip&java_package_type=jdk&release_status=ga&availability_types=CA&latest=true")
        package = next(x for x in packages if "win_x64" in x["name"] and "-fx-" not in x["name"] and "-crac-" not in x["name"])
        jdk = read_json("https://api.azul.com/metadata/v1/zulu/packages/" + package["package_uuid"])
        with urllib.request.urlopen("https://dl.google.com/android/repository/repository2-1.xml", timeout=45) as response:
            repository = ET.fromstring(response.read())
        commandline = next(x for x in repository.iter("remotePackage") if x.attrib["path"] == "cmdline-tools;latest")
        archive = next(x for x in commandline.iter("archive") if x.findtext("host-os") == "windows")
        items = [
            {"name": "Flutter", "version": flutter["version"], "commit": flutter["hash"], "url": releases["base_url"] + "/" + flutter["archive"], "filename": Path(flutter["archive"]).name, "algorithm": "sha256", "checksum": flutter["sha256"], "destination": ".toolchains"},
            {"name": "JDK", "version": ".".join(map(str, jdk["java_version"])), "url": jdk["download_url"], "filename": jdk["name"], "algorithm": "sha256", "checksum": jdk["sha256_hash"], "destination": ".toolchains/java"},
            {"name": "Android command-line tools", "version": commandline.findtext("revision/major"), "url": "https://dl.google.com/android/repository/" + archive.findtext("complete/url"), "filename": archive.findtext("complete/url"), "algorithm": "sha1", "checksum": archive.findtext("complete/checksum"), "destination": ".toolchains/android-sdk/cmdline-tools/latest"},
        ]
        lock_path.write_text(json.dumps({"tools": items}, indent=2), encoding="utf-8")
    manager_lock = ROOT / "android-manager.lock.json"
    if manager_lock.exists():
        items.append(json.loads(manager_lock.read_text(encoding="utf-8")))
    for item in items:
        print(item["name"] + " " + item["version"], flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(install, items):
            pass
    print("All toolchains verified and extracted", flush=True)

if __name__ == "__main__":
    main()
