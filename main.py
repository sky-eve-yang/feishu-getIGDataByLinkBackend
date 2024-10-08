import re
import time

import requests
from flask import Flask, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
app.config['CORS_ALLOW_ORIGINS'] = '*'
app.config['CORS_ALLOW_METHODS'] = ['GET', 'POST']

PARAMS = r"(\'X-Ig-App-Id\':.*?),|(\'X-Ig-Www-Claim\':.*?),|(csrftoken\':.*?),"


class Ins:

    def __init__(self, cookies: dict):
        self.MAX_GROUPT_NUM = 4
        self.cookies = cookies
        self.session = requests.Session()
        self.headers = {
            'authority': 'www.instagram.com',
            'accept':
            'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'zh-CN,zh;q=0.9',
            'sec-ch-ua-full-version-list':
            '"Google Chrome";v="113.0.5672.63", "Chromium";v="113.0.5672.63", "Not-A.Brand";v="24.0.0.0"',
            'sec-fetch-site': 'same-origin',
            'upgrade-insecure-requests': '1',
            'user-agent':
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36',
            'viewport-width': '1536',
        }
        self.get_Header_params()
        self.next_id = ""

    def ajax_request(self, url: str, /, params=None):
        """
        do requests, the engine of class
        :param url: api url
        :param params: api params
        :return: json object
        """
        for _ in range(5):
            try:
                resp = self.session.get(url,
                                        headers=self.headers,
                                        params=params,
                                        cookies=self.cookies,
                                        timeout=300)  # 设置超时为10秒
                return resp.json()
            except requests.Timeout:
                print("请求超时，重试中...")
                time.sleep(2)  # 等待2秒进行重试
            except requests.exceptions.RequestException as e:
                print("请求异常:", e)
                time.sleep(15)
        else:
            return None

    def get_Header_params(self):
        """
        every time visit ins will change header params, this is to get the header params
        :return: None
        """
        try:
            # response = self.session.get('https://www.instagram.com/', cookies=self.cookies, headers=self.headers)
            matches = re.findall(PARAMS, str(self.cookies))
            result = [
                match[i] for match in matches for i in range(3) if match[i]
            ]
            print(matches)

            # 解析 app_id, claim, csrf_token
            app_id, claim, csrf_token = (
                match.split(':')[1].strip().strip("'\"")
                for match in result[:3])
            # 更新请求头
            self.headers.update({
                'x-asbd-id': '198387',
                'x-csrftoken': csrf_token,
                'x-ig-app-id': app_id,
                'x-ig-www-claim': claim,
                'x-requested-with': 'XMLHttpRequest',
            })
        except requests.exceptions.RequestException as e:
            raise ConnectionError(
                "Request error, please try again and check your Internet settings."
            ) from e
        except IndexError:
            raise ValueError(
                "An error occurred while parsing Instagram's response data.")

    def get_userInfo(self, userName: str):
        """
        get user info by username
        :param userName: name of user
        :return: dict of user info
        """
        params = {
            'username': userName,
        }
        resp = self.ajax_request(
            'https://www.instagram.com/api/v1/users/web_profile_info/',
            params=params)
        if resp:
            try:
                # to avoid exception? Internet went wrong may return wrong information
                data = resp['data']['user']
            except KeyError:
                raise 'Could not get user information...'
            return {
                'biography':
                data.get('biography'),
                'username':
                data.get('username'),
                'fbid':
                data.get('fbid'),
                'full_name':
                data.get('full_name'),
                'id':
                data.get('id'),
                'followed_by':
                data.get('edge_followed_by', {}).get('count'),
                'follow':
                data.get('edge_follow', {}).get('count'),
                'avatar':
                data.get('profile_pic_url_hd'),
                'noteCount':
                data.get('edge_owner_to_timeline_media', {}).get('count'),
                'is_private':
                data.get('is_private'),
                'is_verified':
                data.get('is_verified')
            } if data else 'unknown User'

    def get_comments(self, id):
        """
        get comments by given post id
        :param id:
        :return: generator of comments
        """
        continuations = [{
            'can_support_threading': 'true',
            'permalink_enabled': 'false',
        }]
        # base url
        url = f'https://www.instagram.com/api/v1/media/{id}/comments/'
        while continuations:
            continuation = continuations.pop()
            resp = self.ajax_request(url, params=continuation)
            if resp.get('next_min_id'):
                continuations.append({
                    'can_support_threading': 'true',
                    'min_id': resp.get('next_min_id')
                })
            comments = resp.get('comments')
            if comments:
                for comment in comments:
                    yield {
                        'id': comment.get('pk'),
                        'user_name': comment.get('user', {}).get('username'),
                        'user_fullname': comment.get('user',
                                                     {}).get('full_name'),
                        'text': comment.get('text'),
                        'created_at': comment.get('created_at'),
                        'comment_like_count':
                        comment.get('comment_like_count'),
                        'reply_count': comment.get('child_comment_count')
                    }
                    if comment.get('child_comment_count') > 0:
                        yield from self.get_child_comment(
                            id, comment.get('pk'))
            else:
                yield 'no comments or losing login cookies'

    def get_child_comment(self, main_id, id):
        """
        get child of the comment by comment_id, only used in function get_comments().
        :param main_id: post id
        :param id: comment_id
        :return: to comments generator
        """
        url = f'https://www.instagram.com/api/v1/media/{main_id}/comments/{id}/child_comments/'
        continuations = [{'max_id': ''}]
        while continuations:
            continuation = continuations.pop()
            resp = self.ajax_request(url, params=continuation)
            cursor = resp.get('next_max_child_cursor')
            if cursor:
                continuations.append({'max_id': cursor})
            comments = resp.get('child_comments')
            if comments:
                for comment in comments:
                    yield {
                        'id': comment.get('pk'),
                        'user_name': comment.get('user', {}).get('username'),
                        'user_fullname': comment.get('user',
                                                     {}).get('full_name'),
                        'text': comment.get('text'),
                        'created_at': comment.get('created_at'),
                        'comment_like_count':
                        comment.get('comment_like_count'),
                    }

    def get_userPosts(self, userName: str, max_id: str = "-1"):
        """
        get all posts from the username
        :param userName:  name
        :return: generator
        """
        continuations = [{
            'count': '12',
        }]
        if max_id != "-1" and max_id != '':
            continuations[0]['max_id'] = max_id  # 如果提供了max_id，则使用它
        temp = userName + '/username/'
        while self.MAX_GROUPT_NUM > 0 and continuations:
            continuation = continuations.pop()
            self.MAX_GROUPT_NUM -= 1
            # url will change when second request and later
            url = f'https://www.instagram.com/api/v1/feed/user/{temp}'
            resp = self.ajax_request(url, params=continuation)
            # no such user
            if not resp.get('user'):
                yield 'checking cookie or unknown/private User: {}'.format(
                    userName)
            else:
                _items = {
                    "posts":
                    resp.get('items'),
                    "max_id":
                    resp.get('next_max_id') if resp.get('next_max_id') else "",
                }
                # simulate the mousedown
                if resp.get('more_available'):
                    next_id = resp.get('next_max_id')
                    continuations.append({'count': '12', 'max_id': next_id})
                    user = resp.get('user')
                    temp = user.get('pk_id') if user.get(
                        'pk_id') else user.get('pk')
                    self.next_id = resp.get('next_max_id')

                yield from self.extract_post(_items)

    @staticmethod
    def extract_post(res):
        """
        to extract a post from a list of posts
        :param posts: original instagram posts
        :return: dict of posts
        """
        max_id = res.get('max_id')
        posts = res.get('posts')
        for post in posts:
            caption = post.get('caption')
            item = {
                'code':
                post.get('code'),
                'id':
                post.get('pk'),
                'pk_id':
                post.get('id'),
                'comment_count':
                post.get('comment_count'),
                'video_view_count':
                post.get('play_count'),
                'photo_view_count':
                post.get('view_count'),
                'like_count':
                post.get('like_count'),
                'text':
                caption.get('text') if caption else "",
                'created_at':
                caption.get('created_at') if caption else post.get('taken_at'),
                'max_id':
                max_id
            }
            # other type can be added by yourself
            types = post.get('media_type')
            item.update({
                'photo': [
                    _.get('image_versions2', {}).get('candidates',
                                                     [{}])[0].get('url')
                    for _ in post.get('carousel_media')
                ]
            }) if types == 8 else None
            item.update({
                'video': post.get('video_versions', [{}])[0].get('url')
            }) if types == 2 else None
            item.update({
                'photo':
                post.get('image_versions2', {}).get('candidates',
                                                    [{}])[0].get('url')
            }) if types == 1 else None
            yield item


