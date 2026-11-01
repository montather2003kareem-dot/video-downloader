import os
import re
import json
import urllib.request
import urllib.parse
from flask import Flask, render_template, request, jsonify
import yt_dlp

app = Flask(__name__)

def clean_input_url(raw_url):
    """تنظيف الرابط من أي رموز مقلوبة في البداية"""
    m = re.search(r'https?://[^\s"\'<>]+', raw_url)
    return m.group(0) if m else raw_url.strip().lstrip('/')

def try_cobalt_fallback(url):
    """سيرفرات رديفة ليوتيوب وإنستغرام وتويتر عند حظر السيرفر الأساسي"""
    instances = [
        "https://cobalt.canine.tools/",
        "https://cobalt.meowing.de/"
    ]
    payload = json.dumps({"url": url, "videoQuality": "720"}).encode('utf-8')
    for inst in instances:
        try:
            req = urllib.request.Request(
                inst,
                data=payload,
                headers={
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
                },
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode())
                link = data.get('url') or (data.get('picker')[0].get('url') if data.get('picker') else None)
                if link:
                    return {'title': 'فيديو جاهز للتحميل', 'url': link, 'thumbnail': ''}
        except Exception:
            continue
    return None

def try_instagram_embed(url):
    """استخراج مباشر لفيديوهات إنستغرام عبر صفحة التضمين عند الحظر"""
    m = re.search(r'(?:reel|reels|p|tv)/([A-Za-z0-9_-]+)', url)
    if not m:
        return None
    shortcode = m.group(1)
    embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    try:
        req = urllib.request.Request(
            embed_url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            v_match = re.search(r'"video_url"\s*:\s*"([^"]+)"', html)
            if v_match:
                video_url = v_match.group(1).encode('utf-8').decode('unicode_escape').replace(r'\/', '/')
                return {'title': 'فيديو إنستغرام', 'url': video_url, 'thumbnail': ''}
    except Exception:
        pass
    return None

def try_youtube_fallback(url):
    """سيرفرات احتياطية ليوتيوب"""
    m = re.search(r'(?:youtu\.be/|v=|shorts/)([a-zA-Z0-9_-]{11})', url)
    if not m:
        return None
    yt_id = m.group(1)
    piped_servers = [
        "https://pipedapi.kavin.rocks",
        "https://api.piped.privacy.com.de"
    ]
    for srv in piped_servers:
        try:
            req = urllib.request.Request(f"{srv}/streams/{yt_id}", headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                streams = [s for s in data.get('videoStreams', []) if not s.get('videoOnly') and s.get('url')]
                if streams:
                    return {
                        'title': data.get('title', 'فيديو يوتيوب'),
                        'url': streams[0]['url'],
                        'thumbnail': data.get('thumbnailUrl', '')
                    }
        except Exception:
            continue
    return None

def try_tiktok_direct(url):
    """سيرفر تيك توك المباشر"""
    try:
        req = urllib.request.Request(
            f"https://www.tikwm.com/api/?url={urllib.parse.quote(url)}",
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            if data.get('code') == 0 and data.get('data'):
                return {
                    'title': data['data'].get('title', 'فيديو تيك توك'),
                    'url': data['data'].get('play'),
                    'thumbnail': data['data'].get('cover', '')
                }
    except Exception:
        pass
    return None

def try_twitter_direct(url):
    """سيرفر تويتر / إكس المباشر"""
    m = re.search(r'(?:twitter\.com|x\.com)/\w+/status/(\d+)', url)
    if not m:
        return None
    tweet_id = m.group(1)
    try:
        req = urllib.request.Request(
            f"https://api.fxtwitter.com/status/{tweet_id}",
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            videos = data.get('tweet', {}).get('media', {}).get('videos', [])
            if videos:
                return {
                    'title': data['tweet'].get('text', 'فيديو X'),
                    'url': videos[0].get('url'),
                    'thumbnail': videos[0].get('thumbnail_url', '')
                }
    except Exception:
        pass
    return None


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/api/download', methods=['POST'])
def get_video_data():
    data = request.get_json() or {}
    raw_url = data.get('url', '').strip()

    if not raw_url:
        return jsonify({'success': False, 'message': 'يرجى إدخال رابط صالح'}), 400

    url = clean_input_url(raw_url)

    # 1. تيك توك
    if 'tiktok.com' in url:
        tk = try_tiktok_direct(url)
        if tk and tk.get('url'):
            return jsonify({'success': True, 'title': tk['title'], 'download_url': tk['url'], 'thumbnail': tk['thumbnail']})

    # 2. تويتر / X
    if 'twitter.com' in url or 'x.com' in url:
        tw = try_twitter_direct(url)
        if tw and tw.get('url'):
            return jsonify({'success': True, 'title': tw['title'], 'download_url': tw['url'], 'thumbnail': tw['thumbnail']})

    # 3. المحرك الأساسي yt-dlp بدون تغيير Headers الافتراضية ليعمل إنستغرام بشكل طبيعي
    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'mweb']
            }
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_url = None
            if 'formats' in info:
                combos = [f for f in info['formats'] if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('url')]
                if combos:
                    video_url = combos[-1]['url']
            if not video_url:
                video_url = info.get('url')

            if video_url:
                return jsonify({
                    'success': True,
                    'title': info.get('title', 'فيديو'),
                    'download_url': video_url,
                    'thumbnail': info.get('thumbnail', '')
                })
    except Exception as e:
        last_err = str(e)

    # 4. المحركات الاحتياطية في حال حظر إنستغرام أو يوتيوب
    if 'instagram.com' in url:
        ig_emb = try_instagram_embed(url)
        if ig_emb and ig_emb.get('url'):
            return jsonify({'success': True, 'title': ig_emb['title'], 'download_url': ig_emb['url'], 'thumbnail': ''})

    if 'youtu' in url:
        yt_fb = try_youtube_fallback(url)
        if yt_fb and yt_fb.get('url'):
            return jsonify({'success': True, 'title': yt_fb['title'], 'download_url': yt_fb['url'], 'thumbnail': yt_fb['thumbnail']})

    # 5. محرك Cobalt الاحتياطي الشامل
    cb = try_cobalt_fallback(url)
    if cb and cb.get('url'):
        return jsonify({'success': True, 'title': cb['title'], 'download_url': cb['url'], 'thumbnail': ''})

    return jsonify({'success': False, 'message': 'تعذر سحب هذا الفيديو حالياً، تأكد أن الحساب عام وليس خاصاً.'}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
