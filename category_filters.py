# -*- coding: utf-8 -*-
"""
三 APK 隔离/分类归一化的 Python 真值移植（与 APK 端 Java 逐字一致）。

来源（生产代码，非二手摘要）：
  yinghuo-tv-apk  .../data/{CategoryNormalizer,NormalFilter}.java
  adult19-tv-apk  .../data/{CategoryNormalizer,AdultFilter}.java
  zhuiyi-tv-apk   .../data/{CategoryNormalizer,ChildFilter}.java

铁律（与 APK 一致）：
  - 原始分类永远不丢：feed 仍带 originalCategoryName。
  - 源不是内容类型：仅按 originalCategoryName 判定 scope 归属。
  - 隔离：normal 拒绝成人/体育；adult 拒绝体育/儿童且普通影视映射 x_* 被拒；
         child 仅白名单（无动态兜底），普通动漫/影视一律拒绝。
  - 本模块只做「判定 + 归一化」，不抓取、不写文件。
"""

import re

# ----------------------------------------------------------------------------
# 通用工具
# ----------------------------------------------------------------------------
def _safe_id(s):
    """与 Java safeId 一致：仅保留 a-z A-Z 0-9 与 CJK，其余转 '_'。"""
    out = []
    for ch in (s or ""):
        o = ord(ch)
        if ('a' <= ch <= 'z') or ('A' <= ch <= 'Z') or ('0' <= ch <= '9') \
           or (0x4E00 <= o <= 0x9FA5):
            out.append(ch)
        else:
            out.append('_')
    return "".join(out) if out else "other"


# ============================================================================
# NORMAL（星幕）—— D1
# ============================================================================
NORMAL_AGG_NAME = {}
NORMAL_MAP = {}

def _n_reg(i, name, parent):
    NORMAL_AGG_NAME[i] = parent + " / " + name
def _n_map(raw, agg):
    NORMAL_MAP[raw] = agg

# 电影
for _i, _n in [("movie_action","动作片"),("movie_comedy","喜剧片"),("movie_love","爱情片"),
               ("movie_scifi","科幻片"),("movie_horror","恐怖片"),("movie_story","剧情片"),
               ("movie_war","战争片"),("movie_shaoshi","邵氏电影"),("movie_4k","4K电影"),
               ("movie_netflix","Netflix电影")]:
    _n_reg(_i, _n, "电影")
for _r, _i in [("电影","movie_action"),("院线","movie_action"),("剧情片","movie_story"),
               ("喜剧片","movie_comedy"),("动作片","movie_action"),("科幻片","movie_scifi"),
               ("恐怖片","movie_horror"),("爱情片","movie_love"),("战争片","movie_war"),
               ("悬疑片","movie_story"),("惊悚片","movie_horror"),("犯罪片","movie_story"),
               ("动画片","anime_cartoon"),("动画电影","anime_cartoon"),("4K电影","movie_4k"),
               ("Netflix电影","movie_netflix"),("邵氏电影","movie_shaoshi"),("重生民国","movie_story"),
               ("奇幻片","movie_scifi")]:
    _n_map(_r, _i)
# 电视剧
for _i, _n in [("tv_domestic","国产剧"),("tv_euro","欧美剧"),("tv_korea","韩剧"),("tv_japan","日剧"),
               ("tv_hk","港剧"),("tv_tw","台剧"),("tv_thai","泰剧"),("tv_overseas","海外剧"),
               ("tv_netflix","Netflix自制剧")]:
    _n_reg(_i, _n, "电视剧")
for _r, _i in [("电视剧","tv_domestic"),("剧集","tv_domestic"),("连续剧","tv_domestic"),
               ("国产剧","tv_domestic"),("港剧","tv_hk"),("港台剧","tv_hk"),("台湾剧","tv_tw"),
               ("台剧","tv_tw"),("韩剧","tv_korea"),("韩国剧","tv_korea"),("日剧","tv_japan"),
               ("日本剧","tv_japan"),("欧美剧","tv_euro"),("海外剧","tv_overseas"),("泰剧","tv_thai"),
               ("美剧","tv_euro"),("英剧","tv_euro"),("网络剧","tv_domestic"),("情景剧","tv_domestic"),
               ("泰国剧","tv_thai"),("大陆剧","tv_domestic"),("香港剧","tv_hk"),("港澳剧","tv_hk")]:
    _n_map(_r, _i)
