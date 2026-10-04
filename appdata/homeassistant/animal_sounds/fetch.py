#!/usr/bin/env python3
"""Resolve an animal to a sound clip for script.animal_sound (Home Assistant).

Prints one JSON line: {"result": "ok", "animal": "cow", "url": "...", "seconds": 3} or {"result": "unknown", ...}.
Clips live in /config/www/animals/<animal>.mp3 (served at /local/animals/...). A missing clip is fetched once from
Freesound (CC-licensed preview; token from FREESOUND_API_KEY in the container env, via stacks/home.yaml and the
server .env) and cached, so first ask of a new
animal takes a few seconds, every later ask is instant. Only the standard library plus mutagen (ships with HA).
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

CLIPS = Path("/config/www/animals")
KEY_FILE = Path("/config/animal_sounds/freesound.key")
BASE_URL = "http://192.168.40.40:8123/local/animals"  # HA's IoT-VLAN address: the speakers live there

# Kid words and plurals the model may pass through, plus animals whose sounds are better found by their verb.
SYNONYMS = {
    "puppy": "dog", "puppies": "dog", "doggy": "dog", "doggie": "dog", "dogs": "dog",
    "kitty": "cat", "kitten": "cat", "kittens": "cat", "cats": "cat",
    "piggy": "pig", "piglet": "pig", "pigs": "pig", "hog": "pig",
    "birdie": "bird", "birds": "bird", "chick": "chicken", "hen": "chicken", "rooster": "rooster",
    "cows": "cow", "calf": "cow", "bull": "cow", "ducky": "duck", "ducks": "duck", "duckling": "duck",
    "horsey": "horse", "pony": "horse", "horses": "horse", "lamb": "sheep", "sheeps": "sheep",
    "goats": "goat", "kid goat": "goat", "froggy": "frog", "frogs": "frog", "toad": "frog",
    "owls": "owl", "lions": "lion", "lion cub": "lion", "tiger cub": "tiger", "tigers": "tiger",
    "bears": "bear", "elephants": "elephant", "monkeys": "monkey", "ape": "monkey", "gorilla": "gorilla",
    "wolves": "wolf", "wolf pup": "wolf", "snakes": "snake", "bees": "bee", "bumblebee": "bee",
    "t-rex": "dinosaur", "trex": "dinosaur", "t rex": "dinosaur", "dinosaurs": "dinosaur", "dino": "dinosaur",
    "donkeys": "donkey", "mule": "donkey", "turkeys": "turkey", "geese": "goose", "crows": "crow",
    "whales": "whale", "dolphins": "dolphin", "seals": "seal", "mice": "mouse", "rats": "mouse",
    "zebras": "horse", "giraffes": "giraffe", "hippos": "hippo", "hippopotamus": "hippo",
}
# Freesound search text per animal (its characteristic sound), for better hits than the bare name.
QUERIES = {
    "dog": "dog bark", "cat": "cat meow", "cow": "cow moo", "pig": "pig oink", "sheep": "sheep baa",
    "goat": "goat bleat", "horse": "horse neigh", "duck": "duck quack", "chicken": "chicken cluck",
    "rooster": "rooster crow", "owl": "owl hoot", "lion": "lion roar", "tiger": "tiger growl",
    "bear": "bear growl", "elephant": "elephant trumpet", "monkey": "monkey chatter", "wolf": "wolf howl",
    "frog": "frog croak", "bee": "bee buzz", "snake": "snake hiss", "bird": "bird chirp", "crow": "crow caw",
    "donkey": "donkey bray", "turkey": "turkey gobble", "goose": "goose honk", "mouse": "mouse squeak",
    "whale": "whale song", "dolphin": "dolphin click", "seal": "seal bark", "dinosaur": "dinosaur roar",
    "giraffe": "giraffe hum", "hippo": "hippo grunt", "gorilla": "gorilla grunt", "cricket": "cricket chirp",
}


def normalise(raw: str) -> str:
    a = re.sub(r"[^a-z -]", "", raw.lower()).strip()
    a = re.sub(r"^(a|an|the|baby|little|big)\s+", "", a)
    a = SYNONYMS.get(a, a)
    if a not in QUERIES and a.endswith("s") and a[:-1] in QUERIES:
        a = a[:-1]
    return a


def seconds(path: Path) -> int:
    try:
        import mutagen

        return int(round(mutagen.File(path).info.length))
    except Exception:
        return 3


def fetch(animal: str, dest: Path) -> bool:
    token = os.environ.get("FREESOUND_API_KEY", "").strip() or (KEY_FILE.read_text().strip() if KEY_FILE.exists() else "")
    if not token:
        return False
    # A few seconds of sound, not a single bark: prefer 5-15 s well-rated clips, then relax duration/licence,
    # then try the bare animal name in case the "cow moo"-style hint finds nothing.
    results = []
    for query, flt in [(QUERIES.get(animal, f"{animal} sound"), "duration:[5 TO 15] license:(\"Creative Commons 0\" OR \"Attribution\")"),
                       (QUERIES.get(animal, f"{animal} sound"), "duration:[3 TO 20]"),
                       (animal, "duration:[3 TO 20]")]:
        q = urllib.parse.urlencode({
            "query": query,
            "filter": flt,
            "fields": "id,name,previews,avg_rating,num_ratings",
            "sort": "rating_desc",
            "page_size": 5,
            "token": token,
        })
        req = urllib.request.Request(f"https://freesound.org/apiv2/search/text/?{q}", headers={"User-Agent": "homelab-animal-sounds/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            results = json.load(r).get("results", [])
        if results:
            break
    for hit in results:
        url = (hit.get("previews") or {}).get("preview-hq-mp3")
        if not url:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "homelab-animal-sounds/1.0"}), timeout=30) as r:
            dest.write_bytes(r.read())
        return True
    return False


def main() -> None:
    raw = " ".join(sys.argv[1:])
    animal = normalise(raw)
    if not animal:
        print(json.dumps({"result": "unknown", "animal": raw}))
        return
    clip = CLIPS / f"{animal}.mp3"
    if not clip.exists():
        try:
            ok = fetch(animal, clip)
        except Exception as e:  # network/API trouble: answer in words instead
            ok = False
            print(json.dumps({"result": "unknown", "animal": animal, "error": str(e)[:120]}))
            return
        if not ok:
            print(json.dumps({"result": "unknown", "animal": animal}))
            return
    print(json.dumps({"result": "ok", "animal": animal, "url": f"{BASE_URL}/{animal}.mp3", "seconds": seconds(clip)}))


if __name__ == "__main__":
    main()
