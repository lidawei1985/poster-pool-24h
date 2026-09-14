# poster-pool-24h —— 24 小时无人值守海报采集（GitHub 免费托管）

三库分离（normal=星幕 / child=心屋 / adult=夜航），质量优先（横版主视觉 宽≥1280、海报≥600px 门槛+水印/缩略图过滤），全流程跑在 **GitHub Actions** 上，不依赖任何一台电脑开机。图片与 Feed 通过 **jsDelivr CDN** 免费分发。

## 工作原理

```
GitHub Actions (每 2 小时)
  └─ scripts/run_cycle.py
       ├─ 拉 10 个 appleCMS 片源目录（页数+耗时双预算，单源挂不拖垮）
       ├─ category_filters 分流（与 APK 端 Java 逐字一致的真值）
       │    normal 源 → 先判儿童白名单(动画)→心屋库，否则→星幕库
       │    adult 源 → 夜航库
       ├─ 海报下载（<600px 丢弃，压 900 宽 q82）→ pools/<库>/img/
       ├─ 横版主视觉小批量尝试（Wikimedia，宽≥1280 比例≥1.35，儿童库优先）
       │    → pools/<库>/slide/   （失败 7 天后才重试）
       └─ 导出 feeds/feed.<库>.json（jsDelivr 绝对 URL，heroes 只收真横版）
  └─ 自动 git commit + push（图片进仓库 = 免费存储）
```

## 分发地址（建仓后自动生效）

- Feed：`https://cdn.jsdelivr.net/gh/<用户>/<仓库>@main/feeds/feed.normal.json`（child/adult 同理）
- 图片：`https://cdn.jsdelivr.net/gh/<用户>/<仓库>@main/pools/<库>/slide/<md5>.jpg`

md5 = md5(去空格小写片名)，与本机 poster-warehouse、三端 APK 的命名规则一致。

## 启用步骤（一次性）

1. 在 GitHub 建一个仓库（建议 **Private**；Actions 对 private 每月 2000 分钟免费，本工作流每轮约 40 分钟、每 2 小时一轮 ≈ 1500 分钟/月，够用。公开仓则完全不限）。
2. 推送本目录：
   ```bash
   cd poster-pool-24h
   git init && git add -A && git commit -m "init: 24h poster pool"
   git remote add origin https://github.com/<用户>/<仓库>.git
   git push -u origin main
   ```
3. GitHub 仓库 → Settings → Actions → General → Workflow permissions 选 **Read and write**（提交图库需要）。
4. （可选）Settings → Secrets → 新建 `TMDB_API_KEY`（免费注册 https://www.themoviedb.org/settings/api ）。有了它横版主视觉命中率大幅提升（商业片基本都有官方 backdrop）；没有则只跑 Wikimedia。
5. 手动跑一轮验证：Actions → scrape → Run workflow。

## 护栏（无人值守安全）

- 单轮 38 分钟预算 + 每源页数上限，绝不跑爆 Actions 50 分钟墙钟
- 仓库图库 > 3.2GB 自动停新增（仍刷新 feed）
- hero 失败记入 state/state.json，7 天内不重复浪费尝试
- 三库物理分目录，互不混图；adult 库不抓横版（无合规公开源，保持竖版直出）

## APK 接入（需用户批准，属 HERO 红线范围）

三端 APK 目前写死本机 `http://192.168.8.109:8911/feed.*`。若要切换/备援到 jsDelivr feed，需改 APK 内 feed 地址并重新出包——**HERO 红线流程，必须用户人工批准后由主视觉负责会话执行**。本仓库先独立运行攒图，不主动动 APK。