# 动漫
for _i, _n in [("anime_guoman","国产动漫"),("anime_rijk","日韩动漫"),("anime_oumei","欧美动漫"),
               ("anime_cartoon","动画片"),("anime_gangtai","港台动漫"),("anime_overseas","海外动漫"),
               ("anime_audio","有声动漫"),("anime_manga","漫剧")]:
    _n_reg(_i, _n, "动漫")
for _r, _i in [("动漫","anime_guoman"),("动画","anime_cartoon"),("番剧","anime_rijk"),
               ("国产动漫","anime_guoman"),("日韩动漫","anime_rijk"),("日本动漫","anime_rijk"),
               ("欧美动漫","anime_oumei"),("港台动漫","anime_gangtai"),("海外动漫","anime_overseas"),
               ("有声动漫","anime_audio"),("漫剧","anime_manga"),("中国动漫","anime_guoman"),
               ("AI漫剧","anime_manga")]:
    _n_map(_r, _i)
# 综艺
for _i, _n in [("variety_mainland","大陆综艺"),("variety_rijk","日韩综艺"),("variety_gangtai","港台综艺"),
               ("variety_oumei","欧美综艺")]:
    _n_reg(_i, _n, "综艺")
for _r, _i in [("综艺","variety_mainland"),("真人秀","variety_mainland"),("大陆综艺","variety_mainland"),
               ("港台综艺","variety_gangtai"),("日韩综艺","variety_rijk"),("欧美综艺","variety_oumei")]:
    _n_map(_r, _i)
# 纪录片
_n_reg("doc","纪录片","纪录片")
for _r in ("纪录片","纪实","记录片"):
    _n_map(_r, "doc")
# 短剧
for _i, _n in [("short_love","女频恋爱"),("short_reverse","反转爽剧"),("short_xianxia","古装仙侠"),
               ("short_time","年代穿越"),("short_suspense","脑洞悬疑"),("short_modern","现代都市"),
               ("short_cool","爽文短剧"),("short_edge","擦边短剧")]:
    _n_reg(_i, _n, "短剧")
for _r, _i in [("短剧","short_love"),("微短剧","short_love"),("女频恋爱","short_love"),
               ("反转爽剧","short_reverse"),("古装仙侠","short_xianxia"),("年代穿越","short_time"),
               ("脑洞悬疑","short_suspense"),("现代都市","short_modern"),("爽文短剧","short_cool"),
               ("擦边短剧","short_edge"),("穿越年代","short_time")]:
    _n_map(_r, _i)
# 其他
_n_reg("other_explain","影视解说","其他"); _n_reg("other_trailer","预告片","其他")
_n_map("电影解说","other_explain"); _n_map("影视解说","other_explain"); _n_map("预告片","other_trailer")

NORMAL_ADULT_KW = ["伦理","三级","两性","情色","色情","成人","18禁","18+","激情","床戏","写真","裸"]
NORMAL_SPORTS_KW = ["篮球","足球","网球","斯诺克","台球","乒乓球","排球","田径","游泳","橄榄球",
                    "赛事","比赛","体育","世界杯","NBA","F1","直播","新闻","综艺盛典","演唱会"]

def normal_is_adult(cat):
    if not cat: return False
    return any(k in cat for k in NORMAL_ADULT_KW)

def normal_is_sports(cat):
    if not cat: return False
    return any(k in cat for k in NORMAL_SPORTS_KW)

def normal_classify(raw):
    """返回 (aggId, aggName)；未知分类按关键词动态兜底，绝不返回 None。"""
    if raw:
        known = NORMAL_MAP.get(raw.strip())
        if known:
            return known, NORMAL_AGG_NAME[known]
    name = (raw.strip() if raw and raw.strip() else "其他")
    if "综艺" in name or "秀" in name: parent, pre = "综艺", "variety_"
    elif "动漫" in name or "动画" in name or "漫" in name: parent, pre = "动漫", "anime_"
    elif "纪录" in name: parent, pre = "纪录片", "doc_"
    elif ("短剧" in name or "微短剧" in name or "女频" in name
          or "爽文" in name or "爽剧" in name): parent, pre = "短剧", "short_"
    elif "剧" in name: parent, pre = "电视剧", "tv_"
    else: parent, pre = "电影", "movie_"
    _id = pre + _safe_id(name)
    return _id, parent + " / " + name


# ============================================================================
# ADULT（夜航）—— D2
# ============================================================================
ADULT_AGG_NAME = {}
ADULT_MAP = {}

