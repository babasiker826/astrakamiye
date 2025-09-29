from flask import Flask, render_template, request, jsonify, session
import requests
import threading
import time
from datetime import datetime, timedelta
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Güvenlik için secret key

# Hesaplar - Gerçek deployda bunları environment variables olarak saklayın
HESAPLAR = [
    ("905428313748", "1234"),
    ("905352577415", "1234"),
    ("905426960640", "0101"),
    ("905422653362", "2525"),
    ("905425928280", "1234"),
    ("905421515430", "1234"),
]
TARGET_MSISDN = "905426960640"

# Global değişkenler
last_run_time = None
is_running = False
logs = []

def log_message(message, message_type="info"):
    """Log mesajlarını kaydet"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {
        "timestamp": timestamp,
        "message": message,
        "type": message_type  # info, success, warning, error
    }
    logs.append(log_entry)
    # Log sayısını sınırla
    if len(logs) > 100:
        logs.pop(0)
    print(f"[{timestamp}] {message}")

def otp_al_ve_transfer(token, msisdn, pin, miktar):
    try:
        log_message(f"{msisdn} için OTP alınıyor...", "info")
        
        url_otp = "https://3uptzlakwi.execute-api.eu-west-1.amazonaws.com/api/user/pin/get-otp"
        headers_otp = {
            "Content-Type": "application/json; charset=UTF-8",
            "User-Agent": "okhttp/4.12.0",
            "authorization": "bearer " + token,
            "x-client-device": "ANDROID"
        }
        r = requests.post(url_otp, json={"pin": pin}, headers=headers_otp)
        js = r.json()
        
        pinOtp = js.get("otp")
        if not pinOtp:
            log_message(f"{msisdn} - OTP alınamadı", "error")
            return

        log_message(f"{msisdn} - Transfer yapılıyor: {miktar} FREEBYTE", "info")
        
        url_tx = "https://utxk52xqxk.execute-api.eu-west-1.amazonaws.com/beta/transactions"
        headers_tx = {
            "Content-Type": "application/json; charset=UTF-8",
            "User-Agent": "okhttp/4.12.0",
            "authorization": "bearer " + token,
            "x-client-device": "ANDROID"
        }
        payload_tx = {
            "amount": miktar,
            "pinOtp": pinOtp,
            "toMsisdn": TARGET_MSISDN
        }
        r2 = requests.post(url_tx, json=payload_tx, headers=headers_tx)
        
        if r2.status_code == 200:
            log_message(f"{msisdn} - {miktar} FREEBYTE gönderildi → {TARGET_MSISDN}", "success")
        else:
            log_message(f"{msisdn} - Transfer başarısız: {r2.status_code}", "error")
    except Exception as e:
        log_message(f"{msisdn} - Transfer hatası: {str(e)}", "error")

def bakiye_al(token):
    try:
        url = "https://3uptzlakwi.execute-api.eu-west-1.amazonaws.com/api/user/balance"
        headers = {
            "authorization": "bearer " + token,
            "User-Agent": "okhttp/4.12.0"
        }
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            return r.json().get("balance", 0)
        return 0
    except Exception as e:
        log_message(f"Bakiye alma hatası: {str(e)}", "error")
        return 0

def odul_al(token):
    try:
        url = "https://3uptzlakwi.execute-api.eu-west-1.amazonaws.com/api/user/reward"
        headers = {"authorization": "bearer " + token}
        requests.post(url, headers=headers)
        log_message("Günlük ödül alındı", "info")
    except Exception as e:
        log_message(f"Ödül alma hatası: {str(e)}", "error")

def coklu_reklam(token, tekrar=4):
    try:
        url = "https://3uptzlakwi.execute-api.eu-west-1.amazonaws.com/api/user/ad"
        headers = {"authorization": "bearer " + token}
        for i in range(tekrar):
            requests.post(url, headers=headers)
            log_message(f"Reklam izlendi ({i+1}/{tekrar})", "info")
            time.sleep(2)
    except Exception as e:
        log_message(f"Reklam izleme hatası: {str(e)}", "error")

def manuel_pin_giris(msisdn, pin):
    url = "https://3uptzlakwi.execute-api.eu-west-1.amazonaws.com/api/auth/pin/verify"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "okhttp/4.12.0"
    }
    data = {
        "msisdn": msisdn,
        "osType": "ANDROID",
        "pin": pin
    }
    try:
        r = requests.post(url, json=data, headers=headers)
        js = r.json()
        if "token" in js:
            token = js["token"]
            log_message(f"{msisdn} - Giriş başarılı!", "success")

            odul_al(token)
            coklu_reklam(token, tekrar=4)

            if msisdn == TARGET_MSISDN:
                log_message(f"{msisdn} - Kendi numarasına transfer atlandı", "warning")
            else:
                bakiye = bakiye_al(token)
                if bakiye > 0:
                    otp_al_ve_transfer(token, msisdn, pin, bakiye)
                else:
                    log_message(f"{msisdn} - Gönderilecek bakiye yok", "warning")
        else:
            log_message(f"{msisdn} - Giriş hatası: {js.get('message', 'Bilinmeyen hata')}", "error")
    except Exception as e:
        log_message(f"{msisdn} - Giriş hatası: {str(e)}", "error")

def tum_hesaplari_islem():
    global is_running, last_run_time
    if is_running:
        return
    
    is_running = True
    log_message("Tüm hesaplar için işlem başlatılıyor...", "info")
    
    for numara, pin in HESAPLAR:
        log_message(f"{numara} işleniyor...", "info")
        manuel_pin_giris(numara, pin)
        time.sleep(2)  # API'ye aşırı yüklenmemek için
    
    last_run_time = datetime.now()
    is_running = False
    log_message("Tüm işlemler tamamlandı!", "success")

def otomatik_islem_dongusu():
    """24 saatte bir otomatik çalışacak döngü"""
    while True:
        try:
            # Her saat kontrol et, 24 saat dolduysa çalıştır
            if last_run_time is None or (datetime.now() - last_run_time) >= timedelta(hours=24):
                log_message("24 saat doldu, otomatik işlem başlatılıyor...", "info")
                tum_hesaplari_islem()
            
            time.sleep(3600)  # 1 saat bekle
        except Exception as e:
            log_message(f"Otomatik işlem hatası: {str(e)}", "error")
            time.sleep(300)  # Hata durumunda 5 dakika bekle

@app.route('/')
def index():
    global last_run_time
    next_run = last_run_time + timedelta(hours=24) if last_run_time else "Henüz çalışmadı"
    return render_template('index.html', 
                         last_run=last_run_time,
                         next_run=next_run,
                         hesaplar=HESAPLAR,
                         target=TARGET_MSISDN,
                         is_running=is_running,
                         logs=reversed(logs[-20:]))  # Son 20 log

@app.route('/run_once')
def run_once():
    if not is_running:
        threading.Thread(target=tum_hesaplari_islem, daemon=True).start()
        return jsonify({"status": "success", "message": "İşlem başlatıldı"})
    return jsonify({"status": "error", "message": "Sistem şu anda çalışıyor"})

@app.route('/status')
def status():
    global last_run_time, is_running, logs
    next_run = last_run_time + timedelta(hours=24) if last_run_time else "Henüz çalışmadı"
    return jsonify({
        "is_running": is_running,
        "last_run": last_run_time.strftime("%Y-%m-%d %H:%M:%S") if last_run_time else None,
        "next_run": next_run.strftime("%Y-%m-%d %H:%M:%S") if isinstance(next_run, datetime) else next_run,
        "logs": logs[-10:]  # Son 10 log
    })

@app.route('/clear_logs')
def clear_logs():
    global logs
    logs.clear()
    return jsonify({"status": "success", "message": "Loglar temizlendi"})

if __name__ == '__main__':
    # Otomatik işlem thread'ini başlat
    threading.Thread(target=otomatik_islem_dongusu, daemon=True).start()
    app.run(debug=False, host='0.0.0.0', port=5000)
