# -*- coding: utf-8 -*-
"""
sync_cloud_slides.py —— 把 GitHub poster-pool-24h 云端图库的横版主视觉(slide)
增量同步到本机 poster-warehouse/slide/，让三端 APK 的 HERO 立即吃到云端新图。
说明：
  - 两边文件名同为 md5(去空白小写片名).jpg，同名即同图，只补缺不覆盖。
  - 走 api.github.com Contents API（沙箱代理放行），不需要 git 隧道。
  - 幂等：已存在跳过；失败不影响已有文件。
用法：python sync_cloud_slides.py [repo] [本地slide目录]
"""
import os, sys, json, base64, subprocess, urllib.request

REPO = sys.argv[1] if len(sys.argv) > 1 else "lidawei1985/poster-pool-24h"
DST = sys.argv[2] if len(sys.argv) > 2 else r"C:\Users\sbqqq\WorkBuddy\2026-08-11-16-03-43\poster-warehouse\slide"

def cred_token():
    cred = subprocess.run(["git", "credential", "fill"],
                          input="protocol=https\nhost=github.com\n\n",
                          capture_output=True, text=True).stdout
    for line in cred.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    return ""

TOKEN = cred_token()
proxy = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": proxy, "https": proxy}) if proxy else {})
HDR = {"Authorization": "token " + TOKEN, "User-Agent": "pool-sync"} if TOKEN else {"User-Agent": "pool-sync"}

def api(url):
    req = urllib.request.Request(url, headers=HDR)
    with opener.open(req, timeout=60) as r:
        return json.loads(r.read())

os.makedirs(DST, exist_ok=True)
local = {fn[:-4] for fn in os.listdir(DST) if fn.endswith(".jpg")}
added = skipped = failed = 0
for mode in ("child", "normal", "adult"):   # child 最稀缺，优先同步
    try:
        items = api("https://api.github.com/repos/%s/contents/pools/%s/slide?ref=main" % (REPO, mode))
    except Exception as e:
        print("list %s failed: %r" % (mode, e)); failed += 1
        continue
    for it in items:
        name = it.get("name", "")
        if not name.endswith(".jpg"):
            continue
        md5 = name[:-4]
        if md5 in local:
            skipped += 1
            continue
        try:
            meta = api(it["url"])           # 带 base64 content 的完整对象
            data = base64.b64decode(meta["content"])
            if len(data) > 20000:           # 横版大图不可能只有 20K
                with open(os.path.join(DST, name), "wb") as f:
                    f.write(data)
                local.add(md5)
                added += 1
                print("added [%s] %s (%dKB)" % (mode, name, len(data) // 1024))
        except Exception as e:
            failed += 1
            print("dl %s failed: %r" % (name, e))
print("DONE added=%d skipped=%d failed=%d local_total=%d" % (added, skipped, failed, len(local)))
