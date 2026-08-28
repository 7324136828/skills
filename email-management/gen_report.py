#!/usr/bin/env python3
"""
gen_report.py -- Stage 4 of the inbox audit pipeline.

Renders summary.json + worklist.json as one self-contained HTML page:
the service inventory (answer 1) and the ordered cleanup plan (answer 2).

Every number and every headline is derived from the data, so the page is correct
for any export. The only hand-written text is in annotations.json.

Usage:
    python gen_report.py report/summary.json worklist.json \
        -o inbox_audit.html --annotations config/annotations.json --source "INBOX"
"""

from __future__ import annotations

import argparse
import collections
import html
import json

STRONG = ("signup", "verification", "approval", "security",
          "credentials", "billing", "service_ops")

ACTIONS = {
    "unsubscribe_then_bulk_delete": (
        "Unsubscribe, then delete the lot", "rust",
        "Bulk mail with no account behind it. Opt out first — deleting first just "
        "lets the sender refill the folder."),
    "unsubscribe_keep_account": (
        "Unsubscribe from marketing, keep the account", "amber",
        "You hold an account here. Opt out of the promotional stream; leave receipts "
        "and security mail alone."),
    "settings_or_block": (
        "Turn it off inside the service", "violet",
        "No List-Unsubscribe header in the mail. The switch lives in the account's own "
        "notification settings."),
    "keep_archive": (
        "Keep", "green",
        "Receipts, security alerts, verification codes and real correspondence. "
        "Never unsubscribe from these."),
}

METHOD_LABEL = {
    "one_click_header": "One-click",
    "http_header": "Header link",
    "body_link": "Footer link",
    "mailto_header": "Email opt-out",
    "account_settings": "Account settings",
    "none_found": "No opt-out",
}

