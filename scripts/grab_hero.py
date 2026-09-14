# -*- coding: utf-8 -*-
"""
grab_hero.py —— 从公开图源为单部影片抓「高清横版主视觉」+ 高清竖版海报
=====================================================================
移植自 FilmCollector tools/grab_posters.py（Wikimedia 源，零 Key）。
质量门槛：
  - 长边 < 1000px 判为缩略图丢弃；文件名/描述含 thumb/banner/logo/水印 跳过
  - 横版主视觉(slide)：宽>=1280 且 宽高比>=1.35
  - 竖版海报(img)：长边>=1000
输出：{out_dir}/<标题>/ 下落盘原始大图 + manifest.json，由 run_cycle.py 二次筛选入库。
"""
import os, re, json, time, struct, urllib.parse
import requests

UA = "FilmCollector-PosterGrabber/1.0 (personal media library tool)"
TIMEOUT = 20

def image_dims(data):
    if not data or len(data) < 24:
        return (0, 0)
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", data[16:24])
        return (w, h)
    if data[:2] == b"\xff\xd8":
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            m = data[i + 1]
            if m in (0xC0, 0xC1, 0xC2, 0xC3):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return (w, h)
            if m in (0xD8, 0xD9) or 0xD0 <= m <= 0xD7:
                i += 2
                continue
            ln = struct.unpack(">H", data[i + 2:i + 4])[0]
            i += 2 + ln
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        try:
            if data[12:16] == b"VP8X":
                w = 1 + int.from_bytes(data[24:27], "little")
                h = 1 + int.from_bytes(data[27:30], "little")
                return (w, h)
        except Exception:
            pass
    return (0, 0)

def _get_json(url, params=None, headers=None):
    try:
        r = requests.get(url, params=params, headers=headers or {"User-Agent": UA},
                         timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None

def _get_bytes(url, referer=None):
    try:
        h = {"User-Agent": UA}
        if referer:
            h["Referer"] = referer
        r = requests.get(url, headers=h, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.content
    except Exception:
        pass
    return None

THUMB_RE = re.compile(r"thumb|/1\d{2}px-|/2\d{2}px-|/3\d{2}px-|\.svg|icon", re.I)
WM_RE = re.compile(r"banner|logo|watermark|screenshot|poster_art|title_card|水印|贴纸|台标", re.I)

def looks_bad(title, desc, url):
    return bool(THUMB_RE.search(url or "") or WM_RE.search(title or "") or WM_RE.search(desc or ""))

def search_wikimedia(film, max_n=20):
    """Wikimedia Commons 按片名搜图，返回候选 [{url,title,desc,width,height}]。"""
    api = "https://commons.wikimedia.org/w/api.php"
    out, seen = [], set()
    for term in ('"%s" poster' % film, '"%s" film' % film, film):
        data = _get_json(api, params={
            "action": "query", "format": "json", "generator": "search",
            "gsrsearch": term, "gsrnamespace": 6, "gsrlimit": max_n,
            "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": 0,
        }, headers={"User-Agent": UA})
        pages = ((data or {}).get("query") or {}).get("pages") or {}
        for p in pages.values():
            ii = (p.get("imageinfo") or [{}])[0]
            url = ii.get("url") or ""
            if not url.lower().endswith((".jpg", ".jpeg", ".png")) or url in seen:
                continue
            em = ii.get("extmetadata") or {}
            desc = ((em.get("ImageDescription") or {}).get("value") or "")[:300]
            seen.add(url)
            out.append({"url": url, "title": p.get("title", ""), "desc": desc,
                        "width": ii.get("width", 0), "height": ii.get("height", 0),
                        "mime": ii.get("mime", "image/jpeg"), "source": "wikimedia"})
        if len(out) >= max_n:
            break
    return out[:max_n]

def grab_one(film, out_dir, max_n=20):
    """抓一部影片的高清图。返回 (backdrop_path, poster_path) 或 (None, None)。"""
    film_dir = os.path.join(out_dir, re.sub(r'[\\/:*?"<>|]', "_", film).strip() or "untitled")
    os.makedirs(film_dir, exist_ok=True)
    bd, poster = None, None
    cands = []
    tmdb_key = os.environ.get("TMDB_API_KEY", "")
    if tmdb_key:
        # TMDB 官方图优先（backdrops 1920x1080，最优质横版主视觉）
        cands += [c for c in search_tmdb(film, tmdb_key, max_n)
                  if not looks_bad(c["title"], c["desc"], c["title"])]
    cands += [c for c in search_wikimedia(film, max_n)
              if not looks_bad(c["title"], c["desc"], c["url"])]
    saved = []
    for c in cands:
        if len(saved) >= 8:
            break
        data = _get_bytes(c["url"], referer="https://commons.wikimedia.org/")
        if not data:
            continue
        w, h = image_dims(data)
        if max(w, h) < 1000:          # 缩略图
            continue
        ext = "png" if c["url"].lower().endswith(".png") else "jpg"
        fname = "%dx%d_%s.%s" % (w, h, c["source"], ext)
        path = os.path.join(film_dir, fname)
        with open(path, "wb") as f:
            f.write(data)
        c2 = dict(c); c2.update({"path": path, "width": w, "height": h})
        saved.append(c2)
        ratio = w / float(h) if h else 0
        if bd is None and w >= 1280 and ratio >= 1.35:
            bd = path                  # 横版主视觉
        if poster is None and max(w, h) >= 1000 and ratio < 1.35:
            poster = path              # 竖版高清海报
    with open(os.path.join(film_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump({"film": film, "backdrop": bd, "poster": poster,
                   "generated": time.strftime("%Y-%m-%d %H:%M:%S"), "images": saved},
                  f, ensure_ascii=False, indent=2)
    return bd, poster

if __name__ == "__main__":
    import sys
    for film in sys.argv[1:]:
        b, p = grab_one(film, os.path.join(os.path.dirname(__file__), "..", "tmp_grab"))
        print(film, "->", "backdrop" if b else "-", "/", "poster" if p else "-")
