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
    return jsonify({
        'status': 'ok', 
        'message': '네이버 블로그 트래커 API 서버가 정상 작동 중입니다.',
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/visitor-stats/<blog_id>', methods=['GET'])
def get_visitor_stats(blog_id):
    """
    네이버 블로그의 방문자 통계 가져오기
    NVisitorgp4Ajax.nhn API 사용 (XML 응답)
    """
    try:
        print(f"[방문자 통계] {blog_id} 조회 시작")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': f'https://blog.naver.com/{blog_id}',
            'X-Requested-With': 'XMLHttpRequest'
        }
        
        # 네이버 방문자 통계 Ajax API
        visitor_url = f'https://blog.naver.com/NVisitorgp4Ajax.nhn?blogId={blog_id}'
        
        response = requests.get(visitor_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        print(f"[방문자 통계] API 응답 코드: {response.status_code}")
        
        # XML 파싱
        try:
            root = ET.fromstring(response.content)
            print(f"[방문자 통계] XML 파싱 성공")
            
            # visitorcnts > visitorcnt 요소들 찾기
            visitor_elements = root.findall('.//visitorcnt')
            print(f"[방문자 통계] visitorcnt 요소 {len(visitor_elements)}개 발견")
            
            if not visitor_elements:
                # visitorcnts가 아니라 visitorcnt가 직접 있을 수도 있음
                visitor_elements = root.findall('.//visitorcnt')
            
            if visitor_elements:
                visitor_stats = []
                today = datetime.now()
                
                # 최근 5개만 사용
                recent_elements = visitor_elements[-5:] if len(visitor_elements) > 5 else visitor_elements
                
                for i, elem in enumerate(recent_elements):
                    cnt = elem.get('cnt')
                    date_id = elem.get('id')
                    
                    if cnt:
                        # 날짜 계산
                        days_ago = len(recent_elements) - 1 - i
                        date = (today - timedelta(days=days_ago)).strftime('%Y-%m-%d')
                        
                        visitor_stats.append({
                            'date': date,
                            'visitors': int(cnt)
                        })
                
                print(f"[방문자 통계] 성공: {len(visitor_stats)}일치 데이터")
                print(f"[방문자 통계] 데이터: {visitor_stats}")
                
                if visitor_stats:
                    return jsonify({
                        'blog_id': blog_id,
                        'stats': visitor_stats,
                        'success': True
                    })
        
        except ET.ParseError as e:
            print(f"[방문자 통계] XML 파싱 실패: {e}")
        
        # 파싱 실패
        print(f"[방문자 통계] 실패: 데이터 없음")
        return jsonify({
            'blog_id': blog_id,
            'stats': [],
            'success': False,
            'message': '방문자 데이터를 찾을 수 없습니다. 방문자 그래프 위젯이 활성화되어 있는지 확인하세요.'
        })
        
    except requests.exceptions.RequestException as e:
        print(f"[방문자 통계] 네트워크 오류: {e}")
        return jsonify({
            'error': f'네트워크 오류: {str(e)}',
            'blog_id': blog_id,
            'stats': [],
            'success': False
        }), 500
    except Exception as e:
        print(f"[방문자 통계] 예외 발생: {e}")
        return jsonify({
            'error': f'방문자 통계를 가져올 수 없습니다: {str(e)}',
            'blog_id': blog_id,
            'stats': [],
            'success': False
        }), 500


def format_visitor_array(numbers):
    """숫자 배열을 방문자 통계 포맷으로 변환"""
    stats = []
    today = datetime.now()
    
    # 최근 5개 데이터 사용 (또는 전체)
    recent_numbers = numbers[-5:] if len(numbers) > 5 else numbers
    
    for i, count in enumerate(recent_numbers):
        # 오늘부터 역순으로 날짜 계산
        days_ago = len(recent_numbers) - 1 - i
        date = (today - timedelta(days=days_ago)).strftime('%Y-%m-%d')
        
        stats.append({
            'date': date,
            'visitors': int(count) if isinstance(count, (int, float)) else 0
        })
    
    return stats


@app.route('/api/recent-posts/<blog_id>', methods=['GET'])
def get_recent_posts(blog_id):
    """네이버 블로그의 최신 게시글 가져오기 (RSS 피드 사용) - 최대 5개"""
    try:
        # 최대 5개로 고정
        limit = 5
        
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
                            # RSS pubDate 형식: "Wed, 23 Oct 2024 14:30:00 +0900"
                            date_str = date_elem.text
                            # RFC 2822 형식 파싱
                            dt = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S %z')
                            # ISO 형식으로 변환
                            date_formatted = dt.isoformat()
                        except:
                            # 파싱 실패시 원본 그대로
                            date_formatted = date_elem.text
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
        
    except requests.exceptions.RequestException as e:
        return jsonify({
            'error': f'네트워크 오류: {str(e)}',
            'blog_id': blog_id,
            'success': False
        }), 500
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
    section.blog.naver.com 검색으로 정확한 제목 매칭
    """
    try:
        data = request.get_json()
        blog_id = data.get('blog_id')
        post_title = data.get('post_title')
        post_url = data.get('post_url')
        
        if not all([blog_id, post_title, post_url]):
            return jsonify({
                'error': '필수 파라미터가 누락되었습니다.',
                'exposed': False,
                'success': False
            }), 400
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9'
        }
        
        exposed = False
        post_title_clean = post_title.strip()
        
        # 네이버 VIEW 탭 검색으로 확인
        search_url = f"https://section.blog.naver.com/Search/Post.naver?pageNo=1&rangeType=ALL&orderBy=sim&keyword={requests.utils.quote(post_title)}"
        
        try:
            print(f"[검색] {post_title[:30]}...")
            response = requests.get(search_url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 검색 결과에서 정확히 일치하는 제목 찾기
            all_elements = soup.find_all(['a', 'div', 'span', 'h3', 'h4', 'strong', 'p'])
            
            for element in all_elements:
                element_text = element.get_text(strip=True)
                
                # 정확히 일치하는 제목 발견
                if element_text == post_title_clean:
                    exposed = True
                    print(f"✓ 노출됨: {post_title[:30]}...")
                    break
        
        except requests.exceptions.Timeout:
            print(f"⏱ 타임아웃: {post_title[:30]}...")
            return jsonify({
                'blog_id': blog_id,
                'post_title': post_title,
                'post_url': post_url,
                'exposed': False,
                'success': True,
                'checked_at': datetime.now().isoformat(),
                'timeout': True
            })
        
        except Exception as e:
            print(f"VIEW 검색 중 오류: {e}")
            return jsonify({
                'blog_id': blog_id,
                'post_title': post_title,
                'post_url': post_url,
                'exposed': False,
                'success': True,
                'checked_at': datetime.now().isoformat(),
                'error_detail': str(e)
            })
        
        if not exposed:
            print(f"✗ 누락됨: {post_title[:30]}...")
        
        return jsonify({
            'blog_id': blog_id,
            'post_title': post_title,
            'post_url': post_url,
            'exposed': exposed,
            'success': True,
            'checked_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"검색 확인 중 치명적 오류: {e}")
        return jsonify({
            'error': f'검색 확인 중 오류: {str(e)}',
            'exposed': False,
            'success': False
        }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
