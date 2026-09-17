# ARIA — weekly refresh runbook

This is the exact recipe the scheduled "ARIA weekly refresh" task replays.
Goal: pull fresh Shopify numbers from Supermetrics, rebuild `index.html`, and
push to GitHub (Netlify then auto-deploys). Only the `const DATA={...}` block in
`index.html` changes; the design + ARIA insight logic are untouched and
recompute from the new numbers on load.

## Source
- Supermetrics MCP, data source **Shopify** (`ds_id = SHP`), authenticated on
  team **Tech Bay Leaf** (ID 913930).
- Account (store): `gid://shopify/Shop/56804933743` — "Amar Chitra Katha".
- Currency INR. COGS is not populated, so margin is intentionally omitted.

## Step 1 — run these 8 queries
For each: `data_query(ds_id="SHP", ds_accounts="gid://shopify/Shop/56804933743", fields=..., date_range_type=..., max_rows=...)`,
then poll `get_async_query_results(schedule_id, compress=true)` until `status=="completed"`
(first pull of a session backfills slowly — keep polling for up to ~5 min per query).
Save each completed result's `data` block **verbatim** to the named file in this folder.

| file | fields | date_range | max_rows |
|------|--------|-----------|----------|
| raw_daily.txt    | `date,total_sales,sm_order_count,discounts,returns` | custom, start `2026-03-01`, end = yesterday | 400 |
| raw_monthly.txt  | `yearMonth,total_sales,sm_order_count`               | custom, start `2024-09-01`, end = yesterday | 60  |
| raw_products.txt | `title,total_sales,ordered_quantity`                | last_90_days | 60 |
| raw_channels.txt | `order_channel,total_sales,sm_order_count`          | last_90_days | 50 |
| raw_customers.txt| `order_is_returning_customer,total_sales,sm_order_count` | last_90_days | 10 |
| raw_cities.txt   | `order_shipping_city,total_sales,sm_order_count`    | last_90_days | 400 |
| raw_bd90.txt     | `gross_sales,discounts,returns,net_sales,total_sales,sm_order_count` | last_90_days | (none) |
| raw_bd30.txt     | `gross_sales,discounts,returns,net_sales,total_sales,sm_order_count` | last_30_days | (none) |

Keep the raw file format exactly as Supermetrics returns it (the
`  - [N,]: a,b,c` lines, header row included). `build_dashboard.py` strips the
prefix and drops the header automatically.

## Step 2 — build
`python3 build_dashboard.py`
Prints an `OK ...` line with the refresh date, window, and sanity counts.
It rewrites `../index.html` in place. If it can't find the DATA block or a raw
file is missing, it raises — do not push a half-built file.

## Step 3 — deploy through the Mac
Git lock files don't work inside the mounted folder, so clone/commit/push in the
Mac's **local scratch** (`$HOME`), not under `$HOME/mnt/...`:

    cd "$HOME" && rm -rf aria-work && mkdir aria-work && cd aria-work
    git clone https://x-access-token:$GH_TOKEN@github.com/TechBayLeaf/aria-growth-os.git repo
    # copy the freshly-built index.html into repo/  (from the container via device_commit_files, or rebuild here)
    cd repo && git add -A && git commit -m "Weekly refresh <date>" \
      && git push https://x-access-token:$GH_TOKEN@github.com/TechBayLeaf/aria-growth-os.git HEAD:main

Netlify (linked to this repo) auto-deploys `main` within ~1 min. Confirm the live
site (https://aria-ack-dashboard.netlify.app) shows the new "Refreshed" date.

## Notes / known limits
- The YoY comparison tiles ("August revenue", "Year to date · Jan–Aug", "Sept
  proj. vs last Sept") carry Aug/Sept-oriented labels in the HTML; the numbers
  are dynamic but those three labels read best Aug–Oct. Revisit if kept long-term.
- City names are normalised heuristically (case + common spelling variants of the
  metros). Good enough for the top-10; the long tail rolls into "other cities".
- If the Mac is unreachable at run time, the build still succeeds in the cloud —
  retry the push when the Mac is back, or hand the file to the user to drop on Netlify.
