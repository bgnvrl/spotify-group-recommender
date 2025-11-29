import requests
import streamlit as st
import time

BACKEND_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="Group Hybrid Recommender", page_icon="🎵", layout="centered")

st.title("🎵 Grup Müzik Keşif Sistemi")
st.caption("Collaborative Filtering + Content-Based Filtering Hybrid Engine")

# --- SESSION STATE (Hafıza) ---
if "access_token" not in st.session_state:
    st.session_state.access_token = None
if "current_room" not in st.session_state:
    st.session_state.current_room = None
if "user_info" not in st.session_state:
    st.session_state.user_info = {}
# YENİ EKLENEN HAFIZA: Playlist oluşturulunca burada saklanacak
if "generated_playlist_data" not in st.session_state:
    st.session_state.generated_playlist_data = None

# URL Parametre Kontrolü
params = st.query_params
if params.get("room") and st.session_state.current_room != params.get("room"):
    st.session_state.current_room = params.get("room")

# ================= 1. ODA YÖNETİMİ =================
st.divider()
col1, col2 = st.columns(2)

with col1:
    if st.button("🏠 Yeni Oda Oluştur"):
        try:
            resp = requests.post(f"{BACKEND_URL}/room/create")
            if resp.ok:
                new_id = resp.json()["room_id"]
                st.session_state.current_room = new_id
                st.success(f"Oda: {new_id}")
                st.rerun()
        except: st.error("Backend hatası")

with col2:
    room_input = st.text_input("Oda Kodu:", value=st.session_state.current_room if st.session_state.current_room else "")
    if st.button("Odaya Katıl"):
        if room_input:
            st.session_state.current_room = room_input
            st.rerun()

if st.session_state.current_room:
    st.info(f"📍 Aktif Oda: **{st.session_state.current_room}**")
    st.code(f"http://localhost:8501/?room={st.session_state.current_room}", language="text")

# ================= 2. LOGIN =================
st.divider()

if "code" in params and not st.session_state.access_token:
    try:
        resp = requests.get(f"{BACKEND_URL}/callback", params={"code": params["code"]})
        if resp.ok:
            st.session_state.access_token = resp.json()["access_token"]
            st.query_params.clear()
            if st.session_state.current_room:
                st.query_params["room"] = st.session_state.current_room
            st.rerun()
    except Exception as e: st.error(f"Login hatası: {e}")

if not st.session_state.access_token:
    if st.button("🔐 Spotify ile Giriş Yap"):
        resp = requests.get(f"{BACKEND_URL}/login-url")
        if resp.ok:
            st.link_button("👉 Onay Sayfasına Git", resp.json()["url"])
else:
    st.success("Giriş Başarılı ✅")
    if not st.session_state.user_info:
        me = requests.get(f"{BACKEND_URL}/me", params={"access_token": st.session_state.access_token}).json()
        st.session_state.user_info = me
    st.write(f"Hoşgeldin, **{st.session_state.user_info.get('display_name')}**")

# ================= 3. VERİ TOPLAMA =================
if st.session_state.access_token and st.session_state.current_room:
    st.divider()
    st.subheader("📡 Veri Seti Oluşturma")
    st.write("Grubun müzik zevkini öğrenmem için kütüphaneni havuza ekle.")
    
    if st.button("🚀 Kütüphanemi Tara ve Odaya Gönder (800+ Şarkı)"):
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        all_ids = []
        offset = 0
        limit = 50
        fetching = True
        
        while fetching:
            status_text.text(f"Şarkılar çekiliyor... ({len(all_ids)} adet)")
            try:
                r = requests.get(f"{BACKEND_URL}/liked", params={"access_token": st.session_state.access_token, "limit": limit, "offset": offset})
                data = r.json()
                items = data.get("items", [])
                
                if not items:
                    fetching = False
                else:
                    for item in items:
                        if item.get("track") and item["track"].get("id"):
                            all_ids.append(item["track"]["id"])
                    
                    offset += limit
                    total = data.get("total", 1)
                    progress_bar.progress(min(offset/total, 1.0))
                    
                    if len(items) < limit:
                        fetching = False
            except: fetching = False
            
        # Odaya Gönder
        join_req = {
            "room_id": st.session_state.current_room,
            "user_id": st.session_state.user_info.get("id"),
            "user_name": st.session_state.user_info.get("display_name"),
            "track_ids": all_ids
        }
        requests.post(f"{BACKEND_URL}/room/join", json=join_req)
        status_text.success(f"Tamamlandı! {len(all_ids)} şarkı analiz edildi ve odaya eklendi.")
        time.sleep(1)
        st.rerun()

