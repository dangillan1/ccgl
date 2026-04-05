#!/bin/bash
cd "/Users/dangillan/Documents/Claude/Projects/CCGL Growlink Analyst"
rm -f .git/HEAD.lock .git/index.lock
git add report_template.html generate_report.py CCGL-Hourly-Report-Latest.html index.html
git commit -m "Fix data, remove dropdowns, add password gate, mobile optimization"
git push origin main
echo ""
echo "Done! Check https://dangillan1.github.io/ccgl/ (password: ccgl)"