CSS = """
:root {
  --ground:#F1F4F6; --surface:#FFFFFF; --surface-2:#F7F9FA;
  --ink:#141A21; --ink-2:#525E6B; --ink-3:#8A94A1;
  --line:#DCE2E8; --line-soft:#EAEEF2;
  --accent:#0B5563; --accent-ink:#0B5563; --accent-soft:#E1EEF1;
  --rust:#8F3628; --amber:#7E540E; --violet:#4C4291; --green:#2A5D4B;
  --rust-soft:#F7E9E5; --amber-soft:#F8EEDC; --violet-soft:#ECEAF7; --green-soft:#E3EFEA;
  --shadow:0 1px 2px rgba(20,26,33,.05), 0 8px 24px -16px rgba(20,26,33,.28);
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ground:#0E1319; --surface:#161D25; --surface-2:#1B232C;
    --ink:#E7ECF1; --ink-2:#A6B1BD; --ink-3:#78848F;
    --line:#28313B; --line-soft:#212A33;
    --accent:#5FBACB; --accent-ink:#8FD3E0; --accent-soft:#153138;
    --rust:#E08C79; --amber:#DBA748; --violet:#A79BE8; --green:#6FBFA1;
    --rust-soft:#2C1C18; --amber-soft:#2C2413; --violet-soft:#1F1C31; --green-soft:#152A23;
    --shadow:0 1px 2px rgba(0,0,0,.4), 0 10px 28px -18px rgba(0,0,0,.8);
  }
}
:root[data-theme="dark"] {
  --ground:#0E1319; --surface:#161D25; --surface-2:#1B232C;
  --ink:#E7ECF1; --ink-2:#A6B1BD; --ink-3:#78848F;
  --line:#28313B; --line-soft:#212A33;
  --accent:#5FBACB; --accent-ink:#8FD3E0; --accent-soft:#153138;
  --rust:#E08C79; --amber:#DBA748; --violet:#A79BE8; --green:#6FBFA1;
  --rust-soft:#2C1C18; --amber-soft:#2C2413; --violet-soft:#1F1C31; --green-soft:#152A23;
  --shadow:0 1px 2px rgba(0,0,0,.4), 0 10px 28px -18px rgba(0,0,0,.8);
}

* { box-sizing:border-box; }
body {
  margin:0; background:var(--ground); color:var(--ink);
  font-family:"Source Serif 4", Georgia, serif; font-size:17px; line-height:1.6;
  -webkit-font-smoothing:antialiased;
}
.wrap { max-width:1080px; margin:0 auto; padding:48px 24px 96px; display:flex; flex-direction:column; gap:56px; }
h1,h2,h3,.label,.chip,.method,.state,th,.card-stat,.bar-val,.stat-n { font-family:"Archivo", "Helvetica Neue", Arial, sans-serif; }
.mono, .svc-key, .bar-addr, .dates, td.num, .target a { font-family:"JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace; }

.mast { display:flex; flex-direction:column; gap:14px; border-bottom:2px solid var(--ink); padding-bottom:26px; }
.label { font-size:11.5px; letter-spacing:.14em; text-transform:uppercase; color:var(--accent-ink); font-weight:600; }
h1 { font-size:clamp(34px,5.2vw,52px); line-height:1.04; margin:0; font-weight:700; letter-spacing:-.022em; text-wrap:balance; }
.dek { margin:0; color:var(--ink-2); font-size:19px; max-width:60ch; }
.src { margin:0; color:var(--ink-3); font-size:13.5px; font-family:"JetBrains Mono",monospace; word-break:break-all; }

.stats { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:1px; background:var(--line); border:1px solid var(--line); border-radius:10px; overflow:hidden; }
.stat { background:var(--surface); padding:18px 20px; display:flex; flex-direction:column; gap:3px; }
.stat-n { font-size:30px; font-weight:700; letter-spacing:-.02em; font-variant-numeric:tabular-nums; }
.stat-l { font-size:13.5px; color:var(--ink-2); line-height:1.35; }

section > h2 { font-size:13px; letter-spacing:.14em; text-transform:uppercase; margin:0 0 6px; color:var(--accent-ink); font-weight:600; }
.sec-lead { margin:0 0 26px; font-size:22px; line-height:1.4; max-width:64ch; text-wrap:balance; }
.sec-lead strong { font-weight:600; box-shadow:inset 0 -.42em 0 var(--accent-soft); }
p.body { max-width:65ch; color:var(--ink-2); }

.chart { background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:22px 24px; box-shadow:var(--shadow); display:flex; flex-direction:column; gap:9px; }
.chart-title { font-family:"Archivo",sans-serif; font-size:14px; font-weight:600; margin:0 0 8px; }
.bar-row { display:grid; grid-template-columns:minmax(140px,1.25fr) minmax(100px,2.4fr) 96px; gap:14px; align-items:center; border-radius:6px; padding:3px 4px; }
.bar-row:hover, .bar-row:focus-visible { background:var(--surface-2); outline:none; }
.bar-row:focus-visible { box-shadow:0 0 0 2px var(--accent); }
.bar-name { font-size:14px; display:flex; flex-direction:column; line-height:1.25; min-width:0; }
.bar-addr { font-size:10.5px; color:var(--ink-3); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.bar-track { height:12px; background:var(--line-soft); border-radius:3px; }
.bar-fill { height:100%; background:var(--accent); border-radius:0 4px 4px 0; }
.bar-val { text-align:right; font-size:14px; font-weight:600; font-variant-numeric:tabular-nums; display:flex; flex-direction:column; line-height:1.2; }
.bar-pct { font-size:11px; font-weight:500; color:var(--ink-3); }

.scroll { overflow-x:auto; }
table { border-collapse:collapse; width:100%; font-size:14.5px; }
th { text-align:left; font-size:11px; letter-spacing:.09em; text-transform:uppercase; color:var(--ink-3); font-weight:600; padding:0 14px 9px; border-bottom:1px solid var(--line); white-space:nowrap; }
td { padding:13px 14px; border-bottom:1px solid var(--line-soft); vertical-align:top; }
tbody tr:last-child td { border-bottom:none; }
td.num { text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }
.services { background:var(--surface); border:1px solid var(--line); border-radius:12px; box-shadow:var(--shadow); }
.services table { min-width:900px; }
.services th { padding-top:16px; }
.services td:first-child, .services th:first-child { padding-left:22px; }
.services td:last-child, .services th:last-child { padding-right:22px; }
.svc-name { display:block; font-family:"Archivo",sans-serif; font-weight:600; font-size:15px; }
.svc-key { display:block; font-size:11px; color:var(--ink-3); }
.ev { font-size:12.5px; color:var(--ink-2); font-family:"JetBrains Mono",monospace; }
.dates { display:block; font-size:12px; color:var(--ink-2); white-space:nowrap; }
.note { font-size:13.5px; color:var(--ink-2); min-width:230px; }

.chip { display:inline-block; font-size:10.5px; letter-spacing:.07em; text-transform:uppercase; font-weight:600; padding:3px 8px; border-radius:4px; white-space:nowrap; }
.chip-confirmed { background:var(--green-soft); color:var(--green); }
.chip-probable { background:var(--amber-soft); color:var(--amber); }
.state { font-size:10px; letter-spacing:.07em; text-transform:uppercase; font-weight:600; }
.state-live { color:var(--green); } .state-quiet { color:var(--amber); } .state-dormant { color:var(--ink-3); }

.cards { display:flex; flex-direction:column; gap:22px; }
.card { background:var(--surface); border:1px solid var(--line); border-left:4px solid var(--tone); border-radius:12px; box-shadow:var(--shadow); overflow:hidden; }
.tone-rust { --tone:var(--rust); } .tone-amber { --tone:var(--amber); }
.tone-violet { --tone:var(--violet); } .tone-green { --tone:var(--green); }
.card-head { padding:20px 22px 16px; display:flex; flex-direction:column; gap:6px; border-bottom:1px solid var(--line-soft); }
.card-head h3 { margin:0; font-size:19px; font-weight:600; color:var(--tone); letter-spacing:-.01em; }
.card-blurb { margin:0; font-size:14.5px; color:var(--ink-2); max-width:70ch; }
.card-stat { margin:2px 0 0; font-size:12px; letter-spacing:.05em; text-transform:uppercase; color:var(--ink-3); }
.card-stat strong { color:var(--ink); font-variant-numeric:tabular-nums; }
.work { min-width:840px; }
.work th:first-child, .work td:first-child { padding-left:22px; width:44px; }
.work td:last-child { padding-right:22px; }
.step { color:var(--ink-3); font-size:12px; }
.sender { font-size:12.5px; word-break:break-all; min-width:210px; }
.dim { color:var(--ink-3); font-size:12px; white-space:nowrap; }
.rownote { font-family:"Source Serif 4",serif; font-size:13px; color:var(--ink-2); margin-top:6px; max-width:44ch; word-break:normal; }
.method { font-size:10.5px; letter-spacing:.06em; text-transform:uppercase; font-weight:600; padding:3px 8px; border-radius:4px; white-space:nowrap; display:inline-block; }
.m-one_click_header { background:var(--green-soft); color:var(--green); }
.m-http_header, .m-body_link { background:var(--accent-soft); color:var(--accent-ink); }
.m-mailto_header { background:var(--amber-soft); color:var(--amber); }
.m-account_settings { background:var(--violet-soft); color:var(--violet); }
.m-none_found { background:var(--line-soft); color:var(--ink-3); }
.target { font-size:11.5px; max-width:340px; word-break:break-all; }
.target a { color:var(--accent-ink); text-decoration:none; border-bottom:1px solid color-mix(in srgb, var(--accent) 35%, transparent); }
.target a:hover { border-bottom-color:var(--accent); }
.target a:focus-visible { outline:2px solid var(--accent); outline-offset:2px; border-radius:2px; }
.muted { color:var(--ink-3); }

.keepbox { background:var(--green-soft); border:1px solid color-mix(in srgb, var(--green) 22%, transparent); border-radius:12px; padding:22px; display:flex; flex-direction:column; gap:10px; }
.keepbox h3 { margin:0; font-size:19px; font-weight:600; color:var(--green); }
.keepbox p { margin:0; font-size:14.5px; color:var(--ink-2); max-width:72ch; }
.keepbox .mono { font-size:12px; color:var(--ink); }

.rules { display:grid; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); gap:1px; background:var(--line); border:1px solid var(--line); border-radius:10px; overflow:hidden; }
.rule { background:var(--surface); padding:18px 20px; }
.rule b { display:block; font-family:"Archivo",sans-serif; font-size:14px; margin-bottom:4px; }
.rule span { font-size:14px; color:var(--ink-2); }

footer { border-top:1px solid var(--line); padding-top:22px; color:var(--ink-3); font-size:13.5px; }
footer h2 { font-size:13px; letter-spacing:.14em; text-transform:uppercase; margin:0 0 12px; color:var(--ink-3); }
footer ul { max-width:72ch; padding-left:18px; }
footer li { margin-bottom:7px; }
footer code { font-family:"JetBrains Mono",monospace; font-size:12px; color:var(--ink-2); }

@media (max-width:640px) {
  body { font-size:16px; }
  .wrap { padding:32px 16px 64px; gap:44px; }
  .bar-row { grid-template-columns:minmax(0,1fr) 78px; }
  .bar-track { display:none; }
}
@media (prefers-reduced-motion:reduce) { * { transition:none !important; animation:none !important; } }
"""


