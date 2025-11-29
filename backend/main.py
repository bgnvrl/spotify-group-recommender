from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import requests
import random
from urllib.parse import quote
from pydantic import BaseModel
from typing import List, Dict, Set
from uuid import uuid4

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")

# GERÇEK SPOTIFY URL'LERİ
SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"

def get_auth_header(token):
    return {"Authorization": f"Bearer {token}"}

@app.get("/")
def root():
    return {"message": "Hybrid Recommender Backend Hazır 🚀"}

@app.get("/login-url")
def login_url():
    scope = "user-read-email user-read-private user-top-read user-library-read playlist-modify-public"
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": scope,
        "show_dialog": "true"
    }
    query_string = "&".join([f"{k}={quote(v, safe='')}" for k, v in params.items()])
    return {"url": f"{SPOTIFY_AUTH_URL}?{query_string}"}

@app.get("/callback")
def callback(code: str):
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }
    resp = requests.post(SPOTIFY_TOKEN_URL, data=payload)
    if not resp.ok:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()

@app.get("/me")
def get_me(access_token: str):
    resp = requests.get(f"{SPOTIFY_API_BASE_URL}/me", headers=get_auth_header(access_token))
    return resp.json()

@app.get("/liked")
def liked_tracks(access_token: str, limit: int = 50, offset: int = 0):
    # 'market=from_token' eklemek bazen hataları çözer
    params = {"limit": limit, "offset": offset, "market": "from_token"}
    resp = requests.get(f"{SPOTIFY_API_BASE_URL}/me/tracks", headers=get_auth_header(access_token), params=params)
    return resp.json()

# --- ODA YÖNETİMİ ---

class JoinRoomRequest(BaseModel):
    room_id: str
    user_id: str
    user_name: str
    track_ids: List[str]

ROOMS: Dict[str, Dict[str, Dict]] = {}

@app.post("/room/create")
def create_room():
    room_id = uuid4().hex[:6].upper()
    ROOMS[room_id] = {}
    return {"room_id": room_id}

@app.post("/room/join")
def join_room(req: JoinRoomRequest):
    room = ROOMS.setdefault(req.room_id, {})
    room[req.user_id] = {
        "user_name": req.user_name,
        "track_ids": set(req.track_ids),
    }
    return analyze_room_status(req.room_id)

@app.get("/room/{room_id}")
def get_room(room_id: str):
    if room_id not in ROOMS:
        raise HTTPException(status_code=404, detail="Oda bulunamadı")
    return analyze_room_status(room_id)

def analyze_room_status(room_id):
    room = ROOMS.get(room_id, {})
    members = []
    track_sets = []
    for uid, info in room.items():
        members.append({
            "user_id": uid,
            "user_name": info["user_name"],
            "track_count": len(info["track_ids"])
        })
        track_sets.append(info["track_ids"])
    common_ids = set.intersection(*track_sets) if track_sets else set()
    return {
        "room_id": room_id,
        "members": members,
        "common_track_ids": list(common_ids),
        "member_count": len(members)
    }

