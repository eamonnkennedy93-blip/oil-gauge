# Oil Gauge — static build

This is a self-contained, host-anywhere version of Oil Gauge. It's a plain
HTML/CSS/JS page plus two JSON files — no server, no database, no build
step. This snapshot has real data: 279 weeks of NI heating oil prices
(31 Mar 2021 – 3 Sept 2026) and 3 buying clubs.

## Files

```
index.html                         the whole app (routing, chart, gauge logic all in here)
data/weekly.json                   price history — one row per surveyed week
data/clubs.json                    the buying club directory
scripts/update_prices.py           the weekly scraper (see below)
scripts/requirements.txt           its two dependencies
.github/workflows/update-prices.yml   the schedule that runs it
```

## Deploying it (pick one, both are free)

**Netlify — easiest, no account setup needed to try it:**
1. Go to https://app.netlify.com/drop
2. Drag the whole `site` folder (the one containing `index.html` and `data/`) onto the page
3. It's live immediately on a netlify.app address. Add your own domain later in Site settings → Domain management.

**GitHub Pages — if you want it version-controlled:**
1. Create a new GitHub repo, push these files to it (index.html and data/ at the repo root)
2. Repo Settings → Pages → set source to the main branch
3. It publishes at `<username>.github.io/<repo>` within a minute or two. Custom domain goes in the same Pages settings screen.

Either way, once it's live, pointing your `.com` at it is the same two steps
everywhere: buy the domain (Namecheap, GoDaddy, whoever), then in that
registrar's DNS settings add the CNAME/A record the host's domain page
tells you to add. Both Netlify and GitHub Pages walk you through the exact
record when you add the domain in their settings — follow what they show
you rather than a generic guide, it changes slightly by host.

## Keeping the price data current — it's automated

`.github/workflows/update-prices.yml` runs every Friday at 08:05 UTC
(also triggerable manually from the Actions tab). It:

1. Fetches the Consumer Council NI's public price archive and parses out
   any week not already in `data/weekly.json` — it only adds new dates,
   never overwrites a date already stored, so a source correction can't
   silently rewrite history that's already published.
2. Fetches the current council-area breakdown and attaches it to the
   latest week.
3. Commits and pushes the updated file only if something actually
   changed.

This starts working the moment you push these files to a GitHub repo —
GitHub Pages and this Action live in the same repo, no extra account or
token needed (the Action uses GitHub's own built-in permissions to push
back to your repo). If you deploy via Netlify instead of GitHub Pages,
either connect Netlify to auto-deploy from the same GitHub repo on every
push (Netlify's "Deploys" settings), or the data still updates weekly on
GitHub even if you're manually re-dragging the folder occasionally — you
just won't see the redeploy until you do.

**The scraper is defensive on purpose.** The Consumer Council's page is
server-rendered HTML with no JavaScript needed to read it — I fetched the
real page, checked its exact table structure, and tested the actual
parsing code against real captured markup (all 280 historical rows,
reproduced the already-published data exactly, byte for byte, including
the one known source duplicate from November 2021). Even so, if the site
gets redesigned, or the parser ever gets a wildly implausible price
(outside roughly £50–£1700), it refuses to write and fails the Action
loudly instead of guessing — you'd see a red X in the repo's Actions tab
rather than silently wrong numbers on the site. If that ever happens,
send me the page and I'll fix the selectors.

**A small real backend** (Firebase/Supabase free tier) is the next step
up if you ever want live writes back — e.g. letting people submit buying
clubs directly instead of by email. Bigger step, only worth it if the
site gets real usage.

For now, "suggest a club" opens a pre-filled email to you instead of
writing to a database — add anything real to `data/clubs.json` by hand and
redeploy (or just let the Action's next run carry your manual edit
forward, since it only ever adds price rows, never touches clubs.json).

## If you want to edit content directly

`data/weekly.json` is a flat array of `{date, niAvg300, niAvg500, niAvg900,
source, byCouncil?}` objects, one per surveyed week. `data/clubs.json` is
`{name, area, notes, addedAt, updatedAt}` objects. Add, edit, or remove
entries with any text editor — no schema migration, no build step, just
save and redeploy.
