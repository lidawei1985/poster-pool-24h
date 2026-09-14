# -*- coding: utf-8 -*-
"""
run_cycle.py —— poster-pool-24h 单轮采集（GitHub Actions 每 2 小时跑一次）
=========================================================================
流程：
  1. 从 sources.json 拉取各片源目录（appleCMS ac=detail，页数/耗时双预算）
  2. 用 category_filters（与 APK 端 Java 逐字一致）把影片分流到 normal/child/adult 三库
  3. 质量优先下载竖版海报（<600px 丢弃，压到 900 宽 q82）
  4. 每轮小批量尝试抓「高清横版主视觉」（Wikimedia，宽>=1280 比例>=1.35，儿童库优先）
  5. 导出 feeds/feed.<mode>.json（jsDelivr 绝对 URL， heroes 只收真横版）
设计约束：
  - 三库物理分离：pools/<mode>/img、pools/<mode>/slide，互不混用
  - 图片 md5(归一化片名).jpg —— 与本机 poster-warehouse / APK 命名规则一致
  - 全部幂等：已存在的图不重抓；hero 失败 7 天后才重试
  - 仓库体积护栏：pools 总量 > 3.2GB 停止新增（仍会刷新 feed）
"""
import os, sys, re, json, time, hashlib, argparse
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import category_filters as cf
import requests

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCES_FILE = os.path.join(BASE, "sources.json")
STATE_FILE = os.path.join(BASE, "state", "state.json")
POOLS = {m: os.path.join(BASE, "pools", m) for m in ("normal", "child", "adult")}
FEEDS = os.path.join(BASE, "feeds")
TMP_GRAB = os.path.join(BASE, "tmp_grab")
HERO_RETRY_DAYS = 7
POOL_MAX_BYTES = 3.2 * 1024**3

UA = "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 Chrome/108 Mobile Safari/537.36"
for d in list(POOLS.values()) + [FEEDS, os.path.dirname(STATE_FILE), TMP_GRAB]:
    for sub in ("img", "slide"):
        os.makedirs(os.path.join(d, sub), exist_ok=True)


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def md5name(name):
    s = re.sub(r"\s+", "", name or "").lower()
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def jsdelivr_base():
    """GitHub Actions 里自动取 GITHUB_REPOSITORY；本地用 POOL_REPO 环境变量。"""
    repo = os.environ.get("GITHUB_REPOSITORY") or os.environ.get("POOL_REPO") or "OWNER/REPO"
    return "https://cdn.jsdelivr.net/gh/%s@main" % repo


def load_sources():
    with open(SOURCES_FILE, encoding="utf-8") as f:
        return json.load(f)["sources"]


def parse_time(v):
    """vod_time 可能是秒级时间戳或 'YYYY-mm-dd HH:MM:SS'，统一转秒。"""
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        try:
            return int(time.mktime(time.strptime((v or "")[:19], "%Y-%m-%d %H:%M:%S")))
        except Exception:
            return 0


def fetch_source(src, pages, deadline):
    """拉一个源的分页目录，返回 [(title, category, pic, time, scope)]。"""
    out = []
    sess = requests.Session()
    sess.headers.update({"User-Agent": UA})
    for p in range(1, pages + 1):
        if time.time() > deadline:
            break
        try:
            r = sess.get(src["api"].format(p=p), timeout=15)
            jobs = (r.json().get("list") or []) if r.status_code == 200 else []
        except Exception:
            break
        if not jobs:
            break
        for v in jobs:
            name = (v.get("vod_name") or "").strip()
            if not name:
                continue
            out.append({"title": name,
                        "category": v.get("type_name") or "",
                        "pic": v.get("vod_pic") or "",
                        "time": parse_time(v.get("vod_time"))})
        time.sleep(0.3)
    return out


def classify_bucket(category):
    """按 APK 真值分流：返回 'normal' | 'child' | 'adult' | None。
    普通源影片：先判儿童白名单（动画），再判 normal；成人源只进成人库。"""
    if cf.classify_for_scope("child", category):
        return "child"
    if cf.classify_for_scope("normal", category):
        return "normal"
    return None


