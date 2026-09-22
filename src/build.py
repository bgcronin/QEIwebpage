#!/usr/bin/env python3
"""Static site generator for the Queensland Eye Institute website.

Reads editable content from ``content/`` (JSON, Markdown with YAML front matter),
renders Jinja2 templates from ``src/templates`` and writes a complete static site to
``web/`` (relative links, so it works on any host or path).

Run:  python src/build.py            # full build into web/
      python src/build.py --check    # build into a temp dir and report only
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

import markdown
import yaml
from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
SRC = ROOT / "src"
TEMPLATES = SRC / "templates"
ASSETS = SRC / "assets"
MIRROR = ROOT / "site"
CACHE = ROOT / ".cache"

MEDIA_MAX = {"hero": 1600, "body": 1200, "card": 800, "portrait": 640, "thumb": 480, "icon": 240}
ALLOWED_TAGS = {"p", "h2", "h3", "h4", "ul", "ol", "li", "a", "strong", "b", "em", "i", "br", "blockquote",
                "figure", "figcaption", "img", "table", "thead", "tbody", "tr", "th", "td", "sup", "sub", "hr", "span", "div"}

CATEGORY_SLUGS = {"QEI Clinic": "qei-clinic", "QEI Foundation": "qei-foundation", "Research": "research",
                  "Education": "education", "Events": "events", "Patient Stories": "patient-stories", "News": "news"}

_current_url = "/"
_warnings: list[str] = []


def warn(msg: str) -> None:
    if msg in _warnings:
        return
    _warnings.append(msg)
    print(f"  warning: {msg}", file=sys.stderr)


def slugify(text: str) -> str:
    text = re.sub(r"[’'\"]", "", text.lower())
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "item"


def rel(url: str) -> str:
    """Relative link from the page currently being rendered to ``url`` (site-absolute)."""
    if not url or re.match(r"^(https?:|mailto:|tel:|#|data:)", url):
        return url
    base_dir = _current_url.rsplit("/", 1)[0] + "/"
    depth = base_dir.count("/") - 1
    prefix = "../" * depth if depth > 0 else "./"
    target = url.lstrip("/")
    if target == "":
        return prefix
    return prefix + target


def read_json(path: Path):
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def read_markdown(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    meta: dict = {}
    body = text
    if text.startswith("---"):
        parts = text.split("\n---", 2)
        if len(parts) >= 3:
            meta = yaml.safe_load(parts[0][3:]) or {}
            body = parts[2].lstrip("\n")
        elif len(parts) == 2:
            meta = yaml.safe_load(parts[0][3:]) or {}
            body = parts[1].lstrip("\n")
    return meta, body


MD = markdown.Markdown(extensions=["extra", "sane_lists", "toc", "attr_list", "md_in_html"], output_format="html5")

_media_hook = None  # set by Site so markdown images go through the media pipeline


def finalize_html(html_text: str) -> str:
    """Make rendered HTML portable: relative root links and optimised local images."""
    def fix_href(m):
        url = m.group(2)
        return f'{m.group(1)}="{rel(url)}"'
    html_text = re.sub(r'\b(href|src)="(/(?!/)[^"]*)"', fix_href, html_text)

    def fix_img(m):
        ref = m.group(1)
        if _media_hook is None:
            return m.group(0)
        info = _media_hook(ref, "body")
        if not info:
            return m.group(0)
        size = f' width="{info["width"]}" height="{info["height"]}"' if info.get("width") else ""
        return f'src="{rel(info["url"])}"{size} loading="lazy" decoding="async"'
    html_text = re.sub(r'src="((?:wp-content|content/media)/[^"]+)"', fix_img, html_text)
    return html_text


def render_markdown(text: str) -> str:
    MD.reset()
    return finalize_html(MD.convert(text or ""))


# ---------------------------------------------------------------------------
# Media pipeline
# ---------------------------------------------------------------------------
class Media:
    def __init__(self, out_dir: Path):
        self.out_dir = out_dir / "media"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        CACHE.mkdir(exist_ok=True)
        self.manifest_path = CACHE / "media-manifest.json"
        try:
            self.manifest = read_json(self.manifest_path)
        except Exception:
            self.manifest = {}
        self.used: set[str] = set()
        self.webp_ok = True
        try:
            from PIL import features
            self.webp_ok = bool(features.check("webp"))
        except Exception:
            self.webp_ok = False

    def source_path(self, ref: str) -> Path | None:
        ref = ref.split("?")[0]
        candidates = []
        if ref.startswith("wp-content/"):
            candidates.append(MIRROR / ref)
        candidates += [ROOT / ref, SRC / "assets" / ref, CONTENT / "media" / ref]
        for c in candidates:
            if c.is_file():
                return c
        # Fall back to the un-resized WordPress original when a -WxH variant is missing
        m = re.match(r"^(.*)-\d+x\d+(\.[a-z]+)$", ref, re.I)
        if m:
            return self.source_path(m.group(1) + m.group(2))
        return None

    def process(self, ref: str | None, kind: str = "body", width: int | None = None) -> dict | None:
        """Return {url, width, height} for an optimised copy of ``ref`` or None."""
        if not ref:
            return None
        ref = ref.strip()
        if ref.startswith("http"):
            return {"url": ref, "width": None, "height": None}
        src = self.source_path(ref)
        max_w = width or MEDIA_MAX.get(kind, 1200)
        digest = hashlib.sha1(ref.encode("utf-8")).hexdigest()[:10]
        stem = slugify(Path(ref).stem)[:60]
        ext = Path(ref).suffix.lower()
        if src is None:
            # keep a previously generated file if it exists
            existing = sorted(self.out_dir.glob(f"{digest}-{stem}-w{max_w}.*"))
            if existing:
                p = existing[0]
                self.used.add(p.name)
                info = self.manifest.get(p.name, {})
                return {"url": f"/media/{p.name}", "width": info.get("width"), "height": info.get("height")}
            warn(f"media source missing: {ref}")
            return None
        if ext == ".svg":
            name = f"{digest}-{stem}.svg"
            dest = self.out_dir / name
            if not dest.exists() or dest.stat().st_size != src.stat().st_size:
                shutil.copyfile(src, dest)
            self.used.add(name)
            return {"url": f"/media/{name}", "width": None, "height": None}
        st = src.stat()
        key_base = f"{digest}-{stem}-w{max_w}"
        cached = self.manifest.get(key_base)
        if cached and cached.get("mtime") == st.st_mtime and cached.get("size") == st.st_size and (self.out_dir / cached["name"]).exists():
            self.used.add(cached["name"])
            return {"url": f"/media/{cached['name']}", "width": cached["width"], "height": cached["height"]}
        try:
            with Image.open(src) as im:
                im = ImageOps.exif_transpose(im)
                has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
                if im.width > max_w:
                    ratio = max_w / im.width
                    im = im.resize((max_w, max(1, round(im.height * ratio))), Image.LANCZOS)
                if has_alpha and self.webp_ok:
                    name = f"{key_base}.webp"
                    im.convert("RGBA").save(self.out_dir / name, "WEBP", quality=84, method=6)
                elif has_alpha:
                    name = f"{key_base}.png"
                    im.convert("RGBA").save(self.out_dir / name, "PNG", optimize=True)
                else:
                    name = f"{key_base}.jpg"
                    im.convert("RGB").save(self.out_dir / name, "JPEG", quality=82, optimize=True, progressive=True)
                w, h = im.width, im.height
        except Exception as exc:  # pragma: no cover - defensive
            warn(f"could not process {ref}: {exc}")
            return None
        self.manifest[key_base] = {"name": name, "width": w, "height": h, "mtime": st.st_mtime, "size": st.st_size}
        self.used.add(name)
        return {"url": f"/media/{name}", "width": w, "height": h}

    def save_manifest(self) -> None:
        self.manifest_path.write_text(json.dumps(self.manifest, indent=1), encoding="utf-8")

    def prune(self) -> None:
        for p in self.out_dir.iterdir():
            if p.is_file() and p.name not in self.used:
                p.unlink()


# ---------------------------------------------------------------------------
# Site model
# ---------------------------------------------------------------------------
class Page:
    def __init__(self, url: str, title: str, template: str, *, description: str = "", section: str = "",
                 lastmod: str | None = None, noindex: bool = False, image: str | None = None,
                 breadcrumbs: list | None = None, jsonld: list | None = None, search: dict | None = None,
                 changefreq: str = "monthly", priority: float = 0.6, **context):
        self.url = url
        self.title = title
        self.template = template
        self.description = description
        self.section = section
        self.lastmod = lastmod
        self.noindex = noindex
        self.image = image
        self.breadcrumbs = breadcrumbs or []
        self.jsonld = jsonld or []
        self.search = search
        self.changefreq = changefreq
        self.priority = priority
        self.context = context


class Site:
    def __init__(self, out_dir: Path, verbose: bool = True):
        self.out = out_dir
        self.verbose = verbose
        self.config = read_json(CONTENT / "site.json")
        self.pages: list[Page] = []
        self.media = Media(out_dir)
        self.env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]),
                               trim_blocks=True, lstrip_blocks=True)
        self.env.globals.update(rel=rel, site=self.config, media=self.media_url, media_info=self.media_info, now=dt.date.today(),
                                slugify=slugify, category_slug=self.category_slug, fmt_date=self.fmt_date)
        self.base_path = "/"
        self.env.tests["contains"] = lambda seq, value: value in (seq or [])
        global _media_hook
        _media_hook = self.media.process
        self.env.filters["md"] = render_markdown
        self.env.filters["rel"] = rel
        self.env.filters["fmt_date"] = self.fmt_date
        self.env.filters["excerpt"] = self.excerpt
        self.doctors: list[dict] = []
        self.conditions: list[dict] = []
        self.news: list[dict] = []
        self.stories: list[dict] = []
        self.events: list[dict] = []
        self.people: list[dict] = []
        self.researchers: list[dict] = []
        self.groups: list[dict] = []
        self.pages_md: list[dict] = []
        self.treatments: list[dict] = []

    # ----- helpers -----
    def media_url(self, ref, kind="body", width=None):
        info = self.media.process(ref, kind, width)
        return info["url"] if info else ""

    def media_info(self, ref, kind="body", width=None):
        return self.media.process(ref, kind, width)

    @staticmethod
    def category_slug(cat: str) -> str:
        return CATEGORY_SLUGS.get(cat, slugify(cat))

    @staticmethod
    def fmt_date(value) -> str:
        if not value:
            return ""
        if isinstance(value, (dt.date, dt.datetime)):
            d = value
        else:
            try:
                d = dt.date.fromisoformat(str(value)[:10])
            except ValueError:
                return str(value)
        return f"{d.day} {d.strftime('%B %Y')}"

    @staticmethod
    def excerpt(html_text: str, length: int = 180) -> str:
        text = BeautifulSoup(html_text or "", "lxml").get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text)
        if len(text) <= length:
            return text
        cut = text[:length].rsplit(" ", 1)[0]
        return cut + "…"

    def abs_url(self, url: str) -> str:
        return self.config["canonical_base"].rstrip("/") + url

    def old_to_new_url(self, href: str) -> str:
        """Map a link found in mirrored content to the new site (or the live site)."""
        h = href.strip()
        if not h or h.startswith("#") or re.match(r"^(mailto:|tel:|javascript:)", h):
            return h
        if h.startswith("http"):
            m = re.match(r"^https?://(www\.)?qei\.org\.au(/.*)?$", h)
            if not m:
                return h
            path = m.group(2) or "/"
        else:
            path = h
            path = re.sub(r"^(\.\./)+", "/", path)
            path = re.sub(r"^\./", "/", path)
            if not path.startswith("/"):
                path = "/" + path
        path = re.sub(r"index\.html$", "", path)
        path = path.split("#")[0].split("?")[0]
        if path.startswith("/wp-content/uploads/"):
            return self.config["live_site"] + path
        if not path.endswith("/"):
            path += "/"
        for r in self.config.get("redirects", []):
            if path == r["from"]:
                return r["to"]
        if path in self.known_urls:
            return path
        if path.startswith("/news/") or path.startswith("/patientstory/") or path.startswith("/events/"):
            return path if path in self.known_urls else self.config["live_site"] + path
        return self.config["live_site"] + path

    def clean_html(self, raw: str, image_kind: str = "body") -> str:
        """Sanitise imported HTML, optimise images and rewrite links for the new site."""
        soup = BeautifulSoup(raw or "", "lxml")
        body = soup.body or soup
        for tag in body.find_all(True):
            if tag.name not in ALLOWED_TAGS:
                tag.unwrap()
                continue
            attrs = {}
            if tag.name == "a" and tag.get("href"):
                href = self.old_to_new_url(tag["href"])
                attrs["href"] = rel(href) if href.startswith("/") else href
                if href.startswith("http") and "qei.org.au" not in href:
                    attrs["rel"] = "noopener"
            if tag.name == "img":
                src = tag.get("src") or tag.get("data-src") or ""
                src = re.sub(r"^(\.\./)+", "", src)
                src = re.sub(r"^https?://(www\.)?qei\.org\.au/", "", src)
                info = self.media.process(src, image_kind) if src and not src.startswith("http") else ({"url": src, "width": None, "height": None} if src else None)
                if not info:
                    tag.decompose()
                    continue
                attrs["src"] = rel(info["url"]) if info["url"].startswith("/") else info["url"]
                attrs["alt"] = tag.get("alt", "") or ""
                attrs["loading"] = "lazy"
                attrs["decoding"] = "async"
                if info.get("width"):
                    attrs["width"] = str(info["width"])
                    attrs["height"] = str(info["height"])
            if tag.name in ("th", "td") and tag.get("colspan"):
                attrs["colspan"] = tag["colspan"]
            if tag.name == "span" or tag.name == "div":
                # keep only alignment wrappers from WordPress
                cls = " ".join(tag.get("class", []))
                if "aligncenter" in cls or "wp-block-image" in cls:
                    attrs["class"] = "align-center"
                else:
                    tag.unwrap()
                    continue
            if tag.name == "figure":
                attrs["class"] = "figure"
            tag.attrs = attrs
        # remove empty paragraphs
        for p in body.find_all(["p", "div", "span"]):
            if not p.get_text(strip=True) and not p.find(["img", "br"]):
                p.decompose()
        out = "".join(str(c) for c in body.contents)
        return out.strip()

    # ----- loading -----
    def load(self) -> None:
        self.doctors = sorted((read_json(p) for p in sorted((CONTENT / "doctors").glob("*.json"))), key=lambda d: (d.get("order", 100), d["name"]))
        for d in self.doctors:
            d["url"] = f"/ophthalmologists/{d['slug']}/"
        self.news = sorted((read_json(p) for p in sorted((CONTENT / "news").glob("*.json"))), key=lambda n: n.get("date", ""), reverse=True)
        for n in self.news:
            n["url"] = f"/news/{n['slug']}/"
            n["categories"] = n.get("categories") or ["News"]
        self.stories = sorted((read_json(p) for p in sorted((CONTENT / "stories").glob("*.json"))), key=lambda n: n.get("date", ""), reverse=True)
        for s in self.stories:
            s["url"] = f"/patientstory/{s['slug']}/"
        self.events = sorted((read_json(p) for p in sorted((CONTENT / "events").glob("*.json"))), key=lambda n: n.get("date", ""), reverse=True)
        for e in self.events:
            e["url"] = f"/events/{e['slug']}/"
        self.people = sorted((read_json(p) for p in sorted((CONTENT / "people").glob("*.json"))), key=lambda p: (p.get("order", 100), p["name"]))
        for p in self.people:
            p["url"] = f"/qei-foundation/our-people/{p['group']}/{p['slug']}/"
        self.researchers = sorted((read_json(p) for p in sorted((CONTENT / "researchers").glob("*.json"))), key=lambda p: p.get("order", 100))
        for r in self.researchers:
            r["url"] = f"/research/researchers/{r['slug']}/"
        self.groups = sorted((read_json(p) for p in sorted((CONTENT / "research-groups").glob("*.json"))), key=lambda g: g.get("order", 100))
        for g in self.groups:
            g["url"] = f"/research/groups-publications/{g['slug']}/"
        self.conditions = []
        for p in sorted((CONTENT / "conditions").glob("*.md")):
            meta, body = read_markdown(p)
            meta["body_md"] = body
            meta["slug"] = meta.get("slug") or p.stem
            meta["url"] = f"/eye-conditions/{meta['slug']}/"
            self.conditions.append(meta)
        self.conditions.sort(key=lambda c: c["title"])
        self.pages_md = []
        for p in sorted((CONTENT / "pages").rglob("*.md")):
            meta, body = read_markdown(p)
            if not meta.get("url"):
                relp = p.relative_to(CONTENT / "pages").with_suffix("")
                parts = list(relp.parts)
                if parts[-1] == "index":
                    parts = parts[:-1]
                meta["url"] = "/" + "/".join(parts) + "/" if parts else "/"
            meta["body_md"] = body
            meta["_path"] = str(p)
            self.pages_md.append(meta)
        self.treatments = sorted([p for p in self.pages_md if p.get("template") == "treatment"], key=lambda t: t.get("order", 100))
        # every URL the site will produce (used for link rewriting)
        self.known_urls = set()
        for coll in (self.doctors, self.news, self.stories, self.events, self.people, self.researchers, self.groups, self.conditions, self.pages_md):
            for item in coll:
                self.known_urls.add(item["url"])
        for extra in ("/", "/ophthalmologists/", "/eye-conditions/", "/news/", "/events/", "/qei-clinics/", "/research/researchers/",
                      "/research/groups-publications/", "/qei-foundation/our-people/", "/qei-foundation/our-people/our-board/",
                      "/qei-foundation/our-people/management/", "/qei-foundation/our-people/ambassadors/", "/qei-foundation/patient-stories/",
                      "/search/", "/sitemap/"):
            self.known_urls.add(extra)
        for c in self.config["clinics"]:
            self.known_urls.add(f"/qei-clinics/{c['slug']}/")
        for d in self.doctors:
            d["conditions"] = [c for c in self.conditions if d["slug"] in (c.get("doctors") or [])]
            surname = d.get("surname") or d["name"].split()[-1]
            d["related_news"] = [n for n in self.news if re.search(r"\b" + re.escape(surname) + r"\b", n["title"] + " " + n.get("body_html", ""))][:4]
        for c in self.conditions:
            c["doctor_items"] = [d for d in self.doctors if d["slug"] in (c.get("doctors") or [])]

    # ----- page construction -----
    def crumbs(self, *items) -> list:
        out = [{"label": "Home", "url": "/"}]
        for label, url in items:
            out.append({"label": label, "url": url})
        return out

    def add(self, page: Page) -> None:
        self.pages.append(page)

    def build_pages(self) -> None:
        cfg = self.config
        # --- markdown pages (hand-authored) ---
        for meta in self.pages_md:
            template = {"hub": "hub.html", "landing": "dryeye-landing.html", "treatment": "treatment.html", "home": "home.html",
                        "contact": "contact.html", "clinics": "clinics-index.html"}.get(meta.get("template", "page"), "page.html")
            crumbs = [{"label": "Home", "url": "/"}]
            if meta.get("section") and meta.get("parent") and meta["parent"] != meta["url"]:
                crumbs.append({"label": meta["section"], "url": meta["parent"]})
            if meta["url"] != "/":
                crumbs.append({"label": meta.get("short_title") or meta["title"], "url": meta["url"]})
            jsonld = []
            if meta.get("faq"):
                jsonld.append(self.ld_faq(meta["faq"]))
            if meta.get("jsonld"):
                jsonld.append(meta["jsonld"])
            self.add(Page(meta["url"], meta["title"], template, description=meta.get("summary", ""), section=meta.get("section", ""),
                          noindex=bool(meta.get("noindex")), image=meta.get("hero_image"), breadcrumbs=crumbs, jsonld=jsonld,
                          changefreq=meta.get("changefreq", "monthly"), priority=float(meta.get("priority", 0.7)),
                          search={"t": meta["title"], "s": meta.get("section") or "Information", "d": meta.get("summary", ""), "b": meta["body_md"], "k": " ".join(meta.get("keywords", []))},
                          doc=meta))
        # --- doctors ---
        self.add(Page("/ophthalmologists/", "Our ophthalmologists", "doctors-index.html",
                      description="Meet the Queensland Eye Institute's ophthalmologists: fellowship-trained specialist eye surgeons in cornea, cataract, retina, glaucoma, neuro-ophthalmology, oculoplastics and refractive surgery.",
                      section="Ophthalmologists", breadcrumbs=self.crumbs(("Our ophthalmologists", "/ophthalmologists/")), priority=0.9,
                      search={"t": "Our ophthalmologists", "s": "Ophthalmologists", "d": "Specialist eye surgeons at QEI in Brisbane", "b": " ".join(d["name"] + " " + d["role"] for d in self.doctors)}))
        for d in self.doctors:
            self.add(Page(d["url"], d["name"], "doctor.html", description=d.get("summary", "")[:300], section="Ophthalmologists",
                          image=d.get("photo"), breadcrumbs=self.crumbs(("Our ophthalmologists", "/ophthalmologists/"), (d["name"], d["url"])),
                          jsonld=[self.ld_physician(d)], priority=0.8,
                          search={"t": d["name"], "s": "Ophthalmologist", "d": d["role"], "b": self.excerpt(d.get("bio_html", ""), 800) + " " + " ".join(d.get("treats", [])), "k": " ".join(d.get("subspecialties", []))},
                          doctor=d))
        # --- conditions ---
        self.add(Page("/eye-conditions/", "Eye conditions", "conditions-index.html",
                      description="Plain-English information about common eye conditions, their symptoms, causes and treatment, from Queensland Eye Institute ophthalmologists.",
                      section="Eye conditions", breadcrumbs=self.crumbs(("Eye conditions", "/eye-conditions/")), priority=0.9,
                      search={"t": "Eye conditions", "s": "Eye conditions", "d": "Information about eye conditions", "b": " ".join(c["title"] for c in self.conditions)}))
        for c in self.conditions:
            jsonld = [self.ld_condition(c)]
            if c.get("faq"):
                jsonld.append(self.ld_faq(c["faq"]))
            self.add(Page(c["url"], c["title"], "condition.html", description=c.get("summary", ""), section="Eye conditions",
                          breadcrumbs=self.crumbs(("Eye conditions", "/eye-conditions/"), (c["title"], c["url"])), jsonld=jsonld, priority=0.8,
                          search={"t": c["title"], "s": "Eye condition", "d": c.get("summary", ""), "b": c["body_md"], "k": " ".join(c.get("keywords", []))},
                          condition=c))
        # --- clinics ---
        self.add(Page("/qei-clinics/", "Our clinics and how to find us", "clinics-index.html",
                      description="QEI Clinic locations in Woolloongabba and Clayfield, Brisbane: addresses, opening hours, parking and public transport.",
                      section="Patients", breadcrumbs=self.crumbs(("Patients", "/patient-info/"), ("Our clinics", "/qei-clinics/")), priority=0.9,
                      jsonld=[self.ld_clinic(c) for c in cfg["clinics"]],
                      search={"t": "Our clinics and how to find us", "s": "Patients", "d": "Woolloongabba and Clayfield clinic locations, parking and transport", "b": " ".join(c["address_line1"] + " " + c["suburb"] for c in cfg["clinics"])}))
        for c in cfg["clinics"]:
            url = f"/qei-clinics/{c['slug']}/"
            self.add(Page(url, c["name"], "clinic.html", description=f"{c['name']} — {c['address_line1']}, {c['suburb']} {c['state']} {c['postcode']}. Opening hours, parking, public transport and contact details.",
                          section="Patients", image=c.get("photo"), breadcrumbs=self.crumbs(("Our clinics", "/qei-clinics/"), (c["name"], url)),
                          jsonld=[self.ld_clinic(c)], priority=0.8,
                          search={"t": c["name"], "s": "Clinic", "d": f"{c['address_line1']}, {c['suburb']}", "b": c["parking"] + " " + c["transport"] + " " + c["hours"]},
                          clinic=c))
        # --- news ---
        per_page = 24
        cats = {}
        for n in self.news:
            for cat in n["categories"]:
                cats.setdefault(cat, []).append(n)
        pages = [self.news[i:i + per_page] for i in range(0, len(self.news), per_page)] or [[]]
        for i, chunk in enumerate(pages, start=1):
            url = "/news/" if i == 1 else f"/news/page/{i}/"
            self.add(Page(url, "News" if i == 1 else f"News — page {i}", "news-index.html",
                          description="Latest news from the Queensland Eye Institute: clinical advances, research discoveries, education and Foundation updates.",
                          section="News", noindex=(i > 1), breadcrumbs=self.crumbs(("News", "/news/")), changefreq="weekly", priority=0.8 if i == 1 else 0.3,
                          search={"t": "News", "s": "News", "d": "Latest news from QEI", "b": ""} if i == 1 else None,
                          items=chunk, page_num=i, page_count=len(pages), categories=sorted(cats), active_category=None, events=self.events[:3]))
        for cat, items in sorted(cats.items()):
            url = f"/news/category/{self.category_slug(cat)}/"
            self.add(Page(url, f"{cat} news", "news-index.html", description=f"Queensland Eye Institute news in the category {cat}.", section="News",
                          breadcrumbs=self.crumbs(("News", "/news/"), (cat, url)), priority=0.4,
                          items=items, page_num=1, page_count=1, categories=sorted(cats), active_category=cat, events=[]))
        for idx, n in enumerate(self.news):
            newer = self.news[idx - 1] if idx > 0 else None
            older = self.news[idx + 1] if idx + 1 < len(self.news) else None
            self.add(Page(n["url"], n["title"], "news.html", description=n.get("excerpt", ""), section="News", lastmod=n.get("date"), image=n.get("hero"),
                          breadcrumbs=self.crumbs(("News", "/news/"), (n["title"], n["url"])), jsonld=[self.ld_article(n)], priority=0.5,
                          search={"t": n["title"], "s": "News", "d": n.get("excerpt", ""), "b": self.excerpt(n.get("body_html", ""), 700)},
                          item=n, newer=newer, older=older, related=[m for m in self.news if m is not n and set(m["categories"]) & set(n["categories"])][:3]))
        # --- patient stories ---
        self.add(Page("/qei-foundation/patient-stories/", "Patient stories", "stories-index.html",
                      description="Real stories from Queensland Eye Institute patients and supporters about living with eye disease and the difference research and care make.",
                      section="QEI Foundation", breadcrumbs=self.crumbs(("QEI Foundation", "/qei-foundation/"), ("Patient stories", "/qei-foundation/patient-stories/")), priority=0.6,
                      search={"t": "Patient stories", "s": "QEI Foundation", "d": "Stories from QEI patients", "b": " ".join(s["title"] for s in self.stories)}, items=self.stories))
        for idx, s in enumerate(self.stories):
            newer = self.stories[idx - 1] if idx > 0 else None
            older = self.stories[idx + 1] if idx + 1 < len(self.stories) else None
            self.add(Page(s["url"], s["title"], "story.html", description=s.get("excerpt", ""), section="Patient stories", lastmod=s.get("date"), image=s.get("hero"),
                          breadcrumbs=self.crumbs(("QEI Foundation", "/qei-foundation/"), ("Patient stories", "/qei-foundation/patient-stories/"), (s["title"], s["url"])),
                          jsonld=[self.ld_article(s, kind="Article")], priority=0.4,
                          search={"t": s["title"], "s": "Patient story", "d": s.get("excerpt", ""), "b": self.excerpt(s.get("body_html", ""), 600)},
                          item=s, newer=newer, older=older))
        # --- events ---
        self.add(Page("/events/", "Events", "events-index.html",
                      description="Education events, CPD evenings and community events hosted by the Queensland Eye Institute.",
                      section="News", breadcrumbs=self.crumbs(("News", "/news/"), ("Events", "/events/")), changefreq="weekly", priority=0.6,
                      search={"t": "Events", "s": "Events", "d": "QEI education and community events", "b": " ".join(e["title"] for e in self.events)}, items=self.events))
        for e in self.events:
            self.add(Page(e["url"], e["title"], "event.html", description=e.get("excerpt", ""), section="Events", lastmod=e.get("date"), image=e.get("hero"),
                          breadcrumbs=self.crumbs(("Events", "/events/"), (e["title"], e["url"])), jsonld=[self.ld_event(e)], priority=0.4,
                          search={"t": e["title"], "s": "Event", "d": e.get("excerpt", ""), "b": self.excerpt(e.get("body_html", "") + e.get("details_html", ""), 600)}, item=e))
        # --- people ---
        groups = [("our-board", "Our Board", "The QEIF Board brings together respected leaders with a diverse range of health, medical, business, finance and philanthropic experience."),
                  ("management", "Management", "Talented people join QEIF for the opportunity to apply their skills to the complex challenge of saving sight each and every day."),
                  ("ambassadors", "Ambassadors", "The Queensland Eye Institute is honoured to have the support of the following talented Ambassadors.")]
        self.add(Page("/qei-foundation/our-people/", "Our people", "people-index.html",
                      description="The Board, management and Ambassadors of the Queensland Eye Institute Foundation.", section="QEI Foundation",
                      breadcrumbs=self.crumbs(("QEI Foundation", "/qei-foundation/"), ("Our people", "/qei-foundation/our-people/")), priority=0.5,
                      search={"t": "Our people", "s": "QEI Foundation", "d": "Board, management and ambassadors", "b": " ".join(p["name"] for p in self.people)},
                      groups=[{"slug": g, "title": t, "intro": i, "people": [p for p in self.people if p["group"] == g]} for g, t, i in groups], show_all=True))
        for g, title, intro in groups:
            url = f"/qei-foundation/our-people/{g}/"
            self.add(Page(url, title, "people-index.html", description=intro, section="QEI Foundation",
                          breadcrumbs=self.crumbs(("QEI Foundation", "/qei-foundation/"), ("Our people", "/qei-foundation/our-people/"), (title, url)), priority=0.4,
                          groups=[{"slug": g, "title": title, "intro": intro, "people": [p for p in self.people if p["group"] == g]}], show_all=False))
        for p in self.people:
            gtitle = {g: t for g, t, _ in groups}[p["group"]]
            self.add(Page(p["url"], p["name"], "person.html", description=p.get("summary", ""), section="QEI Foundation", image=p.get("photo"),
                          breadcrumbs=self.crumbs(("Our people", "/qei-foundation/our-people/"), (gtitle, f"/qei-foundation/our-people/{p['group']}/"), (p["name"], p["url"])),
                          jsonld=[self.ld_person(p)], priority=0.3,
                          search={"t": p["name"], "s": gtitle, "d": p.get("role", ""), "b": self.excerpt(p.get("bio_html", ""), 500)}, person=p, back={"label": gtitle, "url": f"/qei-foundation/our-people/{p['group']}/"}))
        # --- researchers & groups ---
        self.add(Page("/research/researchers/", "Researchers", "researchers-index.html",
                      description="Queensland Eye Institute researchers and honorary scientists working to understand, detect and treat eye disease.", section="Research",
                      breadcrumbs=self.crumbs(("Research", "/research/"), ("Researchers", "/research/researchers/")), priority=0.6,
                      search={"t": "Researchers", "s": "Research", "d": "QEI research team", "b": " ".join(r["name"] for r in self.researchers)}, items=self.researchers))
        for r in self.researchers:
            self.add(Page(r["url"], r["name"], "person.html", description=r.get("summary", ""), section="Research", image=r.get("photo"),
                          breadcrumbs=self.crumbs(("Research", "/research/"), ("Researchers", "/research/researchers/"), (r["name"], r["url"])),
                          jsonld=[self.ld_person(r)], priority=0.4,
                          search={"t": r["name"], "s": "Researcher", "d": r.get("role", ""), "b": self.excerpt(r.get("bio_html", ""), 600)}, person=r, back={"label": "Researchers", "url": "/research/researchers/"}))
        for g in self.groups:
            self.add(Page(g["url"], g["title"], "group.html", description=g.get("summary", ""), section="Research",
                          breadcrumbs=self.crumbs(("Research", "/research/"), ("Research groups and publications", "/research/groups-publications/"), (g["title"], g["url"])), priority=0.5,
                          search={"t": g["title"], "s": "Research group", "d": g.get("summary", ""), "b": self.excerpt(g.get("body_html", ""), 600)}, group=g))
        # --- utility pages ---
        self.add(Page("/search/", "Search", "search.html", description="Search the Queensland Eye Institute website.", section="Search", noindex=True, priority=0.1,
                      breadcrumbs=self.crumbs(("Search", "/search/"))))
        self.add(Page("/sitemap/", "Sitemap", "sitemap.html", description="All pages on the Queensland Eye Institute website.", section="Sitemap", priority=0.2,
                      breadcrumbs=self.crumbs(("Sitemap", "/sitemap/"))))

    # ----- JSON-LD builders -----
    def ld_org(self) -> dict:
        cfg = self.config
        return {"@context": "https://schema.org", "@type": "MedicalOrganization", "@id": self.abs_url("/#organization"), "name": cfg["name"],
                "legalName": cfg["legal_name"], "url": self.abs_url("/"), "logo": self.abs_url("/assets/img/logo-512.png"), "telephone": cfg["phone_intl"],
                "email": cfg["email_reception"], "sameAs": [s["url"] for s in cfg["social"]],
                "address": {"@type": "PostalAddress", "streetAddress": cfg["clinics"][0]["address_line1"], "addressLocality": cfg["clinics"][0]["suburb"],
                            "addressRegion": cfg["clinics"][0]["state"], "postalCode": cfg["clinics"][0]["postcode"], "addressCountry": "AU"},
                "medicalSpecialty": "Ophthalmologic", "department": [self.ld_clinic(c) for c in cfg["clinics"]]}

    def ld_clinic(self, c: dict) -> dict:
        cfg = self.config
        return {"@context": "https://schema.org", "@type": "MedicalClinic", "name": c["name"], "url": self.abs_url(f"/qei-clinics/{c['slug']}/"),
                "telephone": cfg["phone_intl"], "email": cfg["email_reception"], "medicalSpecialty": "Ophthalmologic",
                "address": {"@type": "PostalAddress", "streetAddress": c["address_line1"], "addressLocality": c["suburb"], "addressRegion": c["state"], "postalCode": c["postcode"], "addressCountry": "AU"},
                "geo": {"@type": "GeoCoordinates", "latitude": c["lat"], "longitude": c["lng"]},
                "openingHoursSpecification": {"@type": "OpeningHoursSpecification", "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
                                              "opens": c["opening_hours_spec"].split(" ")[1].split("-")[0], "closes": c["opening_hours_spec"].split(" ")[1].split("-")[1]},
                "parentOrganization": {"@id": self.abs_url("/#organization")}}

    def ld_physician(self, d: dict) -> dict:
        photo = self.media.process(d.get("photo"), "portrait")
        out = {"@context": "https://schema.org", "@type": "Physician", "name": d["name"], "url": self.abs_url(d["url"]), "medicalSpecialty": "Ophthalmologic",
               "description": d.get("summary", ""), "jobTitle": d["role"], "worksFor": {"@id": self.abs_url("/#organization")},
               "hospitalAffiliation": {"@type": "MedicalOrganization", "name": self.config["name"]}}
        if photo:
            out["image"] = self.abs_url(photo["url"])
        if d.get("qualifications"):
            out["honorificSuffix"] = d["qualifications"]
        return out

    def ld_person(self, p: dict) -> dict:
        photo = self.media.process(p.get("photo"), "portrait")
        out = {"@context": "https://schema.org", "@type": "Person", "name": p["name"], "url": self.abs_url(p["url"]), "jobTitle": p.get("role", ""),
               "affiliation": {"@id": self.abs_url("/#organization")}}
        if photo:
            out["image"] = self.abs_url(photo["url"])
        return out

    def ld_condition(self, c: dict) -> dict:
        out = {"@context": "https://schema.org", "@type": "MedicalWebPage", "name": c["title"], "url": self.abs_url(c["url"]), "description": c.get("summary", ""),
               "about": {"@type": "MedicalCondition", "name": c["title"], "description": c.get("summary", "")},
               "audience": {"@type": "MedicalAudience", "audienceType": "Patient"}, "publisher": {"@id": self.abs_url("/#organization")}}
        if c.get("reviewed_on"):
            out["lastReviewed"] = str(c["reviewed_on"])
        if c.get("reviewed_by"):
            out["reviewedBy"] = {"@type": "Person", "name": c["reviewed_by"]}
        return out

    def ld_faq(self, faq: list) -> dict:
        return {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q["q"], "acceptedAnswer": {"@type": "Answer", "text": BeautifulSoup(render_markdown(q["a"]), "lxml").get_text(" ", strip=True)}} for q in faq]}

    def ld_article(self, n: dict, kind: str = "NewsArticle") -> dict:
        hero = self.media.process(n.get("hero"), "hero")
        out = {"@context": "https://schema.org", "@type": kind, "headline": n["title"], "url": self.abs_url(n["url"]), "description": n.get("excerpt", ""),
               "publisher": {"@id": self.abs_url("/#organization")}, "author": {"@type": "Organization", "name": self.config["name"]}, "mainEntityOfPage": self.abs_url(n["url"])}
        if n.get("date"):
            out["datePublished"] = str(n["date"])
            out["dateModified"] = str(n.get("modified") or n["date"])
        if hero:
            out["image"] = self.abs_url(hero["url"])
        return out

    def ld_event(self, e: dict) -> dict:
        out = {"@context": "https://schema.org", "@type": "Event", "name": e["title"], "url": self.abs_url(e["url"]), "description": e.get("excerpt", ""),
               "organizer": {"@id": self.abs_url("/#organization")}, "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode"}
        if e.get("date"):
            out["startDate"] = str(e["date"])
        if e.get("venue"):
            out["location"] = {"@type": "Place", "name": e["venue"]}
        return out

    # ----- rendering -----
    def render_all(self) -> None:
        global _current_url
        base_ld = self.ld_org()
        website_ld = {"@context": "https://schema.org", "@type": "WebSite", "name": self.config["name"], "url": self.abs_url("/"),
                      "potentialAction": {"@type": "SearchAction", "target": {"@type": "EntryPoint", "urlTemplate": self.abs_url("/search/?q={search_term_string}")}, "query-input": "required name=search_term_string"}}
        seen = set()
        for page in self.pages:
            if page.url in seen:
                warn(f"duplicate url {page.url}")
            seen.add(page.url)
            _current_url = page.url
            page.breadcrumbs = page.breadcrumbs or [{"label": "Home", "url": "/"}]
            crumbs_ld = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "name": b["label"], "item": self.abs_url(b["url"])} for i, b in enumerate(page.breadcrumbs)]}
            jsonld = list(page.jsonld) + [crumbs_ld]
            if page.url == "/":
                jsonld = [base_ld, website_ld] + jsonld
            og_image = None
            if page.image:
                info = self.media.process(page.image, "hero")
                if info:
                    og_image = self.abs_url(info["url"])
            if not og_image:
                og_image = self.abs_url("/assets/img/og-default.jpg")
            ctx = dict(page=page, jsonld=jsonld, og_image=og_image, canonical=self.abs_url(page.url),
                       doctors=self.doctors, conditions=self.conditions, news=self.news, stories=self.stories, events=self.events,
                       treatments=self.treatments, clinics=self.config["clinics"], researchers=self.researchers, groups=self.groups, people=self.people,
                       all_pages=self.pages, clean_html=self.clean_html, render_md=render_markdown)
            ctx.update(page.context)
            tpl = self.env.get_template(page.template)
            html_out = tpl.render(**ctx)
            dest = self.out / page.url.lstrip("/") / "index.html"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(html_out, encoding="utf-8")
        # 404
        # 404 pages are served for any missing path, so links must be absolute from the hosting base path
        _current_url = "/404.html"
        page = Page("/404.html", "Page not found", "404.html", description="The page you were looking for could not be found.", noindex=True)
        page.breadcrumbs = [{"label": "Home", "url": "/"}]
        self.env.globals["rel"] = lambda url: (self.base_path.rstrip("/") + url) if url and url.startswith("/") else url
        self.env.filters["rel"] = self.env.globals["rel"]
        (self.out / "404.html").write_text(self.env.get_template("404.html").render(page=page, jsonld=[], og_image=self.abs_url("/assets/img/og-default.jpg"), canonical=self.abs_url("/404.html"), doctors=self.doctors, conditions=self.conditions, base_path=self.base_path), encoding="utf-8")
        self.env.globals["rel"] = rel
        self.env.filters["rel"] = rel
        # redirects for old URLs
        for r in self.config.get("redirects", []):
            if r["from"] == r["to"]:
                continue
            _current_url = r["from"]
            dest = self.out / r["from"].lstrip("/") / "index.html"
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(self.env.get_template("redirect.html").render(target=r["to"], canonical=self.abs_url(r["to"])), encoding="utf-8")

    def write_support_files(self) -> None:
        cfg = self.config
        indexable = bool(cfg.get("indexable"))
        urls = [p for p in self.pages if not p.noindex]
        lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for p in urls:
            lines.append("  <url>")
            lines.append(f"    <loc>{html.escape(self.abs_url(p.url))}</loc>")
            if p.lastmod:
                lines.append(f"    <lastmod>{str(p.lastmod)[:10]}</lastmod>")
            lines.append(f"    <changefreq>{p.changefreq}</changefreq>")
            lines.append(f"    <priority>{p.priority:.1f}</priority>")
            lines.append("  </url>")
        lines.append("</urlset>")
        (self.out / "sitemap.xml").write_text("\n".join(lines) + "\n", encoding="utf-8")
        if indexable:
            robots = f"User-agent: *\nAllow: /\nDisallow: /search/\nSitemap: {self.abs_url('/sitemap.xml')}\n"
        else:
            robots = "# Preview build: search engines are blocked until launch. Set \"indexable\": true in content/site.json to publish.\nUser-agent: *\nDisallow: /\n"
        (self.out / "robots.txt").write_text(robots, encoding="utf-8")
        (self.out / ".nojekyll").write_text("", encoding="utf-8")
        manifest = {"name": cfg["name"], "short_name": cfg["short_name"], "start_url": "./", "display": "minimal-ui", "background_color": "#ffffff", "theme_color": "#00305d",
                    "icons": [{"src": "assets/img/icon-192.png", "sizes": "192x192", "type": "image/png"}, {"src": "assets/img/logo-512.png", "sizes": "512x512", "type": "image/png"}]}
        (self.out / "manifest.webmanifest").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        # search index
        index = []
        for p in self.pages:
            if not p.search or p.noindex:
                continue
            s = p.search
            body = BeautifulSoup(render_markdown(s.get("b", "")) if s.get("b") else "", "lxml").get_text(" ", strip=True)
            body = re.sub(r"\s+", " ", body)[:700]
            index.append({"t": s["t"], "u": p.url, "s": s.get("s", ""), "d": (s.get("d") or "")[:220], "b": body, "k": s.get("k", "")})
        (self.out / "search-index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        # security/hosting hints
        (self.out / "_headers").write_text("/*\n  X-Content-Type-Options: nosniff\n  X-Frame-Options: SAMEORIGIN\n  Referrer-Policy: strict-origin-when-cross-origin\n  Permissions-Policy: camera=(), microphone=(), geolocation=()\n", encoding="utf-8")

    def copy_assets(self) -> None:
        dest = self.out / "assets"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(ASSETS, dest)
        # default social image is source-controlled; generate it once if it is ever missing
        og = ASSETS / "img" / "og-default.jpg"
        if not og.exists():
            self.make_og_image(og)
            shutil.copyfile(og, dest / "img" / "og-default.jpg")

    def make_og_image(self, dest: Path) -> None:
        try:
            from PIL import ImageDraw, ImageFont
            im = Image.new("RGB", (1200, 630), "#00305d")
            logo = Image.open(ASSETS / "img" / "logo-512.png").convert("RGBA").resize((260, 260), Image.LANCZOS)
            im.paste(logo, (90, 185), logo)
            draw = ImageDraw.Draw(im)
            try:
                font_big = ImageFont.truetype(str(MIRROR / "wp-content/themes/qei/fonts/worksans/WorkSans-SemiBold.ttf"), 64)
                font_small = ImageFont.truetype(str(MIRROR / "wp-content/themes/qei/fonts/worksans/WorkSans-Regular.ttf"), 34)
            except Exception:
                font_big = ImageFont.load_default()
                font_small = ImageFont.load_default()
            draw.text((400, 220), "Queensland", fill="white", font=font_big)
            draw.text((400, 295), "Eye Institute", fill="white", font=font_big)
            draw.text((400, 395), "Saving sight every day", fill="#cde6ef", font=font_small)
            im.save(dest, "JPEG", quality=88)
        except Exception as exc:  # pragma: no cover
            warn(f"could not create og image: {exc}")

    def build(self, clean: bool = True) -> None:
        if clean and self.out.exists():
            for child in self.out.iterdir():
                if child.name in (".git", "media"):
                    continue
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
        self.out.mkdir(parents=True, exist_ok=True)
        self.load()
        self.copy_assets()
        self.build_pages()
        self.render_all()
        self.write_support_files()
        self.media.prune()
        self.media.save_manifest()
        if self.verbose:
            print(f"Built {len(self.pages)} pages into {self.out}")
            if _warnings:
                print(f"{len(_warnings)} warning(s)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(ROOT / "web"))
    ap.add_argument("--check", action="store_true", help="build into a temporary directory only")
    ap.add_argument("--base-path", default="/", help="hosting path prefix used only by 404.html (for example /QEIwebpage/)")
    args = ap.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            s = Site(Path(tmp)); s.base_path = args.base_path; s.build(clean=False)
        return 0
    s = Site(Path(args.out)); s.base_path = args.base_path; s.build()
    return 0


if __name__ == "__main__":
    sys.exit(main())
