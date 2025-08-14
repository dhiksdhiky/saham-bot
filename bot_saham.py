import os
import yfinance as yf
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# --- (DATABASE LOKAL) Konfigurasi file untuk menyimpan data ---
# Di Railway, ini akan disimpan secara persisten di volume
DATA_FILE = "bot_data.json"

# --- Fungsi untuk memuat dan menyimpan data ---
def load_data():
    """Memuat data user dari file JSON."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {"portfolios": {}, "alerts": {}}

def save_data(data):
    """Menyimpan data user ke file JSON."""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# --- (Semua fungsi get_stock_... Anda tetap sama) ---
def get_stock_price_info(ticker_symbol):
    if not ticker_symbol.upper().endswith('.JK'): ticker_symbol += '.JK'
    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info
    if 'regularMarketPrice' not in info or info['regularMarketPrice'] is None: return None
    return {'harga_terakhir': info.get('regularMarketPrice', 0), 'nama_perusahaan': info.get('longName', ticker_symbol.upper())}

def get_stock_info(ticker_symbol):
    if not ticker_symbol.upper().endswith('.JK'): ticker_symbol += '.JK'
    ticker = yf.Ticker(ticker_symbol)
    info = ticker.info
    if 'regularMarketPrice' not in info or info['regularMarketPrice'] is None: return f"❌ Kode saham '{ticker_symbol.upper().replace('.JK','')}' tidak ditemukan."
    nama_perusahaan, harga_terakhir, harga_sebelumnya = info.get('longName', 'N/A'), info.get('regularMarketPrice', 0), info.get('previousClose', 0)
    perubahan = harga_terakhir - harga_sebelumnya
    persentase_perubahan = (perubahan / harga_sebelumnya) * 100 if harga_sebelumnya else 0
    emoji = "📈" if perubahan >= 0 else "📉"
    pesan = (
        f"{emoji} *{nama_perusahaan} ({ticker_symbol.upper().replace('.JK','')})*\n\n"
        f"Harga Terakhir: *Rp {harga_terakhir:,.0f}*\n"
        f"Perubahan: *{'+' if perubahan >= 0 else ''}{perubahan:,.0f} ({'+' if persentase_perubahan >= 0 else ''}{persentase_perubahan:.2f}%)*\n\n"
        f"Tertinggi Hari Ini: Rp {info.get('dayHigh', 0):,.0f}\n"
        f"Terendah Hari Ini: Rp {info.get('dayLow', 0):,.0f}\n"
        f"Volume: {info.get('volume', 0):,}"
    )
    return pesan


# --- (Handler Perintah diperbarui dengan penyimpanan data) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mengirim pesan selamat datang."""
    await update.message.reply_markdown(
        "Selamat datang di Bot PantauSaham!\n\n"
        "Gunakan perintah berikut:\n"
        "📈 `/cek [KODE]` - Cek harga saham.\n"
        "➕ `/tambah [KODE] [LOT] [HARGA]` - Tambah ke portfolio.\n"
        "📒 `/portfolio` - Lihat portfolio Anda.\n"
        "🔔 `/alert [KODE] [diatas/dibawah] [HARGA]` - Setel notifikasi harga.\n"
        "🗑️ `/hapus_alert [KODE]` - Hapus semua alert untuk satu saham."
    )

