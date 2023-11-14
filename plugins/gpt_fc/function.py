from urllib.parse import unquote

import requests
from datetime import datetime


def search_bing(subscription_key, query, count=10):
    """
    This function makes a call to the Bing Web Search API with a query and returns relevant web search.
    Documentation: https://docs.microsoft.com/en-us/bing/search-apis/bing-web-search/overview
    """
    # Construct a request
    endpoint = "https://api.bing.microsoft.com/v7.0/search"
    mkt = 'zh-CN'
    params = {'q': query, 'mkt': mkt, 'count': count}
    headers = {'Ocp-Apim-Subscription-Key': subscription_key}

    # Call the API
    try:
        response = requests.get(endpoint, headers=headers, params=params)
        response.raise_for_status()

        # Parse the response
        data = response.json()

        # Extract the required news data
        news_data = data.get('news', {}).get('value', [])
        web_pages = data.get('webPages', {}).get('value', []),

        current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
        query = query.replace('搜索', '')
        refined_news = f"北京时间 {current_time}\n 以下是 '{query}' 的搜索结果：\n\n"
        if news_data:
            for news_item in news_data:
                url = unquote(news_item.get('url', "N/A"))
                refined_news += f"🚀 ** {news_item.get('name', 'N/A')} **\n"
                description = news_item.get('description', 'N/A')
                refined_news += f"{description}\n"
                refined_news += f"查看详情: {url}\n\n"
        elif web_pages:
            for item in web_pages[0]:
                url = unquote(item.get('url', 'N/A'))
                name = item.get('name', 'N/A')
                refined_news += f"🚀 **: {name} **\n\n"
                refined_news += f"查看详情: {url}\n\n"

        return refined_news
    except Exception as ex:
        raise ex


def get_hotlist(api_key, type):
    """获取热榜信息的实现代码，但不返回链接信息"""
    type_mapping = {
        "知乎": "zhihu",
        "微博": "weibo",
        "微信": "weixin",
        "百度": "baidu",
        "头条": "toutiao",
        "163": "163",
        "36氪": "36k",
        "历史上的今天": "hitory",
        "少数派": "sspai",
        "CSDN": "csdn",
        "掘金": "juejin",
        "哔哩哔哩": "bilibili",
        "抖音": "douyin",
        "吾爱破解": "52pojie",
        "V2EX": "v2ex",
        "Hostloc": "hostloc",
    }

    # 如果用户直接提供的是英文名，则直接使用
    if type.lower() in type_mapping.values():
        api_type = type.lower()
    else:
        api_type = type_mapping.get(type, None)
        if api_type is None:
            raise ValueError(f"未知的类型: {type}")

    url = "https://v2.alapi.cn/api/tophub/get"
    payload = {"token": api_key, "type": api_type}
    headers = {'Content-Type': "application/x-www-form-urlencoded"}
    response = requests.request("POST", url, data=payload, headers=headers)
    hotlist_info = response.json()
    if hotlist_info['code'] == 200:  # 验证请求是否成功
        # 遍历每个条目，删除它们的 "link" 属性
        for item in hotlist_info['data']['list']:
            item.pop('link', None)
        return hotlist_info['data']  # 返回 'data' 部分
    else:
        raise ValueError(f"Unable to get hotlist information: {hotlist_info.get('msg', '')}")


def get_current_weather(api_key, city):
    """获取天气的实现代码"""
    url = "https://v2.alapi.cn/api/tianqi"
    payload = {"token": api_key, "city": city}
    headers = {'Content-Type': "application/x-www-form-urlencoded"}
    response = requests.request("POST", url, data=payload, headers=headers)
    weather_info = response.json()
    # print(f"payload ={payload}")
    if weather_info['code'] == 200:  # 验证请求是否成功
        return weather_info['data']  # 直接返回 'data' 部分
    else:
        return {"error": "Unable to get weather information"}
