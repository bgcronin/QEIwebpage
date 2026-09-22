#!/usr/bin/env python3
"""Download the QEI Laser (qeilaser.com.au) images referenced by the QEI Laser pages.

The images live on the Squarespace CDN. Run this where that host is reachable
(a developer machine, or the "Fetch QEI Laser images" GitHub Actions workflow):

    python src/fetch_qeilaser_images.py

Files are saved to content/media/qei-laser/ using the names the pages expect.
Existing files are kept unless --force is given.
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / "content" / "media" / "qei-laser"
CDN = "https://images.squarespace-cdn.com/content/v1/5bcffe79a9ab954023c4fa0e/"

IMAGES = {
    # page photographs
    "dr-brendan-cronin-laser.jpg": "0bc021df-edc4-4719-b815-040f57a2e214/img-Dr%2BBrendan%2BCronin%2BBrisbane%2BOphthalmologist%2BQueensland%2BEye%2BInstitute%2BLaser.jpg?format=original",
    "dr-david-gunn-slit-lamp.jpg": "b3179ac6-22d8-42d6-a6bf-d31acab0d3b3/img-Brisbane%2BOphthalmologist%2BDr%2BDavid%2BGunn%2BSlit%2BLamp.jpg?format=original",
    "dr-david-gunn-consult.jpg": "6462683f-c682-46bc-896c-f2375ef7f91d/img-Dr%2BDavid%2BGunn%2BQueensland%2BEye%2BInstitute%2BBrisbane%2BOphthalmologist.jpg?format=original",
    "topography-irregular-astigmatism.jpg": "d139a4a1-d1c6-42ba-bf65-3281c9388bd1/img-Irregular%2Bastigmatism%2BQEI%2BLaser.jpg?format=original",
    "post-corneal-transplant.jpg": "d1649816-a66d-46d2-8bfe-62dc509b3b24/img-Post%2BCorneal%2BTransplant%2BQueensland%2BLaser%2BEye%2BSurgery%2BBrisbane.jpg?format=original",
    "corneal-scarring.jpg": "407e1c6b-4adf-4e2f-91ca-1dd7599ee127/img-Corneal%2BScarring%2BQueensland%2BLaser%2BEye%2BSurgery%2BBrisbane.jpg?format=original",
    "recurrent-erosion.jpg": "69aaf422-4c93-4d9f-9d39-0337951fbaa5/img-Corneal%2BDystrophies%2BQueensland%2BLaser%2BEye%2BSurgery%2BBrisbane.jpg?format=original",
    "corneal-dystrophy.jpg": "8b1e82d6-a980-4023-b3a3-d2156dcd3cf2/img-Corneal%2BDystrophies%2BLaser%2BEye%2BSurgery%2BBrisbane%2BQueensland.jpg?format=original",
    "topography-keratoconus.jpg": "0dfb947b-36e8-4289-b464-f3147116e304/img-Keratoconus%2BPTK%2BBrisbane%2Blaser%2BQEI.jpg?format=original",
    "cairs.jpg": "5b2d5757-053f-44ea-8fc9-02b84399e3d7/img-CAIRS%2Beye%2Bsurgery%2Bring%2Bsegments%2BKeratoconus%2BBrisbanecairs.jpg?format=original",
    # treatment icons used on the hub cards
    "icon-post-corneal-transplant.png": "0dd928fe-fab9-4f6b-be1e-cab9a5519677/img-Post%2BCorneal%2BTransplant.png",
    "icon-corneal-ring-segments.png": "196352d4-b6d7-47db-ab09-673c3005d52e/img-Corneal%2BRing%2BSegments.png",
    "icon-irregular-astigmatism.png": "74aa4c75-3c2c-4bd2-bd18-9c78563285f2/img-Irregular%2BAsigmatism.png",
    "icon-corneal-erosion.png": "aa1b8e78-9a92-4d51-9d5b-622b2cc9a877/img-Corneal%2BErosion.png",
    "icon-corneal-scarring.png": "cb688b48-c94b-4ddb-8e04-f992d257b6ee/img-Corneal%2BScarring.png",
    "icon-keratoconus-cross-linking.png": "d31cdad0-eb01-48c0-8c51-2e1326bbe535/img-Keratoconus%2BCross%2BLinking%2Btreatment.png",
    "icon-corneal-dystrophy.png": "fce89222-00c1-41e2-bc89-0aefeb4e77c8/img-Corneal%2BDystrophy.png",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="re-download files that already exist")
    args = ap.parse_args()
    DEST.mkdir(parents=True, exist_ok=True)
    failures = 0
    for name, path in IMAGES.items():
        dest = DEST / name
        if dest.exists() and not args.force:
            print(f"kept     {name}")
            continue
        url = CDN + path
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "QEI-Authorised-Site-Migration/1.0 (+https://qei.org.au/contact/)"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            if len(data) < 1000:
                raise ValueError(f"unexpectedly small response ({len(data)} bytes)")
            dest.write_bytes(data)
            print(f"saved    {name} ({len(data) // 1024} KiB)")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAILED   {name}: {exc}", file=sys.stderr)
    print(f"done, {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