def _a_reg(i, name):
    ADULT_AGG_NAME[i] = name
def _a_map(raw, agg):
    ADULT_MAP[raw] = agg

for _i, _n in [("ethics","伦理"),("hk3","港台三级"),("kr_ethics","韩国伦理"),
               ("west_ethics","西方伦理"),("jp_ethics","日本伦理"),("edu","两性课堂"),
               ("photo","写真热舞")]:
    _a_reg(_i, _n)
# 伦理
for _r in ["伦理","伦理三级","亚洲情色","中文字幕","无码专区","制服丝袜","巨乳美乳","群交淫乱",
           "少女萝莉","女同性恋","强奸乱伦","国产情色","欧美情色","日本无码","日本有码",
           "熟女人妻","人妻","处女","重口色情","制服诱惑"]:
    _a_map(_r, "ethics")
_a_map("港台三级","hk3")
_a_map("韩国伦理","kr_ethics")
_a_map("西方伦理","west_ethics"); _a_map("欧美性爱","west_ethics")
_a_map("日本伦理","jp_ethics")
_a_map("两性课堂","edu"); _a_map("卡通动漫","edu")
_a_map("写真热舞","photo"); _a_map("写真","photo"); _a_map("国产自拍","photo")
_a_map("偷拍自拍","photo"); _a_map("国产裸聊","photo"); _a_map("国产盗摄","photo")
_a_map("模特","photo"); _a_map("自拍","photo"); _a_map("网友自拍","photo"); _a_map("街拍","photo")
_a_map("私房","photo"); _a_map("网红","photo")
# 普通影视（成人源中若出现 → x_* → 被拒）
for _r, _i in [("电影","x_movie"),("电视剧","x_tv"),("动漫","x_anime"),("综艺","x_variety"),
               ("国产剧","x_tv"),("港剧","x_tv"),("韩剧","x_tv"),("日剧","x_tv"),("欧美剧","x_tv"),
               ("国产动漫","x_anime"),("日韩动漫","x_anime"),("欧美动漫","x_anime"),
               ("大陆综艺","x_variety"),("港台综艺","x_variety")]:
    _a_map(_r, _i)

ADULT_ADULT_AGGS = {"ethics","hk3","kr_ethics","west_ethics","jp_ethics","edu","photo"}
ADULT_SPORTS_KW = ["篮球","足球","网球","斯诺克","台球","乒乓球","排球","田径","游泳","橄榄球",
                   "赛事","比赛","体育","世界杯","NBA","F1","直播","新闻"]
ADULT_CHILD_KW = ["儿童","少儿","儿歌","早教","益智","绘本","宝宝","启蒙","幼儿","亲子",
                  "睡前故事","儿童故事","动画电影","儿童电影","幼教"]

def adult_is_sports(cat):
    if not cat: return False
    return any(k in cat for k in ADULT_SPORTS_KW)

def adult_is_child(cat):
    if not cat: return False
    return any(k in cat for k in ADULT_CHILD_KW)

def adult_is_known(agg):
    return agg in ADULT_AGG_NAME and (agg.startswith("adult_") or agg in ADULT_ADULT_AGGS)

def adult_classify(raw):
    """返回 (aggId, aggName)；未知成人分类动态生成 adult_<id>（isKnown 通过），
    普通影视映射 x_*（isKnown 失败 → 被 AdultFilter 拒绝）。"""
    if raw:
        known = ADULT_MAP.get(raw.strip())
        if known:
            return known, ADULT_AGG_NAME.get(known)
    name = (raw.strip() if raw and raw.strip() else "成人")
    _id = "adult_" + _safe_id(name)
    ADULT_AGG_NAME[_id] = "成人 / " + name
    return _id, "成人 / " + name


# ============================================================================
# CHILD（心屋）—— D3（严格白名单，无动态兜底）
# ============================================================================
CHILD_AGG_NAME = {}
CHILD_MAP = {}

def _c_reg(i, name):
    CHILD_AGG_NAME[i] = name
def _c_map(raw, agg):
    CHILD_MAP[raw] = agg

for _i, _n in [("edu_science","科普学习"),("nursery_rhyme","儿童儿歌"),("cartoon","动画片"),
               ("child_guoman","国产动画"),("child_rijk","日韩动画"),("child_oumei","欧美动画"),
               ("child_gangtai","港台动画"),("child_overseas","海外动画"),("child_film","儿童电影")]:
    _c_reg(_i, _n)
