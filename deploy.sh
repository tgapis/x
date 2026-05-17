#!/bin/bash
set -e

pip install -q -r requirements.txt

# stash scripts before switching branches
cp scrape.py              /tmp/scrape.py
cp schema.py              /tmp/schema.py
cp bin.js                 /tmp/bin.js
cp index.js               /tmp/index.js
cp ferogram/generate.py   /tmp/ferogram_generate.py
cp get-all-tl.py          /tmp/get-all-tl.py
cp tl/index.html          /tmp/tl_index.html
cp tl/app.js              /tmp/tl_app.js

IFS="
"

python /tmp/scrape.py
python /tmp/schema.py "https://core.telegram.org/schema"    "core.tl"
python /tmp/schema.py "https://corefork.telegram.org/schema" "corefork.tl"
python /tmp/schema.py "https://blogfork.telegram.org/schema" "blogfork.tl"
wget -q -O tdesktop.tl "https://github.com/telegramdesktop/tdesktop/raw/dev/Telegram/SourceFiles/mtproto/scheme/api.tl"
wget -q -O tdlib.tl    "https://github.com/tdlib/td/raw/master/td/generate/scheme/telegram_api.tl"
node /tmp/bin.js tdesktop.tl  tdesktop.json
node /tmp/bin.js core.tl      core.json
node /tmp/bin.js corefork.tl  corefork.json
node /tmp/bin.js blogfork.tl  blogfork.json
node /tmp/bin.js tdlib.tl     tdlib.json

# stash then remove generated files (untracked files block checkout)
cp botapi.json botapi.min.json /tmp/
cp core.tl core.json corefork.tl corefork.json blogfork.tl blogfork.json /tmp/
cp tdesktop.tl tdesktop.json tdlib.tl tdlib.json /tmp/
rm -f botapi.json botapi.min.json \
      core.tl core.json corefork.tl corefork.json blogfork.tl blogfork.json \
      tdesktop.tl tdesktop.json tdlib.tl tdlib.json

git fetch origin data
git checkout -B data origin/data

# restore generated files
cp /tmp/botapi.json /tmp/botapi.min.json .
cp /tmp/core.tl /tmp/core.json /tmp/corefork.tl /tmp/corefork.json /tmp/blogfork.tl /tmp/blogfork.json .
cp /tmp/tdesktop.tl /tmp/tdesktop.json /tmp/tdlib.tl /tmp/tdlib.json .

git config --global user.email "igor.beatle@gmail.com"
git config --global user.name "GitHub Action <Igor Zhukov>"
git add botapi.json botapi.min.json
git commit -m "update BOT API docs" || true

git config --global user.email "johnprestonmail@gmail.com"
git config --global user.name "GitHub Action <John Preston>"
git add tdesktop.tl tdesktop.json
git commit -m "update tDesktop API scheme" || true

git config --global user.email "levlam@telegram.org"
git config --global user.name "GitHub Action <Aliaksei Levin>"
git add tdlib.tl tdlib.json
git commit -m "update TDLib API scheme" || true

git config --global user.email "durov2005@gmail.com"
git config --global user.name "GitHub Action <Pavel Durov>"
git add core.tl core.json corefork.tl corefork.json blogfork.tl blogfork.json
git commit -m "update OW (3) API scheme" || true

# Telethon docs
git clone -q --depth=1 --branch v1 https://github.com/LonamiWebs/Telethon /tmp/Telethon/
a=$(pwd)
rm -rf telethon
mkdir -p telethon
cd /tmp/Telethon/
cp "${a}/tdesktop.tl" /tmp/Telethon/telethon_generator/data/api.tl
python setup.py gen docs
mv docs/* "${a}/telethon/"
cd "${a}"
rm -rf /tmp/Telethon/
cd "${a}/telethon/"
git config --global user.email "Lonami@users.noreply.github.com"
git config --global user.name "GitHub Action <Lonami Exo>"
git add constructors/ types/ methods/ index.html 404.html js/search.js css/ img/
git commit -m "update telethon docs" || true
cd "${a}"

# TL diff: run twice with different env vars (tdesktop, then TDLib)
# app.js and index.html are vendored in tl/ on the main branch (stashed to /tmp/).
a=$(pwd)
rm -rf TL/
mkdir -p TL/diff/
mkdir -p /tmp/tldiff
cd /tmp/tldiff

FQDN="https://tgapis.github.io/x/TL/diff" GH="https://github.com/telegramdesktop/tdesktop/" python /tmp/get-all-tl.py
cp /tmp/tl_app.js atom.xml diff.js "${a}/TL/diff/"
cp /tmp/tl_index.html "${a}/TL/diff/tdesktop.html"
mkdir -p "${a}/TL/diff/schemes/tDesktop"
mv schemes/* "${a}/TL/diff/schemes/tDesktop/"
rm -rf tdesktop schemes

FQDN="https://tgapis.github.io/x/TL/diff" TDLIBGH="https://github.com/tdlib/td" python /tmp/get-all-tl.py
cp tdatom.xml tddiff.js "${a}/TL/diff/"
cp /tmp/tl_index.html "${a}/TL/diff/tdlib.html"
cp /tmp/tl_app.js "${a}/TL/diff/tdapp.js"
mkdir -p "${a}/TL/diff/schemes/TDLib"
mv schemes/* "${a}/TL/diff/schemes/TDLib/"
rm -rf td schemes
cd "${a}"
rm -rf /tmp/tldiff

git add -A TL/
git config --global user.email "Lonami@users.noreply.github.com"
git config --global user.name "GitHub Action <Lonami Exo> | GitHub Action <John Preston>"
git commit -m "update TL diff" || true

# ferogram raw API docs
mkdir -p /tmp/ferogram_site
LAYER=$(grep '// LAYER' tdesktop.tl | tail -1 | grep -o '[0-9]*')
python /tmp/ferogram_generate.py tdesktop.tl /tmp/ferogram_site/
cp -r /tmp/ferogram_site/constructors /tmp/ferogram_site/types /tmp/ferogram_site/methods \
      /tmp/ferogram_site/css /tmp/ferogram_site/js "${a}/"
cp /tmp/ferogram_site/index.html /tmp/ferogram_site/404.html "${a}/"
echo "tl.ferogram.dev" > "${a}/CNAME"
git add constructors/ types/ methods/ css/ js/ index.html 404.html CNAME
git config --global user.email "ankitchaubey.dev@gmail.com"
git config --global user.name "Ankit Chaubey"
git commit -m "update ferogram raw API docs (Layer ${LAYER})" || true

git push origin data
