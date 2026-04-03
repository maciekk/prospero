#!/bin/bash

cd ~/src/prospero

rm -f ~/.prospero/acb_ledger.json

uv run prospero acb add-opening-balance \
  --ticker ACME \
  --date 2022-12-31 \
  --shares 287.500 \
  --opening-acb-usd 23806.25

uv run prospero acb import-ms --dir data-sample/complete --ticker ACME --pdf /tmp/prospero-acb-import.pdf

echo "Now you can run reports; e.g.,"
echo "  $ uv run prospero acb report --year 2023 --pdf acb.pdf"