for _r, _i in [("科普学习","edu_science"),("科普","edu_science"),("科学教育","edu_science"),
               ("知识动画","edu_science"),("儿童儿歌","nursery_rhyme"),("儿歌","nursery_rhyme"),
               ("儿童动画","cartoon"),("动画片","cartoon"),("少儿动画","cartoon"),("少儿动漫","cartoon"),
               ("卡通动画","cartoon"),("国产动画","child_guoman"),("国产少儿","child_guoman"),
               ("国产动漫","child_guoman"),("国创","child_guoman"),("国产动画电影","child_guoman"),
               ("儿童电影","child_film"),("少儿电影","child_film"),("日韩动画","child_rijk"),
               ("日本动画","child_rijk"),("韩国动画","child_rijk"),("日番","child_rijk"),
               ("日韩动漫","child_rijk"),("日本动漫","child_rijk"),("欧美动画","child_oumei"),
               ("欧美卡通","child_oumei"),("欧美动漫","child_oumei"),("港台动画","child_gangtai"),
               ("港台动漫","child_gangtai"),("海外动画","child_overseas"),("海外动漫","child_overseas"),
               ("早教动画","edu_science"),("早教","edu_science"),("益智","edu_science"),
               ("动画电影","cartoon"),("幼儿","nursery_rhyme"),("幼儿儿歌","nursery_rhyme"),
               ("亲子","nursery_rhyme"),("儿童故事","nursery_rhyme"),("绘本","nursery_rhyme"),
               ("睡前故事","nursery_rhyme"),("宝宝","nursery_rhyme"),("启蒙","edu_science"),
               ("益智动画","edu_science"),("幼教","edu_science"),("儿童动画电影","child_film"),
               ("少儿电影","child_film")]:
    _c_map(_r, _i)
# 普通影视（若儿童源中出现 → x_* → 被拒）
for _r, _i in [("电影","x_movie"),("电视剧","x_tv"),("剧集","x_tv"),("综艺","x_variety"),
               ("动漫","x_anime"),("成人动漫","x_adult_anime"),("里番","x_adult_anime"),
               ("H动漫","x_adult_anime")]:
    _c_map(_r, _i)

def child_is_known(agg):
    return agg in CHILD_AGG_NAME and not agg.startswith("x_")

def child_normalize(raw):
    """返回 aggId 或 None（未知 → None → 拒绝）。"""
    if not raw: return None
    return CHILD_MAP.get(raw.strip())


# ============================================================================
# 统一入口：按 scope 判定 + 归一化
# ============================================================================
def classify_for_scope(scope, original_category):
    """
    返回 (aggId, aggName) 或 None（该条目不属于此 scope，应被隔离拒绝）。
    scope: 'normal' | 'adult' | 'child'
    original_category: 源站 type_name 原始分类名
    """
    if scope == "normal":
        if normal_is_adult(original_category): return None
        if normal_is_sports(original_category): return None
        return normal_classify(original_category)
    elif scope == "adult":
        if adult_is_sports(original_category): return None
        if adult_is_child(original_category): return None
        agg, name = adult_classify(original_category)
        if not adult_is_known(agg): return None
        return agg, name
    elif scope == "child":
        agg = child_normalize(original_category)
        if agg is None or not child_is_known(agg): return None
        return agg, CHILD_AGG_NAME[agg]
    return None


if __name__ == "__main__":
    # 自测：与已知 APK 行为对照
    tests = [
        ("normal", "泰剧", ("tv_thai","电视剧 / 泰剧")),
        ("normal", "伦理", None),                       # 成人 → 拒
        ("normal", "篮球直播", None),                   # 体育 → 拒
        ("normal", "某未知分类X", ("movie_某未知分类X","电影 / 某未知分类X")),  # 动态兜底
        ("adult", "伦理", ("ethics","伦理")),
        ("adult", "国产剧", None),                       # 普通影视 → x_tv → 拒
        ("adult", "篮球", None),                        # 体育 → 拒
        ("child", "儿童动画", ("cartoon","动画片")),
        ("child", "动漫", None),                        # 模糊动漫 → 拒
        ("child", "国产剧", None),                      # 普通影视 → 拒
    ]
    ok = 0
    for sc, cat, exp in tests:
        got = classify_for_scope(sc, cat)
        status = "OK" if got == exp else "FAIL"
        if got == exp: ok += 1
        print(f"[{status}] {sc}/{cat} -> {got} (expect {exp})")
    print(f"self-test: {ok}/{len(tests)} passed")