def esc(s):
    return html.escape(str(s or ""))


def short(u, n=64):
    return u if len(u) <= n else u[:n] + "…"


def build(summary, worklist, notes, source_label):
    T = summary["totals"]
    total = T["messages"] or 1

    # ---- top senders -------------------------------------------------------
    senders = sorted(summary["senders"], key=lambda s: -s["message_count"])[:10]
    peak = max(s["message_count"] for s in senders) if senders else 1
    top = senders[0] if senders else None
    top_share = (top["message_count"] / total * 100) if top else 0
    ten_share = sum(s["message_count"] for s in senders) / total * 100

    bars = []
    for s in senders:
        pct = s["message_count"] / total * 100
        bars.append(
            '<div class="bar-row" tabindex="0" aria-label="%s: %s messages, %.1f percent '
            'of the mailbox">'
            '<div class="bar-name">%s<span class="bar-addr">%s</span></div>'
            '<div class="bar-track"><div class="bar-fill" style="width:%.2f%%"></div></div>'
            '<div class="bar-val">%s<span class="bar-pct">%.1f%%</span></div></div>'
            % (esc(s["key"]), s["message_count"], pct, esc(s["display_name"]), esc(s["key"]),
               s["message_count"] / peak * 100, f'{s["message_count"]:,}', pct))

    # ---- services ----------------------------------------------------------
    rows = []
    for s in summary["registered_services"]:
        ev = ", ".join("%s&thinsp;×&thinsp;%d" % (k, v)
                       for k, v in sorted(s["account_evidence"].items()) if k in STRONG)
        conf = s["registration_confidence"]
        idle = s["days_since_last"]
        state = "live" if idle is not None and idle <= 90 else (
            "quiet" if idle is not None and idle <= 400 else "dormant")
        rows.append(
            '      <tr>\n'
            '        <td class="svc"><span class="svc-name">%s</span>'
            '<span class="svc-key">%s</span></td>\n'
            '        <td><span class="chip chip-%s">%s</span></td>\n'
            '        <td class="ev">%s</td>\n'
            '        <td class="num">%s</td>\n'
            '        <td class="span"><span class="dates">%s → %s</span>'
            '<span class="state state-%s">%s</span></td>\n'
            '        <td class="note">%s</td>\n'
            '      </tr>'
            % (esc(s["display_name"]), esc(s["key"]), conf, conf, ev,
               f'{s["message_count"]:,}', esc(s["first_seen"]), esc(s["last_seen"]),
               state, state, esc(notes.get(s["key"], ""))))

    # ---- work list ---------------------------------------------------------
    groups = collections.defaultdict(list)
    for r in worklist:
        groups[r["action"]].append(r)

    blocks = []
    for action in ("unsubscribe_then_bulk_delete", "unsubscribe_keep_account", "settings_or_block"):
        items = groups.get(action, [])
        if not items:
            continue
        title, tone, blurb = ACTIONS[action]
        trs = []
        for r in items:
            tgt = r["target"]
            if tgt.startswith("http"):
                link = '<a href="%s" target="_blank" rel="noopener">%s</a>' % (esc(tgt), esc(short(tgt)))
            elif tgt.startswith("mailto:"):
                link = '<span class="mono">%s</span>' % esc(short(tgt))
            else:
                link = '<span class="muted">—</span>'
            note = '<div class="rownote">%s</div>' % esc(r["note"]) if r.get("note") else ""
            trs.append(
                '        <tr>\n'
                '          <td class="num step">%d</td>\n'
                '          <td class="mono sender">%s%s</td>\n'
                '          <td class="num">%s</td>\n'
                '          <td class="mono dim">%s</td>\n'
                '          <td><span class="method m-%s">%s</span></td>\n'
                '          <td class="target">%s</td>\n'
                '        </tr>'
                % (r["step"], esc(r["sender"]), note, f'{r["messages"]:,}', esc(r["last_seen"]),
                   r["method"], METHOD_LABEL[r["method"]], link))
        blocks.append(
            '  <section class="card tone-%s">\n'
            '    <header class="card-head">\n      <h3>%s</h3>\n'
            '      <p class="card-blurb">%s</p>\n'
            '      <p class="card-stat"><strong>%d</strong> senders · <strong>%s</strong> messages</p>\n'
            '    </header>\n    <div class="scroll">\n      <table class="work">\n'
            '        <thead><tr><th>#</th><th>Sender</th><th>Msgs</th><th>Last seen</th>'
            '<th>Route</th><th>Opt-out target</th></tr></thead>\n        <tbody>\n%s\n'
            '        </tbody>\n      </table>\n    </div>\n  </section>'
            % (tone, title, blurb, len(items), f'{sum(i["messages"] for i in items):,}',
               "\n".join(trs)))

    keep = groups.get("keep_archive", [])
    keep_msgs = sum(i["messages"] for i in keep)
    keep_named = ", ".join('<span class="mono">%s</span>' % esc(k["sender"])
                           for k in sorted(keep, key=lambda x: -x["messages"])[:8])

    one_click = sum(1 for r in worklist
                    if r["action"] != "keep_archive" and r["method"] == "one_click_header")
    settings_items = sorted(groups.get("settings_or_block", []),
                            key=lambda x: -x["messages"])
    settings_lead = settings_items[0]["name"] if settings_items else "the biggest sender"

    # ---- headline ----------------------------------------------------------
    if top_share >= 40:
        h1 = ("%s messages, %d senders,<br>and one that is %.0f%% of the pile"
              % (f'{T["messages"]:,}', T["distinct_sending_addresses"], top_share))
    else:
        h1 = ("%s messages, %d senders,<br>%d services behind them"
              % (f'{T["messages"]:,}', T["distinct_sending_addresses"],
                 len(summary["registered_services"])))

    listed = summary["list_only_senders"]
    listed_msgs = sum(x["message_count"] for x in listed)

    parts = ['<!doctype html>',
             '<html lang="en">',
             "<head>",
             '<meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             "<title>Inbox Audit</title>",
             '<link rel="preconnect" href="https://fonts.googleapis.com">',
             '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
             '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
             'family=Archivo:wght@500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600'
             '&family=JetBrains+Mono:wght@400;500&display=swap">',
             "<style>%s</style>" % CSS,
             "</head>",
             "<body>",
             '<div class="wrap">',
             '  <header class="mast">',
             '    <p class="label">Mailbox audit · %s</p>' % esc(summary["generated_at"][:10]),
             "    <h1>%s</h1>" % h1,
             '    <p class="dek">Everything this export knows about which services hold an '
             'account, and what it takes to make the inbox quiet again.</p>',
             '    <p class="src">%s · %s → %s</p>'
             % (esc(source_label), esc(T["date_range"][0]), esc(T["date_range"][1])),
             "  </header>",
             '  <div class="stats">',
             '    <div class="stat"><span class="stat-n">%s</span>'
             '<span class="stat-l">messages parsed</span></div>' % f'{T["messages"]:,}',
             '    <div class="stat"><span class="stat-n">%d</span>'
             '<span class="stat-l">sending addresses across %d brands</span></div>'
             % (T["distinct_sending_addresses"], T["distinct_brands"]),
             '    <div class="stat"><span class="stat-n">%d</span>'
             '<span class="stat-l">services with real account evidence</span></div>'
             % len(summary["registered_services"]),
             '    <div class="stat"><span class="stat-n">%s</span>'
             '<span class="stat-l">carry List-Unsubscribe<br>(%s one-click)</span></div>'
             % (f'{T["with_list_unsubscribe"]:,}', f'{T["one_click_capable"]:,}'),
             "  </div>",
             "  <section>",
             "    <h2>The shape of it</h2>",
             '    <p class="sec-lead">Ten senders account for <strong>%.0f%% of this mailbox'
             '</strong>. The largest, <strong>%s</strong>, is %s messages on its own — '
             '<strong>%.0f%%</strong> of everything.</p>'
             % (ten_share, esc(top["display_name"]) if top else "—",
                f'{top["message_count"]:,}' if top else "0", top_share),
             '    <div class="chart">',
             '      <p class="chart-title">Messages per sending address · top %d of %d</p>'
             % (len(senders), T["distinct_sending_addresses"]),
             "      %s" % "".join(bars),
             "    </div>",
             "  </section>",
             "  <section>",
             "    <h2>Answer 1 · Services with an account</h2>",
             '    <p class="sec-lead">%d services sent account-lifecycle mail — a signup, '
             'a verification code, a security notice, a receipt. <strong>Marketing volume was '
             'never counted as evidence</strong>, so a brand that sent hundreds of promos and '
             'one welcome mail scores no higher than one that sent three messages.</p>'
             % len(summary["registered_services"]),
             '    <div class="services scroll">',
             "      <table>",
             "        <thead><tr><th>Service</th><th>Confidence</th><th>Evidence</th>"
             "<th>Msgs</th><th>Active</th><th>What it is</th></tr></thead>",
             "        <tbody>",
             "\n".join(rows),
             "        </tbody>",
             "      </table>",
             "    </div>",
             '    <p class="body" style="margin-top:20px">A further <strong>%d brands '
             '(%s messages)</strong> sent no account mail at all. Those are lists the address '
             'landed on, not accounts to worry about closing.</p>' % (len(listed), f"{listed_msgs:,}"),
             "  </section>",
             "  <section>",
             "    <h2>Answer 2 · The cleanup plan</h2>",
             '    <p class="sec-lead">Every sender routes to exactly one action. The order below '
             'is cheapest-first: <strong>one-click opt-outs need no login at all</strong>, header '
             'links need a browser, and only a handful require signing in.</p>',
             '    <div class="cards">',
             "\n".join(blocks),
             '      <div class="keepbox">',
             "        <h3>Keep · %d senders · %s messages</h3>" % (len(keep), f"{keep_msgs:,}"),
             "        <p>Receipts, verification codes, sign-in alerts and real correspondence. "
             "There is no opt-out on most of these because there should not be one — a "
             '<span class="mono">No opt-out</span> route on transactional mail is correct '
             "behaviour, not a gap.</p>",
             "        <p>Largest: %s</p>" % keep_named,
             "      </div>",
             "    </div>",
             "  </section>",
             "  <section>",
             "    <h2>Rules that decide the outcome</h2>",
             '    <div class="rules">',
             "      <div class=\"rule\"><b>Unsubscribe before deleting</b><span>Delete first and "
             "the sender simply refills the folder. The exception is a sender that has already "
             "stopped on its own — that mail can go straight to the bin.</span></div>",
             "      <div class=\"rule\"><b>Never unsubscribe from transactional mail</b><span>"
             "Sign-in alerts, appointment mail, receipts. Opting out of these removes the notice "
             "that tells you when something is wrong with the account.</span></div>",
             "      <div class=\"rule\"><b>Order of effort</b><span>One-click → header link "
             "→ footer link → email opt-out → account settings. Working in that "
             "order clears %d senders before you have to log in to anything.</span></div>" % one_click,
             "      <div class=\"rule\"><b>The stubborn ones are last</b><span>%s and the rest of "
             "the settings group publish no opt-out header at all. They need a login, so they are "
             "worth doing in one sitting at the end.</span></div>" % esc(settings_lead),
             "    </div>",
             "  </section>",
             "  <footer>",
             "    <h2>Method &amp; what this cannot tell you</h2>",
             "    <ul>",
             "      <li>Every <code>.eml</code> under the source folder was parsed by "
             "<code>eml_extract.py</code>, regrouped by <code>sender_groups.py</code>, scored by "
             "<code>inbox_summary.py</code> and ordered by <code>worklist.py</code>. "
             "%s messages, %d sending addresses.</li>" % (f'{T["messages"]:,}',
                                                          T["distinct_sending_addresses"]),
             "      <li>Registration is scored on account-lifecycle evidence only — signup, "
             "verification, approval, security, credentials, billing, service ops. Two independent "
             "categories scores <em>confirmed</em>; one scores <em>probable</em>.</li>",
             "      <li>Shared platforms (Constant Contact, Wix, free webmail) were split per "
             "sending address and ESP domains merged onto their parent brand. Without that, one "
             "real account splits into a genuine row plus a phantom list-only row.</li>",
             "      <li><strong>%d route(s) were corrected by hand</strong> after reading the raw "
             "messages, and are recorded in <code>annotations.json</code>. Senders that ship no "
             "<code>List-Unsubscribe</code> header and wrap their footer opt-out in a click "
             "tracker can still be mis-scored the same way.</li>"
             % sum(1 for r in worklist if r.get("note")),
             "      <li><em>Confirmed</em> means account mail <em>arrived</em> at some point — "
             "not that the account is still open. <code>Last seen</code> is the honest bound.</li>",
             "      <li>Subject-line evidence matching is English-only, so a non-English signup or "
             "receipt is not scored and its sender may appear as list-only.</li>",
             "    </ul>",
             "  </footer>",
             "</div>",
             "</body>",
             "</html>"]
    return "\n".join(parts) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render the audit report as HTML.")
    ap.add_argument("summary", help="report/summary.json from stage 2")
    ap.add_argument("worklist", help="worklist.json from stage 3")
    ap.add_argument("-o", "--out", default="inbox_audit.html")
    ap.add_argument("--annotations", default=None)
    ap.add_argument("--source", default="mail export", help="label shown under the headline")
    args = ap.parse_args(argv)

    summary = json.load(open(args.summary, encoding="utf-8"))
    worklist = json.load(open(args.worklist, encoding="utf-8"))
    notes = {}
    if args.annotations:
        with open(args.annotations, encoding="utf-8") as fh:
            notes = json.load(fh).get("service_notes", {})

    doc = build(summary, worklist, notes, args.source)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(doc)
    print(f"stage 4: wrote {args.out} ({len(doc):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
