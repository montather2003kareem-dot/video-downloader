import os
from flask import Flask, render_template, request, jsonify
import yt_dlp

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/download', methods=['POST'])
def get_video_data():
    data = request.get_json() or {}
    url = data.get('url', '').strip()

    if not url:
        return jsonify({'success': False, 'message': 'يرجى إدخال رابط صالح'}), 400

    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            video_url = info.get('url')
            if not video_url and 'formats' in info:
                formats = [f for f in info['formats'] if f.get('vcodec') != 'none' and f.get('acodec') != 'none']
                if formats:
                    video_url = formats[-1].get('url')
                else:
                    video_url = info['formats'][-1].get('url')

            return jsonify({
                'success': True,
                'title': info.get('title', 'فيديو'),
                'download_url': video_url,
                'thumbnail': info.get('thumbnail', '')
            })

    except Exception as e:
        return jsonify({'success': False, 'message': f'تعذر سحب الفيديو: {str(e)}'}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