async def cek_saham(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        ticker = context.args[0].upper()
        info_saham = get_stock_info(ticker)
        await update.message.reply_markdown(info_saham)
    except IndexError:
        await update.message.reply_text("Format: `/cek [KODE_SAHAM]`")

async def tambah_saham(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    try:
        kode, lot, harga_beli = context.args[0].upper(), int(context.args[1]), float(context.args[2])
        data = load_data()
        if user_id not in data["portfolios"]: data["portfolios"][user_id] = []
        data["portfolios"][user_id].append({'kode': kode, 'lot': lot, 'harga_beli': harga_beli})
        save_data(data)
        await update.message.reply_text(f"✅ Berhasil ditambahkan: {kode} {lot} lot @ {harga_beli:,.0f}")
    except (IndexError, ValueError):
        await update.message.reply_text("Format: `/tambah [KODE] [LOT] [HARGA_BELI]`")

async def lihat_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    data = load_data()
    if user_id not in data["portfolios"] or not data["portfolios"][user_id]:
        await update.message.reply_text("Portfolio Anda kosong.")
        return
    
    await update.message.reply_text("📊 Menganalisis portfolio...")
    pesan = "*📒 Portfolio Anda*\n\n"
    total_modal, total_nilai_sekarang = 0, 0
    
    for saham in data["portfolios"][user_id]:
        kode, lot, harga_beli = saham['kode'], saham['lot'], saham['harga_beli']
        modal = lot * 100 * harga_beli
        total_modal += modal
        info_harga = get_stock_price_info(kode)
        
        if info_harga:
            harga_sekarang = info_harga['harga_terakhir']
            nilai_sekarang = lot * 100 * harga_sekarang
            total_nilai_sekarang += nilai_sekarang
            profit_loss = nilai_sekarang - modal
            persen_pl = (profit_loss / modal) * 100 if modal else 0
            emoji_pl = "🟢" if profit_loss >= 0 else "🔴"
            pesan += f"*{kode}* - {lot} Lot\n" \
                     f"Avg Beli: Rp {harga_beli:,.0f}\n" \
                     f"Harga Skrg: Rp {harga_sekarang:,.0f}\n" \
                     f"{emoji_pl} P/L: *{persen_pl:+.2f}%* (Rp {profit_loss:,.0f})\n\n"
        else:
            pesan += f"*{kode}* - {lot} Lot\n Gagal mengambil harga.\n\n"
            total_nilai_sekarang += modal

    total_pl = total_nilai_sekarang - total_modal
    total_persen_pl = (total_pl / total_modal) * 100 if total_modal else 0
    emoji_total = "🔼" if total_pl >= 0 else "🔽"
    pesan += f"------------------------------\n*Ringkasan:*\n" \
             f"Total Modal: Rp {total_modal:,.0f}\n" \
             f"Nilai Aset Kini: Rp {total_nilai_sekarang:,.0f}\n" \
             f"{emoji_total} Total P/L: *{total_persen_pl:+.2f}%* (Rp {total_pl:,.0f})"
    await update.message.reply_markdown(pesan)

# --- FUNGSI BARU UNTUK ALERT ---
async def set_alert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    try:
        kode = context.args[0].upper()
        kondisi = context.args[1].lower()
        harga_target = float(context.args[2])

        if kondisi not in ["diatas", "dibawah"]:
            await update.message.reply_text("Kondisi harus 'diatas' atau 'dibawah'.")
            return
        
        data = load_data()
        if user_id not in data["alerts"]: data["alerts"][user_id] = []
        
        # Hapus alert lama untuk kode yang sama agar tidak duplikat
        data["alerts"][user_id] = [a for a in data["alerts"][user_id] if a['kode'] != kode]
        
        data["alerts"][user_id].append({
            "kode": kode,
            "kondisi": kondisi,
            "harga_target": harga_target
        })
        save_data(data)
        await update.message.reply_text(f"🔔 Alert terpasang! Saya akan memberitahu Anda jika {kode} bergerak {kondisi} Rp {harga_target:,.0f}.")

    except (IndexError, ValueError):
        await update.message.reply_text("Format: `/alert [KODE] [diatas/dibawah] [HARGA]`")

async def hapus_alert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    try:
        kode_to_delete = context.args[0].upper()
        data = load_data()
        if user_id in data["alerts"]:
            original_count = len(data["alerts"][user_id])
            data["alerts"][user_id] = [a for a in data["alerts"][user_id] if a['kode'] != kode_to_delete]
            
            if len(data["alerts"][user_id]) < original_count:
                save_data(data)
                await update.message.reply_text(f"🗑️ Semua alert untuk saham *{kode_to_delete}* telah dihapus.", parse_mode='Markdown')
            else:
                await update.message.reply_text(f"Tidak ada alert aktif untuk saham *{kode_to_delete}*.", parse_mode='Markdown')
        else:
            await update.message.reply_text("Anda tidak memiliki alert aktif.")
    except IndexError:
        await update.message.reply_text("Format: `/hapus_alert [KODE_SAHAM]`")


# --- MESIN PEMINDAI ALERT (untuk dijalankan terpisah) ---
async def check_alerts(context: ContextTypes.DEFAULT_TYPE):
    """Fungsi ini akan memeriksa semua alert yang tersimpan."""
    print("Mulai memeriksa alerts...")
    data = load_data()
    alerts_to_remove = {}

    for user_id, user_alerts in data["alerts"].items():
        if not user_alerts: continue
        
        for alert in user_alerts:
            kode = alert["kode"]
            info_harga = get_stock_price_info(kode)
            
            if info_harga:
                harga_sekarang = info_harga["harga_terakhir"]
                kondisi = alert["kondisi"]
                harga_target = alert["harga_target"]
                
                pesan_notifikasi = ""
                alert_terpicu = False

                if kondisi == "diatas" and harga_sekarang >= harga_target:
                    pesan_notifikasi = f"🚀 ALERT HARGA! Saham *{kode}* telah mencapai target di atas *Rp {harga_target:,.0f}*.\nHarga saat ini: Rp {harga_sekarang:,.0f}"
                    alert_terpicu = True

                elif kondisi == "dibawah" and harga_sekarang <= harga_target:
                    pesan_notifikasi = f"🔻 ALERT HARGA! Saham *{kode}* telah mencapai target di bawah *Rp {harga_target:,.0f}*.\nHarga saat ini: Rp {harga_sekarang:,.0f}"
                    alert_terpicu = True
                
                if alert_terpicu:
                    try:
                        await context.bot.send_message(chat_id=user_id, text=pesan_notifikasi, parse_mode='Markdown')
                        # Tandai alert untuk dihapus setelah notifikasi terkirim
                        if user_id not in alerts_to_remove: alerts_to_remove[user_id] = []
                        alerts_to_remove[user_id].append(alert)
                    except Exception as e:
                        print(f"Gagal mengirim alert ke {user_id}: {e}")

    # Hapus semua alert yang sudah terpicu dari database
    if alerts_to_remove:
        for user_id, alerts in alerts_to_remove.items():
            for alert in alerts:
                if alert in data["alerts"][user_id]:
                    data["alerts"][user_id].remove(alert)
        save_data(data)
        print(f"Menghapus {sum(len(v) for v in alerts_to_remove.values())} alert yang terpicu.")

    print("Pemeriksaan alerts selesai.")


def main() -> None:
    """Jalankan bot interaktif."""
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    if not TOKEN:
        print("Error: Pastikan variabel TELEGRAM_TOKEN sudah di-set!")
        return

    application = Application.builder().token(TOKEN).build()
    
    # Menambahkan job queue untuk check_alerts
    # Dijalankan setiap 5 menit (300 detik)
    job_queue = application.job_queue
    job_queue.run_repeating(check_alerts, interval=300, first=10)

    # Daftarkan semua handler
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cek", cek_saham))
    application.add_handler(CommandHandler("tambah", tambah_saham))
    application.add_handler(CommandHandler("portfolio", lihat_portfolio))
    application.add_handler(CommandHandler("alert", set_alert))
    application.add_handler(CommandHandler("hapus_alert", hapus_alert))

    print("Bot interaktif dengan pemindai alert sedang berjalan di Railway...")
    application.run_polling()

if __name__ == "__main__":
    main()
