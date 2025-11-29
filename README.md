1️⃣ Gereksinimler

Python 3.10+

Spotify Developer hesabı (ücretsiz)
3️⃣ Python Sanal Ortam (VENV)

Terminal aç ve proje klasörüne gir:

cd spotify-recommender
python -m venv venv


Aktif et:

venv\Scripts\activate


Her yeni terminal açtığında yeniden activate etmen gerekiyor.
4️⃣ Gerekli Paketleri Yükle

Eğer requirements.txt varsa:

pip install -r requirements.txt


Yoksa:

pip install fastapi "uvicorn[standard]" streamlit python-dotenv requests
5️⃣ Spotify Developer Ayarları

https://developer.spotify.com/dashboard
 → giriş yap

Create App

Redirect URI ekle:

http://127.0.0.1:8000/callback


Client ID ve Client Secret kopyala

6️⃣ .env Dosyası Oluştur

Proje köküne .env adlı dosya aç ve içine:

SPOTIFY_CLIENT_ID=BURAYI_DOLDUR
SPOTIFY_CLIENT_SECRET=BURAYI_DOLDUR
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8000/callback
7️⃣ Backend’i Başlat (FastAPI)

Yeni terminal aç:

cd spotify-recommender
venv\Scripts\activate
cd backend
uvicorn main:app --reload --port 8000
