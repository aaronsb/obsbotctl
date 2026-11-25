#!/usr/bin/env python3
"""Find, pin and fetch OBSBOT's public camera firmware for the factory.

Firmware images are inputs to the factory and are never committed to this
repository. This tool keeps them in a local store outside the repository
and checks each one against a SHA256 pin that is committed.

Commands:

  discover   Read OBSBOT's public download catalog and product pages, and
             write factory/firmware/available.json: every published firmware
             file with its download URL.
  pin FILE…  Download the named files (as listed in available.json), record
             their SHA256 and size in factory/firmware/pins.json. Use "all"
             to pin every available file. A pin made this way is trust on
             first use: it records what OBSBOT served on that date.
  hydrate    Fetch every pinned file that is missing from the store, and
             refuse any whose SHA256 differs from its pin.
  verify     Check every pinned file already in the store against its pin.

The store is $OBSBOT_FIRMWARE_DIR, by default
~/.local/share/libobsbot/firmware/.

Downloads go through OBSBOT's own download flow: the tool asks OBSBOT's API
for a signed link to the file, the same request the download page's button
makes, and downloads that link. It sends no cookies, no account and no
personal data.

References:
- ADR-100 D2: vendor files are pinned inputs kept outside the repository.
- ADR-100 D3: the corpus can be rebuilt from scratch from pinned inputs.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
AVAILABLE = os.path.join(HERE, "firmware", "available.json")
PINS = os.path.join(HERE, "firmware", "pins.json")
STORE = os.environ.get("OBSBOT_FIRMWARE_DIR", os.path.expanduser("~/.local/share/libobsbot/firmware"))

SITE = "https://www.obsbot.com"
CATALOG = SITE + "/static/website/download/index.json"
AUTH = "https://remo-api.obsbot.com/fms/v1/files/cdn/authorization"
CDN_FILE = re.compile(r'https://resource-cdn\.obsbothk\.com/[^"\s]+?\.bin')
UA = "libobsbot-factory (+https://github.com/aaronsb/libobsbot)"


def http(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    return urllib.request.urlopen(req, timeout=120)


def load(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
        f.write("\n")


def discover(_args):
    with http(CATALOG) as r:
        keys = [e["productPageKey"] for e in json.load(r)["downloadIndex"]]
    found, read, missing = {}, [], []
    for key in dict.fromkeys(keys):
        try:
            with http(f"{SITE}/download/{key}") as r:
                page = r.read().decode("utf-8", "replace").replace("\\u002F", "/")
        except urllib.error.HTTPError as e:
            missing.append(f"{key} (HTTP {e.code})")
            continue
        read.append(key)
        for url in CDN_FILE.findall(page):
            found.setdefault(url.rsplit("/", 1)[1], url)
    files = [{"file": name, "url": url} for name, url in sorted(found.items())]
    save(AVAILABLE, {"discovered": datetime.date.today().isoformat(), "pages_read": read, "pages_missing": missing, "files": files})
    print(f"{len(files)} firmware files from {len(read)} product pages -> {os.path.relpath(AVAILABLE)}")
    for m in missing:
        print(f"  page not found: {m}")


def signed_link(url):
    body = json.dumps({"url": url}).encode()
    with http(AUTH, data=body, headers={"Content-Type": "application/json"}) as r:
        reply = json.load(r)
    link = reply.get("url") or (reply.get("data") or {}).get("url")
    if not link:
        raise RuntimeError(f"no signed link for {url}: {reply}")
    return link


def fetch(name, url):
    os.makedirs(STORE, exist_ok=True)
    dest = os.path.join(STORE, name)
    tmp = dest + ".part"
    h = hashlib.sha256()
    size = 0
    with http(signed_link(url)) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
            h.update(chunk)
            size += len(chunk)
    os.replace(tmp, dest)
    return dest, h.hexdigest(), size


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def pin(args):
    available = {f["file"]: f["url"] for f in load(AVAILABLE, {"files": []})["files"]}
    if not available:
        sys.exit("no available.json; run discover first")
    names = sorted(available) if args.files == ["all"] else args.files
    pins = load(PINS, {})
    for name in names:
        if name not in available:
            print(f"skip {name}: not in available.json")
            continue
        dest, digest, size = fetch(name, available[name])
        pins[name] = {"sha256": digest, "size": size, "url": available[name], "pinned": datetime.date.today().isoformat()}
        print(f"pinned {name} {digest[:16]}… {size} bytes")
    save(PINS, pins)


def hydrate(_args):
    bad = 0
    for name, p in sorted(load(PINS, {}).items()):
        dest = os.path.join(STORE, name)
        if os.path.exists(dest) and sha256(dest) == p["sha256"]:
            print(f"ok      {name}")
            continue
        dest, digest, size = fetch(name, p["url"])
        if digest != p["sha256"]:
            os.replace(dest, dest + ".mismatch")
            print(f"REFUSED {name}: sha256 {digest} != pin {p['sha256']} (kept as .mismatch)")
            bad += 1
        else:
            print(f"fetched {name}")
    sys.exit(1 if bad else 0)


def verify(_args):
    bad = 0
    for name, p in sorted(load(PINS, {}).items()):
        dest = os.path.join(STORE, name)
        state = "missing" if not os.path.exists(dest) else ("ok" if sha256(dest) == p["sha256"] else "MISMATCH")
        bad += state != "ok"
        print(f"{state:8s} {name}")
    sys.exit(1 if bad else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("discover").set_defaults(func=discover)
    p = sub.add_parser("pin"); p.add_argument("files", nargs="+"); p.set_defaults(func=pin)
    sub.add_parser("hydrate").set_defaults(func=hydrate)
    sub.add_parser("verify").set_defaults(func=verify)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