# --- ZIRHLI PLAYLIST MOTORU (Fallback Özellikli) ---
@app.post("/room/{room_id}/generate_hybrid_playlist")
def generate_hybrid_playlist(room_id: str, access_token: str):
    try:
        if room_id not in ROOMS:
            raise HTTPException(status_code=404, detail="Oda bulunamadı.")
        
        room = ROOMS[room_id]
        track_sets = [info["track_ids"] for info in room.values()]
        
        # Tüm şarkıların havuzu
        all_tracks_pool = [t for user_tracks in track_sets for t in user_tracks]

        if not all_tracks_pool:
            raise HTTPException(status_code=400, detail="Odada veri yok.")

        # 1. TOHUM SEÇİMİ
        common_ids = list(set.intersection(*track_sets))
        seed_tracks = []
        if common_ids:
            seed_tracks = random.sample(common_ids, min(len(common_ids), 3))
        else:
            seed_tracks = random.sample(all_tracks_pool, min(len(all_tracks_pool), 3))

        # 2. ANALİZ (Deneme yap, hata verirse geç)
        avg_energy, avg_dance, avg_valence = 0.6, 0.6, 0.5
        use_targets = False

        try:
            features_resp = requests.get(
                f"{SPOTIFY_API_BASE_URL}/audio-features",
                headers=get_auth_header(access_token),
                params={"ids": ",".join(seed_tracks)}
            )
            if features_resp.ok:
                features_data = features_resp.json().get("audio_features", [])
                # Hesaplamalar...
                count = 0
                e, d, v = 0, 0, 0
                for f in features_data:
                    if f:
                        e += f.get("energy", 0)
                        d += f.get("danceability", 0)
                        v += f.get("valence", 0)
                        count += 1
                if count > 0:
                    avg_energy, avg_dance, avg_valence = e/count, d/count, v/count
                    use_targets = True
        except:
            pass # Analiz hatasını yoksay

        # 3. ÖNERİ İSTEĞİ (Asıl Kritik Nokta)
        playlist_tracks = []
        algorithm_used = "Hybrid Recommendation"

        rec_params = {
            "seed_tracks": ",".join(seed_tracks),
            "limit": 20,
            "market": "from_token" # Market hatasını çözebilir
        }
        if use_targets:
            rec_params["target_energy"] = avg_energy
            rec_params["target_danceability"] = avg_dance
            
        print("Spotify API'ye öneri soruluyor...")
        rec_resp = requests.get(
            f"{SPOTIFY_API_BASE_URL}/recommendations",
            headers=get_auth_header(access_token),
            params=rec_params
        )

        # --- FALLBACK SENARYOSU ---
        # Eğer Spotify 400 veya 403 verirse, B PLANINI devreye sokuyoruz
        if not rec_resp.ok:
            print(f"Spotify Öneri Hatası ({rec_resp.status_code}). FALLBACK MODU devrede.")
            algorithm_used = "Smart Shuffle Mix (Fallback)"
            
            # Odadaki şarkılardan rastgele 20 tane seç (Mix yap)
            # Yerel dosya olmayanları seçmeye çalış (Spotify ID'si 22 karakterdir genelde)
            valid_pool = [t for t in all_tracks_pool if len(t) == 22] 
            
            # Eğer valid pool boşsa hepsini kullan
            pool_to_use = valid_pool if valid_pool else all_tracks_pool
            
            fallback_ids = random.sample(pool_to_use, min(len(pool_to_use), 20))
            
            # Bu ID'lerin detaylarını çek (İsim, Resim vs.)
            tracks_resp = requests.get(
                f"{SPOTIFY_API_BASE_URL}/tracks",
                headers=get_auth_header(access_token),
                params={"ids": ",".join(fallback_ids)}
            )
            
            if tracks_resp.ok:
                playlist_tracks = tracks_resp.json().get("tracks", [])
            else:
                # O da olmazsa boş dön
                playlist_tracks = []
        else:
            # Her şey yolundaysa normal öneriyi al
            playlist_tracks = rec_resp.json().get("tracks", [])

        # Sonuç Döndür
        return {
            "algorithm": algorithm_used,
            "group_stats": {
                "energy": round(avg_energy, 2),
                "danceability": round(avg_dance, 2),
                "valence": round(avg_valence, 2)
            },
            "seed_tracks": seed_tracks,
            "playlist": playlist_tracks
        }

    except Exception as e:
        print(f"SUNUCU KRİTİK HATA: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    # --- main.py EN ALTINA BU KISMI EKLE ---

class SavePlaylistRequest(BaseModel):
    user_id: str
    access_token: str
    track_ids: List[str]
    playlist_name: str = "Grup Ortak Mix 🎧"

@app.post("/save_playlist")
def save_playlist_to_account(req: SavePlaylistRequest):
    try:
        headers = get_auth_header(req.access_token)
        
        # 1. ADIM: Boş Playlist Oluştur
        create_url = f"{SPOTIFY_API_BASE_URL}/users/{req.user_id}/playlists"
        playlist_data = {
            "name": req.playlist_name,
            "description": "Python Grup Öneri Sistemi ile oluşturuldu.",
            "public": True
        }
        
        create_resp = requests.post(create_url, headers=headers, json=playlist_data)
        
        if not create_resp.ok:
            raise HTTPException(status_code=400, detail=f"Playlist oluşturulamadı: {create_resp.text}")
            
        playlist_id = create_resp.json()["id"]
        playlist_link = create_resp.json()["external_urls"]["spotify"]
        
        # 2. ADIM: Şarkıları Ekle
        # Spotify URI formatına çevir (spotify:track:ID)
        uris = [f"spotify:track:{tid}" for tid in req.track_ids]
        
        add_url = f"{SPOTIFY_API_BASE_URL}/playlists/{playlist_id}/tracks"
        add_resp = requests.post(add_url, headers=headers, json={"uris": uris})
        
        if not add_resp.ok:
            raise HTTPException(status_code=400, detail="Şarkılar eklenemedi.")
            
        return {"status": "success", "link": playlist_link}

    except Exception as e:
        print(f"SAVE ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))