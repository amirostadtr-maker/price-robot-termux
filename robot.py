#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PriceRobot – Termux All-in-One
"""
import os, sys, json, time, asyncio, logging, pathlib, hashlib, queue, threading
from datetime import datetime
from typing import List, Dict, Optional
from flask import Flask, request, jsonify, render_template_string, send_file, redirect, url_for, flash

# ---------------- Logger ----------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
log = logging.getLogger("robot")

# ---------------- Config ----------------
BASE_DIR = pathlib.Path.home() / "pricebot"
BASE_DIR.mkdir(exist_ok=True)
DEFAULT_TERMS = ["گوشی سامسونگ A54", "لپ تاپ لنوو ThinkPad", "ساعت هوشمند اپل سری ۹"]

# ---------------- Price Extractor ----------------
class PriceExtractor:
    def extract(self, text: str) -> Optional[Dict]:
        import re
        text = text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
        patterns = {"toman": [r"([\d,]+)\s?تومان"], "rial": [r"([\d,]+)\s?ریال"], "dollar": [r"\$([\d,]+)"], "dirham": [r"([\d,]+)\s?درهم"]}
        rates = {"rial": 0.1, "dollar": 55_000, "dirham": 15_000, "toman": 1}
        for curr, pats in patterns.items():
            for pat in pats:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    num = float(m.group(1).replace(",", ""))
                    return {"original": num, "currency": curr, "toman": num * rates[curr]}
        return None

# ---------------- Async Scraper ----------------
class AsyncScraper:
    async def init(self): pass
    async def close(self): pass
    async def scrape(self, url: str) -> str:
        import aiohttp
        async with aiohttp.ClientSession() as sess:
            async with sess.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15) as resp:
                return await resp.text()

# ---------------- Analyzer ----------------
class Analyzer:
    def run(self, products: List[Dict]) -> Dict:
        import pandas as pd
        df = pd.DataFrame(products)
        if df.empty: return {"total": 0}
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
        df = df.dropna(subset=["price"])
        return {
            "total": len(df), "min": df["price"].min(),
            "max": df["price"].max(), "mean": df["price"].mean(), "median": df["price"].median(),
        }

# ---------------- Notifier ----------------
class Notifier:
    def save_excel(self, report: Dict) -> pathlib.Path:
        import pandas as pd
        products = []
        for r in report["results"]:
            for p in r["products"]:
                products.append({"Search Term": r["search_term"], "Name": p["name"], "Price (Toman)": p["price"], "Website": p["website"], "Country": p["country"], "URL": p["url"]})
        df = pd.DataFrame(products)
        path = BASE_DIR / f"price_report_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        df.to_excel(path, index=False)
        log.info("Excel saved: %s", path)
        return path

# ---------------- Web Robot ----------------
class WebRobot:
    def __init__(self):
        self.scraper = AsyncScraper()
        self.extractor = PriceExtractor()
        self.analyzer = Analyzer()
        self.notifier = Notifier()

    async def search(self, terms: List[str], task_id: str):
        await self.scraper.init()
        all_results = []
        for term in terms:
            log.info("Web search: %s", term)
            urls = [
                f"https://torob.ir/search/?query={term.replace(' ', '%20')}",
                f"https://divar.ir/s/tehran?q={term.replace(' ', '%20')}",
                f"https://www.amazon.com/s?k={term.replace(' ', '+')}",
            ]
            tasks = [self._fetch_one(url, term) for url in urls]
            results = await asyncio.gather(*tasks)
            products = [p for res in results for p in res]
            analysis = self.analyzer.run(products)
            all_results.append({"search_term": term, "products": products, "analysis": analysis})
        await self.scraper.close()
        report = {"summary": {"total": sum(len(r["products"]) for r in all_results)}, "results": all_results}
        excel_path = self.notifier.save_excel(report)
        log.info("Web task %s finished", task_id)
        return excel_path

    async def _fetch_one(self, url: str, term: str) -> List[Dict]:
        from bs4 import BeautifulSoup
        try:
            html = await self.scraper.scrape(url)
            soup = BeautifulSoup(html, "lxml")
            products = []
            for card in soup.select(".product, .item, [data-testid='product-card']")[:5]:
                name = card.get_text(" ", strip=True)[:100]
                price_data = self.extractor.extract(card.get_text(" ", strip=True))
                if price_data:
                    products.append({
                        "name": name, "price": price_data["toman"],
                        "original_currency": price_data["currency"],
                        "website": url.split("/")[2], "country": "Iran", "url": url,
                    })
            return products
        except Exception as e:
            log.error("Fetch error %s: %s", url, e)
            return []


# ---------------- Flask App ----------------
app = Flask(__name__)
app.secret_key = "price_robot_secret_123"
results_store: Dict[str, Dict] = {}


def run_in_thread(terms: List[str], task_id: str):
    robot = WebRobot()
    try:
        excel_path = asyncio.run(robot.search(terms, task_id))
        results_store[task_id] = {"excel_path": str(excel_path), "status": "done"}
    except Exception as e:
        log.exception("Robot failed")
        results_store[task_id] = {"status": "failed", "reason": str(e)}


INDEX_HTML = """
<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><title>PriceRobot</title>
<style>body{margin:0;font-family:Tahoma;background:#f8f9fa;color:#212529}
header{background:#0d6efd;color:white;padding:1rem;text-align:center}
main{padding:2rem;max-width:900px;margin:auto}
textarea{width:100%;resize:vertical;padding:.5rem}
button{background:#198754;color:white;border:none;padding:.5rem 1.5rem;border-radius:.25rem;cursor:pointer}
button:hover{background:#157347}
table{width:100%;border-collapse:collapse;background:white;border-radius:.5rem;overflow:hidden}
th{background:#0d6efd;color:white;padding:.75rem}td{padding:.75rem;text-align:center}
.actions{display:flex;gap:1rem;justify-content:center;margin-top:2rem}
</style></head><body>
<header><h1>🤖 ربات قیمت‌یاب – نسخه وب</h1></header><main>
{% with messages = get_flashed_messages(with_categories=true) %}
  {% if messages %}
    <div class="alerts">
      {% for category, message in messages %}
        <div class="alert alert-{{ category }}">{{ message }}</div>
      {% endfor %}
    </div>
  {% endif %}
{% endwith %}
{% block content %}
<section class="form-box">
  <h2>ورودی کالاها</h2>
  <form method="post">
    <label>نام کالاها (هر خط یک مورد – حداکثر ۱۰)</label>
    <textarea name="terms" rows="6" placeholder="گوشی سامسونگ A54\nلپ تاپ لنوو ThinkPad"></textarea>
    <button type="submit">🔍 شروع جستجو</button>
  </form>
</section>
<section class="samples">
  <h3>نمونه‌های آماده</h3>
  <ul>
    {% for item in sample_terms %}
      <li>{{ item }}</li>
    {% endfor %}
  </ul>
</section>
{% endblock %}
</body></html>
"""

RESULT_HTML = """
{% extends "base.html" %}{% block content %}
<h2>📊 نتیجه‌ی جستجو</h2>
<div id="summary"><p>کل محصولات: <strong>{{ report.summary.total }}</strong></p></div>
<table><thead><tr>
<th>نام کالا</th><th>تعداد</th><th>کمترین (تومان)</th><th>میانگین (تومان)</th><th>بیشترین (تومان)</th>
</tr></thead><tbody>
{% for r in report.results %}
<tr>
  <td>{{ r.search_term }}</td><td>{{ r.products|length }}</td>
  <td>{{ "{:,.0f}".format(r.analysis.min or 0) }}</td>
  <td>{{ "{:,.0f}".format(r.analysis.mean or 0) }}</td>
  <td>{{ "{:,.0f}".format(r.analysis.max or 0) }}</td>
</tr>
{% endfor %}
</tbody></table>
<div class="actions">
  <button onclick="location.href='{{ url_for('api_download', task_id=request.view_args.task_id) }}'">📥 دانلود Excel</button>
  <button onclick="location.href='{{ url_for('index') }}'"> 🔙 جستجوی جدید</button>
</div>
{% endblock %}
"""

WAITING_HTML = """
{% extends "base.html" %}{% block content %}
<h2>⏳ در حال پردازش...</h2>
<p>لطفاً چند لحظه صبر کنید...</p>
<script>
let taskId = "{{ task_id }}";
let checkInterval = setInterval(async () => {
  let res = await fetch(`/api/status/${taskId}`);
  let data = await res.json();
  if (data.status === "done") {
    clearInterval(checkInterval);
    location.replace(`/result/${taskId}`);
  }
}, 2000);
</script>
{% endblock %}
"""


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        raw = request.form.get("terms", "").strip()
        if not raw:
            flash("لطفاً حداقل یک نام کالا وارد کنید", "warning")
            return redirect(request.url)
        terms = [t.strip() for t in raw.split("\n") if t.strip()][:10]
        task_id = str(int(time.time()))
        results_store[task_id] = {"status": "processing"}
        threading.Thread(target=run_in_thread, args=(terms, task_id), daemon=True).start()
        flash("جستجو شروع شد! نتیجه به‌زودی آماده می‌شود...", "info")
        return redirect(url_for("result", task_id=task_id))
    return render_template_string(INDEX_HTML, sample_terms=DEFAULT_TERMS)


@app.route("/result/<task_id>")
def result(task_id):
    if task_id not in results_store:
        return render_template_string(WAITING_HTML, task_id=task_id)
    report = results_store[task_id]
    if report.get("status") == "failed":
        return f"خطا: {report.get('reason')}", 500
    return render_template_string(RESULT_HTML, report=report)


@app.route("/api/status/<task_id>")
def api_status(task_id):
    if task_id not in results_store:
        return jsonify({"status": "not_found"}), 404
    return jsonify({"status": "done", "report": results_store[task_id]})


@app.route("/api/download/<task_id>")
def api_download(task_id):
    if task_id not in results_store:
        return "Not found", 404
    path = results_store[task_id].get("excel_path")
    if path and pathlib.Path(path).exists():
        return send_file(path, as_attachment=True)
    return "File not ready", 202


# ------------------------- CLI Entry -------------------------
def cli_run():
    log.info("🚀 Starting Flask on http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)

if __name__ == "__main__":
    cli_run()
