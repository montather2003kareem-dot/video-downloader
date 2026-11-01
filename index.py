import os
import re
import json
import urllib.request
import urllib.parse
from flask import Flask, render_template, request, jsonify
import yt_dlp

app = Flask(__name__)

def get_youtube_fallback(url):
    """سيرفر احتياطي لتجاوز حظر يوتيوب للروبوتات"""
    m = re.search(r'(?:youtu\.be/|v=|shorts/)([a-zA-Z0-9_-]{11})', url)
    if not m:
        return None
    yt_id = m.group(1)
    piped_servers = [
        "https://api.piped.privacy.com.de",
        "https://pipedapi.kavin.rocks"
    ]
    for srv in piped_servers:
        try:
            req = urllib.request.Request(
                f"{srv}/streams/{yt_id}",
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req, timeout=4) as resp:
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

def get_tiktok_direct(url):
    """سيرفر تيك توك المباشر وفائق السرعة"""
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


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/api/download', methods=['POST'])
def get_video_data():
    data = request.get_json() or {}
    url = data.get('url', '').strip()

    if not url:
        return jsonify({'success': False, 'message': 'يرجى إدخال رابط صالح'}), 400

    # 1. تيك توك
    if 'tiktok.com' in url:
        tk_data = get_tiktok_direct(url)
        if tk_data and tk_data.get('url'):
            return jsonify({
                'success': True,
                'title': tk_data['title'],
                'download_url': tk_data['url'],
                'thumbnail': tk_data.get('thumbnail', '')
            })

    # 2. إعدادات yt-dlp مع تجاوز حظر الروبوت
    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'web_safari']
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1',
            'Accept-Language': 'en-US,en;q=0.9',
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

            return jsonify({
                'success': True,
                'title': info.get('title', 'فيديو'),
                'download_url': video_url,
                'thumbnail': info.get('thumbnail', '')
            })

    except Exception as e:
        if 'youtu' in url:
            fallback = get_youtube_fallback(url)
            if fallback and fallback.get('url'):
                return jsonify({
                    'success': True,
                    'title': fallback['title'],
                    'download_url': fallback['url'],
                    'thumbnail': fallback.get('thumbnail', '')
                })

        return jsonify({'success': False, 'message': f'تعذر سحب الفيديو: {str(e)}'}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
