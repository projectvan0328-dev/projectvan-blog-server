from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime, timedelta
import xml.etree.ElementTree as ET

app = Flask(__name__)
CORS(app)

@app.route('/health', methods=['GET'])
def health():
    """서버 상태 확인"""
    return jsonify({'status': 'ok', 'message': '네이버 블로그 트래커 API 서버가 정상 작동 중입니다.'})


@app.route('/api/visitor-stats/<blog_id>', methods=['GET'])
def get_visitor_stats(blog_id):
    """
    네이버 블로그의 방문자 통계 가져오기
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': f'https://blog.naver.com/{blog_id}'
        }
        
        # 방문자 통계 위젯 URL (네이버 블로그 위젯 API)
        widget_url = f'https://blog.naver.com/widgetblogstats.nhn?blogId={blog_id}'
        
        response = requests.get(widget_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        # HTML 파싱
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 방문자 데이터 추출 시도
        visitor_stats = []
        
        # 방법 1: JavaScript 변수에서 데이터 추출
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                # visitorCntList 같은 변수 찾기
                match = re.search(r'var\s+\w*[Vv]isitor\w*\s*=\s*(\[.*?\]);', script.string, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        visitor_stats = format_visitor_data(data)
                        break
                    except:
                        continue
                
                # 다른 형태의 데이터 구조
                match = re.search(r'visitorData\s*:\s*(\[.*?\])', script.string, re.DOTALL)
                if match:
                    try:
                        data = json.loads(match.group(1))
                        visitor_stats = format_visitor_data(data)
                        break
                    except:
                        continue
        
        # 방법 2: 테이블에서 직접 파싱
        if not visitor_stats:
            visitor_stats = extract_from_table(soup)
        
        if visitor_stats:
            return jsonify({
                'blog_id': blog_id,
                'stats': visitor_stats,
                'success': True
            })
        else:
            return jsonify({
                'blog_id': blog_id,
                'stats': [],
                'success': False,
                'message': '방문자 그래프 위젯이 설정되어 있지 않거나 데이터를 찾을 수 없습니다.'
            })
        
    except Exception as e:
        return jsonify({
            'error': f'방문자 통계를 가져올 수 없습니다: {str(e)}',
            'blog_id': blog_id,
            'stats': [],
            'success': False
        }), 500


def format_visitor_data(data):
    """방문자 데이터 포맷팅"""
    stats = []
    today = datetime.now()
    
    if isinstance(data, list):
        for i, count in enumerate(data[-5:]):  # 최근 5일
            date = (today - timedelta(days=4-i)).strftime('%Y-%m-%d')
            if isinstance(count, dict):
                visitors = count.get('count', 0) or count.get('visitors', 0)
            else:
                visitors = int(count) if count else 0
            
            stats.append({
                'date': date,
                'visitors': visitors
            })
    
    return stats


def extract_from_table(soup):
    """테이블 형태에서 방문자 데이터 추출"""
    stats = []
    today = datetime.now()
    
    try:
        # 방문자 수가 표시된 요소 찾기
        visitor_elements = soup.find_all(text=re.compile(r'\d+'))
        
        # 숫자만 추출
        numbers = []
        for elem in visitor_elements[:10]:  # 최대 10개
            try:
                num = int(re.search(r'\d+', elem).group())
                if num > 0:
                    numbers.append(num)
            except:
                continue
        
        # 최근 5일치 데이터 생성
        if len(numbers) >= 5:
            for i, count in enumerate(numbers[-5:]):
                date = (today - timedelta(days=4-i)).strftime('%Y-%m-%d')
                stats.append({
                    'date': date,
                    'visitors': count
                })
    except:
        pass
    
    return stats


@app.route('/api/recent-posts/<blog_id>', methods=['GET'])
def get_recent_posts(blog_id):
    """네이버 블로그의 최신 게시글 가져오기 (RSS 피드 사용)"""
    try:
        limit = request.args.get('limit', 5, type=int)
        limit = min(limit, 20)
        
        rss_url = f'https://rss.blog.naver.com/{blog_id}.xml'
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(rss_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        
        posts = []
        items = root.findall('.//item')[:limit]
        
        if not items:
            return jsonify({
                'blog_id': blog_id,
                'posts': [],
                'message': 'RSS 피드에서 게시글을 찾을 수 없습니다.',
                'success': False
            }), 404
        
        for item in items:
            try:
                title_elem = item.find('title')
                link_elem = item.find('link')
                date_elem = item.find('pubDate')
                
                if title_elem is not None and link_elem is not None:
                    title = title_elem.text or ''
                    url = link_elem.text or ''
                    
                    if date_elem is not None and date_elem.text:
                        try:
                            date_str = date_elem.text
                            date_parts = date_str.split()
                            if len(date_parts) >= 4:
                                date_formatted = f"{date_parts[1]} {date_parts[2]} {date_parts[3]}"
                            else:
                                date_formatted = date_str[:16]
                        except:
                            date_formatted = date_elem.text[:16]
                    else:
                        date_formatted = 'Unknown'
                    
                    posts.append({
                        'title': title,
                        'url': url,
                        'date': date_formatted
                    })
            except Exception as e:
                continue
        
        return jsonify({
            'blog_id': blog_id,
            'posts': posts,
            'success': True
        })
        
    except Exception as e:
        return jsonify({
            'error': f'게시글을 가져올 수 없습니다: {str(e)}',
            'blog_id': blog_id,
            'success': False
        }), 500


@app.route('/api/check-exposure', methods=['POST'])
def check_exposure():
    """
    게시글이 네이버 VIEW 탭에 노출되는지 확인
    """
    try:
        data = request.get_json()
        blog_id = data.get('blog_id')
        post_title = data.get('post_title')
        post_url = data.get('post_url')
        
        if not all([blog_id, post_title, post_url]):
            return jsonify({'error': '필수 파라미터가 누락되었습니다.'}), 400
        
        # 네이버 검색으로 게시글 확인
        search_query = f"{post_title} {blog_id}"
        search_url = f"https://search.naver.com/search.naver?where=view&query={requests.utils.quote(search_query)}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9'
        }
        
        response = requests.get(search_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 검색 결과에서 해당 게시글 URL 찾기
        post_number = post_url.split('/')[-1]
        exposed = False
        
        # 검색 결과 링크들 확인
        links = soup.find_all('a', href=True)
        for link in links:
            href = link.get('href', '')
            if blog_id in href and post_number in href:
                exposed = True
                break
        
        return jsonify({
            'blog_id': blog_id,
            'post_title': post_title,
            'post_url': post_url,
            'exposed': exposed,
            'checked_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'error': f'검색 확인 중 오류: {str(e)}',
            'exposed': None
        }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
