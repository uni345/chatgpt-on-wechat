import requests
import json
import re
import plugins
from bridge.reply import Reply, ReplyType
from bridge.context import ContextType
from plugins import *
from common.log import logger
from urllib.parse import urlparse, quote


def encode_url(url):
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    path = parsed_url.path
    encoded_url = base_url + quote(path)
    # 解析查询字符串参数（如果有的话）
    print(encoded_url)
    return encoded_url


@plugins.register(
    name="sum4all",
    desire_priority=2,
    hidden=False,
    desc="A plugin for summarizing videos and articels",
    version="0.2.0",
    author="fatwang2",
)
class sum4all(Plugin):
    def __init__(self):
        super().__init__()
        try:
            # 使用父类的方法来加载配置
            config = super().load_config()
            if not conf:
                raise Exception("config.json not found")
            # 从配置中提取所需的设置
            self.sum_service = config["sum_service"]
            self.bibigpt_key = config["bibigpt_key"]
            self.outputLanguage = config["outputLanguage"]
            self.group_sharing = config["group_sharing"]
            self.opensum_key = config["opensum_key"]
            self.open_ai_api_key = conf().get("open_ai_api_key")
            self.model = config["model"]
            self.open_ai_api_base = config["open_ai_api_base"]
            self.prompt = config["prompt"]
            self.sum4all_key = config["sum4all_key"]
            self.search_sum = config["search_sum"]
            # 设置事件处理函数
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            # 初始化成功日志
            logger.info("sum4all inited.")

        except Exception as e:
            # 初始化失败日志
            logger.warn(f"sum4all init failed: {e}")

    def on_handle_context(self, e_context: EventContext):
        context = e_context["context"]
        if context.type not in [ContextType.TEXT, ContextType.SHARING]:
            return
        content = context.content
        isgroup = e_context["context"].get("isgroup", False)

        url_match = re.match('https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+', content)
        unsupported_urls = re.search(
            r'.*finder\.video\.qq\.com.*|.*support\.weixin\.qq\.com/update.*|.*support\.weixin\.qq\.com/security.*|.*mp\.weixin\.qq\.com/mp/waerrpage.*',
            content)

        # 检查输入是否以"搜" 开头
        if content.startswith("搜") and self.search_sum:
            # Call new function to handle search operation
            self.handle_search(content, e_context)
            return
        if context.type == ContextType.SHARING:  # 匹配卡片分享
            if unsupported_urls:  # 匹配不支持总结的卡片
                if isgroup:  ##群聊中忽略
                    return
                else:  ##私聊回复不支持
                    logger.info("[sum4all] Unsupported URL : %s", content)
                    reply = Reply(type=ReplyType.TEXT, content="不支持总结小程序和视频号")
                    e_context["reply"] = reply
                    e_context.action = EventAction.BREAK_PASS
            else:  # 匹配支持总结的卡片
                if isgroup:  # 处理群聊总结
                    if self.group_sharing:  # group_sharing = True进行总结，False则忽略。
                        logger.info("[sum4all] Summary URL : %s", content)
                        self.call_service(content, e_context)
                        return
                    else:
                        return
                else:  # 处理私聊总结
                    logger.info("[sum4all] Summary URL : %s", content)
                    self.call_service(content, e_context)
                    return
        elif url_match:  # 匹配URL链接
            if unsupported_urls:  # 匹配不支持总结的网址
                return
            else:
                logger.info("[sum4all] Summary URL : %s", content)
                self.call_service(self.short_url(encode_url(content)), e_context)
                return

    def call_service(self, content, e_context):
        # 根据配置的服务进行不同的处理
        if self.sum_service == "bibigpt":
            self.handle_bibigpt(content, e_context)
        elif self.sum_service == "openai":
            self.handle_openai(content, e_context)
        elif self.sum_service == "opensum":
            self.handle_opensum(content, e_context)
        elif self.sum_service == "sum4all":
            self.handle_sum4all(content, e_context)

    def short_url(self, long_url):
        url = "https://s.fatwang2.com"
        payload = {
            "url": long_url
        }
        headers = {'Content-Type': "application/json"}
        response = requests.request("POST", url, json=payload, headers=headers)
        if response.status_code == 200:
            res_data = response.json()
            if res_data.get('status') == 200:
                short_key = res_data.get('key', None)  # 获取 'key' 字段的值

                if short_key:
                    # 拼接成完整的短链接
                    return f"https://s.fatwang2.com{short_key}"
        return None

    def handle_openai(self, content, e_context):
        meta = None
        headers = {
            'Content-Type': 'application/json',
            'WebPilot-Friend-UID': 'fatwang2'
        }
        payload = json.dumps({"link": content})
        try:
            api_url = "https://gpts.webpilot.ai/api/visit-web"
            response = requests.request("POST", api_url, headers=headers, data=payload)
            response.raise_for_status()
            data = json.loads(response.text)
            meta = data.get('content', 'content not available')  # 获取data字段

        except requests.exceptions.RequestException as e:
            logger.info(e)
            reply = Reply()
            reply.type = ReplyType.TEXT
            reply.content = "哎呀,读取数据失败,请检查URL是否正确或者换一个URL试试"
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            return
            # 如果meta获取成功，发送请求到OpenAI
        if meta:
            try:
                headers = {
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {self.open_ai_api_key}'  # 使用你的OpenAI API密钥
                }
                data = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": self.prompt},
                        {"role": "user", "content": meta}
                    ]
                }
                proxy = conf().get("proxy")
                proxies = {
                    'http': proxy,
                    'https': proxy,
                } if proxy else {}
                response = requests.post(f"{self.open_ai_api_base}/chat/completions", headers=headers,
                                         data=json.dumps(data), proxies=proxies)
                response.raise_for_status()

                # 处理响应数据
                response_data = response.json()
                # 这里可以根据你的需要处理响应数据
                # 解析 JSON 并获取 content
                if "choices" in response_data and len(response_data["choices"]) > 0:
                    first_choice = response_data["choices"][0]
                    if "message" in first_choice and "content" in first_choice["message"]:
                        content = first_choice["message"]["content"]
                    else:
                        print("Content not found in the response")
                else:
                    print("No choices available in the response")
            except requests.exceptions.RequestException as e:
                # 处理可能出现的错误
                logger.error(f"Error calling OpenAI API: {e}")
            reply = Reply()
            reply.type = ReplyType.TEXT
            reply.content = f"{content}"
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

    def handle_sum4all(self, content, e_context):
        meta = None
        headers = {
            'Content-Type': 'application/json',
            'WebPilot-Friend-UID': 'fatwang2'
        }
        payload = json.dumps({"link": content})
        try:
            api_url = "https://gpts.webpilot.ai/api/visit-web"
            response = requests.request("POST", api_url, headers=headers, data=payload)
            response.raise_for_status()
            data = json.loads(response.text)
            meta = data.get('content', 'content not available')  # 获取data字段

        except requests.exceptions.RequestException as e:
            meta = f"An error occurred: {e}"

        if meta:
            try:
                headers = {
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {self.sum4all_key}'  # 使用你的sum4all key
                }
                data = {
                    "model": "sum4all",
                    "messages": [
                        {"role": "system", "content": self.prompt},
                        {"role": "user", "content": meta}
                    ]
                }
                api_url_2 = "https://hy2.fatwang2.com/v1/chat/completions"
                response = requests.post(api_url_2, headers=headers, data=json.dumps(data))
                response.raise_for_status()

                # 处理响应数据
                response_data = response.json()
                # 这里可以根据你的需要处理响应数据
                # 解析 JSON 并获取 content
                if "choices" in response_data and len(response_data["choices"]) > 0:
                    first_choice = response_data["choices"][0]
                    if "message" in first_choice and "content" in first_choice["message"]:
                        content = first_choice["message"]["content"]
                        content = content.replace("\\n", "\n")
                    else:
                        print("Content not found in the response")
                else:
                    print("No choices available in the response")
            except requests.exceptions.RequestException as e:
                # 处理可能出现的错误
                logger.error(f"Error calling sum4all api: {e}")
            reply = Reply()
            reply.type = ReplyType.TEXT
            reply.content = f"{content}"
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

    def handle_bibigpt(self, content, e_context):
        headers = {
            'Content-Type': 'application/json'
        }
        payload_params = {
            "url": content,
            "includeDetail": False,
            "promptConfig": {
                "outputLanguage": self.outputLanguage
            }
        }

        payload = json.dumps(payload_params)
        try:
            api_url = f"https://bibigpt.co/api/open/{self.bibigpt_key}"
            response = requests.request("POST", api_url, headers=headers, data=payload)
            response.raise_for_status()
            data = json.loads(response.text)
            summary_original = data.get('summary', 'Summary not available')
            html_url = data.get('htmlUrl', 'HTML URL not available')
            # 获取短链接
            short_url = self.short_url(html_url)

            # 如果获取短链接失败，使用 html_url
            if short_url is None:
                short_url = html_url if html_url != 'HTML URL not available' else 'URL not available'

            # 移除 "##摘要"、"## 亮点" 和 "-"
            summary = summary_original.split("详细版（支持对话追问）")[0].replace("## 摘要\n", "📌总结：").replace(
                "## 亮点\n", "").replace("- ", "")
        except requests.exceptions.RequestException as e:
            summary = f"An error occurred: {e}"

        reply = Reply()
        reply.type = ReplyType.TEXT
        reply.content = f"{summary}详细链接：{short_url}"

        e_context["reply"] = reply
        e_context.action = EventAction.BREAK_PASS

    def handle_opensum(self, content, e_context):
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.opensum_key}'
        }
        payload = json.dumps({"link": content})
        try:
            api_url = "https://read.thinkwx.com/api/v1/article/summary"
            response = requests.request("POST", api_url, headers=headers, data=payload)
            response.raise_for_status()
            data = json.loads(response.text)
            summary_data = data.get('data', {})  # 获取data字段                
            summary_original = summary_data.get('summary', 'Summary not available')
            # 使用正则表达式提取URL
            url_pattern = r'https:\/\/[^\s]*'
            match = re.search(url_pattern, summary_original)
            html_url = match.group(0) if match else 'HTML URL not available'
            # 获取短链接
            short_url = self.short_url(html_url) if match else html_url
            summary = re.sub(url_pattern, '', summary_original).strip()

        except requests.exceptions.RequestException as e:
            summary = f"An error occurred: {e}"
            short_url = 'URL not available'

        reply = Reply()
        reply.type = ReplyType.TEXT
        reply.content = f"{summary}详细链接：{short_url}"

        e_context["reply"] = reply
        e_context.action = EventAction.BREAK_PASS

    def handle_search(self, content, e_context):
        meta = None
        headers = {
            'Content-Type': 'application/json',
            'WebPilot-Friend-UID': 'fatwang2'
        }
        payload = json.dumps({"ur": content})
        try:
            api_url = "https://gpts.webpilot.ai/api/visit-web"
            response = requests.request("POST", api_url, headers=headers, data=payload)
            response.raise_for_status()
            data = json.loads(response.text)
            meta = data.get('content', 'content not available')  # 获取data字段

        except requests.exceptions.RequestException as e:
            meta = f"An error occurred: {e}"

        if meta:
            try:
                headers = {
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {self.sum4all_key}'  # 使用你的sum4all key
                }
                data = {
                    "model": "sum4all",
                    "messages": [
                        {"role": "system", "content": self.prompt},
                        {"role": "user", "content": meta}
                    ]
                }
                api_url_2 = "https://hy2.fatwang2.com/v1/chat/completions"
                response = requests.post(api_url_2, headers=headers, data=json.dumps(data))
                response.raise_for_status()

                # 处理响应数据
                response_data = response.json()
                # 这里可以根据你的需要处理响应数据
                # 解析 JSON 并获取 content
                if "choices" in response_data and len(response_data["choices"]) > 0:
                    first_choice = response_data["choices"][0]
                    if "message" in first_choice and "content" in first_choice["message"]:
                        content = first_choice["message"]["content"]
                        content = content.replace("\\n", "\n")
                    else:
                        print("Content not found in the response")
                else:
                    print("No choices available in the response")
            except requests.exceptions.RequestException as e:
                # 处理可能出现的错误
                logger.error(f"Error calling sum4all api: {e}")
            reply = Reply()
            reply.type = ReplyType.TEXT
            reply.content = f"{content}"
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS

    def get_help_text(self, **kwargs):
        help_text = "输入url，直接为你总结，包括视频、文章等\n"
        return help_text