def pool_bytes():
    total = 0
    for m in POOLS:
        for root, _, files in os.walk(POOLS[m]):
            for fn in files:
                try:
                    total += os.path.getsize(os.path.join(root, fn))
                except OSError:
                    pass
    return total


def shrink_to(data, max_w, quality=82):
    """PIL 压缩：超过 max_w 等比缩小，转 JPEG。失败返回 None。"""
    try:
        import io
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        if im.mode != "RGB":
            im = im.convert("RGB")
        if im.width > max_w:
            im = im.resize((max_w, int(im.height * max_w / im.width)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True)
        return buf.getvalue()
    except Exception:
        return None


def img_dims(data):
    try:
        import io
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        return im.width, im.height
    except Exception:
        return 0, 0


def dl_pool_image(url, mode, md5, kind, max_w):
    """下载并按质量门槛入库 pools/<mode>/<kind>/<md5>.jpg。返回 bool。"""
    dst = os.path.join(POOLS[mode], kind, md5 + ".jpg")
    if os.path.exists(dst):
        return True
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        if r.status_code != 200 or len(r.content) < 8000:
            return False
    except Exception:
        return False
    w, h = img_dims(r.content)
    if max(w, h) < 600:                       # 质量门槛：600px 以下视为劣图
        return False
    data = shrink_to(r.content, max_w)
    if not data:
        return False
    with open(dst, "wb") as f:
        f.write(data)
    return True


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"hero_fail": {}}


def save_state(st):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def list_pool(mode, kind):
    d = os.path.join(POOLS[mode], kind)
    return {fn[:-4] for fn in os.listdir(d) if fn.endswith(".jpg")}


def hero_batch(titles_by_mode, have_slide, st, batch):
    """挑 hero 抓取候选：无 slide、距上次失败>7天；儿童库优先（最稀缺）。"""
    now = time.time()
    order = ["child", "normal"]                # adult 无公开图源，不抓横版
    cands = []
    for m in order:
        for t, ts in sorted(titles_by_mode[m], key=lambda x: -x[1]):
            h = md5name(t)
            if h in have_slide[m]:
                continue
            fail = st["hero_fail"].get(h)
            if fail and now - fail < HERO_RETRY_DAYS * 86400:
                continue
            cands.append((m, t))
            if len(cands) >= batch:
                return cands
    return cands


