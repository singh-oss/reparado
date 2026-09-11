#!/usr/bin/env python3
"""Velqio – Stripe Auto-Setup (läuft auf dem Server).
Liest STRIPE_SECRET_KEY + APP_BASE_URL aus config.py, legt (idempotent) die 3 Abo-Produkte
+ monatliche Preise (Basic 49,90 / Pro 84,90 / AI 99,90 €) an, richtet den Webhook-Endpunkt
ein und schreibt Price-IDs + Webhook-Secret zurück in config.py. Kein pip nötig (Stdlib)."""
import json, os, re, urllib.request, urllib.parse, urllib.error

CFG = "/opt/reparado/config.py"

def cfgval(name):
    if not os.path.exists(CFG): return ""
    s = open(CFG).read()
    m = re.search(r'(?m)^' + re.escape(name) + r'\s*=\s*["\'](.*?)["\']', s)
    return m.group(1) if m else ""

def setcfg(vals):
    s = open(CFG).read() if os.path.exists(CFG) else ""
    for k, v in vals.items():
        line = k + ' = "' + v + '"'
        if re.search(r'(?m)^' + re.escape(k) + r'\s*=', s):
            s = re.sub(r'(?m)^' + re.escape(k) + r'\s*=.*', line, s)
        else:
            s = s.rstrip() + "\n" + line + "\n"
    open(CFG, "w").write(s)

KEY = cfgval("STRIPE_SECRET_KEY")
BASE = (cfgval("APP_BASE_URL") or "https://velqio.de").rstrip("/")
if not KEY.startswith("sk_"):
    raise SystemExit("FEHLER: Kein gueltiger STRIPE_SECRET_KEY in config.py gefunden.")

def stripe(method, path, params=None):
    data = urllib.parse.urlencode(params, doseq=True).encode() if params is not None else None
    req = urllib.request.Request("https://api.stripe.com/v1/" + path, data=data, method=method)
    req.add_header("Authorization", "Bearer " + KEY)
    if data is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise SystemExit("Stripe-Fehler bei " + method + " " + path + ": " + e.read().decode())

PLANS = [("basic", "Velqio Basic", 4990), ("pro", "Velqio Pro", 8490), ("ai", "Velqio AI", 9990)]

# vorhandene Produkte per metadata (velqio_plan) wiederverwenden
existing = {}
prods = stripe("GET", "products?limit=100&active=true")
for p in prods.get("data", []):
    tag = (p.get("metadata") or {}).get("velqio_plan")
    if tag:
        existing[tag] = p["id"]

price_ids = {}
for plan, name, amount in PLANS:
    pid = existing.get(plan)
    if not pid:
        prod = stripe("POST", "products", {"name": name, "metadata[velqio_plan]": plan})
        pid = prod["id"]
    found = ""
    prices = stripe("GET", "prices?product=" + pid + "&active=true&limit=100")
    for pr in prices.get("data", []):
        rec = pr.get("recurring") or {}
        if pr.get("unit_amount") == amount and pr.get("currency") == "eur" and rec.get("interval") == "month":
            found = pr["id"]; break
    if not found:
        pr = stripe("POST", "prices", {"product": pid, "unit_amount": amount, "currency": "eur", "recurring[interval]": "month"})
        found = pr["id"]
    price_ids[plan] = found

# Webhook-Endpunkt fuer unsere URL: vorhandenen wiederverwenden, sonst anlegen (Secret nur bei Neuanlage)
url = BASE + "/api/stripe/webhook"
whsec = cfgval("STRIPE_WEBHOOK_SECRET")
hooks = stripe("GET", "webhook_endpoints?limit=100")
have = [h for h in hooks.get("data", []) if h.get("url") == url]
if not have:
    evs = ["checkout.session.completed", "customer.subscription.created",
           "customer.subscription.updated", "customer.subscription.deleted"]
    wh = stripe("POST", "webhook_endpoints", {"url": url, "enabled_events[]": evs})
    whsec = wh.get("secret") or whsec

vals = {"STRIPE_PRICE_BASIC": price_ids["basic"], "STRIPE_PRICE_PRO": price_ids["pro"], "STRIPE_PRICE_AI": price_ids["ai"]}
if whsec:
    vals["STRIPE_WEBHOOK_SECRET"] = whsec
setcfg(vals)
print("OK  Basic=%s  Pro=%s  AI=%s  Webhook=%s  whsec=%s" % (
    price_ids["basic"], price_ids["pro"], price_ids["ai"], url, "gesetzt" if whsec else "FEHLT(bestehender Webhook? Secret im Dashboard pruefen)"))
