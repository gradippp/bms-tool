# bms-tool

A small CLI that takes a BookMyShow *buytickets* link and tells you **which days**
the movie is showing and **what times** each cinema has, without opening a browser.

## Install

```sh
pip install -r requirements.txt          # just `requests`
# or, to get a `bms` command on your PATH:
pip install -e .
```

## Usage

```sh
python -m bmstool "https://in.bookmyshow.com/movies/mumbai/some-movie/buytickets/ET00000000/20260101"
```

```
Some Movie - Mumbai
THU 01 JAN  (20260101)
  Example Cinema: Example Mall
    Cancellation available
    ~ 02:00 PM   English • 3D   Rs.500
    ~ 08:00 PM   English • 3D   Rs.500

legend:  available   ~ filling fast   ! almost full   x sold out
```

By default the tool fetches the URL's date once, reads the date strip to learn which
days actually have shows, and then fetches only those days.

### Options

| Flag | Meaning |
| --- | --- |
| `--dates-only` | just list which days have shows; skip the per-cinema fetches |
| `--date YYYYMMDD` | fetch one specific date (repeatable) |
| `--days N` | fetch the next N days from the URL's date |
| `--venue TEXT` | only cinemas whose name contains TEXT (repeatable) |
| `--after HH:MM` / `--before HH:MM` | filter showtimes (24h clock) |
| `--available-only` | hide sold-out shows |
| `--format table\|compact\|json` | output format (default `table`) |
| `--no-color` | disable ANSI colours (also honours `NO_COLOR`) |

Exit codes: `0` shows found, `1` nothing found, `2` bad URL / fetch / parse error.

### Examples

```sh
bms "<url>" --dates-only
bms "<url>" --venue pvr --venue inox --after 18:00 --available-only
bms "<url>" --days 7 --format json > shows.json
```

## `bms-notify` — email me when tickets open

A second tool in the same package, meant for a Linux server + cron. You tell it the
dates you're waiting for; it emails you (via SMTP, credentials from the environment)
as soon as those days have shows, and never mails you about the same thing twice.

```sh
python -m bmstool.notify            # one polling cycle
python -m bmstool.notify --dry-run  # print the mail instead of sending it
python -m bmstool.notify --reset    # forget what was already notified
python -m bmstool.notify --quiet    # only warnings and errors (good for cron)
```

Exit codes: `0` mail sent, `1` nothing new, `2` config / fetch / SMTP error.

### Environment

| Variable | Required | Meaning |
| --- | --- | --- |
| `BMS_URL` | yes | the buytickets link to watch |
| `BMS_DATES` | no | dates you want, comma-separated, `YYYY-MM-DD` or `YYYYMMDD`. Unset (or `any`) watches **every** date BookMyShow offers |
| `BMS_MAIL_TO` | yes | recipient(s), comma-separated |
| `BMS_MAIL_FROM` | no | sender (defaults to `BMS_SMTP_USER`) |
| `BMS_MAIL_SUBJECT_PREFIX` | no | subject prefix, default `[BMS]` |
| `BMS_SMTP_HOST` | yes | SMTP server |
| `BMS_SMTP_PORT` | no | default `465` when SSL, else `587` |
| `BMS_SMTP_USER` / `BMS_SMTP_PASSWORD` | no | omit for an unauthenticated relay |
| `BMS_SMTP_SSL` | no | implicit TLS; defaults true on port 465 |
| `BMS_SMTP_STARTTLS` | no | STARTTLS on a plain connection, default `true` |
| `BMS_VENUES` | no | only these cinemas (comma-separated substrings) |
| `BMS_AFTER` / `BMS_BEFORE` | no | `HH:MM` bounds on showtimes |
| `BMS_AVAILABLE_ONLY` | no | ignore sold-out shows, default `true` |
| `BMS_STATE_FILE` | no | dedupe state, default `~/.cache/bms-notify/state.json` |
| `BMS_NOTIFY_ON_CHANGE` | no | re-mail if a watched day's showtimes change, default `true` |
| `BMS_LABEL` | no | name used in the subject line, defaults to the movie |
| `BMS_DRY_RUN` | no | same as `--dry-run` |

### Cron example

```cron
*/15 * * * * BMS_URL="https://in.bookmyshow.com/movies/mumbai/some-movie/buytickets/ET00000000/20260101" \
  BMS_DATES="2026-01-03,2026-01-04" \
  BMS_MAIL_TO="you@example.com" \
  BMS_SMTP_HOST="smtp.gmail.com" BMS_SMTP_SSL=true \
  BMS_SMTP_USER="you@gmail.com" BMS_SMTP_PASSWORD="app-password" \
  /usr/local/bin/bms-notify --quiet
```

Keep credentials out of the crontab in practice — put them in a root-only env file
and source it, e.g. `set -a; . /etc/bms-notify.env; set +a; bms-notify --quiet`.

State is written atomically to `BMS_STATE_FILE`, so a day is mailed once; if its
showtimes later change (new screening, sell-out) you get one follow-up mail.

## How it works

BookMyShow's mobile API is token-gated (403), but the showtimes page itself is
plain server-rendered HTML containing a `window.__INITIAL_STATE__` blob:

```
__INITIAL_STATE__.showtimesFunctionalApi.queries["fetchPrimaryDynamic-…"].data.data
  ├─ topStickyWidgets[0].data[]   → the date strip (which days have shows)
  └─ showtimeWidgets[] (groupList → venueGroup → venue-card)
       ├─ additionalData.venueName / venueCode
       └─ showtimesSections[].showtimes[]
            ├─ additionalData: showTime, showTimeCode, sessionId, availStatus
            └─ customGestureCTA…bottomSheetData.widgets[] → format + seat prices
```

Asking for a date that has no shows makes BookMyShow silently serve the nearest
date that does, so the tool compares the *selected* date in the response against
the date requested and reports "no shows" on a mismatch rather than duplicating a day.

## Layout

| Module | Responsibility |
| --- | --- |
| `bmstool/url.py` | parse / rebuild buytickets URLs (`BmsTarget`) |
| `bmstool/fetch.py` | `requests` session, browser headers, retry, polite delay |
| `bmstool/extract.py` | pull `__INITIAL_STATE__` out of the HTML, locate the payload |
| `bmstool/parse.py` | payload → `DateOption` / `Venue` / `Show` / `SeatCategory` |
| `bmstool/render.py` | table, compact and JSON rendering |
| `bmstool/client.py` | `ShowtimesClient`: fetch + parse one date, reusing a session |
| `bmstool/filters.py` | `ShowFilter`: venue / time / availability filtering |
| `bmstool/cli.py` | `bms` — argument parsing and the fetch/filter/render flow |
| `bmstool/config.py` | `bms-notify` configuration read from the environment |
| `bmstool/state.py` | dedupe state file + per-day fingerprints |
| `bmstool/mailer.py` | SMTP delivery (stdlib `smtplib`, no extra dependency) |
| `bmstool/notify.py` | `bms-notify` — polling cycle and mail composition |

`client.py` and `filters.py` are shared by both entrypoints, so the CLI and the
notifier always agree on what "a matching show" means.

If BookMyShow changes its markup, the failure surfaces as a clear `BmsParseError`
from `extract.py` — that's the only module that knows about the page's shape.