def export_feeds(catalog_by_mode):
    """按库导出 feed.<mode>.json（URL 为 jsDelivr 绝对地址）。"""
    base = jsdelivr_base()
    CAT = {"normal": cf.NORMAL_AGG_NAME, "child": cf.CHILD_AGG_NAME, "adult": cf.ADULT_AGG_NAME}
    for mode, items in catalog_by_mode.items():
        have_img, have_slide = list_pool(mode, "img"), list_pool(mode, "slide")
        out = []
        for it in (items.values() if isinstance(items, dict) else items):
            h = md5name(it["title"])
            agg = it.get("agg") or ("", "")
            rec = {"name": it["title"],
                   "originalCategoryName": it["category"],
                   "aggregateCategoryId": agg[0],
                   "aggregateCategoryName": agg[1],
                   "vodTime": it["time"],
                   "appMode": mode if mode != "normal" else "normal"}
            if h in have_img:
                rec["cover"] = "%s/pools/%s/img/%s.jpg" % (base, mode, h)
                rec["playUrl"] = it.get("play", "")
                out.append(rec)
        heroes = []
        for rec in out:
            h = md5name(rec["name"])
            if h in have_slide:
                rec["backdrop"] = "%s/pools/%s/slide/%s.jpg" % (base, mode, h)
                rec["hero"] = rec["backdrop"]
                heroes.append({"title": rec["name"], "backdrop": rec["backdrop"],
                               "poster": rec.get("cover", "")})
        heroes.sort(key=lambda x: -next(i["vodTime"] for i in out if i["name"] == x["title"]))
        feed = {"meta": {"mode": mode, "count": len(out), "heroCount": len(heroes),
                         "generated": time.strftime("%Y-%m-%d %H:%M:%S")},
                "items": out[:5000], "heroes": heroes[:8]}
        path = os.path.join(FEEDS, "feed.%s.json" % mode)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(feed, f, ensure_ascii=False)
        log("feed.%s.json: items=%d heroes=%d" % (mode, len(out), len(heroes)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=6, help="每源本轮抓取页数")
    ap.add_argument("--img-batch", type=int, default=120, help="本轮最多新下载海报数")
    ap.add_argument("--hero-batch", type=int, default=15, help="本轮横版主视觉抓取尝试数")
    ap.add_argument("--minutes", type=int, default=38, help="本轮总耗时预算(分钟)")
    ap.add_argument("--hero", default="1", help="是否抓横版(0/1)")
    args = ap.parse_args()
    deadline = time.time() + args.minutes * 60

    st = load_state()
    sources = load_sources()
    catalog = {m: {} for m in ("normal", "child", "adult")}   # title -> item（同题去重，时间取新）
    for src in sources:
        if not src.get("enabled", True) or time.time() > deadline:
            continue
        rows = fetch_source(src, args.pages, deadline)
        n = 0
        for it in rows:
            if src.get("scope") == "adult":
                mode = "adult" if cf.classify_for_scope("adult", it["category"]) else None
            else:
                mode = classify_bucket(it["category"])
            if not mode:
                continue
            agg = cf.classify_for_scope("child" if mode == "child" else
                                        ("adult" if mode == "adult" else "normal"),
                                        it["category"])
            it["agg"], it["mode"] = agg, mode
            old = catalog[mode].get(it["title"])
            if old is None or it["time"] > old["time"]:
                catalog[mode][it["title"]] = it
            n += 1
        log("source %s(%s): rows=%d scoped=%d" % (src["name"], src["scope"], len(rows), n))

    # ---- 海报下载（质量优先，预算内按时间新的优先） ----
    downloaded = 0
    for mode in ("normal", "child", "adult"):
        have = list_pool(mode, "img")
        cand = sorted(catalog[mode].values(), key=lambda x: -x["time"])
        attempts = 0
        for it in cand:
            if (downloaded >= args.img_batch or attempts >= args.img_batch * 8
                    or time.time() > deadline or pool_bytes() > POOL_MAX_BYTES):
                break
            h = md5name(it["title"])
            if h in have or not it.get("pic"):
                continue
            attempts += 1
            if dl_pool_image(it["pic"], mode, h, "img", max_w=900):
                downloaded += 1
        log("pool %s img total=%d (+%d this round)" % (mode, len(list_pool(mode, "img")), downloaded))

    # ---- 横版主视觉小批量尝试 ----
    if args.hero != "0":
        titles_by_mode = {m: [(t, it["time"]) for t, it in catalog[m].items()] for m in catalog}
        have_slide = {m: list_pool(m, "slide") for m in POOLS}
        from grab_hero import grab_one
        done = 0
        for mode, title in hero_batch(titles_by_mode, have_slide, st, args.hero_batch):
            if time.time() > deadline:
                break
            try:
                bd, poster = grab_one(title, TMP_GRAB, max_n=16)
            except Exception as e:
                log("hero %s err: %r" % (title, e)); continue
            h = md5name(title)
            if bd:
                data = open(bd, "rb").read()
                if img_dims(data)[0] >= 1280:
                    data = shrink_to(data, 1920) or data
                    with open(os.path.join(POOLS[mode], "slide", h + ".jpg"), "wb") as f:
                        f.write(data)
                    done += 1
                    log("HERO [%s] %s OK" % (mode, title))
                st["hero_fail"].pop(h, None)
            else:
                st["hero_fail"][h] = time.time()
            st["hero_fail"] = {k: v for k, v in st["hero_fail"].items()
                               if time.time() - v < 30 * 86400}   # 状态瘦身
            for d in (bd, poster):
                if d and os.path.exists(d):
                    try: os.remove(d)
                    except OSError: pass
        log("hero done=%d" % done)

    save_state(st)
    export_feeds(catalog)
    log("cycle complete")


if __name__ == "__main__":
    main()
