import cloudscraper
import json
import re
import os
import requests
import time

# --- 설정 (GitHub Secrets) ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
DB_FILE = "sent_urls.txt"
EXPIRATION_SEC = 24 * 60 * 60  # 24시간 (초 단위) ㅡ,.ㅡ

def get_html(url):
    scraper = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True}
    )
    res = scraper.get(f"{url}&_={int(time.time())}")
    return res.text if res.status_code == 200 else None

def extract_balanced_json(html, start_marker):
    start_idx = html.find(start_marker)
    if start_idx == -1: return None
    json_start_idx = html.find('{', start_idx)
    if json_start_idx == -1: return None
    count = 0
    for i in range(json_start_idx, len(html)):
        if html[i] == '{': count += 1
        elif html[i] == '}':
            count -= 1
            if count == 0: return html[json_start_idx : i + 1]
    return None

def load_db():
    """파일에서 데이터를 읽고 24시간이 지난 항목은 즉시 필터링합니다."""
    valid_db = {}
    now = time.time()
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            for line in f:
                try:
                    ts, url = line.strip().split("|", 1)
                    if now - float(ts) < EXPIRATION_SEC:
                        valid_db[url] = ts
                except ValueError:
                    continue
    return valid_db

def save_db(db_dict):
    """현재 유효한 데이터만 파일에 기록합니다."""
    with open(DB_FILE, "w") as f:
        for url, ts in db_dict.items():
            f.write(f"{ts}|{url}\n")

def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ 텔레GRAM 설정 미비")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML", "disable_web_page_preview": False}
    requests.post(url, json=payload)

def parse_and_notify(name, url, db_dict):
    html = get_html(url)
    if not html: return db_dict

    raw_json = extract_balanced_json(html, 'window.__INITIAL_STATE__=')
    if not raw_json: return db_dict

    new_articles = []
    now = time.time()
    try:
        raw_json = raw_json.replace(":undefined", ":null")
        data = json.loads(raw_json)
        
        articles = []
        for path in [['page', 'news', 'mostRead'], ['news', 'mostRead']]:
            temp = data
            for key in path:
                if isinstance(temp, dict): temp = temp.get(key, {})
            if isinstance(temp, list) and len(temp) > 0:
                articles = temp
                break

        domain = "https://www.newsnow.co.uk" if "co.uk" in url else "https://www.newsnow.com"
        
        for art in articles[:10]:
            title = art.get('title')
            link = art['url'] if art['url'].startswith('http') else domain + art['url']
            
            if link not in db_dict:
                new_articles.append(f"• {title}\n{link}")
                db_dict[link] = str(now) # 발송 시간과 함께 저장
                
    except Exception as e:
        print(f"❌ {name} 파싱 에러: {e}")
        
    if new_articles:
        msg = f"🏆 <b>[{name} 인기 뉴스]</b>\n\n" + "\n\n".join(new_articles)
        send_telegram(msg)
        print(f"✅ {name}: {len(new_articles)}개 신규 뉴스 발송")
    
    return db_dict

if __name__ == "__main__":
    current_db = load_db()
    current_db = parse_and_notify("NewsNow US", "https://www.newsnow.com/us/Sports/Soccer?type=ts", current_db)
    current_db = parse_and_notify("NewsNow UK", "https://www.newsnow.co.uk/h/Sport/Football/International/2026+FIFA+World+Cup?type=ts", current_db)
    save_db(current_db)
