# Personal website: Md Nahidul Islam Opu

Live at **https://home.cc.umanitoba.ca/~opumni/**. The site is plain HTML with one CSS file and one small JS file, and there is no build step. `public_html/` holds exactly what goes on the server.

```
public_html/
  index.html          Home: intro, news, selected papers
  publications.html   all papers, grouped by year
  experience.html     education, experience, awards, skills
  projects.html  talks.html
  blog/index.html     post list; blog/_template.html is the starting point for a post
  assets/             style.css, main.js (visit counter), profile.jpg, favicon.svg
  cv.pdf
  cgi-bin/hit.py      records anonymous visits into ~/site-data/visits.sqlite
  cgi-bin/stats.py    your private stats dashboard
deploy.sh             uploads public_html/ to the server
```

## Preview locally

```sh
cd public_html
env SITE_DATA_DIR=/tmp/site-data-test python3 -m http.server --cgi 8000
```

Open http://localhost:8000/. The stats dashboard is at http://localhost:8000/cgi-bin/stats.py. Local visits go into the test folder, not the real data. To log in locally, first run `env SITE_DATA_DIR=/tmp/site-data-test python3 cgi-bin/stats.py --set-password`.

## Publish

**On the UManitoba server** (`ssh opumni@ccl.cc.umanitoba.ca`). Keep the repo outside `public_html`, so `.git` is never public.
```sh
git clone https://github.com/nahidul-opu/nahidul-opu.github.io.git ~/website   # first time only
cd ~/website
git pull
./deploy.sh --here
```

**From another machine:** run `./deploy.sh`. It uploads over ssh and asks for your UManitoba (IST Linux) password once per run.

Either way, it lists what will change on the live site and asks before copying.

To skip the password prompt, set up an SSH key once:
```sh
ssh-keygen -t ed25519
ssh-copy-id opumni@ccl.cc.umanitoba.ca
```

## First-time setup (once)

1. Publish as above. The first run replaces the old "Welcome!" page.
2. Set the dashboard password. On the server, run `python3 ~/public_html/cgi-bin/stats.py --set-password`; from another machine, run `ssh -t opumni@ccl.cc.umanitoba.ca python3 public_html/cgi-bin/stats.py --set-password`.
3. Open https://home.cc.umanitoba.ca/~opumni/cgi-bin/stats.py and log in.
4. On GitHub, open the repo's Settings → Pages and unpublish the site, so GitHub doesn't serve a second copy.

## How to add things

Every list has an HTML comment above it that says where to paste. Edit the file, preview it, then run `./deploy.sh`.

**News item.** In `index.html`, paste a line at the top of the News list:
```html
<li><time datetime="2026-11-02">Nov 2026</time><span>Paper accepted at <a href="https://...">ICSE 2027</a>!</span></li>
```
When the list gets long, move old lines into the commented-out "Older updates" block below it, and delete that block's comment markers.

**Paper.** In `publications.html`, copy a whole `<li class="pub"> ... </li>` block, paste it at the top of the right year, and edit it.
- Badge classes: `venue` for a conference, `venue journal` for a journal, `venue preprint` for a preprint.
- Link the Publisher page, DOI and arXiv. Don't upload publisher PDFs: the IST usage policy forbids posting already-published work unless your publication agreement allows it.
- If it's a first-author paper, also paste the block (without the `<details>` BibTeX part) at the top of "Selected publications" in `index.html`.

**Blog post.**
1. Copy `blog/_template.html` to `blog/2026-11-02-my-post.html`.
2. Replace TITLE, DATE, SUMMARY and FILE-NAME, then write the post inside `<article>`.
3. Paste the list line shown in the comment in `blog/index.html` at the top of its list.
4. Delete the "No posts yet" paragraph there.

**Project or talk.** Copy an `<article class="card">` block in `projects.html` or `talks.html` and edit it. Slides go in `assets/` as PDF.

**Teaching page (later).**
1. Copy `talks.html` to `teaching.html` and replace the cards with your courses.
2. Add the nav link to every page:
   ```sh
   sed -i -E 's|(<a href="(\.\./)?talks\.html"[^>]*>Talks</a>)|\1\n      <a href="\2teaching.html">Teaching</a>|' public_html/*.html public_html/blog/*.html
   ```
3. In `teaching.html`, move `aria-current="page"` from the Talks link to the Teaching link.

## Visitor stats

- **What's sent:** each page sends one small beacon to `cgi-bin/hit.py`, with the page, the referring site and the browser's time zone. Clicks on PDFs (your CV) and on links to other sites are counted too.
- **What's stored:** the time, page, referring site, browser/OS/device type, time zone and a visitor id. The visitor id is a hash of (a secret that changes daily + IP + browser). No IP addresses and no cookies.
- **Visitors:** each person counts once per day.
- **Location:** country and region come from the browser time zone, e.g. `Asia/Dhaka` → Bangladesh. It's accurate to the country for almost everyone but can't give cities.
- **Your own visits:** open the site once with `?notrack` (e.g. `https://home.cc.umanitoba.ca/~opumni/?notrack`) and that browser stops being counted; `?track` undoes it. Logging into the dashboard does the same automatically.
- **Where the data lives:** `~/site-data/` on the server, outside `public_html`, so it's never public. Back it up by copying `~/site-data/visits.sqlite`.
- **Change the password:** run the `--set-password` command from First-time setup again.

**If `stats.py` shows "Internal Server Error":** on the server, run `chmod 755 ~/public_html/cgi-bin ~/public_html/cgi-bin/*.py` (or IST's `makepublic cgi-bin` from inside `public_html`). IST's notes are at https://home.cc.umanitoba.ca/cgi.html.