@app.route('/')
def index():
    return 'Hello from Flask!'


@app.route('/get_user_total_posts', methods=['POST'])
def get_user_total_posts():
    data = request.get_json()
    cookie_part_string = data.get('cookie')
    app_id = data.get('app_id')
    claim = data.get('claim')
    hashtag = data.get('hashtag')
    user = data.get('user')
    max_id = data.get('max_id')
    print("max_id: ", max_id)

    cookie_string = f'X-Ig-App-Id={app_id}; X-Ig-Www-Claim={claim}; {cookie_part_string}'

    cookies = {}
    try:
        for item in cookie_string.split('; '):
            key, value = item.split('=', 1)
            cookies[key] = value
    except Exception:
        return {"error": "cookie error"}, 400

    INS = Ins(cookies)
    # get user posts, return is a generator

    posts_entry = INS.get_userPosts(user, max_id=max_id)
    print()
    print(22222)

    total_length = 0
    hashtag_length = 0
    res = []
    next_max_id = ""
    filtered_list = []

    filtered_list = list(posts_entry)
    total_length = len(filtered_list)
    hashtag_length = total_length
    next_max_id = INS.next_id

    # for post in posts_entry:
    #     total_length += 1
    #     try:
    #         res.append(post)
    #     except Exception as e:
    #         return {"error": "The cookie is invalid."}, 401

    #     if total_length == 48:
    #         try:
    #             # filtered_list = [p for p in res if hashtag in p.get("text")] # 标签过滤
    #             filtered_list = res
    #             hashtag_length = len(filtered_list)
    #             print(f"hashtag_length: {hashtag_length}")
    #             next_max_id = post.get("max_id", "")
    #         except Exception as e:
    #             print("啊，报错了:", e)
    #             return {"error": str(e)}, 402
    #         break

    return {
        "res": filtered_list,
        "next_max_id": next_max_id,
        "total_length": total_length,
        "hashtag_length": hashtag_length
    }, 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