# ================= 4. ANALİZ VE PLAYLIST (DÜZELTİLEN KISIM) =================
if st.session_state.current_room and st.session_state.access_token:
    st.divider()
    st.subheader("📊 Grup Analizi & Öneri")
    
    if st.button("🔄 Oda Durumunu Yenile"):
        pass 

    try:
        room_resp = requests.get(f"{BACKEND_URL}/room/{st.session_state.current_room}")
        if room_resp.ok:
            room_data = room_resp.json()
            members = room_data.get("members", [])
            common_count = len(room_data.get("common_track_ids", []))
            
            col_k1, col_k2 = st.columns(2)
            col_k1.write("### 👥 Odadakiler")
            for m in members:
                col_k1.write(f"- {m['user_name']} ({m['track_count']} şarkı)")
            col_k2.metric("Ortak Beğenilen Şarkı", common_count)

            st.divider()
            st.write("### 🤖 Hybrid Recommender Engine")
            st.write("Algoritma: `Artist-Based Filtering` (Spotify AI yerine özel algoritma)")
            
            if len(members) < 2:
                st.warning("Playlist oluşturmak için odada en az 2 kişi olmalı.")
            else:
                # --- PLAYLIST OLUŞTURMA BUTONU (Veriyi Çeker ve Hafızaya Atar) ---
                if st.button("✨ Bize Özel Mix Playlist Oluştur!"):
                    with st.spinner("Grubun 'Müzik DNA'sı çıkarılıyor..."):
                        try:
                            mix_resp = requests.post(
                                f"{BACKEND_URL}/room/{st.session_state.current_room}/generate_hybrid_playlist",
                                params={"access_token": st.session_state.access_token}
                            )
                            if mix_resp.ok:
                                # VERİYİ SAKLA
                                st.session_state.generated_playlist_data = mix_resp.json()
                                st.rerun() # Sayfayı yenile ki aşağıdaki blok çalışsın
                            else:
                                st.error(f"Hata: {mix_resp.text}")
                        except Exception as e:
                            st.error(f"Bağlantı hatası: {e}")

            # --- PLAYLIST HAFIZADA VARSA GÖSTER VE KAYDET ---
            if st.session_state.generated_playlist_data:
                data = st.session_state.generated_playlist_data
                stats = data.get("group_stats")
                playlist = data.get("playlist", [])
                
                st.success("Playlist Hazır! 🎧")

                # KAYDETME BUTONU (Artık bağımsız çalışabilir)
                col_save, col_dummy = st.columns([3, 1])
                with col_save:
                    if st.button("💾 Bu Listeyi Spotify Hesabıma Kaydet"):
                        with st.spinner("Kaydediliyor..."):
                            try:
                                track_ids = [t["id"] for t in playlist]
                                save_payload = {
                                    "user_id": st.session_state.user_info.get("id"),
                                    "access_token": st.session_state.access_token,
                                    "track_ids": track_ids,
                                    "playlist_name": f"Grup Mix - {st.session_state.current_room}"
                                }
                                save_resp = requests.post(f"{BACKEND_URL}/save_playlist", json=save_payload)
                                
                                if save_resp.ok:
                                    link = save_resp.json()["link"]
                                    st.balloons()
                                    st.success("Kaydedildi!")
                                    st.link_button("👉 Spotify'da Aç", link)
                                else:
                                    st.error(f"Kaydedilemedi: {save_resp.text}")
                            except Exception as e:
                                st.error(f"Hata: {e}")

                # İstatistikler
                if stats:
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Grup Enerjisi ⚡", stats.get("energy"))
                    c2.metric("Dans Modu 💃", stats.get("danceability"))
                    c3.metric("Mutluluk 😊", stats.get("valence"))
                
                # Şarkı Listesi
                st.write("### 🎼 Önerilen Şarkılar")
                for t in playlist:
                    with st.container():
                        cl1, cl2 = st.columns([1, 5])
                        if t.get("album") and t["album"].get("images"):
                            img = t["album"]["images"][-1]["url"]
                            cl1.image(img, width=50)
                        cl2.markdown(f"**{t['name']}**")
                        if t.get("artists"):
                            cl2.caption(f"{t['artists'][0]['name']}")
                            
    except Exception as e:
        st.error(f"Veri çekme hatası: {e}")