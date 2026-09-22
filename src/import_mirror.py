#!/usr/bin/env python3
"""Extract editable content from the authorised static mirror in ``site/``.

Writes JSON/Markdown into ``content/``. Hand-edited files are never overwritten unless
``--force`` is given (collections such as news are always refreshed because they are
generated content). Run after the mirror has been refreshed to pick up new articles.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import re
import sys
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
MIRROR = ROOT / "site"
CONTENT = ROOT / "content"

KNOWN_CATEGORIES = ["QEI Clinic", "QEI Foundation", "Patient Stories", "Research", "Education", "Events"]
NOISE_SELECTORS = ["nav.header-section", "footer.footer-section", ".modal", "#fb-pxl-ajax-code", ".newsletter-section",
                   ".latest-news", ".event-pagination-sect", ".clinical-help", ".responsive-menu", ".desktop-menu", ".qei-static-form-notice"]


def slugify(text: str) -> str:
    text = re.sub(r"[’'\"]", "", text.lower())
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def load(path: Path) -> BeautifulSoup:
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "lxml")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    for sel in NOISE_SELECTORS:
        for t in soup.select(sel):
            t.decompose()
    return soup


def yoast(path: Path) -> dict:
    html = path.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r'<script class="yoast-schema-graph" type="application/ld\+json">(.*?)</script>', html, re.S)
    out = {}
    if not m:
        return out
    try:
        graph = json.loads(m.group(1)).get("@graph", [])
    except json.JSONDecodeError:
        return out
    for node in graph:
        if node.get("@type") == "WebPage":
            out["published"] = (node.get("datePublished") or "")[:10]
            out["modified"] = (node.get("dateModified") or "")[:10]
            out["description"] = node.get("description", "")
    m2 = re.search(r'<meta content="([^"]*)" name="description"', html)
    if m2:
        out["meta_description"] = m2.group(1)
    return out


def media_ref(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    value = re.sub(r"^url\(['\"]?(.*?)['\"]?\)$", r"\1", value)
    value = re.sub(r"^https?://(www\.)?qei\.org\.au/", "", value)
    value = re.sub(r"^(\.\./)+", "", value)
    value = re.sub(r"^\./", "", value)
    if "wp-content/uploads" not in value:
        return None
    return value


def bg_image(tag) -> str | None:
    if tag is None:
        return None
    m = re.search(r"url\(['\"]?([^'\")]+)['\"]?\)", tag.get("style", ""))
    return media_ref(m.group(1)) if m else None


def parse_date(text: str) -> str | None:
    text = (text or "").strip()
    for fmt in ("%d %b, %Y", "%d %B, %Y", "%d %b %Y"):
        try:
            return dt.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def inner_html(tag) -> str:
    if tag is None:
        return ""
    return "".join(str(c) for c in tag.contents).strip()


def text(tag) -> str:
    return re.sub(r"\s+", " ", tag.get_text(" ", strip=True)) if tag else ""


def header(soup: BeautifulSoup) -> dict:
    h = soup.select_one("header.header-cover-section")
    out = {"title": "", "role": "", "quals": "", "summary": "", "date": None, "hero": None}
    if not h:
        return out
    out["title"] = text(h.find("h1"))
    det = h.select_one(".inner-header-details")
    if det:
        h4 = det.find("h4")
        out["role"] = text(h4)
        ps = [text(p) for p in det.find_all("p") if text(p)]
        for p in ps:
            if parse_date(p):
                out["date"] = parse_date(p)
            elif h4 is not None and not out["quals"]:
                out["quals"] = p
            elif not out["summary"]:
                out["summary"] = p
    else:
        p = h.find("p")
        out["summary"] = text(p)
    out["hero"] = bg_image(h.select_one(".header-inner-right"))
    return out


def profile_sections(soup: BeautifulSoup) -> dict:
    """Return {label: tag} for the labelled blocks on profile-style pages (document order)."""
    out = {}
    for block in soup.select(".team-information-sect .about-table"):
        label = text(block.select_one(".team-info-left h3"))
        right = block.select_one(".team-info-right")
        if right is None or not text(right):
            continue
        key = label or "_"
        while key in out:
            key += " "
        out[key] = right
    return out


BIO_EXCLUDE = ("disorders treated", "referral")


def bio_from_sections(secs: dict) -> str:
    """Concatenate every narrative block (Bio, About, History, Qualifications ...) in page order."""
    parts = []
    for label, tag in secs.items():
        if any(label.strip().lower().startswith(x) for x in BIO_EXCLUDE):
            continue
        parts.append(inner_html(tag))
    return "\n".join(parts)


def write_json(path: Path, data: dict, force: bool) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        return False
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


SUBSPECIALTY_RULES = [
    ("cornea", r"cornea|corneal|keratoconus|anterior segment|pterygium"),
    ("cataract", r"cataract"),
    ("retina", r"retina|retinal|macula|vitreoretinal|diabetic"),
    ("glaucoma", r"glaucoma"),
    ("neuro-ophthalmology", r"neuro"),
    ("oculoplastics", r"oculoplastic|eyelid|lacrimal|orbital|tear drainage"),
    ("refractive", r"refractive|laser"),
    ("uveitis", r"uveitis|inflammatory"),
    ("genetic", r"genetic|inherited"),
]


def import_doctors(force: bool) -> int:
    count = 0
    for path in sorted((MIRROR / "ophthalmologists").glob("*/index.html")):
        slug = path.parent.name
        if slug in ("refer-a-patient-form",):
            continue
        soup = load(path)
        h = header(soup)
        secs = profile_sections(soup)
        bio = secs.get("Bio") or secs.get("About") or secs.get("_")
        bio_html_all = bio_from_sections(secs)
        treats = []
        for label in ("Disorders Treated", "Disorders treated"):
            if label in secs:
                treats = [text(li) for li in secs[label].find_all("li")]
        notes = ""
        for label, tag in secs.items():
            if label.lower().startswith("referral"):
                notes = inner_html(tag)
        bio_html = bio_html_all
        first_p = bio.find("p") if bio else None
        summary = text(first_p)
        hay = (h["role"] + " " + " ".join(treats)).lower()
        tags = [tag for tag, pattern in SUBSPECIALTY_RULES if re.search(pattern, hay)]
        y = yoast(path)
        surname = h["title"].split()[-1]
        data = {
            "slug": slug, "name": h["title"], "role": h["role"], "qualifications": h["quals"], "photo": h["hero"],
            "photo_alt": f"Portrait of {h['title']}", "summary": summary or y.get("meta_description", ""),
            "meta_description": y.get("meta_description", ""), "bio_html": bio_html, "treats": treats, "subspecialties": tags,
            "notes_html": notes, "order": 100, "surname": surname, "old_url": f"/ophthalmologists/{slug}/",
        }
        if write_json(CONTENT / "doctors" / f"{slug}.json", data, force):
            count += 1
    return count


def gather_categories() -> dict[str, set]:
    cats: dict[str, set] = collections.defaultdict(set)
    for path in (MIRROR / "newscategories").glob("*/index.html"):
        soup = load(path)
        cat = text(soup.find("h1"))
        for a in soup.select(".latest-news-inner a[href]"):
            m = re.search(r"news/([^/]+)/", a["href"])
            if m:
                cats[m.group(1)].add(cat)
    for path in MIRROR.rglob("index.html"):
        if "/wp-content/" in str(path) or "_subdomains" in str(path):
            continue
        html = path.read_text(encoding="utf-8", errors="ignore")
        if "latest-news-inner" not in html:
            continue
        soup = BeautifulSoup(html, "lxml")
        for item in soup.select(".latest-news-inner"):
            a = item.find("a", href=re.compile(r"news/[^/]+/"))
            if not a:
                continue
            slug = re.search(r"news/([^/]+)/", a["href"]).group(1)
            for li in item.select("li"):
                t = text(li)
                if not t or parse_date(t):
                    continue
                for known in KNOWN_CATEGORIES:
                    if known in t:
                        cats[slug].add(known)
    return cats


def article_body(soup: BeautifulSoup) -> str:
    sec = soup.select_one("section.clinics-section .container-inner")
    if sec is None:
        return ""
    for p in sec.select("p.event-date"):
        p.decompose()
    return inner_html(sec)


def import_articles(force: bool) -> dict:
    cats = gather_categories()
    counts = {"news": 0, "stories": 0, "events": 0}
    for path in sorted((MIRROR / "news").glob("*/index.html")):
        slug = path.parent.name
        soup = load(path)
        h = header(soup)
        y = yoast(path)
        body = article_body(soup)
        data = {"slug": slug, "title": h["title"], "date": h["date"] or y.get("published"), "modified": y.get("modified"),
                "categories": sorted(cats.get(slug, [])) or ["News"], "hero": h["hero"], "hero_alt": "",
                "excerpt": y.get("meta_description") or y.get("description", ""), "body_html": body, "old_url": f"/news/{slug}/"}
        if write_json(CONTENT / "news" / f"{slug}.json", data, True):
            counts["news"] += 1
    for path in sorted((MIRROR / "patientstory").glob("*/index.html")):
        slug = path.parent.name
        soup = load(path)
        h = header(soup)
        y = yoast(path)
        data = {"slug": slug, "title": h["title"], "date": y.get("published"), "modified": y.get("modified"), "subtitle": h["summary"],
                "hero": h["hero"], "hero_alt": "", "excerpt": y.get("meta_description") or h["summary"], "body_html": article_body(soup),
                "old_url": f"/patientstory/{slug}/"}
        if write_json(CONTENT / "stories" / f"{slug}.json", data, True):
            counts["stories"] += 1
    for path in sorted((MIRROR / "events").glob("*/index.html")):
        slug = path.parent.name
        soup = load(path)
        h = header(soup)
        y = yoast(path)
        details = soup.select_one(".clinic-findus .findus-right")
        venue = ""
        if details:
            ps = [text(p) for p in details.find_all("p") if text(p)]
            for p in ps:
                if re.search(r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday|january|february|march|april|may|june|july|august|september|october|november|december)", p, re.I):
                    continue
                if re.search(r"street|road|st\b|centre|hospital|ristorante|restaurant|auditorium|institute|qld|southbank|south bank|brisbane|rooftop", p, re.I) and not re.search(r"^\d", p):
                    venue = p
                    break
        data = {"slug": slug, "title": h["title"], "date": h["date"] or y.get("published"), "modified": y.get("modified"), "hero": h["hero"],
                "hero_alt": "", "excerpt": y.get("meta_description") or y.get("description", ""), "body_html": article_body(soup),
                "details_html": inner_html(details), "venue": venue, "old_url": f"/events/{slug}/"}
        if write_json(CONTENT / "events" / f"{slug}.json", data, True):
            counts["events"] += 1
    return counts


def import_people(force: bool) -> int:
    count = 0
    groups = {"our-board": "our-board", "management": "management", "ambassadors": "ambassadors"}
    for group in groups:
        index = MIRROR / "qei-foundation" / "our-people" / group / "index.html"
        if not index.exists():
            continue
        soup = load(index)
        items = []
        for order, block in enumerate(soup.select(".our-board-inner"), start=1):
            name = text(block.find("h3"))
            role = text(block.select_one(".board-pos")).title() if block.select_one(".board-pos") else ""
            photo = bg_image(block.select_one(".board-img"))
            right = block.select_one(".our-board-right")
            paras = [p for p in right.find_all("p")] if right else []
            bio = "".join(str(p) for p in paras)
            items.append({"name": name, "role": role, "photo": photo, "bio_html": bio, "order": order})
        if not items:
            main = soup.select_one("section.clinics-section .container-inner") or soup.select_one("main") or soup.body
            current = None
            for el in main.find_all(["h3", "p", "ul"], recursive=True):
                if el.name == "h3":
                    current = {"name": text(el), "role": "", "photo": None, "bio_html": "", "order": len(items) + 1}
                    items.append(current)
                elif current is not None:
                    current["bio_html"] += str(el)
        for item in items:
            slug = slugify(item["name"].replace("OAM", "").replace("AM", "").strip(" ,"))
            page = MIRROR / "qei-foundation" / "our-people" / group / slug / "index.html"
            quals = ""
            if not page.exists():
                for cand in (MIRROR / "qei-foundation" / "our-people" / group).glob("*/index.html"):
                    if slugify(item["name"]).split("-")[-1] in cand.parent.name:
                        page = cand
                        break
            if page.exists():
                ps = load(page)
                h = header(ps)
                secs = profile_sections(ps)
                bio_all = bio_from_sections(secs)
                if bio_all.strip():
                    item["bio_html"] = bio_all
                item["photo"] = h["hero"] or item["photo"]
                item["role"] = item["role"] or h["role"]
                quals = h["quals"]
                slug = page.parent.name
            data = {"slug": slug, "name": item["name"], "group": group, "role": item["role"], "qualifications": quals, "photo": item["photo"],
                    "photo_alt": f"Portrait of {item['name']}", "summary": text(BeautifulSoup(item["bio_html"], "lxml").find("p")),
                    "bio_html": item["bio_html"], "order": item["order"]}
            if write_json(CONTENT / "people" / f"{group}--{slug}.json", data, force):
                count += 1
    return count


def import_researchers(force: bool) -> int:
    count = 0
    index = load(MIRROR / "research" / "researchers" / "index.html")
    order = {}
    for i, h3 in enumerate(index.find_all("h3"), start=1):
        order[slugify(text(h3))] = i
    for path in sorted((MIRROR / "research" / "researchers").glob("*/index.html")):
        slug = path.parent.name
        soup = load(path)
        h = header(soup)
        secs = profile_sections(soup)
        bio_html = bio_from_sections(secs)
        first = BeautifulSoup(bio_html, "lxml").find("p")
        data = {"slug": slug, "name": h["title"], "role": h["role"], "qualifications": h["quals"], "photo": h["hero"], "photo_alt": f"Portrait of {h['title']}",
                "summary": text(first), "bio_html": bio_html, "order": order.get(slugify(h["title"]), 100), "old_url": f"/research/researchers/{slug}/"}
        if write_json(CONTENT / "researchers" / f"{slug}.json", data, force):
            count += 1
    return count


def import_groups(force: bool) -> int:
    count = 0
    for i, path in enumerate(sorted((MIRROR / "research" / "groups-publications").glob("*/index.html")), start=1):
        slug = path.parent.name
        soup = load(path)
        h = header(soup)
        body = article_body(soup)
        data = {"slug": slug, "title": h["title"], "summary": h["summary"], "body_html": body, "order": i, "old_url": f"/research/groups-publications/{slug}/"}
        if write_json(CONTENT / "research-groups" / f"{slug}.json", data, force):
            count += 1
    return count


def import_conditions(force: bool) -> int:
    count = 0
    for path in sorted((MIRROR / "eye-conditions").glob("*/index.html")):
        slug = path.parent.name.replace("diabetic-ratinopathy", "diabetic-retinopathy")
        dest = CONTENT / "conditions" / f"{slug}.md"
        if dest.exists() and not force:
            continue
        soup = load(path)
        h = header(soup)
        sec = soup.select_one("section.clinics-section .container-inner")
        body = inner_html(sec)
        front = {"title": h["title"], "slug": slug, "summary": h["summary"], "icon": h["hero"], "doctors": [], "keywords": [], "reviewed_by": "", "reviewed_on": ""}
        fm = "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in front.items())
        dest.write_text(f"---\n{fm}\n---\n\n{body}\n", encoding="utf-8")
        count += 1
    return count


def import_policies(force: bool) -> int:
    count = 0
    for slug, title, section in (("privacy-policy", "Privacy policy", "About"), ("terms-and-conditions", "Terms and conditions", "About")):
        path = MIRROR / slug / "index.html"
        dest = CONTENT / "pages" / f"{slug}.md"
        if not path.exists() or (dest.exists() and not force):
            continue
        soup = load(path)
        h = header(soup)
        sec = soup.select_one("section.clinics-section .container-inner")
        body = inner_html(sec)
        y = yoast(path)
        fm = {"title": h["title"] or title, "url": f"/{slug}/", "section": section, "parent": "/about/", "summary": y.get("meta_description", ""), "template": "page", "raw_html": True, "sidebar": ["contact"]}
        fmtxt = "\n".join(f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in fm.items())
        dest.write_text(f"---\n{fmtxt}\n---\n\n{body}\n", encoding="utf-8")
        count += 1
    return count


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="overwrite hand-editable files (doctors, people, researchers, groups, conditions, policies)")
    ap.add_argument("--only", nargs="*", default=None, help="limit to collections: doctors articles people researchers groups conditions policies")
    args = ap.parse_args()
    if not MIRROR.exists():
        print("site/ mirror not found", file=sys.stderr)
        return 1
    steps = {"doctors": import_doctors, "articles": import_articles, "people": import_people, "researchers": import_researchers,
             "groups": import_groups, "conditions": import_conditions, "policies": import_policies}
    for name, fn in steps.items():
        if args.only and name not in args.only:
            continue
        print(f"{name}:", fn(args.force))
    return 0


if __name__ == "__main__":
    sys.exit(main())
